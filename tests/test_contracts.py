"""Contract signature tests.

Verify that all public functions match the contract signatures
and return the expected types/shapes.
"""

import tempfile
from pathlib import Path

from musicdiff.align import BEAT_ALIGNMENT_TOLERANCE, align_events
from musicdiff.diff import generate_diffs, generate_report, get_duration_tolerance
from musicdiff.models import (
    AlignedPair,
    AlignmentSummary,
    Diff,
    DiffReport,
    MidiEvent,
    MidiMetadata,
    ScoreEvent,
    ScoreMetadata,
    TempoEvent,
    UnsupportedFeature,
)
from musicdiff.parser_midi import parse_midi
from musicdiff.parser_xml import (
    detect_unsupported_features,
    get_last_unsupported_features,
    parse_musicxml,
)


class TestParserXMLContract:
    """Verify parser_xml function signatures match contracts."""

    def test_parse_musicxml_signature(self) -> None:
        """parse_musicxml accepts path and returns (events, metadata)."""
        # Create minimal valid MusicXML
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
            result = parse_musicxml(path)
            unsupported = get_last_unsupported_features()

            # Must return 2-tuple
            assert isinstance(result, tuple)
            assert len(result) == 2

            events, metadata = result

            # Check types
            assert isinstance(events, list)
            assert isinstance(metadata, ScoreMetadata)
            assert isinstance(unsupported, list)

            # Events must be ScoreEvent instances
            for ev in events:
                assert isinstance(ev, ScoreEvent)

            # Unsupported must be UnsupportedFeature instances
            for uf in unsupported:
                assert isinstance(uf, UnsupportedFeature)
        finally:
            path.unlink()

    def test_detect_unsupported_features_signature(self) -> None:
        """detect_unsupported_features accepts path and returns list."""
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
            result = detect_unsupported_features(path)
            assert isinstance(result, list)
        finally:
            path.unlink()


class TestParserMidiContract:
    """Verify parser_midi function signatures match contracts."""

    def test_parse_midi_signature(self) -> None:
        """parse_midi accepts path and returns (events, metadata)."""
        sample_midi = Path(__file__).parent.parent / "samples" / "sample.mid"
        if not sample_midi.exists():
            # Skip if sample not available, but this shouldn't happen
            return

        result = parse_midi(sample_midi)

        # Must return 2-tuple
        assert isinstance(result, tuple)
        assert len(result) == 2

        events, metadata = result

        # Check types
        assert isinstance(events, list)
        assert isinstance(metadata, MidiMetadata)

        # Events must be MidiEvent instances
        for ev in events:
            assert isinstance(ev, MidiEvent)

        # Metadata fields
        assert isinstance(metadata.has_tempo_map, bool)
        assert isinstance(metadata.tempo_events, list)


class TestAlignContract:
    """Verify align function signatures match contracts."""

    def test_align_events_signature(self) -> None:
        """align_events returns (pairs, summary)."""
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

        # Must return 2-tuple
        assert isinstance(result, tuple)
        assert len(result) == 2

        pairs, summary = result

        # Check types
        assert isinstance(pairs, list)
        assert isinstance(summary, AlignmentSummary)

        # Pairs must be AlignedPair instances
        for pair in pairs:
            assert isinstance(pair, AlignedPair)

        # Summary required fields
        assert summary.tempo_source in ("musicxml", "midi_tempo_map", "override", "default_120")
        assert summary.alignment_confidence in ("high", "medium", "low")

    def test_beat_alignment_tolerance_is_constant(self) -> None:
        """BEAT_ALIGNMENT_TOLERANCE must be 0.125 per contract."""
        assert BEAT_ALIGNMENT_TOLERANCE == 0.125


