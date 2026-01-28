"""Tests for alignment logic.

Verifies deterministic alignment (matches, misses, tolerance) per contract.
Uses in-memory synthetic fixtures for precision.
"""

from musicdiff.align import BEAT_ALIGNMENT_TOLERANCE, align_events
from musicdiff.models import (
    MidiEvent,
    ScoreEvent,
    TempoEvent,
)


class TestAlignEventsBasic:
    """Basic alignment tests."""

    def test_align_perfect_match(
        self,
        score_events_simple: list[ScoreEvent],
        midi_events_matching_simple: list[MidiEvent],
    ) -> None:
        """Perfectly matching events should all pair with high confidence."""
        pairs, summary = align_events(
            score_events_simple,
            midi_events_matching_simple,
            tempo_bpm=120.0,
            time_signature=(4, 4),
        )

        # All events should be matched
        matched_pairs = [p for p in pairs if p.score_event and p.midi_event]
        assert len(matched_pairs) == len(score_events_simple)

        # All should have high confidence
        for pair in matched_pairs:
            assert pair.confidence > 0.5

        # No unmatched events
        missing = [p for p in pairs if p.score_event and not p.midi_event]
        extra = [p for p in pairs if p.midi_event and not p.score_event]
        assert len(missing) == 0
        assert len(extra) == 0

    def test_align_missing_midi_events(
        self,
        score_events_simple: list[ScoreEvent],
    ) -> None:
        """Score events with no MIDI should produce unmatched pairs."""
        # Empty MIDI list
        pairs, summary = align_events(
            score_events_simple,
            [],
            tempo_bpm=120.0,
            time_signature=(4, 4),
        )

        # All score events should be unmatched
        missing = [p for p in pairs if p.score_event and not p.midi_event]
        assert len(missing) == len(score_events_simple)

    def test_align_extra_midi_events(
        self,
        midi_events_with_extra: list[MidiEvent],
    ) -> None:
        """MIDI events with no score should produce unmatched pairs."""
        # One score event matching first MIDI
        score_events = [
            ScoreEvent(
                event_id="m1-b1.00-p60-v1-i0",
                measure=1,
                beat=1.0,
                pitch_midi=60,
                pitch_spelled="C4",
                duration=1.0,
                logical_duration=1.0,
            )
        ]

        pairs, summary = align_events(
            score_events,
            midi_events_with_extra,
            tempo_bpm=120.0,
            time_signature=(4, 4),
        )

        # One matched, one extra
        matched = [p for p in pairs if p.score_event and p.midi_event]
        extra = [p for p in pairs if p.midi_event and not p.score_event]

        assert len(matched) == 1
        assert len(extra) == 1
        assert extra[0].midi_event is not None
        assert extra[0].midi_event.pitch == 72  # The extra C5


class TestAlignmentDeterminism:
    """Tests to verify alignment is deterministic."""

    def test_same_input_same_output(
        self,
        score_events_simple: list[ScoreEvent],
        midi_events_matching_simple: list[MidiEvent],
    ) -> None:
        """Same inputs must produce identical outputs."""
        pairs1, summary1 = align_events(
            score_events_simple,
            midi_events_matching_simple,
            tempo_bpm=120.0,
            time_signature=(4, 4),
        )

        pairs2, summary2 = align_events(
            score_events_simple,
            midi_events_matching_simple,
            tempo_bpm=120.0,
            time_signature=(4, 4),
        )

        # Same number of pairs
        assert len(pairs1) == len(pairs2)

        # Same alignment confidence
        assert summary1.alignment_confidence == summary2.alignment_confidence

        # Same pairings
        for p1, p2 in zip(pairs1, pairs2):
            if p1.score_event:
                assert p2.score_event is not None
                assert p1.score_event.event_id == p2.score_event.event_id
            if p1.midi_event:
                assert p2.midi_event is not None
                assert p1.midi_event.event_id == p2.midi_event.event_id


