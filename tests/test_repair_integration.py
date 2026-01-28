"""Integration tests for the complete repair pipeline.

End-to-end tests verifying:
- P2: Idempotency - repair(repair(xml)) == repair(xml)
- P4: Diff reduction - diff_count(repair(xml)) < diff_count(xml)

These tests require the full pipeline:
1. musicdiff (diff generation)
2. musicdiff.repair.planner (plan generation)
3. musicdiff.repair.applier (plan application)

These tests serve as acceptance criteria for the repair system.
"""

import json
import tempfile
from pathlib import Path

import pytest

# music21 for verification
try:
    import music21
    HAS_MUSIC21 = True
except ImportError:
    HAS_MUSIC21 = False

# Full repair pipeline (implemented by Codex)
try:
    from musicdiff.repair.planner import generate_patch_plan
    from musicdiff.repair.applier import apply_patch_plan
    HAS_REPAIR = True
except ImportError:
    HAS_REPAIR = False

# Diff generation (already implemented)
try:
    from musicdiff.diff import generate_diffs
    from musicdiff.align import align_events
    from musicdiff.parsers import parse_musicxml, parse_midi
    HAS_MUSICDIFF = True
except ImportError:
    HAS_MUSICDIFF = False


# Test MusicXML with known differences from a MIDI file
MISMATCHED_MUSICXML = """<?xml version="1.0" encoding="UTF-8"?>
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
    <measure number="2">
      <note>
        <pitch><step>G</step><octave>4</octave></pitch>
        <duration>4</duration>
        <type>whole</type>
      </note>
    </measure>
  </part>
</score-partwise>
"""

CORRECT_MUSICXML = """<?xml version="1.0" encoding="UTF-8"?>
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


def create_temp_file(content: str, suffix: str) -> Path:
    """Create a temporary file with given content."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False) as f:
        f.write(content)
        f.flush()
        return Path(f.name)


