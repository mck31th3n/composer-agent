"""Tests for PatchPlan application (P3 - parse survival, P4 - diff reduction).

GATE P3: Output MusicXML must be validly parsable by music21.
GATE P4: Diff count must decrease after repair.

These tests verify that:
1. Applied patches produce valid MusicXML (parsable by music21)
2. Applying repairs reduces the diff count
3. Forbidden operations are rejected
4. Safety constraints are enforced

These tests serve as acceptance criteria for the repair system implementation.
The actual implementation is owned by Codex (musicdiff.repair.planner, musicdiff.repair.applier).
"""

import tempfile
from pathlib import Path

import pytest

# music21 is required for parse survival tests
try:
    import music21
    HAS_MUSIC21 = True
except ImportError:
    HAS_MUSIC21 = False

# Repair module imports (will work once Codex implements)
try:
    from musicdiff.repair.planner import generate_patchplan  # noqa: F401
    from musicdiff.repair.applier import apply_patchplan  # noqa: F401
    HAS_REPAIR_MODULE = True
except ImportError:
    HAS_REPAIR_MODULE = False


# Test MusicXML content
MUSICXML_WITH_C4_WHOLE = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0 Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">
<score-partwise version="4.0">
  <part-list>
    <score-part id="P1"><part-name>Music</part-name></score-part>
  </part-list>
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
      </note>
    </measure>
  </part>
</score-partwise>
"""

MUSICXML_WITH_TWO_MEASURES = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0 Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">
<score-partwise version="4.0">
  <part-list>
    <score-part id="P1"><part-name>Music</part-name></score-part>
  </part-list>
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
      </note>
    </measure>
    <measure number="2">
      <note>
        <pitch><step>D</step><octave>4</octave></pitch>
        <duration>4</duration>
        <type>whole</type>
      </note>
    </measure>
  </part>
</score-partwise>
"""


@pytest.fixture
def temp_musicxml_single() -> Path:
    """Create temp MusicXML with single measure."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
        f.write(MUSICXML_WITH_C4_WHOLE)
        f.flush()
        return Path(f.name)


@pytest.fixture
def temp_musicxml_two_measures() -> Path:
    """Create temp MusicXML with two measures."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
        f.write(MUSICXML_WITH_TWO_MEASURES)
        f.flush()
        return Path(f.name)


def cleanup_file(path: Path) -> None:
    """Clean up temporary file."""
    if path.exists():
        path.unlink()