class TestAlignmentTolerance:
    """Tests for beat alignment tolerance."""

    def test_within_tolerance_matches(self) -> None:
        """Events within beat tolerance should match."""
        # Score event at beat 1 (absolute beat 0)
        score_events = [
            ScoreEvent(
                event_id="m1-b1.00-p60-v1-i0",
                measure=1,
                beat=1.0,
                pitch_midi=60,
                pitch_spelled="C4",
                duration=1.0,
                logical_duration=1.0,
            )
        ]

        # MIDI event slightly off (0.05s at 120 BPM = 0.1 beats)
        midi_events = [
            MidiEvent(
                event_id="t0.050-p60-c0-i0",
                start_sec=0.05,  # 0.1 beats at 120 BPM (within 0.125 tolerance)
                end_sec=0.55,
                pitch=60,
                velocity=80,
                channel=0,
            )
        ]

        pairs, summary = align_events(
            score_events,
            midi_events,
            tempo_bpm=120.0,
            time_signature=(4, 4),
        )

        # Should match
        matched = [p for p in pairs if p.score_event and p.midi_event]
        assert len(matched) == 1
        assert matched[0].beat_error <= BEAT_ALIGNMENT_TOLERANCE

    def test_outside_tolerance_no_match(self) -> None:
        """Events outside beat tolerance should not match."""
        # Score event at beat 1 (absolute beat 0)
        score_events = [
            ScoreEvent(
                event_id="m1-b1.00-p60-v1-i0",
                measure=1,
                beat=1.0,
                pitch_midi=60,
                pitch_spelled="C4",
                duration=1.0,
                logical_duration=1.0,
            )
        ]

        # MIDI event far off (0.5s at 120 BPM = 1.0 beat, way outside 0.125 tolerance)
        midi_events = [
            MidiEvent(
                event_id="t0.500-p60-c0-i0",
                start_sec=0.5,  # 1.0 beat off
                end_sec=1.0,
                pitch=60,
                velocity=80,
                channel=0,
            )
        ]

        pairs, summary = align_events(
            score_events,
            midi_events,
            tempo_bpm=120.0,
            time_signature=(4, 4),
        )

        # Should NOT match - both should be unmatched
        matched = [p for p in pairs if p.score_event and p.midi_event]
        assert len(matched) == 0

        missing = [p for p in pairs if p.score_event and not p.midi_event]
        extra = [p for p in pairs if p.midi_event and not p.score_event]
        assert len(missing) == 1
        assert len(extra) == 1