class TestDiffContract:
    """Verify diff function signatures match contracts."""

    def test_generate_diffs_signature(self) -> None:
        """generate_diffs returns list of Diff objects."""
        pairs: list[AlignedPair] = []
        unsupported: list[UnsupportedFeature] = []
        align_events(
            [],
            [],
            tempo_bpm=120.0,
            time_signature=(4, 4),
        )

        result = generate_diffs(pairs, unsupported)

        assert isinstance(result, list)
        for diff in result:
            assert isinstance(diff, Diff)

    def test_generate_report_signature(self) -> None:
        """generate_report returns DiffReport."""
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

        result = generate_report(
            xml_path="test.xml",
            midi_path="test.mid",
            diffs=[],
            metadata=metadata,
            alignment_summary=summary,
            unsupported_features=[],
            warnings=[],
            tempo_bpm_used=120.0,
        )

        assert isinstance(result, DiffReport)

        # Required fields per contract
        assert result.source_xml == "test.xml"
        assert result.source_midi == "test.mid"
        assert result.timestamp  # Must be non-empty
        assert result.tempo_bpm == 120.0
        assert result.total_measures == 1
        assert result.alignment_summary is not None  # REQUIRED even if empty diffs

    def test_get_duration_tolerance_signature(self) -> None:
        """get_duration_tolerance returns float."""
        metadata = ScoreMetadata(
            total_measures=1,
            tempo_bpm=120.0,
            time_signature=(4, 4),
            smallest_notated_duration=0.5,
        )

        result = get_duration_tolerance(metadata)

        assert isinstance(result, float)
        # Per contract: min(0.25, smallest_notated_duration / 2)
        assert result == min(0.25, 0.5 / 2)


class TestModelContracts:
    """Verify model required fields per contract."""

    def test_score_event_required_fields(self) -> None:
        """ScoreEvent has all required fields."""
        event = ScoreEvent(
            event_id="test",
            measure=1,
            beat=1.0,
            pitch_midi=60,
            pitch_spelled="C4",
            duration=1.0,
            logical_duration=1.0,
        )

        # Required fields exist
        assert hasattr(event, "event_id")
        assert hasattr(event, "measure")
        assert hasattr(event, "beat")
        assert hasattr(event, "pitch_midi")
        assert hasattr(event, "pitch_spelled")
        assert hasattr(event, "duration")
        assert hasattr(event, "logical_duration")
        assert hasattr(event, "voice")
        assert hasattr(event, "tie_start")
        assert hasattr(event, "tie_end")
        assert hasattr(event, "is_logical_merged")

    def test_midi_event_required_fields(self) -> None:
        """MidiEvent has all required fields."""
        event = MidiEvent(
            event_id="test",
            start_sec=0.0,
            end_sec=1.0,
            pitch=60,
            velocity=80,
            channel=0,
        )

        assert hasattr(event, "event_id")
        assert hasattr(event, "start_sec")
        assert hasattr(event, "end_sec")
        assert hasattr(event, "pitch")
        assert hasattr(event, "velocity")
        assert hasattr(event, "channel")
        assert hasattr(event, "duration_sec")  # property
        assert event.duration_sec == 1.0

    def test_diff_required_fields(self) -> None:
        """Diff has all required fields per contract."""
        diff = Diff(
            type="missing_note",
            measure=1,
            beat=1.0,
            expected={"pitch": 60},
            observed={},
            confidence=0.9,
            severity="error",
            reason="test",
            suggestion="test suggestion",
        )

        assert hasattr(diff, "type")
        assert hasattr(diff, "measure")
        assert hasattr(diff, "beat")
        assert hasattr(diff, "expected")
        assert hasattr(diff, "observed")
        assert hasattr(diff, "confidence")
        assert hasattr(diff, "severity")
        assert hasattr(diff, "reason")
        assert hasattr(diff, "suggestion")

    def test_diff_types_match_contract(self) -> None:
        """Diff type literals match contract."""
        valid_types = [
            "duration_mismatch",
            "duration_mismatch_tie",
            "missing_note",
            "extra_note",
            "pitch_mismatch",
            "unsupported_feature",
        ]

        for dtype in valid_types:
            diff = Diff(
                type=dtype,  # type: ignore[arg-type]
                measure=1,
                beat=1.0,
                expected={},
                observed={},
                confidence=0.5,
                severity="info",
                reason="test",
                suggestion="test",
            )
            assert diff.type == dtype

    def test_alignment_summary_required_fields(self) -> None:
        """AlignmentSummary has required fields."""
        summary = AlignmentSummary(
            tempo_source="musicxml",
            time_signature_map_used=False,
            has_pickup=False,
            alignment_confidence="high",
            midi_has_tempo_map=False,
        )

        assert hasattr(summary, "tempo_source")
        assert hasattr(summary, "time_signature_map_used")
        assert hasattr(summary, "has_pickup")
        assert hasattr(summary, "alignment_confidence")
        assert hasattr(summary, "midi_has_tempo_map")
        assert hasattr(summary, "pedal_accounted_for")
        assert summary.pedal_accounted_for is False  # Always False for MVP

    def test_tempo_event_fields(self) -> None:
        """TempoEvent has required fields."""
        event = TempoEvent(time_sec=0.0, tempo_bpm=120.0)
        assert hasattr(event, "time_sec")
        assert hasattr(event, "tempo_bpm")
