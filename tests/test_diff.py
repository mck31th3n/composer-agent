"""Tests for diff generation.

Ensures ALL mismatch types are detected:
- duration_mismatch
- duration_mismatch_tie
- missing_note
- extra_note
- pitch_mismatch
- unsupported_feature
"""

import pytest

from musicdiff.diff import generate_diffs, generate_report
from musicdiff.models import (
    AlignedPair,
    AlignmentSummary,
    MidiEvent,
    ScoreEvent,
    ScoreMetadata,
    UnsupportedFeature,
)


@pytest.fixture(autouse=True)
def _alignment_context(alignment_context_simple: None) -> None:
    """Ensure alignment context is set for diff generation tests."""
    return None


class TestMissingNoteDetection:
    """Tests for missing_note diff type."""

    def test_missing_note_detected(
        self,
        aligned_pair_missing_note: AlignedPair,
    ) -> None:
        """Score event with no MIDI should produce missing_note diff."""
        diffs = generate_diffs(
            [aligned_pair_missing_note],
            [],
        )

        assert len(diffs) == 1
        diff = diffs[0]
        assert diff.type == "missing_note"
        assert diff.severity == "error"
        assert diff.reason == "no_matching_midi_event"
        assert "pitch_midi" in diff.expected
        assert diff.observed == {}

    def test_missing_note_has_location(
        self,
        aligned_pair_missing_note: AlignedPair,
    ) -> None:
        """Missing note diff should include measure and beat."""
        diffs = generate_diffs(
            [aligned_pair_missing_note],
            [],
        )

        diff = diffs[0]
        assert diff.measure == aligned_pair_missing_note.score_event.measure  # type: ignore
        assert diff.beat == aligned_pair_missing_note.score_event.beat  # type: ignore


class TestExtraNoteDetection:
    """Tests for extra_note diff type."""

    def test_extra_note_detected(
        self,
        aligned_pair_extra_note: AlignedPair,
    ) -> None:
        """MIDI event with no score should produce extra_note diff."""
        diffs = generate_diffs(
            [aligned_pair_extra_note],
            [],
        )

        assert len(diffs) == 1
        diff = diffs[0]
        assert diff.type == "extra_note"
        assert diff.severity == "warn"
        assert diff.reason == "no_matching_score_event"
        assert diff.expected == {}
        assert "pitch" in diff.observed

    def test_extra_note_measure_clamped(self) -> None:
        """Extra note measure should be clamped to valid range."""
        # MIDI event at very late time
        late_midi = MidiEvent(
            event_id="t10.000-p60-c0-i0",
            start_sec=10.0,  # Way past 4 measures at 120 BPM
            end_sec=10.5,
            pitch=60,
            velocity=80,
            channel=0,
        )
        pair = AlignedPair(
            score_event=None,
            midi_event=late_midi,
            confidence=0.0,
            beat_error=0.0,
        )

        diffs = generate_diffs([pair], [])

        diff = diffs[0]
        # Measure should be reasonable (based on available context or default)
        assert diff.measure >= 0


class TestDurationMismatchDetection:
    """Tests for duration_mismatch diff type."""

    def test_duration_mismatch_detected(self) -> None:
        """Significant duration difference should produce duration_mismatch."""
        score_event = ScoreEvent(
            event_id="m1-b1.00-p60-v1-i0",
            measure=1,
            beat=1.0,
            pitch_midi=60,
            pitch_spelled="C4",
            duration=1.0,
            logical_duration=1.0,
        )
        # MIDI with significantly shorter duration (0.25 beats at 120 BPM = 0.125s)
        midi_event = MidiEvent(
            event_id="t0.000-p60-c0-i0",
            start_sec=0.0,
            end_sec=0.125,  # 0.25 beats at 120 BPM
            pitch=60,
            velocity=80,
            channel=0,
        )
        pair = AlignedPair(
            score_event=score_event,
            midi_event=midi_event,
            confidence=0.9,
            beat_error=0.0,
        )

        diffs = generate_diffs([pair], [])

        assert len(diffs) == 1
        diff = diffs[0]
        assert diff.type == "duration_mismatch"
        assert diff.reason == "duration_differs"
        assert "duration" in diff.expected
        assert "duration_beats" in diff.observed

    def test_duration_within_tolerance_no_diff(self) -> None:
        """Duration within tolerance should not produce diff."""
        score_event = ScoreEvent(
            event_id="m1-b1.00-p60-v1-i0",
            measure=1,
            beat=1.0,
            pitch_midi=60,
            pitch_spelled="C4",
            duration=1.0,
            logical_duration=1.0,
        )
        # MIDI with nearly matching duration (0.95 beats at 120 BPM = 0.475s)
        midi_event = MidiEvent(
            event_id="t0.000-p60-c0-i0",
            start_sec=0.0,
            end_sec=0.475,  # ~0.95 beats at 120 BPM
            pitch=60,
            velocity=80,
            channel=0,
        )
        pair = AlignedPair(
            score_event=score_event,
            midi_event=midi_event,
            confidence=0.9,
            beat_error=0.0,
        )

        diffs = generate_diffs([pair], [])

        # Tolerance is 0.25, difference is ~0.05, so no diff
        assert len(diffs) == 0