class TestAlignmentSummary:
    """Tests for alignment summary generation."""

    def test_summary_always_present(
        self,
        score_events_simple: list[ScoreEvent],
        midi_events_matching_simple: list[MidiEvent],
    ) -> None:
        """AlignmentSummary must always be present."""
        pairs, summary = align_events(
            score_events_simple,
            midi_events_matching_simple,
            tempo_bpm=120.0,
            time_signature=(4, 4),
        )

        assert summary is not None
        assert summary.tempo_source in ("musicxml", "midi_tempo_map", "override", "default_120")
        assert summary.alignment_confidence in ("high", "medium", "low")

    def test_summary_tempo_source_musicxml(
        self,
        score_events_simple: list[ScoreEvent],
        midi_events_matching_simple: list[MidiEvent],
    ) -> None:
        """When tempo comes from MusicXML (no tempo map), source should be 'musicxml'."""
        pairs, summary = align_events(
            score_events_simple,
            midi_events_matching_simple,
            tempo_bpm=120.0,
            time_signature=(4, 4),
            midi_tempo_map=None,
        )

        assert summary.tempo_source == "musicxml"

    def test_summary_tempo_source_midi_tempo_map(
        self,
        score_events_simple: list[ScoreEvent],
        midi_events_matching_simple: list[MidiEvent],
    ) -> None:
        """When MIDI tempo map is provided, source should be 'midi_tempo_map'."""
        pairs, summary = align_events(
            score_events_simple,
            midi_events_matching_simple,
            tempo_bpm=120.0,
            time_signature=(4, 4),
            midi_tempo_map=[TempoEvent(time_sec=0.0, tempo_bpm=100.0)],
        )

        assert summary.tempo_source == "midi_tempo_map"
        assert summary.midi_has_tempo_map is True

    def test_summary_beat_error_stats(self) -> None:
        """Beat error mean and max should be calculated."""
        score_events = [
            ScoreEvent(
                event_id="m1-b1.00-p60-v1-i0",
                measure=1,
                beat=1.0,
                pitch_midi=60,
                pitch_spelled="C4",
                duration=1.0,
                logical_duration=1.0,
            )
        ]

        # Slight offset (0.025s at 120 BPM = 0.05 beats)
        midi_events = [
            MidiEvent(
                event_id="t0.025-p60-c0-i0",
                start_sec=0.025,
                end_sec=0.525,
                pitch=60,
                velocity=80,
                channel=0,
            )
        ]

        pairs, summary = align_events(
            score_events,
            midi_events,
            tempo_bpm=120.0,
            time_signature=(4, 4),
        )

        # Should have recorded the beat error
        assert summary.estimated_beat_error_mean > 0
        assert summary.estimated_beat_error_max > 0

    def test_tempo_map_midstream_change(self) -> None:
        """Tempo map integration should align events across a tempo change."""
        score_events = [
            ScoreEvent(
                event_id="m1-b1.00-p60-v1-i0",
                measure=1,
                beat=1.0,
                pitch_midi=60,
                pitch_spelled="C4",
                duration=1.0,
                logical_duration=1.0,
            ),
            ScoreEvent(
                event_id="m1-b4.00-p60-v1-i1",
                measure=1,
                beat=4.0,
                pitch_midi=60,
                pitch_spelled="C4",
                duration=1.0,
                logical_duration=1.0,
            ),
        ]

        midi_events = [
            MidiEvent(
                event_id="t0.000-p60-c0-i0",
                start_sec=0.0,
                end_sec=0.5,
                pitch=60,
                velocity=80,
                channel=0,
            ),
            MidiEvent(
                event_id="t2.000-p60-c0-i1",
                start_sec=2.0,
                end_sec=2.5,
                pitch=60,
                velocity=80,
                channel=0,
            ),
        ]

        tempo_map = [
            TempoEvent(time_sec=0.0, tempo_bpm=120.0),
            TempoEvent(time_sec=1.0, tempo_bpm=60.0),
        ]

        pairs, summary = align_events(
            score_events,
            midi_events,
            tempo_bpm=120.0,
            time_signature=(4, 4),
            midi_tempo_map=tempo_map,
        )

        matched = [p for p in pairs if p.score_event and p.midi_event]
        assert len(matched) == 2
        assert summary.tempo_source == "midi_tempo_map"


class TestTieHandling:
    """Tests for tie handling in alignment."""

    def test_tied_notes_use_merged_event(
        self,
        score_events_with_tie: list[ScoreEvent],
    ) -> None:
        """Tied notes should be aligned using the merged logical event."""
        # MIDI event matching the merged duration (4 beats = 2 seconds at 120 BPM)
        # Starts at beat 3 of measure 1 = absolute beat 2 = 1.0 seconds
        midi_events = [
            MidiEvent(
                event_id="t1.000-p60-c0-i0",
                start_sec=1.0,  # Beat 3 of m.1
                end_sec=3.0,  # 4 beats = 2 seconds at 120 BPM
                pitch=60,
                velocity=80,
                channel=0,
            )
        ]

        pairs, summary = align_events(
            score_events_with_tie,
            midi_events,
            tempo_bpm=120.0,
            time_signature=(4, 4),
        )

        # Should match the merged event
        matched = [p for p in pairs if p.score_event and p.midi_event]
        assert len(matched) == 1
        assert matched[0].score_event is not None
        assert matched[0].score_event.is_logical_merged is True


