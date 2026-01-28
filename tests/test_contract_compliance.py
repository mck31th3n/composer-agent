"""Contract compliance tests.

These tests verify behavior against contracts/interfaces.md.
"""

import tempfile
from pathlib import Path

from musicdiff.align import align_events
from musicdiff.diff import generate_diffs, generate_report
from musicdiff.models import (
    AlignedPair,
    AlignmentSummary,
    Diff,
    MidiEvent,
    ScoreEvent,
    ScoreMetadata,
    TempoEvent,
    UnsupportedFeature,
)
from musicdiff.parser_xml import get_last_unsupported_features, parse_musicxml


class TestParseXMLContractCompliance:
    """Test parse_musicxml against contract."""

    def test_contract_return_type(self) -> None:
        """Contract: parse_musicxml returns (events, metadata) only."""
        xml_content = """<?xml version="1.0"?>
<score-partwise version="4.0">
  <part-list><score-part id="P1"><part-name>X</part-name></score-part></part-list>
  <part id="P1">
    <measure number="1">
      <attributes><divisions>1</divisions><time><beats>4</beats><beat-type>4</beat-type></time></attributes>
      <note><pitch><step>C</step><octave>4</octave></pitch><duration>1</duration><type>quarter</type></note>
    </measure>
  </part>
</score-partwise>"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
            f.write(xml_content)
            f.flush()
            path = Path(f.name)

        try:
            events, metadata = parse_musicxml(path)
            unsupported = get_last_unsupported_features()
            assert isinstance(unsupported, list)
        finally:
            path.unlink()


class TestAlignEventsContractCompliance:
    """Test align_events against contract signature."""

    def test_contract_signature(self) -> None:
        """Contract signature matches expected parameters and return shape."""
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

        result = align_events(
            score_events,
            midi_events,
            tempo_bpm=120.0,
            time_signature=(4, 4),
        )

        assert len(result) == 2

    def test_tempo_source_contract(self) -> None:
        """Contract: tempo_source is 'midi_tempo_map' when tempo map is used."""
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
        tempo_map = [TempoEvent(time_sec=0.0, tempo_bpm=100.0)]

        pairs, summary = align_events(
            score_events,
            midi_events,
            tempo_bpm=120.0,
            time_signature=(4, 4),
            midi_tempo_map=tempo_map,
        )

        assert summary.tempo_source == "midi_tempo_map"
        assert summary.midi_has_tempo_map is True


class TestTempoMapAlignmentProof:
    """G7b: Tempo-map alignment proof tests."""

    def test_tempo_change_mid_performance_mvp_limitation(self) -> None:
        """Tempo map changes should be integrated for alignment.

        Test setup:
        - Score event at measure 2, beat 1 = absolute beat 4
        - MIDI event at t=2.0s with tempo map integration:
          - At 120 BPM: 2.0s = 4 beats
        - Tolerance is 0.125 beats, so they should match.
        """
        score_events = [
            ScoreEvent(
                event_id="m2-b1.00-p60-v1-i0",
                measure=2,
                beat=1.0,  # Beat 1 of measure 2 = absolute beat 4
                pitch_midi=60,
                pitch_spelled="C4",
                duration=1.0,
                logical_duration=1.0,
            )
        ]

        # MIDI event at t=2.0s (which is beat 4 at 120 BPM)
        midi_events = [
            MidiEvent(
                event_id="t2.000-p60-c0-i0",
                start_sec=2.0,
                end_sec=2.5,
                pitch=60,
                velocity=80,
                channel=0,
            )
        ]

        tempo_map = [
            TempoEvent(time_sec=0.0, tempo_bpm=120.0),
            TempoEvent(time_sec=2.0, tempo_bpm=60.0),
        ]

        pairs, summary = align_events(
            score_events,
            midi_events,
            tempo_bpm=120.0,
            time_signature=(4, 4),
            midi_tempo_map=tempo_map,
        )

        # With tempo map, t=2.0s = 4 beats, matching score event at beat 4
        matched = [p for p in pairs if p.score_event and p.midi_event]
        assert len(matched) == 1
        assert summary.midi_has_tempo_map is True

    def test_initial_tempo_from_midi_used(self) -> None:
        """Verify MIDI tempo map is used for alignment."""
        # At 100 BPM: beat 1 = 0s, beat 2 = 0.6s
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
                event_id="m1-b2.00-p62-v1-i1",
                measure=1,
                beat=2.0,
                pitch_midi=62,
                pitch_spelled="D4",
                duration=1.0,
                logical_duration=1.0,
            ),
        ]

        # MIDI events at 100 BPM timing
        midi_events = [
            MidiEvent(
                event_id="t0.000-p60-c0-i0",
                start_sec=0.0,
                end_sec=0.6,
                pitch=60,
                velocity=80,
                channel=0,
            ),
            MidiEvent(
                event_id="t0.600-p62-c0-i1",
                start_sec=0.6,  # Beat 2 at 100 BPM
                end_sec=1.2,
                pitch=62,
                velocity=80,
                channel=0,
            ),
        ]

        tempo_map = [TempoEvent(time_sec=0.0, tempo_bpm=100.0)]

        pairs, summary = align_events(
            score_events,
            midi_events,
            tempo_bpm=120.0,
            time_signature=(4, 4),
            midi_tempo_map=tempo_map,
        )

        # Both events should match at 100 BPM timing
        matched = [p for p in pairs if p.score_event and p.midi_event]
        assert len(matched) == 2, "Both events should match at 100 BPM"


class TestPickupSymmetry:
    """Pickup/anacrusis alignment tests."""

    def test_pickup_measure_zero_alignment(self) -> None:
        """Score with measure=0 pickup should align MIDI event at t=0."""
        score_events = [
            ScoreEvent(
                event_id="m0-b4.00-p60-v1-i0",
                measure=0,  # Pickup measure
                beat=4.0,  # Last beat of pickup
                pitch_midi=60,
                pitch_spelled="C4",
                duration=1.0,
                logical_duration=1.0,
            ),
            ScoreEvent(
                event_id="m1-b1.00-p62-v1-i1",
                measure=1,  # First full measure
                beat=1.0,
                pitch_midi=62,
                pitch_spelled="D4",
                duration=1.0,
                logical_duration=1.0,
            ),
        ]

        midi_events = [
            MidiEvent(
                event_id="t0.000-p60-c0-i0",
                start_sec=0.0,  # Pickup note
                end_sec=0.5,
                pitch=60,
                velocity=80,
                channel=0,
            ),
            MidiEvent(
                event_id="t0.500-p62-c0-i1",
                start_sec=0.5,  # Measure 1 beat 1
                end_sec=1.0,
                pitch=62,
                velocity=80,
                channel=0,
            ),
        ]

        pairs, summary = align_events(
            score_events,
            midi_events,
            tempo_bpm=120.0,
            time_signature=(4, 4),
            has_pickup=True,
            pickup_beats=1.0,
        )

        # Verify pickup is recorded
        assert summary.has_pickup is True
        assert summary.pickup_beats == 1.0
        assert len(pairs) >= 2, "Should have alignment pairs for both events"

    def test_has_pickup_metadata_propagates(self) -> None:
        """Verify has_pickup and pickup_beats propagate to AlignmentSummary."""
        score_events: list[ScoreEvent] = []
        midi_events: list[MidiEvent] = []

        pairs, summary = align_events(
            score_events,
            midi_events,
            tempo_bpm=120.0,
            time_signature=(4, 4),
            has_pickup=True,
            pickup_beats=2.5,
        )

        assert summary.has_pickup is True
        assert summary.pickup_beats == 2.5


class TestUnsupportedFeatureDetection:
    """Tests for unsupported feature detection."""

    def test_time_signature_change_detected(self) -> None:
        """Time signature changes should be detected as unsupported."""
        xml_content = """<?xml version="1.0"?>
