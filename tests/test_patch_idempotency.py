"""Tests for PatchPlan idempotency (P2).

These tests verify that:
1. Running the repair twice produces no additional changes
2. The PatchPlan generated from a repaired file should be empty or noop-only
3. Applying the same patch twice produces identical output

GATE P2: Re-running repair on repaired output must yield no changes.

These tests serve as acceptance criteria for the repair system implementation.
The actual implementation is owned by Codex (musicdiff.repair.planner, musicdiff.repair.applier).
"""

import tempfile
from pathlib import Path

import pytest

# These imports will work once Codex implements the repair module
# For now, tests will skip if module not available
try:
    from musicdiff.repair.planner import generate_patchplan  # noqa: F401
    from musicdiff.repair.applier import apply_patchplan  # noqa: F401
    HAS_REPAIR_MODULE = True
except ImportError:
    HAS_REPAIR_MODULE = False


# Minimal MusicXML for testing
MINIMAL_MUSICXML = """<?xml version="1.0" encoding="UTF-8"?>
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


@pytest.fixture
def temp_musicxml() -> Path:
    """Create a temporary MusicXML file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
        f.write(MINIMAL_MUSICXML)
        f.flush()
        return Path(f.name)


def cleanup_file(path: Path) -> None:
    """Clean up temporary file."""
    if path.exists():
        path.unlink()


@pytest.mark.skipif(not HAS_REPAIR_MODULE, reason="Repair module not implemented yet")
class TestIdempotencyGateP2:
    """Gate P2: Idempotency tests for repair system."""

    def test_empty_patchplan_is_idempotent(self, temp_musicxml: Path) -> None:
        """Applying an empty PatchPlan produces no changes.

        Property: apply(xml, empty_plan) == xml
        """
        from musicdiff.repair.applier import apply_patchplan

        try:
            plan = {
                "source_file": str(temp_musicxml),
                "source_diff_timestamp": "2026-01-21T12:00:00Z",
                "operations": [],
            }

            # Read original content
            original = temp_musicxml.read_text()

            # Apply empty plan
            output_path = temp_musicxml.with_suffix(".repaired.xml")
            apply_patchplan(plan, output_path)

            # Verify content unchanged (structurally)
            repaired = output_path.read_text()

            # Parse both and compare (content may have whitespace differences)
            import music21
            original_score = music21.converter.parse(temp_musicxml)
            repaired_score = music21.converter.parse(output_path)

            # Same number of notes
            original_notes = list(original_score.recurse().notes)
            repaired_notes = list(repaired_score.recurse().notes)
            assert len(original_notes) == len(repaired_notes)

            cleanup_file(output_path)
        finally:
            cleanup_file(temp_musicxml)

    def test_noop_plan_is_idempotent(self, temp_musicxml: Path) -> None:
        """Applying a noop-only PatchPlan produces no changes.

        Property: apply(xml, noop_plan) == xml
        """
        from musicdiff.repair.applier import apply_patchplan

        try:
            plan = {
                "source_file": str(temp_musicxml),
                "source_diff_timestamp": "2026-01-21T12:00:00Z",
                "operations": [
                    {
                        "op_id": "op-001",
                        "type": "noop",
                        "measure": 1,
                        "beat": 1.0,
                        "voice": 1,
                        "params": {},
                    }
                ],
            }

            output_path = temp_musicxml.with_suffix(".repaired.xml")
            apply_patchplan(plan, output_path)

            # Parse and compare
            import music21
            original_score = music21.converter.parse(temp_musicxml)
            repaired_score = music21.converter.parse(output_path)

            original_notes = list(original_score.recurse().notes)
            repaired_notes = list(repaired_score.recurse().notes)
            assert len(original_notes) == len(repaired_notes)

            cleanup_file(output_path)
        finally:
            cleanup_file(temp_musicxml)

    def test_repair_then_plan_yields_empty(self, temp_musicxml: Path) -> None:
        """After repair, generating a new plan should yield no operations.

        This is the core idempotency test:
        1. Generate diff between XML and MIDI
        2. Generate PatchPlan from diff
        3. Apply PatchPlan to XML
        4. Generate new diff between repaired XML and same MIDI
        5. New PatchPlan should be empty (or all noops)

        Property: plan(diff(apply(xml, plan(diff(xml, midi))), midi)) == empty
        """
        # This test requires full integration with musicdiff
        # Skip until repair module is implemented
        pytest.skip("Requires full repair module implementation")

    def test_double_apply_is_same_as_single(self, temp_musicxml: Path) -> None:
        """Applying a patch twice produces same result as applying once.

        Property: apply(apply(xml, plan), plan) == apply(xml, plan)
        """
        from musicdiff.repair.applier import apply_patchplan

        try:
            # Plan that inserts a note
            plan = {
                "source_file": str(temp_musicxml),
                "source_diff_timestamp": "2026-01-21T12:00:00Z",
                "operations": [
                    {
                        "op_id": "op-001",
                        "type": "insert_note",
                        "measure": 1,
                        "beat": 2.0,
                        "voice": 1,
                        "params": {"pitch_midi": 62, "duration": 1.0},
                    }
                ],
            }

            # First application
            output1 = temp_musicxml.with_suffix(".repaired1.xml")
            apply_patchplan(plan, output1)

            # Second application (on already repaired file)
            plan["source_file"] = str(output1)
            output2 = temp_musicxml.with_suffix(".repaired2.xml")

            # This should either:
            # a) Skip the operation (note already exists) - preferred
            # b) Create duplicate (not idempotent - test fails)
            apply_patchplan(plan, output2)

            # Parse and compare
            import music21
            score1 = music21.converter.parse(output1)
            score2 = music21.converter.parse(output2)

            notes1 = list(score1.recurse().notes)
            notes2 = list(score2.recurse().notes)

            # Same number of notes means idempotent
            assert len(notes1) == len(notes2), (
                f"Double apply created {len(notes2)} notes vs single apply {len(notes1)}"
            )

            cleanup_file(output1)
            cleanup_file(output2)
        finally:
            cleanup_file(temp_musicxml)


