"""Pytest fixtures with synthetic test data.

These fixtures create in-memory ScoreEvent and MidiEvent objects
for precise, deterministic testing without relying on external files.
"""

import pytest

from musicdiff.align import align_events
from musicdiff.models import (
    AlignedPair,
    MidiEvent,
    MidiMetadata,
    ScoreEvent,
    ScoreMetadata,
    UnsupportedFeature,
)

# --- ScoreEvent Fixtures ---


@pytest.fixture
def simple_score_event() -> ScoreEvent:
    """A single C4 quarter note at measure 1, beat 1."""
    return ScoreEvent(
        event_id="m1-b1.00-p60-v1-i0",
        measure=1,
        beat=1.0,
        pitch_midi=60,
        pitch_spelled="C4",
        duration=1.0,
        logical_duration=1.0,
        voice=1,
        staff=1,
        tie_start=False,
        tie_end=False,
        is_logical_merged=False,
    )


@pytest.fixture
def score_events_simple() -> list[ScoreEvent]:
    """Simple 4-note melody: C4, D4, E4, F4 (quarter notes in m.1)."""
    return [
        ScoreEvent(
            event_id=f"m1-b{beat:.2f}-p{pitch}-v1-i{i}",
            measure=1,
            beat=beat,
            pitch_midi=pitch,
            pitch_spelled=spelled,
            duration=1.0,
            logical_duration=1.0,
            voice=1,
            staff=1,
        )
        for i, (beat, pitch, spelled) in enumerate([
            (1.0, 60, "C4"),
            (2.0, 62, "D4"),
            (3.0, 64, "E4"),
            (4.0, 65, "F4"),
        ])
    ]


@pytest.fixture
def score_events_with_tie() -> list[ScoreEvent]:
    """Two tied half notes: C4 tied across m.1 beat 3 to m.2 beat 1.

    Individual events + merged logical event.
    """
    # First half note (starts tie)
    ev1 = ScoreEvent(
        event_id="m1-b3.00-p60-v1-i0",
        measure=1,
        beat=3.0,
        pitch_midi=60,
        pitch_spelled="C4",
        duration=2.0,
        logical_duration=2.0,
        voice=1,
        staff=1,
        tie_start=True,
        tie_end=False,
        is_logical_merged=False,
    )
    # Second half note (ends tie)
    ev2 = ScoreEvent(
        event_id="m2-b1.00-p60-v1-i1",
        measure=2,
        beat=1.0,
        pitch_midi=60,
        pitch_spelled="C4",
        duration=2.0,
        logical_duration=2.0,
        voice=1,
        staff=1,
        tie_start=False,
        tie_end=True,
        is_logical_merged=False,
    )
    # Merged logical event
    merged = ScoreEvent(
        event_id="m1-b3.00-p60-v1-merged",
        measure=1,
        beat=3.0,
        pitch_midi=60,
        pitch_spelled="C4",
        duration=2.0,
        logical_duration=4.0,  # Sum of both tied notes
        voice=1,
        staff=1,
        tie_start=True,
        tie_end=True,
        is_logical_merged=True,
    )
    return [ev1, ev2, merged]


# --- MidiEvent Fixtures ---


@pytest.fixture
def simple_midi_event() -> MidiEvent:
    """A single C4 note at time 0, duration 0.5 seconds (at 120 BPM = 1 beat)."""
    return MidiEvent(
        event_id="t0.000-p60-c0-i0",
        start_sec=0.0,
        end_sec=0.5,  # 1 beat at 120 BPM
        pitch=60,
        velocity=80,
        channel=0,
    )


@pytest.fixture
def midi_events_matching_simple(score_events_simple: list[ScoreEvent]) -> list[MidiEvent]:
    """MIDI events that exactly match score_events_simple at 120 BPM."""
    # At 120 BPM: 1 beat = 0.5 seconds
    # Beat 1 = 0.0s, Beat 2 = 0.5s, Beat 3 = 1.0s, Beat 4 = 1.5s
    tempo_bpm = 120.0
    sec_per_beat = 60.0 / tempo_bpm

    events = []
    for i, se in enumerate(score_events_simple):
        # Convert beat position to seconds (beat 1 = 0s)
        start_sec = (se.beat - 1.0) * sec_per_beat
        end_sec = start_sec + (se.duration * sec_per_beat)
        events.append(MidiEvent(
            event_id=f"t{start_sec:.3f}-p{se.pitch_midi}-c0-i{i}",
            start_sec=start_sec,
            end_sec=end_sec,
            pitch=se.pitch_midi,
            velocity=80,
            channel=0,
        ))
    return events