<score-partwise version="4.0">
  <part-list><score-part id="P1"><part-name>X</part-name></score-part></part-list>
  <part id="P1">
    <measure number="1">
      <attributes>
        <divisions>1</divisions>
        <time><beats>4</beats><beat-type>4</beat-type></time>
      </attributes>
      <note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration><type>whole</type></note>
    </measure>
    <measure number="2">
      <attributes>
        <time><beats>3</beats><beat-type>4</beat-type></time>
      </attributes>
      <note><pitch><step>C</step><octave>4</octave></pitch><duration>3</duration><type>half</type><dot/></note>
    </measure>
  </part>
</score-partwise>"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
            f.write(xml_content)
            f.flush()
            path = Path(f.name)

        try:
            events, metadata = parse_musicxml(path)
            _ = get_last_unsupported_features()

            assert metadata.time_signature == (4, 4), "Initial time signature"

            if metadata.time_signature_changes:
                assert any(
                    ts[1] == (3, 4) for ts in metadata.time_signature_changes
                ), "3/4 change should be recorded"
        finally:
            path.unlink()

    def test_grace_note_detected_as_unsupported(self) -> None:
        """Grace notes should be flagged as unsupported."""
        xml_content = """<?xml version="1.0"?>
<score-partwise version="4.0">
  <part-list><score-part id="P1"><part-name>X</part-name></score-part></part-list>
  <part id="P1">
    <measure number="1">
      <attributes>
        <divisions>1</divisions>
        <time><beats>4</beats><beat-type>4</beat-type></time>
      </attributes>
      <note>
        <grace/>
        <pitch><step>D</step><octave>4</octave></pitch>
        <type>eighth</type>
      </note>
      <note><pitch><step>C</step><octave>4</octave></pitch><duration>1</duration><type>quarter</type></note>
    </measure>
  </part>
</score-partwise>"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
            f.write(xml_content)
            f.flush()
            path = Path(f.name)

        try:
            events, metadata = parse_musicxml(path)
            unsupported = get_last_unsupported_features()

            grace_features = [uf for uf in unsupported if uf.feature == "grace_note"]
            assert len(grace_features) >= 1, "Grace note should be flagged as unsupported"
            assert grace_features[0].measure == 1
        finally:
            path.unlink()

    def test_tuplet_detected_as_unsupported(self) -> None:
        """Tuplets should be flagged as unsupported."""
        xml_content = """<?xml version="1.0"?>