@pytest.mark.skipif(not HAS_REPAIR_MODULE, reason="Repair module not implemented yet")
class TestIdempotencyByOperationType:
    """Test idempotency for each operation type."""

    def test_insert_note_idempotent(self, temp_musicxml: Path) -> None:
        """insert_note should not duplicate if note already exists."""
        from musicdiff.repair.applier import apply_patchplan

        try:
            plan = {
                "source_file": str(temp_musicxml),
                "source_diff_timestamp": "2026-01-21T12:00:00Z",
                "operations": [
                    {
                        "op_id": "op-001",
                        "type": "insert_note",
                        "measure": 1,
                        "beat": 1.0,
                        "voice": 1,
                        "params": {"pitch_midi": 60, "duration": 4.0},  # C4 whole note
                    }
                ],
            }

            output = temp_musicxml.with_suffix(".repaired.xml")
            apply_patchplan(plan, output)

            import music21
            score = music21.converter.parse(output)
            notes = [n for n in score.recurse().notes if n.pitch.midi == 60]

            # Should still have just one C4 (original or replaced, not duplicated)
            assert len(notes) == 1, "insert_note should not duplicate existing note"

            cleanup_file(output)
        finally:
            cleanup_file(temp_musicxml)

    def test_delete_note_idempotent(self, temp_musicxml: Path) -> None:
        """delete_note on already-deleted note should be safe (no error)."""
        from musicdiff.repair.applier import apply_patchplan

        try:
            # First delete
            plan = {
                "source_file": str(temp_musicxml),
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

            output1 = temp_musicxml.with_suffix(".repaired1.xml")
            apply_patchplan(plan, output1)

            # Second delete (on already deleted)
            plan["source_file"] = str(output1)
            output2 = temp_musicxml.with_suffix(".repaired2.xml")

            # Should not raise, even though note doesn't exist
            apply_patchplan(plan, output2)

            # Verify both outputs are the same
            import music21
            score1 = music21.converter.parse(output1)
            score2 = music21.converter.parse(output2)

            notes1 = list(score1.recurse().notes)
            notes2 = list(score2.recurse().notes)

            assert len(notes1) == len(notes2)

            cleanup_file(output1)
            cleanup_file(output2)
        finally:
            cleanup_file(temp_musicxml)

    def test_update_pitch_idempotent(self, temp_musicxml: Path) -> None:
        """update_pitch applied twice should not change anything second time."""
        from musicdiff.repair.applier import apply_patchplan

        try:
            plan = {
                "source_file": str(temp_musicxml),
                "source_diff_timestamp": "2026-01-21T12:00:00Z",
                "operations": [
                    {
                        "op_id": "op-001",
                        "type": "update_pitch",
                        "measure": 1,
                        "beat": 1.0,
                        "voice": 1,
                        "params": {
                            "pitch_midi": 62,  # Change C4 to D4
                            "duration": 4.0,
                            "old_pitch_midi": 60,
                        },
                    }
                ],
            }

            output1 = temp_musicxml.with_suffix(".repaired1.xml")
            apply_patchplan(plan, output1)

            # Second application
            plan["source_file"] = str(output1)
            output2 = temp_musicxml.with_suffix(".repaired2.xml")
            apply_patchplan(plan, output2)

            import music21
            score1 = music21.converter.parse(output1)
            score2 = music21.converter.parse(output2)

            # Get the note that was updated
            notes1 = [n for n in score1.recurse().notes]
            notes2 = [n for n in score2.recurse().notes]

            assert len(notes1) == len(notes2)
            assert notes1[0].pitch.midi == notes2[0].pitch.midi == 62

            cleanup_file(output1)
            cleanup_file(output2)
        finally:
            cleanup_file(temp_musicxml)

    def test_update_duration_idempotent(self, temp_musicxml: Path) -> None:
        """update_duration applied twice should not change anything second time."""
        from musicdiff.repair.applier import apply_patchplan

        try:
            plan = {
                "source_file": str(temp_musicxml),
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
                            "duration": 2.0,  # Change from whole to half
                            "old_duration": 4.0,
                        },
                    }
                ],
            }

            output1 = temp_musicxml.with_suffix(".repaired1.xml")
            apply_patchplan(plan, output1)

            plan["source_file"] = str(output1)
            output2 = temp_musicxml.with_suffix(".repaired2.xml")
            apply_patchplan(plan, output2)

            import music21
            score1 = music21.converter.parse(output1)
            score2 = music21.converter.parse(output2)

            notes1 = [n for n in score1.recurse().notes]
            notes2 = [n for n in score2.recurse().notes]

            assert len(notes1) == len(notes2)
            # Duration should be the same
            assert notes1[0].duration.quarterLength == notes2[0].duration.quarterLength

            cleanup_file(output1)
            cleanup_file(output2)
        finally:
            cleanup_file(temp_musicxml)


class TestIdempotencyTheorems:
    """Theoretical properties that must hold for idempotency."""

    def test_theorem_empty_plan_identity(self) -> None:
        """Theorem: apply(xml, []) == xml

        An empty PatchPlan is the identity operation.
        """
        # This is a property that must hold - documented here
        # Actual test is in TestIdempotencyGateP2.test_empty_patchplan_is_idempotent
        pass

    def test_theorem_noop_identity(self) -> None:
        """Theorem: apply(xml, [noop]) == xml

        A noop operation is also the identity operation.
        """
        # Documented property
        pass

    def test_theorem_idempotent_operations(self) -> None:
        """Theorem: apply(apply(xml, plan), plan) == apply(xml, plan)

        For a well-formed plan, applying twice equals applying once.
        This requires the applier to check for existing state before modifying.
        """
        # Documented property
        pass

    def test_theorem_repair_fixpoint(self) -> None:
        """Theorem: plan(diff(repair(xml, midi), midi)) == []

        A repaired file should produce no new diffs against the same MIDI,
        therefore no new plan should be generated.

        This is the ultimate idempotency guarantee.
        """
        # Documented property
        pass