@pytest.mark.skipif(not HAS_MUSIC21, reason="music21 not installed")
class TestParseSurvivalGateP3:
    """Gate P3: Output MusicXML must be valid after repair."""

    def test_original_file_parses(self, temp_musicxml_single: Path) -> None:
        """Verify our test fixture is valid MusicXML."""
        try:
            score = music21.converter.parse(temp_musicxml_single)
            assert score is not None
            notes = list(score.recurse().notes)
            assert len(notes) == 1
        finally:
            cleanup_file(temp_musicxml_single)

    @pytest.mark.skipif(not HAS_REPAIR_MODULE, reason="Repair module not implemented yet")
    def test_insert_note_produces_valid_xml(self, temp_musicxml_single: Path) -> None:
        """insert_note operation produces parsable MusicXML."""
        from musicdiff.repair.applier import apply_patchplan

        try:
            plan = {
                "source_file": str(temp_musicxml_single),
                "source_diff_timestamp": "2026-01-21T12:00:00Z",
                "operations": [
                    {
                        "op_id": "op-001",
                        "type": "insert_note",
                        "measure": 1,
                        "beat": 3.0,
                        "voice": 2,  # Insert in voice 2 to avoid collision
                        "params": {"pitch_midi": 64, "duration": 2.0},
                    }
                ],
            }

            output = temp_musicxml_single.with_suffix(".repaired.xml")
            apply_patchplan(plan, output)

            # P3: Must parse successfully
            score = music21.converter.parse(output)
            assert score is not None, "Repaired XML must be parsable"

            cleanup_file(output)
        finally:
            cleanup_file(temp_musicxml_single)

    @pytest.mark.skipif(not HAS_REPAIR_MODULE, reason="Repair module not implemented yet")
    def test_delete_note_produces_valid_xml(self, temp_musicxml_single: Path) -> None:
        """delete_note operation produces parsable MusicXML with rest."""
        from musicdiff.repair.applier import apply_patchplan

        try:
            plan = {
                "source_file": str(temp_musicxml_single),
                "source_diff_timestamp": "2026-01-21T12:00:00Z",
                "operations": [
                    {
                        "op_id": "op-001",
                        "type": "delete_note",
                        "measure": 1,
                        "beat": 1.0,
                        "voice": 1,
                        "params": {"pitch_midi": 60, "duration": 4.0},
                    }
                ],
            }

            output = temp_musicxml_single.with_suffix(".repaired.xml")
            apply_patchplan(plan, output)

            # P3: Must parse successfully
            score = music21.converter.parse(output)
            assert score is not None

            # Verify delete left a rest (not empty measure)
            rests = list(score.recurse().getElementsByClass("Rest"))
            assert len(rests) >= 1, "delete_note must leave rest in place"

            cleanup_file(output)
        finally:
            cleanup_file(temp_musicxml_single)

    @pytest.mark.skipif(not HAS_REPAIR_MODULE, reason="Repair module not implemented yet")
    def test_update_pitch_produces_valid_xml(self, temp_musicxml_single: Path) -> None:
        """update_pitch operation produces parsable MusicXML."""
        from musicdiff.repair.applier import apply_patchplan

        try:
            plan = {
                "source_file": str(temp_musicxml_single),
                "source_diff_timestamp": "2026-01-21T12:00:00Z",
                "operations": [
                    {
                        "op_id": "op-001",
                        "type": "update_pitch",
                        "measure": 1,
                        "beat": 1.0,
                        "voice": 1,
                        "params": {
                            "pitch_midi": 62,
                            "duration": 4.0,
                            "old_pitch_midi": 60,
                        },
                    }
                ],
            }

            output = temp_musicxml_single.with_suffix(".repaired.xml")
            apply_patchplan(plan, output)

            # P3: Must parse successfully
            score = music21.converter.parse(output)
            assert score is not None

            # Verify pitch changed
            notes = list(score.recurse().notes)
            assert len(notes) == 1
            assert notes[0].pitch.midi == 62, "Pitch should be updated to D4"

            cleanup_file(output)
        finally:
            cleanup_file(temp_musicxml_single)

    @pytest.mark.skipif(not HAS_REPAIR_MODULE, reason="Repair module not implemented yet")
    def test_update_duration_produces_valid_xml(self, temp_musicxml_single: Path) -> None:
        """update_duration operation produces parsable MusicXML."""
        from musicdiff.repair.applier import apply_patchplan

        try:
            plan = {
                "source_file": str(temp_musicxml_single),
                "source_diff_timestamp": "2026-01-21T12:00:00Z",
                "operations": [
                    {
                        "op_id": "op-001",
                        "type": "update_duration",
                        "measure": 1,
                        "beat": 1.0,
                        "voice": 1,
                        "params": {
                            "pitch_midi": 60,
                            "duration": 2.0,
                            "old_duration": 4.0,
                        },
                    }
                ],
            }

            output = temp_musicxml_single.with_suffix(".repaired.xml")
            apply_patchplan(plan, output)

            # P3: Must parse successfully
            score = music21.converter.parse(output)
            assert score is not None

            # Verify duration changed and rest fills gap
            notes = list(score.recurse().notes)
            rests = list(score.recurse().getElementsByClass("Rest"))

            assert len(notes) >= 1
            assert notes[0].duration.quarterLength == 2.0, "Duration should be 2 beats"
            assert len(rests) >= 1, "Shortening should leave rest"

            cleanup_file(output)
        finally:
            cleanup_file(temp_musicxml_single)

    @pytest.mark.skipif(not HAS_REPAIR_MODULE, reason="Repair module not implemented yet")
    def test_multiple_operations_produce_valid_xml(
        self, temp_musicxml_two_measures: Path
    ) -> None:
        """Multiple operations in one plan produce parsable MusicXML."""
        from musicdiff.repair.applier import apply_patchplan

        try:
            plan = {
                "source_file": str(temp_musicxml_two_measures),
                "source_diff_timestamp": "2026-01-21T12:00:00Z",
                "operations": [
                    {
                        "op_id": "op-001",
                        "type": "update_pitch",
                        "measure": 1,
                        "beat": 1.0,
                        "voice": 1,
                        "params": {"pitch_midi": 62, "duration": 4.0, "old_pitch_midi": 60},
                    },
                    {
                        "op_id": "op-002",
                        "type": "update_duration",
                        "measure": 2,
                        "beat": 1.0,
                        "voice": 1,
                        "params": {"pitch_midi": 62, "duration": 2.0, "old_duration": 4.0},
                    },
                ],
            }

            output = temp_musicxml_two_measures.with_suffix(".repaired.xml")
            apply_patchplan(plan, output)

            # P3: Must parse successfully
            score = music21.converter.parse(output)
            assert score is not None

            cleanup_file(output)
        finally:
            cleanup_file(temp_musicxml_two_measures)


