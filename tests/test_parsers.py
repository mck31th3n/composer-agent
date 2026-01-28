"""Smoke tests for parsers.

Tests that parsers return valid structures.
Uses temporary files with minimal valid content.
"""

import tempfile
from pathlib import Path

import pytest

from musicdiff.exceptions import ParseError
from musicdiff.models import MidiEvent, MidiMetadata, ScoreEvent, ScoreMetadata
from musicdiff.parser_midi import parse_midi
from musicdiff.parser_xml import (
    detect_unsupported_features,
    get_last_unsupported_features,
    parse_musicxml,
)

# Minimal valid MusicXML
MINIMAL_MUSICXML = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0 Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">
<score-partwise version="4.0">
  <part-list>
    <score-part id="P1">
      <part-name>Music</part-name>
    </score-part>
  </part-list>
  <part id="P1">
    <measure number="1">
      <attributes>
        <divisions>1</divisions>
        <time>
          <beats>4</beats>
          <beat-type>4</beat-type>
        </time>
        <clef>
          <sign>G</sign>
          <line>2</line>
        </clef>
      </attributes>
      <direction placement="above">
        <direction-type>
          <metronome>
            <beat-unit>quarter</beat-unit>
            <per-minute>120</per-minute>
          </metronome>
        </direction-type>
      </direction>
      <note>
        <pitch>
          <step>C</step>
          <octave>4</octave>
        </pitch>
        <duration>1</duration>
        <type>quarter</type>
      </note>
    </measure>
  </part>
</score-partwise>
"""

# MusicXML with tied notes
MUSICXML_WITH_TIE = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0 Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">
<score-partwise version="4.0">
  <part-list>
    <score-part id="P1">
      <part-name>Music</part-name>
    </score-part>
  </part-list>
  <part id="P1">
    <measure number="1">
      <attributes>
        <divisions>1</divisions>
        <time>
          <beats>4</beats>
          <beat-type>4</beat-type>
        </time>
      </attributes>
      <note>
        <pitch>
          <step>C</step>
          <octave>4</octave>
        </pitch>
        <duration>2</duration>
        <type>half</type>
        <tie type="start"/>
        <notations>
          <tied type="start"/>
        </notations>
      </note>
    </measure>
    <measure number="2">
      <note>
        <pitch>
          <step>C</step>
          <octave>4</octave>
        </pitch>
        <duration>2</duration>
        <type>half</type>
        <tie type="stop"/>
        <notations>
          <tied type="stop"/>
        </notations>
      </note>
    </measure>
  </part>
</score-partwise>
"""


class TestMusicXMLParser:
    """Tests for MusicXML parser."""

    def test_parse_minimal_musicxml(self) -> None:
        """Parser should handle minimal valid MusicXML."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
            f.write(MINIMAL_MUSICXML)
            f.flush()
            path = Path(f.name)

        try:
            events, metadata = parse_musicxml(path)
            unsupported = get_last_unsupported_features()

            # Check structure
            assert isinstance(events, list)
            assert isinstance(metadata, ScoreMetadata)
            assert isinstance(unsupported, list)

            # Check we got at least one event
            assert len(events) >= 1

            # Check event structure
            for event in events:
                assert isinstance(event, ScoreEvent)
                assert event.measure >= 0
                assert event.beat >= 1.0
                assert 0 <= event.pitch_midi <= 127
                assert event.duration > 0
                assert event.logical_duration > 0

            # Check metadata structure
            assert metadata.total_measures >= 1
            assert metadata.tempo_bpm > 0
            assert len(metadata.time_signature) == 2
        finally:
            path.unlink()

    def test_parse_file_not_found(self) -> None:
        """Parser should raise FileNotFoundError for missing file."""
        with pytest.raises(FileNotFoundError):
            parse_musicxml("/nonexistent/file.xml")

    def test_parse_invalid_xml_raises_parse_error(self) -> None:
        """Parser should raise ParseError for invalid content."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
            f.write("not valid xml content")
            f.flush()
            path = Path(f.name)

        try:
            with pytest.raises(ParseError):
                parse_musicxml(path)
        finally:
            path.unlink()

    def test_parse_tied_notes(self) -> None:
        """Parser should detect ties and create merged events."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
            f.write(MUSICXML_WITH_TIE)
            f.flush()
            path = Path(f.name)

        try:
            events, metadata = parse_musicxml(path)
            _ = get_last_unsupported_features()

            # Should have individual events + merged event
            tied_events = [e for e in events if e.tie_start or e.tie_end]
            merged_events = [e for e in events if e.is_logical_merged]

            # Should have at least one tied event and one merged
            assert len(tied_events) >= 1
            assert len(merged_events) >= 1

            # Merged event should have logical_duration = sum of tied durations
            for merged in merged_events:
                assert merged.logical_duration >= merged.duration
        finally:
            path.unlink()

    def test_metadata_time_signature(self) -> None:
        """Parser should extract time signature correctly."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
            f.write(MINIMAL_MUSICXML)
            f.flush()
            path = Path(f.name)

        try:
            _, metadata = parse_musicxml(path)

            assert metadata.time_signature == (4, 4)
        finally:
            path.unlink()

    def test_metadata_tempo(self) -> None:
        """Parser should extract tempo correctly."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
            f.write(MINIMAL_MUSICXML)
            f.flush()
            path = Path(f.name)

        try:
            _, metadata = parse_musicxml(path)

            assert metadata.tempo_bpm == 120.0
        finally:
            path.unlink()


class TestDetectUnsupportedFeatures:
    """Tests for unsupported feature detection."""

    def test_detect_returns_list(self) -> None:
        """detect_unsupported_features should return a list."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
            f.write(MINIMAL_MUSICXML)
            f.flush()
            path = Path(f.name)

        try:
            features = detect_unsupported_features(path)
            assert isinstance(features, list)
        finally:
            path.unlink()


