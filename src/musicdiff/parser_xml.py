"""MusicXML parser using music21."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from music21 import converter, expressions, key, note, stream, tempo

from .exceptions import ParseError
from .models import ScoreEvent, ScoreMetadata, UnsupportedFeature

if TYPE_CHECKING:
    from music21.base import Music21Object

_last_unsupported_features: list[UnsupportedFeature] = []
_last_tempo_missing = False
_last_time_sig_missing = False


def _pitch_to_spelled(n: note.Note) -> str:
    """Convert music21 pitch to spelled string like 'C#4'."""
    return n.pitch.nameWithOctave


def _is_cue_note(n: note.Note) -> bool:
    """Best-effort detection of cue-sized notes from style metadata."""
    try:
        style = getattr(n, "style", None)
        if style is None:
            return False
        note_size = getattr(style, "noteSize", None)
        if isinstance(note_size, (int, float)) and note_size < 1.0:
            return True
        size = getattr(style, "size", None)
        if isinstance(size, (int, float)) and size < 1.0:
            return True
    except Exception:
        return False
    return False


def _detect_unsupported_in_measure(
    m: stream.Measure, measure_num: int
) -> list[UnsupportedFeature]:
    """Detect unsupported features in a measure."""
    features: list[UnsupportedFeature] = []

    for elem in m.recurse():
        # Grace notes
        if isinstance(elem, note.Note) and elem.duration.isGrace:
            features.append(
                UnsupportedFeature(
                    feature="grace_note",
                    measure=measure_num,
                    description=f"Grace note {elem.pitch.nameWithOctave} - timing ambiguous",
                )
            )
        # Tuplets (time modification)
        if isinstance(elem, note.GeneralNote):
            if elem.duration.tuplets:
                features.append(
                    UnsupportedFeature(
                        feature="tuplet",
                        measure=measure_num,
                        description="Tuplet detected - rhythm may be misaligned",
                    )
                )
            for expr in getattr(elem, "expressions", []):
                expr_name = expr.__class__.__name__
                if isinstance(expr, expressions.Fermata):
                    features.append(
                        UnsupportedFeature(
                            feature="fermata",
                            measure=measure_num,
                            description="Fermata detected - tempo variance possible",
                        )
                    )
                if "Tremolo" in expr_name:
                    features.append(
                        UnsupportedFeature(
                            feature="tremolo",
                            measure=measure_num,
                            description="Tremolo detected - duration unclear",
                        )
                    )
        # Cue notes
        if isinstance(elem, note.Note) and _is_cue_note(elem):
            features.append(
                UnsupportedFeature(
                    feature="cue_note",
                    measure=measure_num,
                    description="Cue-sized note detected - may be ornamental",
                )
            )

    return features


def _parse_musicxml_with_features(
    path: str | Path,
) -> tuple[list[ScoreEvent], ScoreMetadata, list[UnsupportedFeature]]:
    """
    Parse MusicXML file into score events.

    Args:
        path: Path to .xml or .musicxml file

    Returns:
        Tuple of (events, metadata, unsupported_features)

    Raises:
        FileNotFoundError: If file doesn't exist
        ParseError: If file is not valid MusicXML
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"MusicXML file not found: {path}")

    try:
        score = converter.parse(str(path))
    except Exception as e:
        raise ParseError(f"Failed to parse MusicXML: {e}", "xml") from e

    # Get the first part (MVP: single-part only)
    parts = list(score.parts)  # type: ignore[union-attr]
    if not parts:
        raise ParseError("No parts found in MusicXML", "xml")

    part = parts[0]

    # Extract metadata
    metadata = _extract_metadata(score, part)

    # Extract events and unsupported features in single pass
    events, unsupported = _extract_events(part, metadata)

    global _last_unsupported_features
    _last_unsupported_features = unsupported

    return events, metadata, unsupported


