"""Alignment logic - deterministic greedy nearest-onset by pitch."""

from __future__ import annotations

from typing import Literal

from .models import (
    AlignedPair,
    AlignmentSummary,
    MidiEvent,
    MidiMetadata,
    ScoreEvent,
    ScoreMetadata,
    TempoEvent,
)

# Contract: beat alignment tolerance is constant 0.125 beats
BEAT_ALIGNMENT_TOLERANCE = 0.125

_last_time_signature: tuple[int, int] | None = None
_last_total_measures: int | None = None
_last_tempo_bpm_used: float | None = None
_last_smallest_duration: float | None = None


def align_from_metadata(
    score_events: list[ScoreEvent],
    midi_events: list[MidiEvent],
    score_metadata: ScoreMetadata,
    midi_metadata: MidiMetadata,
    tempo_override: float | None = None,
) -> tuple[list[AlignedPair], AlignmentSummary, float]:
    """
    Align MIDI events to score events using beat-grid quantization.

    Uses DETERMINISTIC PAIRING ALGORITHM per contract:
        1. Convert all MIDI event start times to ABSOLUTE beat positions
        2. Group score events by pitch_midi (use merged logical events for ties)
        3. Group MIDI events by pitch
        4. For each pitch:
           a. Sort score events by absolute beat
           b. Sort MIDI events by absolute beat
           c. Use GREEDY NEAREST-ONSET matching with constant 0.125 beat tolerance
           d. Ties broken by: earlier onset wins
        5. Unmatched score events → AlignedPair(score_event=X, midi_event=None)
        6. Unmatched MIDI events → AlignedPair(score_event=None, midi_event=X)
        7. Record beat_error for each matched pair
        8. Compute estimated_beat_error_mean and max for AlignmentSummary

    Returns:
        Tuple of (aligned_pairs, alignment_summary, tempo_bpm_used)
    """
    # Determine tempo source and value
    tempo_bpm: float
    tempo_source: Literal["musicxml", "midi_tempo_map", "override", "default_120"]

    if tempo_override is not None:
        tempo_bpm = tempo_override
        tempo_source = "override"
    elif midi_metadata.has_tempo_map and midi_metadata.tempo_events:
        tempo_bpm = midi_metadata.initial_tempo_bpm or score_metadata.tempo_bpm or 120.0
        tempo_source = "midi_tempo_map"
    elif score_metadata.tempo_bpm > 0:
        tempo_bpm = score_metadata.tempo_bpm
        tempo_source = "musicxml"
    else:
        tempo_bpm = 120.0
        tempo_source = "default_120"

    # Beat alignment tolerance is CONSTANT per contract
    beat_tolerance = BEAT_ALIGNMENT_TOLERANCE

    # Beats per measure for absolute beat calculation
    beats_per_measure = score_metadata.time_signature[0]

    def _sec_to_beat_with_map(time_sec: float, tempo_events: list[TempoEvent]) -> float:
        """Convert seconds to beats by integrating over tempo segments."""
        if not tempo_events:
            beats_per_sec = tempo_bpm / 60.0
            return time_sec * beats_per_sec

        events = sorted(tempo_events, key=lambda e: e.time_sec)
        total_beats = 0.0
        prev_time = 0.0
        prev_tempo = tempo_bpm

        for event in events:
            if time_sec <= event.time_sec:
                break
            segment = event.time_sec - prev_time
            total_beats += segment * (prev_tempo / 60.0)
            prev_time = event.time_sec
            prev_tempo = event.tempo_bpm

        if time_sec > prev_time:
            total_beats += (time_sec - prev_time) * (prev_tempo / 60.0)

        return total_beats

    use_tempo_map = tempo_source == "midi_tempo_map"

    def midi_time_to_absolute_beat(time_sec: float) -> float:
        """Convert MIDI time in seconds to ABSOLUTE beat position (0-indexed)."""
        if use_tempo_map and midi_metadata.tempo_events:
            absolute_beat = _sec_to_beat_with_map(time_sec, midi_metadata.tempo_events)
        else:
            beats_per_sec = tempo_bpm / 60.0
            absolute_beat = time_sec * beats_per_sec

        if score_metadata.has_pickup and score_metadata.pickup_beats > 0:
            pickup_offset = beats_per_measure - score_metadata.pickup_beats
            absolute_beat -= pickup_offset

        return absolute_beat

    def score_to_absolute_beat(event: ScoreEvent) -> float:
        """Convert score event to ABSOLUTE beat position (0-indexed).

        For measure M (1-indexed) and beat B (1-indexed within measure):
        absolute_beat = (M-1) * beats_per_measure + (B-1)

        Example: m.1 beat 1.0 → 0.0, m.1 beat 2.0 → 1.0, m.2 beat 1.0 → 4.0 (if 4/4)
        """
        # Handle pickup (measure 0)
        if event.measure == 0:
            # Pickup beats are at negative absolute positions
            return (event.beat - 1.0) - (beats_per_measure - score_metadata.pickup_beats)
        # Normal measures: (measure-1) * beats_per_measure + (beat-1)
        return (event.measure - 1) * beats_per_measure + (event.beat - 1.0)

    # CRITICAL FIX: Use merged logical events for ties, skip individual tied notes
    # This ensures tied notes are compared using logical_duration
    score_by_pitch: dict[int, list[ScoreEvent]] = {}
    for score_ev in score_events:
        # Skip individual notes that are part of a tie chain (use merged instead)
        if score_ev.tie_start and not score_ev.is_logical_merged:
            continue  # Will use the merged event instead
        if score_ev.tie_end and not score_ev.is_logical_merged:
            continue  # Part of tie, skip individual

        pitch = score_ev.pitch_midi
        if pitch not in score_by_pitch:
            score_by_pitch[pitch] = []
        score_by_pitch[pitch].append(score_ev)

    midi_by_pitch: dict[int, list[tuple[MidiEvent, float]]] = {}  # (event, abs_beat)
    for midi_ev in midi_events:
        abs_beat = midi_time_to_absolute_beat(midi_ev.start_sec)
        if midi_ev.pitch not in midi_by_pitch:
            midi_by_pitch[midi_ev.pitch] = []
        midi_by_pitch[midi_ev.pitch].append((midi_ev, abs_beat))

    # Sort each group by absolute beat
    for pitch in score_by_pitch:
        score_by_pitch[pitch].sort(key=lambda se: score_to_absolute_beat(se))
    for pitch in midi_by_pitch:
        midi_by_pitch[pitch].sort(key=lambda x: x[1])

    # Greedy nearest-onset matching
    aligned_pairs: list[AlignedPair] = []
    beat_errors: list[float] = []
    used_midi: set[str] = set()  # event_ids
    used_score: set[str] = set()

    all_pitches = set(score_by_pitch.keys()) | set(midi_by_pitch.keys())

    for pitch in all_pitches:
        score_list = score_by_pitch.get(pitch, [])
        midi_list = midi_by_pitch.get(pitch, [])

        # For each score event, find nearest unmatched MIDI event
        for score_event in score_list:
            if score_event.event_id in used_score:
                continue

            score_abs_beat = score_to_absolute_beat(score_event)
            best_match: tuple[MidiEvent, float] | None = None
            best_error = float("inf")

            for midi_event, midi_abs_beat in midi_list:
                if midi_event.event_id in used_midi:
                    continue

                error = abs(midi_abs_beat - score_abs_beat)
                if error < best_error and error <= beat_tolerance:
                    best_error = error
                    best_match = (midi_event, midi_abs_beat)

            if best_match is not None:
                matched_midi, _ = best_match
                confidence = max(0.0, 1.0 - (best_error / beat_tolerance))
                aligned_pairs.append(
                    AlignedPair(
                        score_event=score_event,
                        midi_event=matched_midi,
                        confidence=confidence,
                        beat_error=best_error,
                    )
                )
                beat_errors.append(best_error)
                used_midi.add(matched_midi.event_id)
                used_score.add(score_event.event_id)
            else:
                # Unmatched score event
                aligned_pairs.append(
                    AlignedPair(
                        score_event=score_event,
                        midi_event=None,
                        confidence=0.0,
                        beat_error=0.0,
                    )
                )
                used_score.add(score_event.event_id)

        # Remaining unmatched MIDI events for this pitch
        for midi_event, _ in midi_list:
            if midi_event.event_id not in used_midi:
                aligned_pairs.append(
                    AlignedPair(
                        score_event=None,
                        midi_event=midi_event,
                        confidence=0.0,
                        beat_error=0.0,
                    )
                )
                used_midi.add(midi_event.event_id)

    # Calculate alignment quality metrics
    if beat_errors:
        estimated_beat_error_mean = sum(beat_errors) / len(beat_errors)
        estimated_beat_error_max = max(beat_errors)
    else:
        estimated_beat_error_mean = 0.0
        estimated_beat_error_max = 0.0

    # Determine confidence level
    alignment_confidence: Literal["high", "medium", "low"]
    if tempo_source == "default_120":
        alignment_confidence = "low"
    elif estimated_beat_error_mean > beat_tolerance * 0.5:
        alignment_confidence = "medium"
    else:
        alignment_confidence = "high"

    summary = AlignmentSummary(
        tempo_source=tempo_source,
        time_signature_map_used=False,
        has_pickup=score_metadata.has_pickup,
        pickup_beats=score_metadata.pickup_beats,
        alignment_confidence=alignment_confidence,
        estimated_beat_error_mean=estimated_beat_error_mean,
        estimated_beat_error_max=estimated_beat_error_max,
        midi_has_tempo_map=midi_metadata.has_tempo_map,
        pedal_accounted_for=False,
    )

    # Return tempo_bpm_used so report can use correct value
    global _last_time_signature
    global _last_total_measures
    global _last_tempo_bpm_used
    global _last_smallest_duration

    _last_time_signature = score_metadata.time_signature
    _last_total_measures = score_metadata.total_measures
    _last_tempo_bpm_used = tempo_bpm
    _last_smallest_duration = score_metadata.smallest_notated_duration

    return aligned_pairs, summary, tempo_bpm


