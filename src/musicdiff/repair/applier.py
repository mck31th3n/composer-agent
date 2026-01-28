"""Apply patch plans to MusicXML files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema
from music21 import converter, note, stream
from music21.base import Music21Object

from .models_repair import PatchPlan


def apply_patch_plan(
    xml_path: str | Path,
    patchplan_path: str | Path,
    patched_out: str | Path | None = None,
) -> Path:
    """Apply a patch plan to a MusicXML file."""
    xml_path = Path(xml_path)
    patchplan_path = Path(patchplan_path)

    if not xml_path.exists():
        raise FileNotFoundError(f"MusicXML file not found: {xml_path}")
    if not patchplan_path.exists():
        raise FileNotFoundError(f"Patch plan not found: {patchplan_path}")

    with open(patchplan_path) as f:
        plan_data = json.load(f)

    _validate_patchplan(plan_data)
    plan = PatchPlan.model_validate(plan_data)

    score = converter.parse(str(xml_path))
    parts = list(score.parts)  # type: ignore[union-attr]
    if not parts:
        raise ValueError("No parts found in MusicXML")
    part = parts[0]

    for op in plan.operations:
        _apply_operation(part, op)

    if patched_out is None:
        patched_out = xml_path.with_name("repaired.musicxml")
    patched_out = Path(patched_out)

    score.write("musicxml", fp=str(patched_out))
    converter.parse(str(patched_out))
    return patched_out


def _apply_operation(part: stream.Part, op: Any) -> None:
    if op.type == "noop":
        return

    measure = part.measure(op.measure)
    if measure is None:
        return

    offset = op.beat - 1.0
    if offset < 0:
        return

    if op.type == "insert_note":
        _apply_insert(measure, offset, op.voice, op.params)
    elif op.type == "delete_note":
        _apply_delete(measure, offset, op.voice, op.params)
    elif op.type == "update_duration":
        _apply_update_duration(measure, offset, op.voice, op.params)
    elif op.type == "update_pitch":
        _apply_update_pitch(measure, offset, op.voice, op.params)


def _apply_insert(
    measure: stream.Measure, offset: float, voice: int, params: Any
) -> None:
    if params.pitch_midi is None or params.duration is None:
        return

    if _note_exists_any_voice(measure, offset, params.pitch_midi, params.duration):
        return

    insert_voice = voice
    if _voice_collision(measure, offset, voice):
        insert_voice = _next_available_voice(measure)

    if not _within_measure(measure, offset, params.duration):
        return

    # Remove any rest at the insertion point to avoid offset shifting on reparse
    container = _select_insert_container(measure, insert_voice)
    _remove_rest_at_offset(measure, offset)

    new_note = note.Note(int(params.pitch_midi))
    new_note.duration.quarterLength = float(params.duration)
    container.insert(offset, new_note)


def _apply_delete(
    measure: stream.Measure, offset: float, voice: int, params: Any
) -> None:
    if params.old_pitch_midi is None or params.old_duration is None:
        return

    container = _voice_container(measure, voice)
    target = _find_note(container, offset, int(params.old_pitch_midi))
    if target is None:
        return

    container.remove(target)
    rest = note.Rest()
    rest.duration.quarterLength = float(params.old_duration)
    container.insert(offset, rest)


def _apply_update_duration(
    measure: stream.Measure, offset: float, voice: int, params: Any
) -> None:
    if params.duration is None or params.old_duration is None:
        return

    container = _voice_container(measure, voice)
    target = _find_note_at_offset(container, offset)
    if target is None:
        return

    old_duration = float(params.old_duration)
    new_duration = float(params.duration)
    if abs(float(target.duration.quarterLength) - new_duration) <= 1e-6:
        return

    if new_duration > old_duration:
        if not _within_measure(measure, offset, new_duration):
            return
        if _has_overlap(container, offset, old_duration, new_duration):
            return

    target.duration.quarterLength = new_duration

    if new_duration < old_duration:
        rest = note.Rest()
        rest.duration.quarterLength = old_duration - new_duration
        container.insert(offset + new_duration, rest)


def _apply_update_pitch(
    measure: stream.Measure, offset: float, voice: int, params: Any
) -> None:
    if params.pitch_midi is None or params.old_pitch_midi is None:
        return

    container = _voice_container(measure, voice)
    target = _find_note(container, offset, int(params.old_pitch_midi))
    if target is None:
        return

    if target.pitch.midi == int(params.pitch_midi):
        return

    target.pitch.midi = int(params.pitch_midi)


def _find_note(
    container: stream.Stream, offset: float, pitch_midi: int
) -> note.Note | None:
    for n in container.recurse().notes:
        if not isinstance(n, note.Note):
            continue
        if _note_matches(n, container, offset) and n.pitch.midi == pitch_midi:
            return n
    return None


def _find_note_at_offset(
    container: stream.Stream, offset: float
) -> note.Note | None:
    for n in container.recurse().notes:
        if not isinstance(n, note.Note):
            continue
        if _note_matches(n, container, offset):
            return n
    return None


def _note_matches(n: note.Note, container: stream.Stream, offset: float) -> bool:
    note_offset = _offset_in_container(n, container)
    if abs(note_offset - offset) > 0.01:
        return False
    return True


def _note_exists_any_voice(
    measure: stream.Measure,
    offset: float,
    pitch_midi: int,
    duration: float,
) -> bool:
    offset_eps = 1e-2
    duration_eps = 1e-3
    for n in measure.recurse().notes:
        if not isinstance(n, note.Note):
            continue
        note_offset = _offset_in_container(n, measure)
        if abs(note_offset - offset) > offset_eps:
            continue
        if (
            n.pitch.midi == pitch_midi
            and abs(float(n.duration.quarterLength) - duration) <= duration_eps
        ):
            return True
    return False


def _offset_in_container(n: Music21Object, container: stream.Stream) -> float:
    try:
        return float(n.getOffsetBySite(container))
    except Exception:
        return float(n.offset)


def _voice_collision(measure: stream.Measure, offset: float, voice: int) -> bool:
    container = _voice_container(measure, voice)
    for n in container.notes:
        if not isinstance(n, note.Note):
            continue
        note_offset = _offset_in_container(n, container)
        if abs(note_offset - offset) > 0.01:
            continue
        return True
    return False


def _next_available_voice(measure: stream.Measure) -> int:
    voices = {
        _voice_id_to_int(v.id)
        for v in measure.getElementsByClass(stream.Voice)
        if _voice_id_to_int(v.id) > 0
    }
    voice = 1
    while voice in voices:
        voice += 1
    return voice


def _voice_id_to_int(voice_id: object) -> int:
    try:
        return int(str(voice_id))
    except (TypeError, ValueError):
        return 0


def _voice_container(measure: stream.Measure, voice: int) -> stream.Stream:
    voice_stream = _get_voice_stream(measure, voice)
    return voice_stream if voice_stream is not None else measure


def _get_voice_stream(
    measure: stream.Measure, voice: int
) -> stream.Voice | None:
    for v in measure.getElementsByClass(stream.Voice):
        if str(v.id) == str(voice):
            return v
    return None


def _ensure_voice_stream(measure: stream.Measure, voice: int) -> stream.Stream:
    voice_stream = _get_voice_stream(measure, voice)
    if voice_stream is not None:
        return voice_stream
    new_voice = stream.Voice()
    new_voice.id = str(voice)
    measure.insert(0, new_voice)
    return new_voice


def _select_insert_container(measure: stream.Measure, voice: int) -> stream.Stream:
    voice_stream = _get_voice_stream(measure, voice)
    if voice_stream is not None:
        return voice_stream
    if voice == 1:
        return measure
    return _ensure_voice_stream(measure, voice)


def _remove_rest_at_offset(measure: stream.Measure, offset: float) -> None:
    """Remove rests at the given offset to make room for a note insertion.

    This prevents offset shifting when music21 writes and reparses the file.
    """
    offset_eps = 0.01
    to_remove = []
    for elem in measure.notesAndRests:
        if not isinstance(elem, note.Rest):
            continue
        if abs(_offset_in_container(elem, measure) - offset) <= offset_eps:
            to_remove.append(elem)
    for r in to_remove:
        measure.remove(r)


def _within_measure(measure: stream.Measure, offset: float, duration: float) -> bool:
    bar_length = float(measure.barDuration.quarterLength)
    return offset + duration <= bar_length + 1e-6


def _has_overlap(
    container: stream.Stream,
    offset: float,
    old_duration: float,
    new_duration: float,
) -> bool:
    start = offset + old_duration
    end = offset + new_duration
    for n in container.notesAndRests:
        note_offset = _offset_in_container(n, container)
        if start < note_offset < end + 1e-6:
            return True
    return False


def _validate_patchplan(plan: dict[str, Any]) -> None:
    schema_path = _schema_path()
    with open(schema_path) as f:
        schema = json.load(f)
    jsonschema.validate(instance=plan, schema=schema)


def _schema_path() -> Path:
    repo_root = Path(__file__).resolve().parents[3]
    return repo_root / "contracts" / "patchplan.schema.json"