def parse_musicxml(path: str | Path) -> tuple[list[ScoreEvent], ScoreMetadata]:
    """
    Parse MusicXML file into score events.

    Contract: returns (events, metadata). Unsupported features are available via
    get_last_unsupported_features().
    """
    events, metadata, unsupported = _parse_musicxml_with_features(path)

    global _last_unsupported_features
    _last_unsupported_features = unsupported

    return events, metadata


def _safe_measure_num(m: stream.Measure | None, default: int = 0) -> int:
    """Safely extract measure number, handling non-integers."""
    if m is None or m.number is None:
        return default
    try:
        return int(m.number)
    except ValueError:
        # Warn or log here if possible, but for now just return default
        return default


def _extract_metadata(score: Music21Object, part: stream.Part) -> ScoreMetadata:
    """Extract metadata from score."""
    global _last_tempo_missing
    global _last_time_sig_missing

    # Get tempo
    tempo_bpm = 120.0  # default
    tempo_marks = list(score.flatten().getElementsByClass(tempo.MetronomeMark))  # type: ignore[attr-defined]
    _last_tempo_missing = not tempo_marks
    if tempo_marks:
        tempo_bpm = float(tempo_marks[0].number)

    # Get time signature
    time_sigs = list(part.flatten().getElementsByClass("TimeSignature"))
    _last_time_sig_missing = not time_sigs
    time_sig = (4, 4)  # default
    if time_sigs:
        ts = time_sigs[0]
        time_sig = (ts.numerator, ts.denominator)

    # Detect time signature changes
    ts_changes: list[tuple[int, tuple[int, int]]] = []
    for ts in time_sigs[1:]:
        m = ts.getContextByClass(stream.Measure)
        if m is not None:
            measure_num = _safe_measure_num(m, default=1)
            ts_changes.append((measure_num, (ts.numerator, ts.denominator)))

    # Count measures
    measures = list(part.getElementsByClass(stream.Measure))
    total_measures = len(measures)

    # Detect pickup
    has_pickup = False
    pickup_beats = 0.0
    if measures:
        first_measure = measures[0]
        # Pickup detection: measure number 0, or measure has fewer beats than time sig
        if first_measure.number == 0:
            has_pickup = True
            pickup_beats = float(first_measure.duration.quarterLength)
        elif first_measure.paddingLeft > 0:
            has_pickup = True
            pickup_beats = float(
                first_measure.duration.quarterLength - first_measure.paddingLeft
            )

    # Find smallest notated duration
    smallest_duration = 4.0  # start with whole note
    for n in part.flatten().notes:
        if isinstance(n, note.Note) and not n.duration.isGrace:
            dur = float(n.duration.quarterLength)
            if dur > 0 and dur < smallest_duration:
                smallest_duration = dur

    # Get title
    title = None
    if hasattr(score, "metadata") and score.metadata and score.metadata.title:
        title = score.metadata.title

    return ScoreMetadata(
        total_measures=total_measures,
        tempo_bpm=tempo_bpm,
        time_signature=time_sig,
        time_signature_changes=ts_changes,
        has_pickup=has_pickup,
        pickup_beats=pickup_beats,
        smallest_notated_duration=smallest_duration,
        title=title,
        part_name=part.partName,
    )