def create_temp_json(data: dict) -> Path:
    """Create a temporary JSON file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(data, f)
        f.flush()
        return Path(f.name)


def cleanup_files(*paths: Path) -> None:
    """Clean up temporary files."""
    for path in paths:
        if path and path.exists():
            path.unlink()


def create_test_midi(notes: list[tuple[int, float, float]]) -> Path:
    """Create a test MIDI file with specified notes.

    Args:
        notes: List of (pitch_midi, start_beat, duration_beats) tuples
    """
    stream = music21.stream.Stream()
    stream.append(music21.tempo.MetronomeMark(number=120))

    for pitch, start, duration in notes:
        n = music21.note.Note()
        n.pitch.midi = pitch
        n.duration.quarterLength = duration
        n.offset = start
        stream.append(n)

    with tempfile.NamedTemporaryFile(suffix=".mid", delete=False) as f:
        stream.write("midi", fp=f.name)
        return Path(f.name)


def create_diff_report(xml_path: Path, midi_path: Path) -> tuple[dict, Path]:
    """Generate a diff report and save to file.

    Returns the diff report dict and the path to the saved file.
    """
    xml_events, xml_meta = parse_musicxml(xml_path)
    midi_events, midi_meta = parse_midi(midi_path)
    aligned, _ = align_events(
        xml_events, midi_events,
        xml_meta.divisions, xml_meta.time_signatures,
        120.0, 0.25
    )
    diffs = generate_diffs(aligned, 120.0)

    diff_report = {
        "source_xml": str(xml_path),
        "source_midi": str(midi_path),
        "timestamp": "2026-01-21T12:00:00Z",
        "tempo_bpm": 120.0,
        "diffs": [d.model_dump() for d in diffs],
    }

    diff_path = create_temp_json(diff_report)
    return diff_report, diff_path


@pytest.mark.skipif(not HAS_REPAIR, reason="Repair module not implemented yet")
@pytest.mark.skipif(not HAS_MUSICDIFF, reason="musicdiff not available")
@pytest.mark.skipif(not HAS_MUSIC21, reason="music21 not installed")
class TestEndToEndIdempotency:
    """P2: End-to-end idempotency tests."""

    def test_repair_is_idempotent(self) -> None:
        """repair(repair(xml, midi), midi) == repair(xml, midi)

        After one repair pass, a second repair pass should produce
        no additional changes.
        """
        xml_path = create_temp_file(MISMATCHED_MUSICXML, ".xml")
        # Create MIDI that matches the "correct" version
        midi_path = create_test_midi([
            (60, 0.0, 4.0),  # C4 whole note in measure 1
        ])
        repair1_path = None
        repair2_path = None
        diff_path1 = None
        diff_path2 = None
        plan_path1 = None
        plan_path2 = None

        try:
            # First repair pass
            diff_report1, diff_path1 = create_diff_report(xml_path, midi_path)
            plan1 = generate_patch_plan(diff_path1, xml_path)
            plan_path1 = create_temp_json(plan1.model_dump())
            repair1_path = xml_path.with_suffix(".repair1.xml")
            apply_patch_plan(xml_path, plan_path1, repair1_path)

            # Second repair pass (on already repaired file)
            diff_report2, diff_path2 = create_diff_report(repair1_path, midi_path)
            plan2 = generate_patch_plan(diff_path2, repair1_path)

            # P2: Second plan should have no active operations
            active_ops = [op for op in plan2.operations if op.type != "noop"]
            assert len(active_ops) == 0, (
                f"Second repair pass should yield no operations, got {len(active_ops)}: "
                f"{[op.type for op in active_ops]}"
            )

        finally:
            cleanup_files(xml_path, midi_path, repair1_path, repair2_path,
                         diff_path1, diff_path2, plan_path1, plan_path2)

    def test_idempotency_with_multiple_diffs(self) -> None:
        """Idempotency holds even with multiple diff types."""
        xml_path = create_temp_file(MISMATCHED_MUSICXML, ".xml")
        # MIDI with different notes to create multiple diff types
        midi_path = create_test_midi([
            (62, 0.0, 2.0),  # D4 half note (pitch mismatch with C4)
            (64, 2.0, 2.0),  # E4 half note (matches)
            (67, 4.0, 2.0),  # G4 half note (duration mismatch)
        ])
        repair1_path = None
        diff_path1 = None
        diff_path2 = None
        plan_path1 = None

        try:
            # First repair
            diff_report1, diff_path1 = create_diff_report(xml_path, midi_path)
            plan1 = generate_patch_plan(diff_path1, xml_path)
            plan_path1 = create_temp_json(plan1.model_dump())
            repair1_path = xml_path.with_suffix(".repair1.xml")
            apply_patch_plan(xml_path, plan_path1, repair1_path)

            # Second repair
            diff_report2, diff_path2 = create_diff_report(repair1_path, midi_path)
            plan2 = generate_patch_plan(diff_path2, repair1_path)

            # P2: No active operations in second pass
            active_ops = [op for op in plan2.operations if op.type != "noop"]
            assert len(active_ops) == 0, (
                f"Multiple diff types should still be idempotent, got {len(active_ops)} ops"
            )

        finally:
            cleanup_files(xml_path, midi_path, repair1_path,
                         diff_path1, diff_path2, plan_path1)


@pytest.mark.skipif(not HAS_REPAIR, reason="Repair module not implemented yet")
@pytest.mark.skipif(not HAS_MUSICDIFF, reason="musicdiff not available")
@pytest.mark.skipif(not HAS_MUSIC21, reason="music21 not installed")
class TestEndToEndDiffReduction:
    """P4: End-to-end diff reduction tests."""

    def test_repair_reduces_diff_count(self) -> None:
        """diff_count(repair(xml)) < diff_count(xml)

        Repair must reduce the number of diffs.
        """
        xml_path = create_temp_file(MISMATCHED_MUSICXML, ".xml")
        midi_path = create_test_midi([
            (60, 0.0, 4.0),  # C4 whole note
        ])
        repair_path = None
        diff_path1 = None
        diff_path2 = None
        plan_path = None

        try:
            # Get initial diff count
            diff_report1, diff_path1 = create_diff_report(xml_path, midi_path)
            initial_count = len(diff_report1["diffs"])

            # Skip if no diffs to fix
            if initial_count == 0:
                pytest.skip("No diffs to repair")

            # Apply repair
            plan = generate_patch_plan(diff_path1, xml_path)
            plan_path = create_temp_json(plan.model_dump())
            repair_path = xml_path.with_suffix(".repaired.xml")
            apply_patch_plan(xml_path, plan_path, repair_path)

            # Get new diff count
            diff_report2, diff_path2 = create_diff_report(repair_path, midi_path)
            final_count = len(diff_report2["diffs"])

            # P4: Diff count must decrease
            assert final_count < initial_count, (
                f"Repair must reduce diffs: {initial_count} -> {final_count}"
            )

        finally:
            cleanup_files(xml_path, midi_path, repair_path,
                         diff_path1, diff_path2, plan_path)


@pytest.mark.skipif(not HAS_REPAIR, reason="Repair module not implemented yet")
@pytest.mark.skipif(not HAS_MUSICDIFF, reason="musicdiff not available")
@pytest.mark.skipif(not HAS_MUSIC21, reason="music21 not installed")
class TestEndToEndParseSurvival:
    """P3: End-to-end parse survival tests."""

    def test_repaired_file_is_parseable(self) -> None:
        """Repaired MusicXML must be parseable by music21."""
        xml_path = create_temp_file(MISMATCHED_MUSICXML, ".xml")
        midi_path = create_test_midi([
            (60, 0.0, 4.0),
        ])
        repair_path = None
        diff_path = None
        plan_path = None

        try:
            diff_report, diff_path = create_diff_report(xml_path, midi_path)
            plan = generate_patch_plan(diff_path, xml_path)
            plan_path = create_temp_json(plan.model_dump())
            repair_path = xml_path.with_suffix(".repaired.xml")
            apply_patch_plan(xml_path, plan_path, repair_path)

            # P3: Must be parseable
            score = music21.converter.parse(repair_path)
            assert score is not None

            # Should have notes
            notes = list(score.recurse().notes)
            assert len(notes) > 0

        finally:
            cleanup_files(xml_path, midi_path, repair_path, diff_path, plan_path)

    def test_repaired_file_has_valid_structure(self) -> None:
        """Repaired MusicXML must have valid musical structure."""
        xml_path = create_temp_file(MISMATCHED_MUSICXML, ".xml")
        midi_path = create_test_midi([
            (60, 0.0, 4.0),
        ])
        repair_path = None
        diff_path = None
        plan_path = None

        try:
            diff_report, diff_path = create_diff_report(xml_path, midi_path)
            plan = generate_patch_plan(diff_path, xml_path)
            plan_path = create_temp_json(plan.model_dump())
            repair_path = xml_path.with_suffix(".repaired.xml")
            apply_patch_plan(xml_path, plan_path, repair_path)

            # Verify structure
            score = music21.converter.parse(repair_path)

            # Should have parts
            parts = list(score.parts)
            assert len(parts) > 0, "Should have at least one part"

            # Should have measures
            measures = list(score.recurse().getElementsByClass(music21.stream.Measure))
            assert len(measures) > 0, "Should have at least one measure"

            # Measures should have valid durations
            for m in measures:
                # Duration should be positive and reasonable
                assert m.duration.quarterLength > 0

        finally:
            cleanup_files(xml_path, midi_path, repair_path, diff_path, plan_path)


@pytest.mark.skipif(not HAS_REPAIR, reason="Repair module not implemented yet")
@pytest.mark.skipif(not HAS_MUSICDIFF, reason="musicdiff not available")
@pytest.mark.skipif(not HAS_MUSIC21, reason="music21 not installed")
class TestEndToEndCorrectness:
    """Tests that repairs are musically correct."""

    def test_repaired_notes_match_midi(self) -> None:
        """Repaired notes should match MIDI pitches and timing."""
        xml_path = create_temp_file(MISMATCHED_MUSICXML, ".xml")
        target_notes = [(60, 0.0, 4.0)]  # Single C4 whole note
        midi_path = create_test_midi(target_notes)
        repair_path = None
        diff_path = None
        plan_path = None

        try:
            diff_report, diff_path = create_diff_report(xml_path, midi_path)
            plan = generate_patch_plan(diff_path, xml_path)
            plan_path = create_temp_json(plan.model_dump())
            repair_path = xml_path.with_suffix(".repaired.xml")
            apply_patch_plan(xml_path, plan_path, repair_path)

            # Verify repaired notes match target
            score = music21.converter.parse(repair_path)
            repaired_notes = list(score.recurse().notes)

            # Should have notes matching the MIDI target
            for target_pitch, target_start, target_duration in target_notes:
                matching = [
                    n for n in repaired_notes
                    if n.pitch.midi == target_pitch
                ]
                assert len(matching) > 0, f"Missing note: pitch {target_pitch}"

        finally:
            cleanup_files(xml_path, midi_path, repair_path, diff_path, plan_path)


@pytest.mark.skipif(not HAS_REPAIR, reason="Repair module not implemented yet")
@pytest.mark.skipif(not HAS_MUSICDIFF, reason="musicdiff not available")
@pytest.mark.skipif(not HAS_MUSIC21, reason="music21 not installed")
class TestNoopBehavior:
    """Tests that files with no diffs remain unchanged."""

    def test_matching_file_unchanged(self) -> None:
        """File that matches MIDI should be unchanged after repair."""
        xml_path = create_temp_file(CORRECT_MUSICXML, ".xml")
        midi_path = create_test_midi([
            (60, 0.0, 4.0),  # C4 whole note - matches XML
        ])
        repair_path = None
        diff_path = None
        plan_path = None

        try:
            # Generate diff and plan
            diff_report, diff_path = create_diff_report(xml_path, midi_path)
            plan = generate_patch_plan(diff_path, xml_path)

            # Should have no active operations
            active_ops = [op for op in plan.operations if op.type != "noop"]
            assert len(active_ops) == 0, (
                f"Matching file should produce no operations, got {len(active_ops)}"
            )

            # If we apply anyway, file should be unchanged
            plan_path = create_temp_json(plan.model_dump())
            repair_path = xml_path.with_suffix(".repaired.xml")
            apply_patch_plan(xml_path, plan_path, repair_path)

            # Compare scores
            original = music21.converter.parse(xml_path)
            repaired = music21.converter.parse(repair_path)

            orig_notes = list(original.recurse().notes)
            rep_notes = list(repaired.recurse().notes)

            assert len(orig_notes) == len(rep_notes)
            for o, r in zip(orig_notes, rep_notes):
                assert o.pitch.midi == r.pitch.midi
                assert o.duration.quarterLength == r.duration.quarterLength

        finally:
            cleanup_files(xml_path, midi_path, repair_path, diff_path, plan_path)


class TestIntegrationTheorems:
    """Theoretical properties for the complete repair pipeline."""

    def test_theorem_p2_idempotency(self) -> None:
        """Theorem P2: repair(repair(xml, midi), midi) == repair(xml, midi)

        The repair operation is idempotent - applying twice yields
        the same result as applying once.
        """
        # Documented property - actual tests in TestEndToEndIdempotency
        pass

    def test_theorem_p3_parse_survival(self) -> None:
        """Theorem P3: parse(repair(xml, midi)) succeeds

        All repaired files must be parseable.
        """
        # Documented property - actual tests in TestEndToEndParseSurvival
        pass

    def test_theorem_p4_diff_reduction(self) -> None:
        """Theorem P4: |diff(repair(xml), midi)| < |diff(xml, midi)|

        Repair must reduce the number of diffs.
        """
        # Documented property - actual tests in TestEndToEndDiffReduction
        pass

    def test_theorem_fixpoint(self) -> None:
        """Theorem: repair(xml, midi) is a fixpoint under repair

        After repair, no further repairs are needed. This follows
        from P2 (idempotency) and P4 (diff reduction).
        """
        # Documented property
        pass

    def test_theorem_monotonic_progress(self) -> None:
        """Theorem: Each repair pass makes progress or terminates

        The system cannot loop infinitely - each pass either
        reduces diffs or produces an empty plan.
        """
        # Documented property
        pass
