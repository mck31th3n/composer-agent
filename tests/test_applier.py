"""Tests for the repair applier module.

Verifies:
- All operation types work on synthetic MusicXML
- delete_note leaves a rest (never shifts content)
- P2 unit-level: operations are idempotent
- P3 unit-level: output is parseable

These tests serve as acceptance criteria for the applier implementation.
"""

import json
import tempfile
from pathlib import Path
from typing import Any

import pytest

# music21 for verification
try:
    import music21
    HAS_MUSIC21 = True
except ImportError:
    HAS_MUSIC21 = False

# Applier module (implemented by Codex)
try:
    from musicdiff.repair.applier import apply_patch_plan
    HAS_APPLIER = True
except ImportError:
    HAS_APPLIER = False


# Synthetic MusicXML templates for testing
SINGLE_NOTE_MUSICXML = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0 Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">
<score-partwise version="4.0">
  <part-list>
    <score-part id="P1"><part-name>Test</part-name></score-part>
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

TWO_NOTE_MUSICXML = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0 Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">
<score-partwise version="4.0">
  <part-list>
    <score-part id="P1"><part-name>Test</part-name></score-part>
  </part-list>
  <part id="P1">
    <measure number="1">
      <attributes>
        <divisions>1</divisions>
        <time><beats>4</beats><beat-type>4</beat-type></time>
      </attributes>
      <note>
        <pitch><step>C</step><octave>4</octave></pitch>
        <duration>2</duration>
        <type>half</type>
      </note>
      <note>
        <pitch><step>E</step><octave>4</octave></pitch>
        <duration>2</duration>
        <type>half</type>
      </note>
    </measure>
  </part>
</score-partwise>
"""

REST_AND_NOTE_MUSICXML = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0 Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">
<score-partwise version="4.0">
  <part-list>
    <score-part id="P1"><part-name>Test</part-name></score-part>
  </part-list>
  <part id="P1">
    <measure number="1">
      <attributes>
        <divisions>1</divisions>
        <time><beats>4</beats><beat-type>4</beat-type></time>
      </attributes>
      <note>
        <rest/>
        <duration>2</duration>
        <type>half</type>
      </note>
      <note>
        <pitch><step>G</step><octave>4</octave></pitch>
        <duration>2</duration>
        <type>half</type>
      </note>
    </measure>
  </part>
</score-partwise>
"""

TWO_MEASURE_MUSICXML = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0 Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">
<score-partwise version="4.0">
  <part-list>
    <score-part id="P1"><part-name>Test</part-name></score-part>
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


def create_temp_musicxml(content: str) -> Path:
    """Create a temporary MusicXML file with given content."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
        f.write(content)
        f.flush()
        return Path(f.name)


def create_temp_patchplan(plan: dict[str, Any]) -> Path:
    """Create a temporary patchplan.json file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(plan, f)
        f.flush()
        return Path(f.name)


def cleanup_files(*paths: Path) -> None:
    """Clean up temporary files."""
    for path in paths:
        if path and path.exists():
            path.unlink()


def make_plan(source_file: str, operations: list[dict[str, Any]]) -> dict[str, Any]:
    """Create a PatchPlan dict."""
    return {
        "source_file": source_file,
        "source_diff_timestamp": "2026-01-21T12:00:00Z",
        "operations": operations,
    }


