"""Generate patch plans from diff reports."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

import jsonschema

from ..models import DiffReport
from ..parser_xml import parse_musicxml
from .models_repair import DiffRef, PatchOperation, PatchParams, PatchPlan

CONFIDENCE_THRESHOLD = 0.8


def generate_patch_plan(
    diff_path: str | Path,
    xml_path: str | Path,
) -> PatchPlan:
    """Generate a patch plan from diff.json and source MusicXML."""
    diff_path = Path(diff_path)
    xml_path = Path(xml_path)

    if not diff_path.exists():
        raise FileNotFoundError(f"Diff file not found: {diff_path}")
    if not xml_path.exists():
        raise FileNotFoundError(f"MusicXML file not found: {xml_path}")

    with open(diff_path) as f:
        diff_data = json.load(f)

    diff_report = DiffReport.model_validate(diff_data)
    _, metadata = parse_musicxml(xml_path)
    total_measures = metadata.total_measures

    diffs = diff_report.diffs
    tempo_bpm = diff_report.tempo_bpm
    ordered_diffs = sorted(
        enumerate(diffs),
        key=lambda item: (item[1].measure, item[1].beat, item[1].type, item[0]),
    )

    candidates: dict[
        tuple[int, float, int],
        tuple[tuple[int, float, str, int], PatchOperation],
    ] = {}
    for idx, diff in ordered_diffs:
        if diff.measure < 0 or diff.measure > total_measures:
            continue
        if diff.confidence <= CONFIDENCE_THRESHOLD:
            continue
        if diff.type == "unsupported_feature":
            continue

        op = _diff_to_operation(diff, tempo_bpm, idx)
        if op is None:
            continue

        key = (op.measure, op.beat, op.voice)
        priority = _diff_priority(diff, idx)
        current = candidates.get(key)
        if current is None:
            candidates[key] = (priority, op)
            continue
        if priority == current[0]:
            candidates.pop(key, None)
            continue
        if priority > current[0]:
            candidates[key] = (priority, op)

    operations = list(
        sorted(
            (item[1] for item in candidates.values()),
            key=lambda op: (op.measure, op.beat, op.op_id),
        )
    )

    plan = PatchPlan(
        source_file=str(xml_path),
        source_diff_timestamp=diff_report.timestamp,
        operations=operations,
    )

    _validate_patchplan(plan.model_dump(exclude_none=True))
    return plan


def _diff_to_operation(
    diff: Any, tempo_bpm: float, index: int
) -> PatchOperation | None:
    diff_type = diff.type

    if diff_type == "missing_note":
        pitch_midi = diff.expected.get("pitch_midi")
        duration = diff.expected.get("duration")
        if pitch_midi is None or duration is None:
            return None
        params = PatchParams(old_pitch_midi=int(pitch_midi), old_duration=float(duration))
        return _make_operation(diff, "delete_note", params, index)

    if diff_type == "extra_note":
        pitch_midi = diff.observed.get("pitch")
        duration = _duration_from_observed(diff.observed, tempo_bpm)
        if pitch_midi is None or duration is None:
            return None
        params = PatchParams(pitch_midi=int(pitch_midi), duration=float(duration))
        return _make_operation(diff, "insert_note", params, index)

    if diff_type in ("duration_mismatch", "duration_mismatch_tie"):
        old_duration = diff.expected.get("duration")
        new_duration = _duration_from_observed(diff.observed, tempo_bpm)
        if old_duration is None or new_duration is None:
            return None
        params = PatchParams(old_duration=float(old_duration), duration=float(new_duration))
        return _make_operation(diff, "update_duration", params, index)

    if diff_type == "pitch_mismatch":
        old_pitch = diff.expected.get("pitch_midi")
        new_pitch = diff.observed.get("pitch")
        duration = diff.expected.get("duration")
        if old_pitch is None or new_pitch is None or duration is None:
            return None
        params = PatchParams(
            old_pitch_midi=int(old_pitch),
            pitch_midi=int(new_pitch),
            duration=float(duration),
        )
        return _make_operation(diff, "update_pitch", params, index)

    return None


def _make_operation(
    diff: Any,
    op_type: Literal["insert_note", "delete_note", "update_duration", "update_pitch", "noop"],
    params: PatchParams,
    index: int,
) -> PatchOperation:
    op_id = _op_id(diff, index)
    return PatchOperation(
        op_id=op_id,
        diff_ref=DiffRef(type=diff.type, measure=diff.measure, beat=diff.beat),
        type=op_type,
        measure=diff.measure,
        beat=diff.beat,
        voice=1,
        params=params,
    )


def _diff_priority(diff: Any, index: int) -> tuple[int, float, str, int]:
    severity = _severity_rank(diff.severity)
    return (severity, diff.confidence, diff.type, index)


def _severity_rank(severity: str) -> int:
    if severity == "error":
        return 2
    if severity == "warn":
        return 1
    return 0


def _duration_from_observed(observed: dict[str, Any], tempo_bpm: float) -> float | None:
    if "duration_beats" in observed:
        return float(observed["duration_beats"])
    if "duration_sec" in observed and tempo_bpm > 0:
        return float(observed["duration_sec"]) * (tempo_bpm / 60.0)
    return None


def _op_id(diff: Any, index: int) -> str:
    pitch = diff.expected.get("pitch_midi") or diff.observed.get("pitch") or "na"
    raw = f"{diff.type}|{diff.measure}|{diff.beat:.3f}|{pitch}|{index}"
    digest = hashlib.sha1(raw.encode("ascii", "ignore")).hexdigest()[:12]
    return f"op-{digest}"


def _validate_patchplan(plan: dict[str, Any]) -> None:
    schema_path = _schema_path()
    with open(schema_path) as f:
        schema = json.load(f)
    jsonschema.validate(instance=plan, schema=schema)


def _schema_path() -> Path:
    repo_root = Path(__file__).resolve().parents[3]
    return repo_root / "contracts" / "patchplan.schema.json"