@pytest.fixture
def midi_events_with_extra() -> list[MidiEvent]:
    """MIDI events with one extra note not in score."""
    return [
        MidiEvent(
            event_id="t0.000-p60-c0-i0",
            start_sec=0.0,
            end_sec=0.5,
            pitch=60,
            velocity=80,
            channel=0,
        ),
        MidiEvent(
            event_id="t0.500-p72-c0-i0",  # Extra C5 not in score
            start_sec=0.5,
            end_sec=1.0,
            pitch=72,
            velocity=80,
            channel=0,
        ),
    ]


@pytest.fixture
def midi_events_with_wrong_duration() -> list[MidiEvent]:
    """MIDI event with significantly wrong duration."""
    return [
        MidiEvent(
            event_id="t0.000-p60-c0-i0",
            start_sec=0.0,
            end_sec=0.25,  # Half the expected duration
            pitch=60,
            velocity=80,
            channel=0,
        ),
    ]


# --- Metadata Fixtures ---


@pytest.fixture
def simple_score_metadata() -> ScoreMetadata:
    """Metadata for a simple 4/4 score at 120 BPM, 4 measures."""
    return ScoreMetadata(
        total_measures=4,
        tempo_bpm=120.0,
        time_signature=(4, 4),
        time_signature_changes=[],
        has_pickup=False,
        pickup_beats=0.0,
        smallest_notated_duration=1.0,
        title="Test Score",
        part_name="Piano",
    )


@pytest.fixture
def alignment_context_simple(score_events_simple: list[ScoreEvent]) -> None:
    """Set alignment context for diff generation tests."""
    align_events(
        score_events_simple,
        [],
        tempo_bpm=120.0,
        time_signature=(4, 4),
    )


@pytest.fixture
def simple_midi_metadata() -> MidiMetadata:
    """Metadata for a simple MIDI with no tempo map."""
    return MidiMetadata(
        has_tempo_map=False,
        tempo_events=[],
        initial_tempo_bpm=120.0,
    )


@pytest.fixture
def midi_metadata_with_tempo() -> MidiMetadata:
    """Metadata for MIDI with a tempo map."""
    from musicdiff.models import TempoEvent
    return MidiMetadata(
        has_tempo_map=True,
        tempo_events=[TempoEvent(time_sec=0.0, tempo_bpm=120.0)],
        initial_tempo_bpm=120.0,
    )


# --- Unsupported Feature Fixtures ---


@pytest.fixture
def unsupported_tuplet() -> UnsupportedFeature:
    """An unsupported tuplet feature."""
    return UnsupportedFeature(
        feature="tuplet",
        measure=2,
        description="Tuplet detected - rhythm may be misaligned",
    )


@pytest.fixture
def unsupported_grace() -> UnsupportedFeature:
    """An unsupported grace note feature."""
    return UnsupportedFeature(
        feature="grace_note",
        measure=1,
        description="Grace note C4 - timing ambiguous",
    )


# --- AlignedPair Fixtures ---


@pytest.fixture
def aligned_pair_matched(
    simple_score_event: ScoreEvent, simple_midi_event: MidiEvent
) -> AlignedPair:
    """A perfectly matched aligned pair."""
    return AlignedPair(
        score_event=simple_score_event,
        midi_event=simple_midi_event,
        confidence=1.0,
        beat_error=0.0,
    )


@pytest.fixture
def aligned_pair_missing_note(simple_score_event: ScoreEvent) -> AlignedPair:
    """An aligned pair with score event but no MIDI (missing note)."""
    return AlignedPair(
        score_event=simple_score_event,
        midi_event=None,
        confidence=0.0,
        beat_error=0.0,
    )


@pytest.fixture
def aligned_pair_extra_note(simple_midi_event: MidiEvent) -> AlignedPair:
    """An aligned pair with MIDI event but no score (extra note)."""
    return AlignedPair(
        score_event=None,
        midi_event=simple_midi_event,
        confidence=0.0,
        beat_error=0.0,
    )