def make_operation(
    op_id: str,
    op_type: str,
    measure: int,
    beat: float,
    voice: int,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Create a PatchOperation dict."""
    return {
        "op_id": op_id,
        "type": op_type,
        "measure": measure,
        "beat": beat,
        "voice": voice,
        "params": params,
    }


@pytest.mark.skipif(not HAS_APPLIER, reason="Applier module not implemented yet")
@pytest.mark.skipif(not HAS_MUSIC21, reason="music21 not installed")
class TestInsertNoteOperation:
    """Test insert_note operation on synthetic MusicXML."""

    def test_insert_note_into_rest(self) -> None:
        """insert_note should replace rest with note."""
        xml_path = create_temp_musicxml(REST_AND_NOTE_MUSICXML)
        output_path = xml_path.with_suffix(".repaired.xml")

        plan = make_plan(str(xml_path), [
            make_operation("op-001", "insert_note", 1, 1.0, 1, {"pitch_midi": 60, "duration": 2.0}),
        ])
        plan_path = create_temp_patchplan(plan)

        try:
            apply_patch_plan(xml_path, plan_path, output_path)

            # Verify output
            score = music21.converter.parse(output_path)
            notes = list(score.recurse().notes)

            # Should have 2 notes now (C4 replacing rest, G4 original)
            assert len(notes) == 2
            pitches = {n.pitch.midi for n in notes}
            assert 60 in pitches, "Inserted C4 should be present"
            assert 67 in pitches, "Original G4 should be present"

        finally:
            cleanup_files(xml_path, plan_path, output_path)

    def test_insert_note_adds_to_empty_beat(self) -> None:
        """insert_note at empty beat should add the note."""
        xml_path = create_temp_musicxml(SINGLE_NOTE_MUSICXML)
        output_path = xml_path.with_suffix(".repaired.xml")

        # Original has C4 whole note, try to insert at beat 3 in a new voice
        plan = make_plan(str(xml_path), [
            make_operation("op-001", "insert_note", 1, 3.0, 2, {"pitch_midi": 64, "duration": 1.0}),
        ])
        plan_path = create_temp_patchplan(plan)

        try:
            apply_patch_plan(xml_path, plan_path, output_path)

            # Verify output is parseable
            score = music21.converter.parse(output_path)
            assert score is not None

        finally:
            cleanup_files(xml_path, plan_path, output_path)

    def test_insert_note_idempotent(self) -> None:
        """Inserting same note twice should not duplicate it (P2)."""
        xml_path = create_temp_musicxml(REST_AND_NOTE_MUSICXML)
        output1 = xml_path.with_suffix(".repaired1.xml")
        output2 = xml_path.with_suffix(".repaired2.xml")

        plan = make_plan(str(xml_path), [
            make_operation("op-001", "insert_note", 1, 1.0, 1, {"pitch_midi": 60, "duration": 2.0}),
        ])
        plan_path = create_temp_patchplan(plan)

        try:
            # First application
            apply_patch_plan(xml_path, plan_path, output1)

            # Second application on output - need to update plan source
            plan2 = make_plan(str(output1), [
                make_operation("op-001", "insert_note", 1, 1.0, 1, {"pitch_midi": 60, "duration": 2.0}),
            ])
            plan_path2 = create_temp_patchplan(plan2)
            apply_patch_plan(output1, plan_path2, output2)

            # Both outputs should have same number of notes
            score1 = music21.converter.parse(output1)
            score2 = music21.converter.parse(output2)

            notes1 = list(score1.recurse().notes)
            notes2 = list(score2.recurse().notes)

            assert len(notes1) == len(notes2), "Insert should be idempotent"

            cleanup_files(plan_path2)
        finally:
            cleanup_files(xml_path, plan_path, output1, output2)


@pytest.mark.skipif(not HAS_APPLIER, reason="Applier module not implemented yet")
@pytest.mark.skipif(not HAS_MUSIC21, reason="music21 not installed")
class TestDeleteNoteOperation:
    """Test delete_note operation - CRITICAL: must leave rest."""

    def test_delete_note_leaves_rest(self) -> None:
        """delete_note MUST leave a rest, never shift content.

        This is the most critical safety requirement.
        """
        xml_path = create_temp_musicxml(TWO_NOTE_MUSICXML)
        output_path = xml_path.with_suffix(".repaired.xml")

        # Delete the first note (C4)
        plan = make_plan(str(xml_path), [
            make_operation("op-001", "delete_note", 1, 1.0, 1, {"old_pitch_midi": 60, "old_duration": 2.0}),
        ])
        plan_path = create_temp_patchplan(plan)

        try:
            apply_patch_plan(xml_path, plan_path, output_path)

            # Verify output
            score = music21.converter.parse(output_path)

            # E4 should still be at beat 3, not shifted to beat 1
            all_elements = list(score.recurse().notesAndRests)

            # Should have a rest at beat 1 and E4 at beat 3
            rests = [e for e in all_elements if isinstance(e, music21.note.Rest)]
            notes = [e for e in all_elements if isinstance(e, music21.note.Note)]

            assert len(rests) >= 1, "Delete must leave a rest"
            assert len(notes) == 1, "Original E4 should remain"
            assert notes[0].pitch.midi == 64, "E4 should be unchanged"

        finally:
            cleanup_files(xml_path, plan_path, output_path)

    def test_delete_note_measure_duration_unchanged(self) -> None:
        """delete_note must not change total measure duration."""
        xml_path = create_temp_musicxml(TWO_NOTE_MUSICXML)
        output_path = xml_path.with_suffix(".repaired.xml")

        plan = make_plan(str(xml_path), [
            make_operation("op-001", "delete_note", 1, 1.0, 1, {"old_pitch_midi": 60, "old_duration": 2.0}),
        ])
        plan_path = create_temp_patchplan(plan)

        try:
            # Get original measure duration
            original_score = music21.converter.parse(xml_path)
            original_measure = list(original_score.recurse().getElementsByClass(music21.stream.Measure))[0]
            original_duration = original_measure.duration.quarterLength

            apply_patch_plan(xml_path, plan_path, output_path)

            # Get new measure duration
            new_score = music21.converter.parse(output_path)
            new_measure = list(new_score.recurse().getElementsByClass(music21.stream.Measure))[0]
            new_duration = new_measure.duration.quarterLength

            assert original_duration == new_duration, (
                f"Measure duration changed from {original_duration} to {new_duration}"
            )

        finally:
            cleanup_files(xml_path, plan_path, output_path)

    def test_delete_nonexistent_note_is_safe(self) -> None:
        """delete_note on non-existent note should not error."""
        xml_path = create_temp_musicxml(SINGLE_NOTE_MUSICXML)
        output_path = xml_path.with_suffix(".repaired.xml")

        # Try to delete a note that doesn't exist
        plan = make_plan(str(xml_path), [
            make_operation("op-001", "delete_note", 1, 1.0, 1, {"old_pitch_midi": 72, "old_duration": 1.0}),
        ])
        plan_path = create_temp_patchplan(plan)

        try:
            # Should not raise
            apply_patch_plan(xml_path, plan_path, output_path)

            # Original should be unchanged
            score = music21.converter.parse(output_path)
            notes = list(score.recurse().notes)
            assert len(notes) == 1
            assert notes[0].pitch.midi == 60  # Original C4

        finally:
            cleanup_files(xml_path, plan_path, output_path)

    def test_delete_note_idempotent(self) -> None:
        """Deleting same note twice should be safe (P2)."""
        xml_path = create_temp_musicxml(TWO_NOTE_MUSICXML)
        output1 = xml_path.with_suffix(".repaired1.xml")
        output2 = xml_path.with_suffix(".repaired2.xml")

        plan = make_plan(str(xml_path), [
            make_operation("op-001", "delete_note", 1, 1.0, 1, {"old_pitch_midi": 60, "old_duration": 2.0}),
        ])
        plan_path = create_temp_patchplan(plan)

        try:
            # First deletion
            apply_patch_plan(xml_path, plan_path, output1)

            # Second deletion (note already gone)
            plan2 = make_plan(str(output1), [
                make_operation("op-001", "delete_note", 1, 1.0, 1, {"old_pitch_midi": 60, "old_duration": 2.0}),
            ])
            plan_path2 = create_temp_patchplan(plan2)
            apply_patch_plan(output1, plan_path2, output2)

            # Both outputs should be equivalent
            score1 = music21.converter.parse(output1)
            score2 = music21.converter.parse(output2)

            notes1 = list(score1.recurse().notes)
            notes2 = list(score2.recurse().notes)

            assert len(notes1) == len(notes2), "Delete should be idempotent"

            cleanup_files(plan_path2)
        finally:
            cleanup_files(xml_path, plan_path, output1, output2)


@pytest.mark.skipif(not HAS_APPLIER, reason="Applier module not implemented yet")
@pytest.mark.skipif(not HAS_MUSIC21, reason="music21 not installed")
class TestUpdateDurationOperation:
    """Test update_duration operation."""

    def test_update_duration_shortens_note(self) -> None:
        """update_duration shortening should leave rest in gap."""
        xml_path = create_temp_musicxml(SINGLE_NOTE_MUSICXML)
        output_path = xml_path.with_suffix(".repaired.xml")

        # Shorten C4 from whole to half
        plan = make_plan(str(xml_path), [
            make_operation("op-001", "update_duration", 1, 1.0, 1, {"duration": 2.0, "old_duration": 4.0}),
        ])
        plan_path = create_temp_patchplan(plan)

        try:
            apply_patch_plan(xml_path, plan_path, output_path)

            # Verify output
            score = music21.converter.parse(output_path)
            all_elements = list(score.recurse().notesAndRests)

            notes = [e for e in all_elements if isinstance(e, music21.note.Note)]
            rests = [e for e in all_elements if isinstance(e, music21.note.Rest)]

            assert len(notes) == 1
            assert notes[0].duration.quarterLength == 2.0
            # Should have a rest filling the gap
            assert len(rests) >= 1, "Shortening should leave a rest"

        finally:
            cleanup_files(xml_path, plan_path, output_path)

    def test_update_duration_idempotent(self) -> None:
        """Updating duration twice should not change further (P2)."""
        xml_path = create_temp_musicxml(SINGLE_NOTE_MUSICXML)
        output1 = xml_path.with_suffix(".repaired1.xml")
        output2 = xml_path.with_suffix(".repaired2.xml")

        plan = make_plan(str(xml_path), [
            make_operation("op-001", "update_duration", 1, 1.0, 1, {"duration": 2.0, "old_duration": 4.0}),
        ])
        plan_path = create_temp_patchplan(plan)

        try:
            # First update
            apply_patch_plan(xml_path, plan_path, output1)

            # Second update
            plan2 = make_plan(str(output1), [
                make_operation("op-001", "update_duration", 1, 1.0, 1, {"duration": 2.0, "old_duration": 4.0}),
            ])
            plan_path2 = create_temp_patchplan(plan2)
            apply_patch_plan(output1, plan_path2, output2)

            # Verify same result
            score1 = music21.converter.parse(output1)
            score2 = music21.converter.parse(output2)

            notes1 = [n for n in score1.recurse().notes if n.pitch.midi == 60]
            notes2 = [n for n in score2.recurse().notes if n.pitch.midi == 60]

            assert notes1[0].duration.quarterLength == notes2[0].duration.quarterLength

            cleanup_files(plan_path2)
        finally:
            cleanup_files(xml_path, plan_path, output1, output2)


@pytest.mark.skipif(not HAS_APPLIER, reason="Applier module not implemented yet")
@pytest.mark.skipif(not HAS_MUSIC21, reason="music21 not installed")
class TestUpdatePitchOperation:
    """Test update_pitch operation."""

    def test_update_pitch_changes_note(self) -> None:
        """update_pitch should change note pitch."""
        xml_path = create_temp_musicxml(SINGLE_NOTE_MUSICXML)
        output_path = xml_path.with_suffix(".repaired.xml")

        # Change C4 to D4
        plan = make_plan(str(xml_path), [
            make_operation("op-001", "update_pitch", 1, 1.0, 1, {"pitch_midi": 62, "duration": 4.0, "old_pitch_midi": 60}),
        ])
        plan_path = create_temp_patchplan(plan)

        try:
            apply_patch_plan(xml_path, plan_path, output_path)

            # Verify output
            score = music21.converter.parse(output_path)
            notes = list(score.recurse().notes)

            assert len(notes) == 1
            assert notes[0].pitch.midi == 62, "Pitch should be changed to D4"

        finally:
            cleanup_files(xml_path, plan_path, output_path)

    def test_update_pitch_preserves_duration(self) -> None:
        """update_pitch should not change note duration."""
        xml_path = create_temp_musicxml(SINGLE_NOTE_MUSICXML)
        output_path = xml_path.with_suffix(".repaired.xml")

        plan = make_plan(str(xml_path), [
            make_operation("op-001", "update_pitch", 1, 1.0, 1, {"pitch_midi": 62, "duration": 4.0, "old_pitch_midi": 60}),
        ])
        plan_path = create_temp_patchplan(plan)

        try:
            apply_patch_plan(xml_path, plan_path, output_path)

            # Verify duration unchanged
            score = music21.converter.parse(output_path)
            notes = list(score.recurse().notes)

            assert notes[0].duration.quarterLength == 4.0

        finally:
            cleanup_files(xml_path, plan_path, output_path)

    def test_update_pitch_idempotent(self) -> None:
        """Updating pitch twice should not change further (P2)."""
        xml_path = create_temp_musicxml(SINGLE_NOTE_MUSICXML)
        output1 = xml_path.with_suffix(".repaired1.xml")
        output2 = xml_path.with_suffix(".repaired2.xml")

        plan = make_plan(str(xml_path), [
            make_operation("op-001", "update_pitch", 1, 1.0, 1, {"pitch_midi": 62, "duration": 4.0, "old_pitch_midi": 60}),
        ])
        plan_path = create_temp_patchplan(plan)

        try:
            # First update
            apply_patch_plan(xml_path, plan_path, output1)

            # Second update
            plan2 = make_plan(str(output1), [
                make_operation("op-001", "update_pitch", 1, 1.0, 1, {"pitch_midi": 62, "duration": 4.0, "old_pitch_midi": 60}),
            ])
            plan_path2 = create_temp_patchplan(plan2)
            apply_patch_plan(output1, plan_path2, output2)

            # Verify same result
            score1 = music21.converter.parse(output1)
            score2 = music21.converter.parse(output2)

            notes1 = list(score1.recurse().notes)
            notes2 = list(score2.recurse().notes)

            assert notes1[0].pitch.midi == notes2[0].pitch.midi == 62

            cleanup_files(plan_path2)
        finally:
            cleanup_files(xml_path, plan_path, output1, output2)


@pytest.mark.skipif(not HAS_APPLIER, reason="Applier module not implemented yet")
@pytest.mark.skipif(not HAS_MUSIC21, reason="music21 not installed")
class TestNoopOperation:
    """Test noop operation."""

    def test_noop_changes_nothing(self) -> None:
        """noop should not modify the file."""
        xml_path = create_temp_musicxml(SINGLE_NOTE_MUSICXML)
        output_path = xml_path.with_suffix(".repaired.xml")

        plan = make_plan(str(xml_path), [
            make_operation("op-001", "noop", 1, 1.0, 1, {}),
        ])
        plan_path = create_temp_patchplan(plan)

        try:
            apply_patch_plan(xml_path, plan_path, output_path)

            # Verify output identical to input (structurally)
            original_score = music21.converter.parse(xml_path)
            repaired_score = music21.converter.parse(output_path)

            original_notes = list(original_score.recurse().notes)
            repaired_notes = list(repaired_score.recurse().notes)

            assert len(original_notes) == len(repaired_notes)
            for orig, rep in zip(original_notes, repaired_notes):
                assert orig.pitch.midi == rep.pitch.midi
                assert orig.duration.quarterLength == rep.duration.quarterLength

        finally:
            cleanup_files(xml_path, plan_path, output_path)


@pytest.mark.skipif(not HAS_APPLIER, reason="Applier module not implemented yet")
@pytest.mark.skipif(not HAS_MUSIC21, reason="music21 not installed")
class TestParseSurvival:
    """Test P3: Output MusicXML must be parseable."""

    def test_output_is_parseable(self) -> None:
        """Applied patch must produce parseable MusicXML (P3)."""
        xml_path = create_temp_musicxml(TWO_NOTE_MUSICXML)
        output_path = xml_path.with_suffix(".repaired.xml")

        plan = make_plan(str(xml_path), [
            make_operation("op-001", "insert_note", 1, 4.0, 2, {"pitch_midi": 67, "duration": 1.0}),
            make_operation("op-002", "delete_note", 1, 1.0, 1, {"old_pitch_midi": 60, "old_duration": 2.0}),
        ])
        plan_path = create_temp_patchplan(plan)

        try:
            apply_patch_plan(xml_path, plan_path, output_path)

            # Must be parseable
            score = music21.converter.parse(output_path)
            assert score is not None

        finally:
            cleanup_files(xml_path, plan_path, output_path)

    def test_complex_operations_produce_valid_xml(self) -> None:
        """Multiple complex operations must produce valid XML."""
        xml_path = create_temp_musicxml(TWO_MEASURE_MUSICXML)
        output_path = xml_path.with_suffix(".repaired.xml")

        plan = make_plan(str(xml_path), [
            make_operation("op-001", "update_pitch", 1, 1.0, 1, {"pitch_midi": 62, "duration": 4.0, "old_pitch_midi": 60}),
            make_operation("op-002", "update_duration", 2, 1.0, 1, {"duration": 2.0, "old_duration": 4.0}),
        ])
        plan_path = create_temp_patchplan(plan)

        try:
            apply_patch_plan(xml_path, plan_path, output_path)

            # Must be parseable
            score = music21.converter.parse(output_path)
            assert score is not None

            # Verify structure
            measures = list(score.recurse().getElementsByClass(music21.stream.Measure))
            assert len(measures) >= 2

        finally:
            cleanup_files(xml_path, plan_path, output_path)


class TestApplierTheorems:
    """Theoretical properties that must hold for the applier."""

    def test_theorem_delete_leaves_rest(self) -> None:
        """Theorem: delete_note(xml, note) leaves rest at note position

        This is the most critical safety property. Deleting a note
        must NEVER shift subsequent content.
        """
        # Documented property - actual test in TestDeleteNoteOperation
        pass

    def test_theorem_duration_conservation(self) -> None:
        """Theorem: measure_duration(apply(xml, plan)) == measure_duration(xml)

        Operations must not change total measure duration.
        """
        # Documented property
        pass

    def test_theorem_idempotent_operations(self) -> None:
        """Theorem: apply(apply(xml, op), op) == apply(xml, op)

        Each operation type must be idempotent.
        """
        # Documented property - actual tests in each operation class
        pass

    def test_theorem_parse_survival(self) -> None:
        """Theorem: parse(apply(xml, plan)) succeeds (P3)

        Applied patches must always produce parseable output.
        """
        # Documented property - actual test in TestParseSurvival
        pass
