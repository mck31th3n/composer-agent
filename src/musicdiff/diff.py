"""Diff generation from aligned pairs."""

from __future__ import annotations

from typing import Literal

from .models import (
    AlignedPair,
    AlignmentSummary,
    Diff,
    DiffReport,
    ScoreMetadata,
    UnsupportedFeature,
)


def get_duration_tolerance_from_value(smallest_duration: float) -> float:
    """Calculate duration tolerance based on score's smallest note value."""
    return min(0.25, smallest_duration / 2)


def get_duration_tolerance(metadata: ScoreMetadata) -> float:
    """Backward-compatible helper for tests."""
    return get_duration_tolerance_from_value(metadata.smallest_notated_duration)


def generate_diffs(
    aligned_pairs: list[AlignedPair],
    unsupported_features: list[UnsupportedFeature],
) -> list[Diff]:
    """
    Generate diff objects from aligned pairs.

    Rules per contract:
        - score_event exists, midi_event is None → missing_note
        - midi_event exists, score_event is None → extra_note
        - both exist, pitch differs → pitch_mismatch
        - both exist, duration differs significantly → duration_mismatch
        - duration differs AND score has tie → duration_mismatch_tie
        - unsupported feature affects alignment → unsupported_feature
    """
    diffs: list[Diff] = []
    from .align import get_last_alignment_context

    time_signature, total_measures, tempo_bpm, smallest_duration = (
        get_last_alignment_context()
    )
    if (
        time_signature is None
        or total_measures is None
        or tempo_bpm is None
        or smallest_duration is None
    ):
        raise ValueError("Missing alignment context: call align_events() first.")

    duration_tolerance = get_duration_tolerance_from_value(smallest_duration)

    for pair in aligned_pairs:
        score_event = pair.score_event
        midi_event = pair.midi_event

        # Missing note: in score but not in MIDI
        if score_event is not None and midi_event is None:
            diffs.append(
                Diff(
                    type="missing_note",
                    measure=score_event.measure,
                    beat=score_event.beat,
                    expected={
                        "pitch_midi": score_event.pitch_midi,
                        "pitch_spelled": score_event.pitch_spelled,
                        "duration": score_event.duration,
                    },
                    observed={},
                    confidence=1.0,
                    severity="error",
                    reason="no_matching_midi_event",
                    suggestion=(
                        f"Note {score_event.pitch_spelled} at m.{score_event.measure} "
                        f"beat {score_event.beat:.1f} not found in MIDI"
                    ),
                )
            )

        # Extra note: in MIDI but not in score
        elif midi_event is not None and score_event is None:
            # Convert MIDI time to measure/beat (approximate)
            beats_per_sec = tempo_bpm / 60.0
            total_beats = midi_event.start_sec * beats_per_sec
            beats_per_measure = time_signature[0]
            measure = int(total_beats // beats_per_measure) + 1
            beat = (total_beats % beats_per_measure) + 1.0

            # Clamp measure to valid range
            measure = max(0, min(measure, total_measures))
            beat = max(1.0, beat)

            diffs.append(
                Diff(
                    type="extra_note",
                    measure=measure,
                    beat=beat,
                    expected={},
                    observed={
                        "pitch": midi_event.pitch,
                        "duration_sec": midi_event.duration_sec,
                        "velocity": midi_event.velocity,
                    },
                    confidence=1.0,
                    severity="warn",
                    reason="no_matching_score_event",
                    suggestion=(
                        f"MIDI pitch {midi_event.pitch} at ~m.{measure} not in score"
                    ),
                )
            )

        # Both exist - check for mismatches
        elif score_event is not None and midi_event is not None:
            # Pitch mismatch (should not happen with our alignment, but check anyway)
            if score_event.pitch_midi != midi_event.pitch:
                diffs.append(
                    Diff(
                        type="pitch_mismatch",
                        measure=score_event.measure,
                        beat=score_event.beat,
                        expected={
                            "pitch_midi": score_event.pitch_midi,
                            "pitch_spelled": score_event.pitch_spelled,
                        },
                        observed={"pitch": midi_event.pitch},
                        confidence=pair.confidence,
                        severity="error",
                        reason="pitch_differs",
                        suggestion=(
                            f"Expected {score_event.pitch_spelled} "
                            f"(MIDI {score_event.pitch_midi}), got {midi_event.pitch}"
                        ),
                    )
                )

            # Duration mismatch
            # Convert MIDI duration to beats
            beats_per_sec = tempo_bpm / 60.0
            midi_duration_beats = midi_event.duration_sec * beats_per_sec

            # Use logical_duration for tied notes
            expected_duration = score_event.logical_duration

            duration_diff = abs(midi_duration_beats - expected_duration)
            if duration_diff > duration_tolerance:
                # Determine if tie-related
                diff_type: Literal["duration_mismatch", "duration_mismatch_tie"]
                reason: str

                if score_event.tie_start or score_event.tie_end:
                    diff_type = "duration_mismatch_tie"
                    reason = "tie_merge"
                else:
                    diff_type = "duration_mismatch"
                    reason = "duration_differs"

                severity: Literal["info", "warn", "error"] = (
                    "warn" if duration_diff < duration_tolerance * 2 else "error"
                )

                diffs.append(
                    Diff(
                        type=diff_type,
                        measure=score_event.measure,
                        beat=score_event.beat,
                        expected={
                            "pitch_midi": score_event.pitch_midi,
                            "pitch_spelled": score_event.pitch_spelled,
                            "duration": expected_duration,
                            "has_tie": score_event.tie_start or score_event.tie_end,
                        },
                        observed={
                            "pitch": midi_event.pitch,
                            "duration_beats": round(midi_duration_beats, 3),
                            "duration_sec": round(midi_event.duration_sec, 3),
                        },
                        confidence=pair.confidence,
                        severity=severity,
                        reason=reason,
                        suggestion=(
                            f"m.{score_event.measure} beat {score_event.beat:.1f}: "
                            f"notated {expected_duration} beats, "
                            f"performed ~{midi_duration_beats:.2f} beats"
                        ),
                    )
                )

    # Add diffs for unsupported features
    for feature in unsupported_features:
        diffs.append(
            Diff(
                type="unsupported_feature",
                measure=feature.measure,
                beat=1.0,
                expected={"feature": feature.feature},
                observed={"description": feature.description},
                confidence=0.5,
                severity="info",
                reason=f"unsupported_{feature.feature}",
                suggestion=f"m.{feature.measure}: {feature.description}",
            )
        )

    return diffs




def generate_report(
    xml_path: str,
    midi_path: str,
    diffs: list[Diff],
    metadata: ScoreMetadata,
    alignment_summary: AlignmentSummary,
    unsupported_features: list[UnsupportedFeature],
    warnings: list[str],
    tempo_bpm_used: float,
) -> DiffReport:
    """
    Assemble final report for JSON output.

    INVARIANT: alignment_summary MUST always be present, even if diffs is empty.

    Args:
        tempo_bpm_used: The ACTUAL tempo used in alignment (may differ from metadata)
    """
    from datetime import datetime, timezone

    return DiffReport(
        source_xml=xml_path,
        source_midi=midi_path,
        timestamp=datetime.now(timezone.utc).isoformat(),
        tempo_bpm=tempo_bpm_used,  # Use actual tempo from alignment, not metadata
        total_measures=metadata.total_measures,
        alignment_summary=alignment_summary,
        unsupported_features=unsupported_features,  # Always emit, even if empty
        diffs=diffs,
        warnings=warnings,  # Always emit, even if empty
    )