def _extract_events(
    part: stream.Part, metadata: ScoreMetadata
) -> tuple[list[ScoreEvent], list[UnsupportedFeature]]:
    """Extract note events from part."""
    events: list[ScoreEvent] = []
    unsupported: list[UnsupportedFeature] = []
    event_idx = 0

    # Flag time signature changes as unsupported for MVP
    for measure_num, sig in metadata.time_signature_changes:
        unsupported.append(
            UnsupportedFeature(
                feature="time_sig_change",
                measure=measure_num,
                description=f"Time signature change to {sig[0]}/{sig[1]} detected",
            )
        )

    # Flag key signature changes as unsupported
    key_sigs = list(part.flatten().getElementsByClass(key.KeySignature))
    if len(key_sigs) > 1:
        for ks in key_sigs[1:]:
            m = ks.getContextByClass(stream.Measure)
            measure_num = _safe_measure_num(m, default=0)
            unsupported.append(
                UnsupportedFeature(
                    feature="key_sig_change",
                    measure=measure_num,
                    description=f"Key signature change to {ks.sharps} sharps detected",
                )
            )

    # Track ties for logical duration merging
    tie_chains: dict[int, list[ScoreEvent]] = {}  # pitch -> chain of tied notes

    for measure in part.getElementsByClass(stream.Measure):
        measure_num = _safe_measure_num(measure, default=0)

        # Detect unsupported features
        unsupported.extend(_detect_unsupported_in_measure(measure, measure_num))

        # Detect multi-voice
        voices = list(measure.voices)
        if len(voices) > 1:
            unsupported.append(
                UnsupportedFeature(
                    feature="multi_voice",
                    measure=measure_num,
                    description=f"{len(voices)} voices detected - using voice 1 only",
                )
            )

        # Process notes
        for n in measure.flatten().notes:
            if not isinstance(n, note.Note):
                continue
            if n.duration.isGrace:
                continue  # Skip grace notes (already flagged)

            # Calculate beat position (1-indexed)
            offset_in_measure = float(n.offset)
            beat = offset_in_measure + 1.0

            # Clamp beat to >= 1.0 (handle potential pickup math edge cases)
            if beat < 1.0:
                beat = 1.0

            pitch_midi = n.pitch.midi
            duration = float(n.duration.quarterLength)

            # Determine voice
            voice_num = 1
            if n.activeSite and hasattr(n.activeSite, "id"):
                try:
                    voice_num = int(str(n.activeSite.id))
                except ValueError:
                    voice_num = 1

            # Check for ties
            tie_start = n.tie is not None and n.tie.type in ("start", "continue")
            tie_end = n.tie is not None and n.tie.type in ("stop", "continue")

            event = ScoreEvent(
                event_id=f"m{measure_num}-b{beat:.2f}-p{pitch_midi}-v{voice_num}-i{event_idx}",
                measure=measure_num,
                beat=beat,
                pitch_midi=pitch_midi,
                pitch_spelled=_pitch_to_spelled(n),
                duration=duration,
                logical_duration=duration,  # Will be updated for tie chains
                voice=voice_num,
                staff=1,
                tie_start=tie_start,
                tie_end=tie_end,
                is_logical_merged=False,
            )
            events.append(event)
            event_idx += 1

            # Handle tie chains for logical duration
            if tie_start or tie_end:
                if pitch_midi not in tie_chains:
                    tie_chains[pitch_midi] = []
                tie_chains[pitch_midi].append(event)

                # If this is the end of a tie chain, create merged event
                if tie_end and not tie_start:
                    chain = tie_chains.pop(pitch_midi, [])
                    if len(chain) > 1:
                        total_duration = sum(e.duration for e in chain)
                        merged_event = ScoreEvent(
                            event_id=f"m{chain[0].measure}-b{chain[0].beat:.2f}-p{pitch_midi}-v{chain[0].voice}-merged",
                            measure=chain[0].measure,
                            beat=chain[0].beat,
                            pitch_midi=pitch_midi,
                            pitch_spelled=chain[0].pitch_spelled,
                            duration=chain[0].duration,
                            logical_duration=total_duration,
                            voice=chain[0].voice,
                            staff=1,
                            tie_start=True,
                            tie_end=True,
                            is_logical_merged=True,
                        )
                        events.append(merged_event)

    return events, unsupported


def get_last_unsupported_features() -> list[UnsupportedFeature]:
    """Return unsupported features from the most recent parse."""
    return list(_last_unsupported_features)


def get_last_parse_warnings() -> tuple[bool, bool]:
    """Return (tempo_missing, time_sig_missing) from the most recent parse."""
    return _last_tempo_missing, _last_time_sig_missing


def detect_unsupported_features(path: str | Path) -> list[UnsupportedFeature]:
    """
    Scan MusicXML for unsupported features.

    Args:
        path: Path to MusicXML file

    Returns:
        List of detected unsupported features
    """
    # Use internal helper to access unsupported features
    _, _, unsupported = _parse_musicxml_with_features(path)
    return unsupported