class TestPickupHandling:
    """Tests for pickup (anacrusis) handling."""

    def test_pickup_measure_aligned(self) -> None:
        """Events in pickup measure (measure 0) should align correctly."""
        # Pickup note at measure 0, beat 4 (one beat before m.1)
        score_events = [
            ScoreEvent(
                event_id="m0-b4.00-p60-v1-i0",
                measure=0,
                beat=4.0,
                pitch_midi=60,
                pitch_spelled="C4",
                duration=1.0,
                logical_duration=1.0,
            )
        ]

        midi_events = [
            MidiEvent(
                event_id="t0.000-p60-c0-i0",
                start_sec=0.0,
                end_sec=0.5,
                pitch=60,
                velocity=80,
                channel=0,
            )
        ]

        pairs, summary = align_events(
            score_events,
            midi_events,
            tempo_bpm=120.0,
            time_signature=(4, 4),
            has_pickup=True,
            pickup_beats=1.0,
        )

        # Summary should note has_pickup
        assert summary.has_pickup is True
        assert summary.pickup_beats == 1.0


class TestTempoMapHandling:
    """Tests for MIDI tempo map handling in alignment."""

    def test_midi_tempo_map_detected(self) -> None:
        """When MIDI has tempo events, midi_has_tempo_map should be True."""
        score_events = [
            ScoreEvent(
                event_id="m1-b1.00-p60-v1-i0",
                measure=1,
                beat=1.0,
                pitch_midi=60,
                pitch_spelled="C4",
                duration=1.0,
                logical_duration=1.0,
            )
        ]
        midi_events = [
            MidiEvent(
                event_id="t0.000-p60-c0-i0",
                start_sec=0.0,
                end_sec=0.5,
                pitch=60,
                velocity=80,
                channel=0,
            )
        ]

        pairs, summary = align_events(
            score_events,
            midi_events,
            tempo_bpm=120.0,
            time_signature=(4, 4),
            midi_tempo_map=[TempoEvent(time_sec=0.0, tempo_bpm=100.0)],
        )

        # Summary should reflect MIDI has tempo map
        assert summary.midi_has_tempo_map is True
        assert summary.tempo_source == "midi_tempo_map"

    def test_midi_initial_tempo_used_when_available(self) -> None:
        """When MIDI tempo map is provided, it should be used."""
        score_events = [
            ScoreEvent(
                event_id="m1-b1.00-p60-v1-i0",
                measure=1,
                beat=1.0,
                pitch_midi=60,
                pitch_spelled="C4",
                duration=1.0,
                logical_duration=1.0,
            )
        ]
        midi_events = [
            MidiEvent(
                event_id="t0.000-p60-c0-i0",
                start_sec=0.0,
                end_sec=0.6,  # 1 beat at 100 BPM
                pitch=60,
                velocity=80,
                channel=0,
            )
        ]

        pairs, summary = align_events(
            score_events,
            midi_events,
            tempo_bpm=120.0,  # Base tempo
            time_signature=(4, 4),
            midi_tempo_map=[
                TempoEvent(time_sec=0.0, tempo_bpm=100.0),
                TempoEvent(time_sec=2.0, tempo_bpm=80.0),
            ],
        )

        assert summary.tempo_source == "midi_tempo_map"
        assert summary.midi_has_tempo_map is True

    def test_no_tempo_map_uses_musicxml_tempo(self) -> None:
        """When MIDI has no tempo map, MusicXML tempo is used."""
        score_events = [
            ScoreEvent(
                event_id="m1-b1.00-p60-v1-i0",
                measure=1,
                beat=1.0,
                pitch_midi=60,
                pitch_spelled="C4",
                duration=1.0,
                logical_duration=1.0,
            )
        ]
        midi_events = [
            MidiEvent(
                event_id="t0.000-p60-c0-i0",
                start_sec=0.0,
                end_sec=0.5,
                pitch=60,
                velocity=80,
                channel=0,
            )
        ]

        pairs, summary = align_events(
            score_events,
            midi_events,
            tempo_bpm=90.0,  # MusicXML tempo
            time_signature=(4, 4),
            midi_tempo_map=None,
        )

        assert summary.tempo_source == "musicxml"
        assert summary.midi_has_tempo_map is False