def align_events(
    score_events: list[ScoreEvent],
    midi_events: list[MidiEvent],
    tempo_bpm: float,
    time_signature: tuple[int, int],
    midi_tempo_map: list[TempoEvent] | None = None,
    has_pickup: bool = False,
    pickup_beats: float = 0.0,
) -> tuple[list[AlignedPair], AlignmentSummary]:
    """Align events using the contract signature."""
    global _last_time_signature
    global _last_total_measures
    global _last_tempo_bpm_used
    global _last_smallest_duration

    total_measures = max((ev.measure for ev in score_events), default=0)
    smallest_duration = min((ev.duration for ev in score_events), default=0.25)

    score_metadata = ScoreMetadata(
        total_measures=total_measures,
        tempo_bpm=tempo_bpm,
        time_signature=time_signature,
        time_signature_changes=[],
        has_pickup=has_pickup,
        pickup_beats=pickup_beats,
        smallest_notated_duration=smallest_duration,
        title=None,
        part_name=None,
    )

    tempo_events = midi_tempo_map or []
    initial_tempo_bpm = tempo_events[0].tempo_bpm if tempo_events else tempo_bpm
    midi_metadata = MidiMetadata(
        has_tempo_map=bool(tempo_events),
        tempo_events=tempo_events,
        initial_tempo_bpm=initial_tempo_bpm,
    )

    aligned_pairs, summary, tempo_bpm_used = align_from_metadata(
        score_events=score_events,
        midi_events=midi_events,
        score_metadata=score_metadata,
        midi_metadata=midi_metadata,
        tempo_override=None,
    )

    _last_time_signature = time_signature
    _last_total_measures = total_measures
    _last_tempo_bpm_used = tempo_bpm_used
    _last_smallest_duration = smallest_duration

    return aligned_pairs, summary


def get_last_alignment_context() -> tuple[
    tuple[int, int] | None, int | None, float | None, float | None
]:
    """Return (time_signature, total_measures, tempo_bpm_used, smallest_duration)."""
    return (
        _last_time_signature,
        _last_total_measures,
        _last_tempo_bpm_used,
        _last_smallest_duration,
    )