@pytest.mark.skipif(not HAS_REPAIR_MODULE, reason="Repair module not implemented yet")
class TestDiffReductionGateP4:
    """Gate P4: Diff count must decrease after repair."""

    def test_single_repair_reduces_diff_count(self) -> None:
        """Repairing a single diff should reduce diff count by 1.

        Setup:
        1. Create MusicXML with known content
        2. Create MIDI that differs in one way
        3. Generate diff → should have 1 error
        4. Generate and apply PatchPlan
        5. Generate new diff → should have 0 errors
        """
        # This is an integration test that requires the full pipeline
        pytest.skip("Requires full repair module and MIDI sample")

    def test_multiple_repairs_reduce_diff_count(self) -> None:
        """Repairing multiple diffs should reduce total count.

        Property: len(diff(repair(xml), midi)) < len(diff(xml, midi))
        """
        pytest.skip("Requires full repair module and MIDI sample")

    def test_diff_count_never_increases(self) -> None:
        """Applying repairs must never increase the diff count.

        This is a safety invariant - repairs should not introduce new problems.
        """
        pytest.skip("Requires full repair module and MIDI sample")


@pytest.mark.skipif(not HAS_REPAIR_MODULE, reason="Repair module not implemented yet")
class TestForbiddenOperations:
    """Tests that forbidden operations are rejected."""

    def test_reject_measure_deletion(self, temp_musicxml_two_measures: Path) -> None:
        """Measure deletion must be rejected.

        Rule: Never delete a measure.
        """
        from musicdiff.repair.applier import apply_patchplan

        try:
            # There's no "delete_measure" operation type - but verify
            # that the schema doesn't allow it
            import json
            schema_path = Path(__file__).parent.parent / "contracts" / "patchplan.schema.json"
            with open(schema_path) as f:
                schema = json.load(f)

            allowed_ops = schema["definitions"]["PatchOperation"]["properties"]["type"]["enum"]
            assert "delete_measure" not in allowed_ops

            cleanup_file(temp_musicxml_two_measures)
        finally:
            cleanup_file(temp_musicxml_two_measures)

    def test_reject_time_signature_change(self, temp_musicxml_single: Path) -> None:
        """Time signature modification must be rejected.

        Rule: Never modify time signature.
        """
        import json
        schema_path = Path(__file__).parent.parent / "contracts" / "patchplan.schema.json"
        with open(schema_path) as f:
            schema = json.load(f)

        allowed_ops = schema["definitions"]["PatchOperation"]["properties"]["type"]["enum"]
        assert "update_time_signature" not in allowed_ops
        assert "change_time_signature" not in allowed_ops

        cleanup_file(temp_musicxml_single)

    def test_reject_measure_reordering(self, temp_musicxml_two_measures: Path) -> None:
        """Measure reordering must be rejected.

        Rule: Never reorder measures.
        """
        import json
        schema_path = Path(__file__).parent.parent / "contracts" / "patchplan.schema.json"
        with open(schema_path) as f:
            schema = json.load(f)

        allowed_ops = schema["definitions"]["PatchOperation"]["properties"]["type"]["enum"]
        assert "reorder_measures" not in allowed_ops
        assert "swap_measures" not in allowed_ops

        cleanup_file(temp_musicxml_two_measures)