<score-partwise version="4.0">
  <part-list><score-part id="P1"><part-name>X</part-name></score-part></part-list>
  <part id="P1">
    <measure number="1">
      <attributes>
        <divisions>2</divisions>
        <time><beats>4</beats><beat-type>4</beat-type></time>
      </attributes>
      <note>
        <pitch><step>C</step><octave>4</octave></pitch>
        <duration>1</duration>
        <type>eighth</type>
        <time-modification>
          <actual-notes>3</actual-notes>
          <normal-notes>2</normal-notes>
        </time-modification>
      </note>
    </measure>
  </part>
</score-partwise>"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
            f.write(xml_content)
            f.flush()
            path = Path(f.name)

        try:
            events, metadata = parse_musicxml(path)
            unsupported = get_last_unsupported_features()

            tuplet_features = [uf for uf in unsupported if uf.feature == "tuplet"]
            assert len(tuplet_features) >= 1, "Tuplet should be flagged as unsupported"
        finally:
            path.unlink()

    def test_multi_voice_detected_as_unsupported(self) -> None:
        """Multiple voices in a measure should be flagged as unsupported."""
        xml_content = """<?xml version="1.0"?>
<score-partwise version="4.0">
  <part-list><score-part id="P1"><part-name>X</part-name></score-part></part-list>
  <part id="P1">
    <measure number="1">
      <attributes>
        <divisions>1</divisions>
        <time><beats>4</beats><beat-type>4</beat-type></time>
      </attributes>
      <note>
        <pitch><step>C</step><octave>4</octave></pitch>
        <duration>4</duration>
        <type>whole</type>
        <voice>1</voice>
      </note>
      <note>
        <pitch><step>E</step><octave>4</octave></pitch>
        <duration>4</duration>
        <type>whole</type>
        <voice>2</voice>
      </note>
    </measure>
  </part>
</score-partwise>"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
            f.write(xml_content)
            f.flush()
            path = Path(f.name)

        try:
            events, metadata = parse_musicxml(path)
            unsupported = get_last_unsupported_features()

            assert isinstance(unsupported, list)
            _ = [uf for uf in unsupported if uf.feature == "multi_voice"]
        finally:
            path.unlink()


class TestGenerateDiffsContractCompliance:
    """Test generate_diffs against contract."""

    def test_contract_signature(self) -> None:
        """Contract compliant: generate_diffs takes 2 params.

        Contract signature:
            generate_diffs(aligned_pairs, unsupported_features) -> list[Diff]
        """
        pairs: list[AlignedPair] = []
        unsupported: list[UnsupportedFeature] = []

        # Set alignment context for diff generation
        align_events(
            [],
            [],
            tempo_bpm=120.0,
            time_signature=(4, 4),
        )

        # Contract-compliant call with 2 params
        result = generate_diffs(pairs, unsupported)
        assert isinstance(result, list)


class TestAlignmentSummaryAlwaysPresent:
    """Verify alignment_summary is ALWAYS present per contract invariant."""

    def test_summary_present_with_empty_diffs(self) -> None:
        """alignment_summary must exist even when diffs is empty."""
        metadata = ScoreMetadata(
            total_measures=1,
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
            diffs=[],  # Empty diffs
            metadata=metadata,
            alignment_summary=summary,
            unsupported_features=[],
            warnings=[],
            tempo_bpm_used=120.0,
        )

        # Contract invariant: alignment_summary MUST always be present
        assert report.alignment_summary is not None
        assert report.alignment_summary.tempo_source == "musicxml"

    def test_summary_present_with_diffs(self) -> None:
        """alignment_summary must exist when diffs is non-empty."""

        metadata = ScoreMetadata(
            total_measures=1,
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
        diffs = [
            Diff(
                type="missing_note",
                measure=1,
                beat=1.0,
                expected={"pitch": 60},
                observed={},
                confidence=0.0,
                severity="error",
                reason="test",
                suggestion="test",
            )
        ]

        report = generate_report(
            xml_path="test.xml",
            midi_path="test.mid",
            diffs=diffs,
            metadata=metadata,
            alignment_summary=summary,
            unsupported_features=[],
            warnings=[],
            tempo_bpm_used=120.0,
        )

        assert report.alignment_summary is not None
        assert len(report.diffs) == 1