class TestDurationMismatchTieDetection:
    """Tests for duration_mismatch_tie diff type."""

    def test_tie_duration_mismatch_detected(self) -> None:
        """Duration mismatch on tied note should produce duration_mismatch_tie."""
        # Tied score event (merged)
        score_event = ScoreEvent(
            event_id="m1-b3.00-p60-v1-merged",
            measure=1,
            beat=3.0,
            pitch_midi=60,
            pitch_spelled="C4",
            duration=2.0,
            logical_duration=4.0,  # 2 half notes tied
            tie_start=True,
            tie_end=True,
            is_logical_merged=True,
        )
        # MIDI with shorter duration (2 beats instead of 4)
        midi_event = MidiEvent(
            event_id="t1.000-p60-c0-i0",
            start_sec=1.0,
            end_sec=2.0,  # 2 beats at 120 BPM
            pitch=60,
            velocity=80,
            channel=0,
        )
        pair = AlignedPair(
            score_event=score_event,
            midi_event=midi_event,
            confidence=0.9,
            beat_error=0.0,
        )

        diffs = generate_diffs([pair], [])

        assert len(diffs) == 1
        diff = diffs[0]
        assert diff.type == "duration_mismatch_tie"
        assert diff.reason == "tie_merge"
        assert diff.expected.get("has_tie") is True


class TestPitchMismatchDetection:
    """Tests for pitch_mismatch diff type."""

    def test_pitch_mismatch_detected(self) -> None:
        """Different pitches should produce pitch_mismatch."""
        score_event = ScoreEvent(
            event_id="m1-b1.00-p60-v1-i0",
            measure=1,
            beat=1.0,
            pitch_midi=60,  # C4
            pitch_spelled="C4",
            duration=1.0,
            logical_duration=1.0,
        )
        midi_event = MidiEvent(
            event_id="t0.000-p62-c0-i0",
            start_sec=0.0,
            end_sec=0.5,
            pitch=62,  # D4, not C4
            velocity=80,
            channel=0,
        )
        pair = AlignedPair(
            score_event=score_event,
            midi_event=midi_event,
            confidence=0.9,
            beat_error=0.0,
        )

        diffs = generate_diffs([pair], [])

        # Should produce pitch mismatch
        pitch_diffs = [d for d in diffs if d.type == "pitch_mismatch"]
        assert len(pitch_diffs) == 1
        diff = pitch_diffs[0]
        assert diff.severity == "error"
        assert diff.reason == "pitch_differs"
        assert diff.expected.get("pitch_midi") == 60
        assert diff.observed.get("pitch") == 62

    def test_pitch_uses_midi_number_not_spelling(self) -> None:
        """Pitch comparison must use MIDI number, not spelled name."""
        # C#4 vs Db4 are same MIDI pitch (61), different spelling
        score_event = ScoreEvent(
            event_id="m1-b1.00-p61-v1-i0",
            measure=1,
            beat=1.0,
            pitch_midi=61,  # Same MIDI pitch
            pitch_spelled="C#4",  # Different spelling
            duration=1.0,
            logical_duration=1.0,
        )
        midi_event = MidiEvent(
            event_id="t0.000-p61-c0-i0",
            start_sec=0.0,
            end_sec=0.5,
            pitch=61,  # Same MIDI pitch (could be Db4)
            velocity=80,
            channel=0,
        )
        pair = AlignedPair(
            score_event=score_event,
            midi_event=midi_event,
            confidence=0.9,
            beat_error=0.0,
        )

        diffs = generate_diffs([pair], [])

        # No pitch mismatch - MIDI numbers match
        pitch_diffs = [d for d in diffs if d.type == "pitch_mismatch"]
        assert len(pitch_diffs) == 0