@pytest.mark.skipif(not HAS_REPAIR_MODULE, reason="Repair module not implemented yet")
class TestSafetyConstraints:
    """Tests for safety constraints in repair operations."""

    def test_delete_note_leaves_rest(self, temp_musicxml_single: Path) -> None:
        """delete_note MUST leave a rest of equivalent duration.

        Rule: Deleting a note MUST leave behind a Rest of equivalent duration.
        This prevents destructive time shifting.
        """
        from musicdiff.repair.applier import apply_patchplan

        try:
            plan = {
                "source_file": str(temp_musicxml_single),
                "source_diff_timestamp": "2026-01-21T12:00:00Z",
                "operations": [
                    {
                        "op_id": "op-001",
                        "type": "delete_note",
                        "measure": 1,
                        "beat": 1.0,
                        "voice": 1,
                        "params": {"pitch_midi": 60, "duration": 4.0},
                    }
                ],
            }

            output = temp_musicxml_single.with_suffix(".repaired.xml")
            apply_patchplan(plan, output)

            score = music21.converter.parse(output)

            # Verify rest exists with correct duration
            rests = list(score.recurse().getElementsByClass("Rest"))
            total_rest_duration = sum(r.duration.quarterLength for r in rests)

            # Original note was 4 beats (whole note), rest should be same
            assert total_rest_duration >= 4.0, "Rest must fill deleted note's duration"

            cleanup_file(output)
        finally:
            cleanup_file(temp_musicxml_single)

    def test_extend_duration_no_overwrite(self, temp_musicxml_two_measures: Path) -> None:
        """Extending duration must not overwrite subsequent notes.

        Rule: Extending duration must not overwrite subsequent notes.
        """
        from musicdiff.repair.applier import apply_patchplan

        try:
            # Try to extend m1 note to 8 beats (would overflow into m2)
            plan = {
                "source_file": str(temp_musicxml_two_measures),
                "source_diff_timestamp": "2026-01-21T12:00:00Z",
                "operations": [
                    {
                        "op_id": "op-001",
                        "type": "update_duration",
                        "measure": 1,
                        "beat": 1.0,
                        "voice": 1,
                        "params": {
                            "pitch_midi": 60,
                            "duration": 8.0,  # Would overflow
                            "old_duration": 4.0,
                        },
                    }
                ],
            }

            output = temp_musicxml_two_measures.with_suffix(".repaired.xml")

            # This should either:
            # a) Reject the operation (with error/warning)
            # b) Clamp duration to measure boundary
            # c) Handle gracefully without destroying m2
            apply_patchplan(plan, output)

            score = music21.converter.parse(output)
            notes = list(score.recurse().notes)

            # m2 note should still exist
            d4_notes = [n for n in notes if n.pitch.midi == 62]  # D4
            assert len(d4_notes) >= 1, "Extension must not destroy subsequent notes"

            cleanup_file(output)
        finally:
            cleanup_file(temp_musicxml_two_measures)

    def test_shorten_duration_fills_gap(self, temp_musicxml_single: Path) -> None:
        """Shortening duration must fill the gap with a rest.

        Rule: Shortening duration must fill the gap with a Rest.
        """
        from musicdiff.repair.applier import apply_patchplan

        try:
            plan = {
                "source_file": str(temp_musicxml_single),
                "source_diff_timestamp": "2026-01-21T12:00:00Z",
                "operations": [
                    {
                        "op_id": "op-001",
                        "type": "update_duration",
                        "measure": 1,
                        "beat": 1.0,
                        "voice": 1,
                        "params": {
                            "pitch_midi": 60,
                            "duration": 2.0,  # Shorten from 4 to 2
                            "old_duration": 4.0,
                        },
                    }
                ],
            }

            output = temp_musicxml_single.with_suffix(".repaired.xml")
            apply_patchplan(plan, output)

            score = music21.converter.parse(output)

            # Check measure duration still adds up
            notes = list(score.recurse().notes)
            rests = list(score.recurse().getElementsByClass("Rest"))

            note_duration = sum(n.duration.quarterLength for n in notes)
            rest_duration = sum(r.duration.quarterLength for r in rests)

            # Total should still be 4 beats (one measure in 4/4)
            assert note_duration + rest_duration >= 4.0, "Gap must be filled with rest"

            cleanup_file(output)
        finally:
            cleanup_file(temp_musicxml_single)


@pytest.mark.skipif(not HAS_REPAIR_MODULE, reason="Repair module not implemented yet")
class TestBoundsChecking:
    """Tests for bounds checking in patch application."""

    def test_reject_out_of_bounds_measure(self, temp_musicxml_single: Path) -> None:
        """Operations targeting non-existent measures should be rejected.

        Rule: Operations must be within measure bounds (1 to TotalMeasures).
        """
        from musicdiff.repair.applier import apply_patchplan

        try:
            plan = {
                "source_file": str(temp_musicxml_single),
                "source_diff_timestamp": "2026-01-21T12:00:00Z",
                "operations": [
                    {
                        "op_id": "op-001",
                        "type": "insert_note",
                        "measure": 99,  # Doesn't exist
                        "beat": 1.0,
                        "voice": 1,
                        "params": {"pitch_midi": 60, "duration": 1.0},
                    }
                ],
            }

            output = temp_musicxml_single.with_suffix(".repaired.xml")

            # Should either skip the operation or raise an error
            # Implementation decides, but must not crash silently
            with pytest.raises(Exception):  # Could be ValueError, IndexError, etc.
                apply_patchplan(plan, output)

            cleanup_file(output)
        finally:
            cleanup_file(temp_musicxml_single)

    def test_reject_negative_measure(self, temp_musicxml_single: Path) -> None:
        """Negative measure numbers (except 0 for pickup) should be rejected."""
        from musicdiff.repair.applier import apply_patchplan

        try:
            plan = {
                "source_file": str(temp_musicxml_single),
                "source_diff_timestamp": "2026-01-21T12:00:00Z",
                "operations": [
                    {
                        "op_id": "op-001",
                        "type": "insert_note",
                        "measure": -1,  # Invalid
                        "beat": 1.0,
                        "voice": 1,
                        "params": {"pitch_midi": 60, "duration": 1.0},
                    }
                ],
            }

            output = temp_musicxml_single.with_suffix(".repaired.xml")

            with pytest.raises(Exception):
                apply_patchplan(plan, output)

            cleanup_file(output)
        finally:
            cleanup_file(temp_musicxml_single)