class TestMidiParser:
    """Tests for MIDI parser."""

    def test_parse_creates_valid_structure(self) -> None:
        """Parser should create valid MidiEvent and MidiMetadata."""
        # Use the sample MIDI file
        sample_midi = Path(__file__).parent.parent / "samples" / "sample.mid"
        if not sample_midi.exists():
            pytest.skip("Sample MIDI file not available")

        events, metadata = parse_midi(sample_midi)

        # Check structure
        assert isinstance(events, list)
        assert isinstance(metadata, MidiMetadata)

        # Check we got events
        assert len(events) >= 1

        # Check event structure
        for event in events:
            assert isinstance(event, MidiEvent)
            assert event.start_sec >= 0
            assert event.end_sec > event.start_sec
            assert 0 <= event.pitch <= 127
            assert 0 <= event.velocity <= 127

        # Check metadata
        assert isinstance(metadata.has_tempo_map, bool)

    def test_parse_file_not_found(self) -> None:
        """Parser should raise FileNotFoundError for missing file."""
        with pytest.raises(FileNotFoundError):
            parse_midi("/nonexistent/file.mid")

    def test_parse_invalid_midi_raises_parse_error(self) -> None:
        """Parser should raise ParseError for invalid MIDI."""
        with tempfile.NamedTemporaryFile(mode="wb", suffix=".mid", delete=False) as f:
            f.write(b"not valid midi content")
            f.flush()
            path = Path(f.name)

        try:
            with pytest.raises(ParseError):
                parse_midi(path)
        finally:
            path.unlink()

    def test_events_sorted_by_time(self) -> None:
        """Events should be sorted by start time."""
        sample_midi = Path(__file__).parent.parent / "samples" / "sample.mid"
        if not sample_midi.exists():
            pytest.skip("Sample MIDI file not available")

        events, _ = parse_midi(sample_midi)

        # Check events are sorted by start_sec
        for i in range(1, len(events)):
            assert events[i].start_sec >= events[i - 1].start_sec

    def test_event_duration_positive(self) -> None:
        """Event duration must be positive."""
        sample_midi = Path(__file__).parent.parent / "samples" / "sample.mid"
        if not sample_midi.exists():
            pytest.skip("Sample MIDI file not available")

        events, _ = parse_midi(sample_midi)

        for event in events:
            assert event.duration_sec > 0


class TestParserIntegration:
    """Integration tests using sample files."""

    def test_sample_files_parse_successfully(self) -> None:
        """Both sample files should parse without errors."""
        sample_xml = Path(__file__).parent.parent / "samples" / "sample.xml"
        sample_midi = Path(__file__).parent.parent / "samples" / "sample.mid"

        if not sample_xml.exists() or not sample_midi.exists():
            pytest.skip("Sample files not available")

        # Should not raise
        events_xml, metadata_xml = parse_musicxml(sample_xml)
        _ = get_last_unsupported_features()
        events_midi, metadata_midi = parse_midi(sample_midi)

        # Basic sanity checks
        assert len(events_xml) > 0
        assert len(events_midi) > 0
        assert metadata_xml.total_measures > 0
        assert metadata_xml.tempo_bpm > 0