class TestUnsupportedFeatureDiffDetection:
    """Tests for unsupported_feature diff type."""

    def test_tuplet_produces_diff(
        self,
        unsupported_tuplet: UnsupportedFeature,
    ) -> None:
        """Tuplet unsupported feature should produce a diff."""
        diffs = generate_diffs([], [unsupported_tuplet])

        assert len(diffs) == 1
        diff = diffs[0]
        assert diff.type == "unsupported_feature"
        assert diff.severity == "info"
        assert diff.reason == "unsupported_tuplet"
        assert diff.measure == 2

    def test_grace_note_produces_diff(
        self,
        unsupported_grace: UnsupportedFeature,
    ) -> None:
        """Grace note unsupported feature should produce a diff."""
        diffs = generate_diffs([], [unsupported_grace])

        assert len(diffs) == 1
        diff = diffs[0]
        assert diff.type == "unsupported_feature"
        assert diff.severity == "info"
        assert diff.reason == "unsupported_grace_note"


class TestGenerateReport:
    """Tests for report generation."""

    def test_report_has_required_fields(self) -> None:
        """DiffReport must have all required fields."""
        metadata = ScoreMetadata(
            total_measures=4,
            tempo_bpm=120.0,
            time_signature=(4, 4),
        )
        summary = AlignmentSummary(
            tempo_source="musicxml",
            time_signature_map_used=False,
            has_pickup=False,
            pickup_beats=0.0,
            alignment_confidence="high",
            estimated_beat_error_mean=0.0,
            estimated_beat_error_max=0.0,
            midi_has_tempo_map=False,
            pedal_accounted_for=False,
        )

        report = generate_report(
            xml_path="test.xml",
            midi_path="test.mid",
            diffs=[],
            metadata=metadata,
            alignment_summary=summary,
            unsupported_features=[],
            warnings=[],
            tempo_bpm_used=120.0,
        )

        assert report.source_xml == "test.xml"
        assert report.source_midi == "test.mid"
        assert report.timestamp  # ISO 8601 format
        assert report.alignment_summary is not None
        assert isinstance(report.diffs, list)
        assert isinstance(report.warnings, list)

    def test_report_alignment_summary_always_present(self) -> None:
        """alignment_summary must be present even with empty diffs."""
        metadata = ScoreMetadata(
            total_measures=4,
            tempo_bpm=120.0,
            time_signature=(4, 4),
        )
        summary = AlignmentSummary(
            tempo_source="default_120",
            time_signature_map_used=False,
            has_pickup=False,
            alignment_confidence="low",
            midi_has_tempo_map=False,
        )

        report = generate_report(
            xml_path="test.xml",
            midi_path="test.mid",
            diffs=[],
            metadata=metadata,
            alignment_summary=summary,
            unsupported_features=[],
            warnings=[],
            tempo_bpm_used=120.0,
        )

        assert report.alignment_summary is not None
        assert report.alignment_summary.tempo_source == "default_120"
        assert report.alignment_summary.alignment_confidence == "low"

    def test_report_timestamp_format(self) -> None:
        """Timestamp must be ISO 8601 format."""
        metadata = ScoreMetadata(
            total_measures=4,
            tempo_bpm=120.0,
            time_signature=(4, 4),
        )
        summary = AlignmentSummary(
            tempo_source="musicxml",
            time_signature_map_used=False,
            has_pickup=False,
            alignment_confidence="high",
            midi_has_tempo_map=False,
        )

        report = generate_report(
            xml_path="test.xml",
            midi_path="test.mid",
            diffs=[],
            metadata=metadata,
            alignment_summary=summary,
            unsupported_features=[],
            warnings=[],
            tempo_bpm_used=120.0,
        )

        # ISO 8601 format should contain 'T' separator
        assert "T" in report.timestamp


class TestDiffSeverity:
    """Tests for diff severity levels."""

    def test_missing_note_is_error(
        self,
        aligned_pair_missing_note: AlignedPair,
    ) -> None:
        """Missing note should have 'error' severity."""
        diffs = generate_diffs([aligned_pair_missing_note], [])
        assert diffs[0].severity == "error"

    def test_extra_note_is_warn(
        self,
        aligned_pair_extra_note: AlignedPair,
    ) -> None:
        """Extra note should have 'warn' severity."""
        diffs = generate_diffs([aligned_pair_extra_note], [])
        assert diffs[0].severity == "warn"

    def test_unsupported_feature_is_info(
        self,
        unsupported_tuplet: UnsupportedFeature,
    ) -> None:
        """Unsupported feature should have 'info' severity."""
        diffs = generate_diffs([], [unsupported_tuplet])
        assert diffs[0].severity == "info"
