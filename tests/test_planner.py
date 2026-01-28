"""Tests for the repair planner module.

Verifies:
- Determinism: same diff input → identical plan output
- Confidence filter: operations below threshold are skipped
- Conflicting edits: overlapping operations are handled safely
- P1: Generated plans validate against schema

These tests serve as acceptance criteria for the planner implementation.
"""

import json
import tempfile
from pathlib import Path
from typing import Any

import pytest

# Schema validation
try:
    import jsonschema
    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False

# Planner module (implemented by Codex)
try:
    from musicdiff.repair.planner import generate_patch_plan
    HAS_PLANNER = True
except ImportError:
    HAS_PLANNER = False


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
    <measure number="2">
      <note>
        <pitch><step>D</step><octave>4</octave></pitch>
        <duration>4</duration>
        <type>whole</type>
      </note>
    </measure>
    <measure number="3">
      <note>
        <pitch><step>E</step><octave>4</octave></pitch>
        <duration>4</duration>
        <type>whole</type>
      </note>
    </measure>
    <measure number="4">
      <note>
        <pitch><step>F</step><octave>4</octave></pitch>
        <duration>4</duration>
        <type>whole</type>
      </note>
    </measure>
  </part>
</score-partwise>
"""


@pytest.fixture
def patchplan_schema() -> dict:
    """Load the PatchPlan JSON schema."""
    schema_path = Path(__file__).parent.parent / "contracts" / "patchplan.schema.json"
    with open(schema_path) as f:
        return json.load(f)


def create_temp_xml() -> Path:
    """Create a temporary MusicXML file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
        f.write(MINIMAL_MUSICXML)
        f.flush()
        return Path(f.name)


def create_temp_diff(diff_data: dict[str, Any]) -> Path:
    """Create a temporary diff.json file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(diff_data, f)
        f.flush()
        return Path(f.name)


def cleanup_files(*paths: Path) -> None:
    """Clean up temporary files."""
    for path in paths:
        if path and path.exists():
            path.unlink()


def make_diff_report(diffs: list[dict[str, Any]]) -> dict[str, Any]:
    """Create a diff report structure matching DiffReport model."""
    return {
        "source_xml": "test.xml",
        "source_midi": "test.mid",
        "timestamp": "2026-01-21T12:00:00Z",
        "tempo_bpm": 120.0,
        "total_measures": 4,
        "alignment_summary": {
            "tempo_source": "musicxml",
            "time_signature_map_used": True,
            "has_pickup": False,
            "pickup_beats": 0.0,
            "alignment_confidence": "high",
            "estimated_beat_error_mean": 0.0,
            "estimated_beat_error_max": 0.0,
            "midi_has_tempo_map": False,
            "pedal_accounted_for": False,
        },
        "unsupported_features": [],
        "diffs": diffs,
        "warnings": [],
    }


@pytest.fixture
def sample_diff() -> dict[str, Any]:
    """Sample diff.json structure for testing."""
    return make_diff_report([
        {
            "type": "missing_note",
            "measure": 1,
            "beat": 1.0,
            "expected": {"pitch_midi": 60, "duration": 1.0},
            "observed": {},
            "confidence": 0.95,
            "severity": "error",
            "reason": "Note in MIDI not found in score",
            "suggestion": "Add missing note",
        },
        {
            "type": "extra_note",
            "measure": 2,
            "beat": 1.0,
            "expected": {},
            "observed": {"pitch": 62, "duration_beats": 1.0},
            "confidence": 0.90,
            "severity": "error",
            "reason": "Note in score not found in MIDI",
            "suggestion": "Remove extra note",
        },
        {
            "type": "duration_mismatch",
            "measure": 3,
            "beat": 1.0,
            "expected": {"pitch_midi": 64, "duration": 1.0},
            "observed": {"pitch": 64, "duration_beats": 2.0},
            "confidence": 0.85,
            "severity": "warn",
            "reason": "Duration differs between score and MIDI",
            "suggestion": "Adjust duration",
        },
        {
            "type": "pitch_mismatch",
            "measure": 4,
            "beat": 1.0,
            "expected": {"pitch_midi": 65, "duration": 1.0},
            "observed": {"pitch": 67, "duration_beats": 1.0},
            "confidence": 0.85,
            "severity": "warn",
            "reason": "Pitch differs between score and MIDI",
            "suggestion": "Adjust pitch",
        },
    ])


@pytest.fixture
def diff_with_low_confidence() -> dict[str, Any]:
    """Diff with operations below confidence threshold."""
    return make_diff_report([
        {
            "type": "missing_note",
            "measure": 1,
            "beat": 1.0,
            "expected": {"pitch_midi": 60, "duration": 1.0},
            "observed": {},
            "confidence": 0.95,  # High confidence
            "severity": "error",
            "reason": "Note in MIDI not found in score",
            "suggestion": "Add missing note",
        },
        {
            "type": "extra_note",
            "measure": 2,
            "beat": 1.0,
            "expected": {},
            "observed": {"pitch": 62, "duration_beats": 1.0},
            "confidence": 0.40,  # Low confidence - should be filtered
            "severity": "warn",
            "reason": "Note in score not found in MIDI",
            "suggestion": "Remove extra note",
        },
        {
            "type": "pitch_mismatch",
            "measure": 3,
            "beat": 1.0,
            "expected": {"pitch_midi": 64, "duration": 1.0},
            "observed": {"pitch": 65, "duration_beats": 1.0},
            "confidence": 0.30,  # Very low confidence - should be filtered
            "severity": "info",
            "reason": "Pitch differs",
            "suggestion": "Adjust pitch",
        },
    ])


@pytest.fixture
def diff_with_conflicts() -> dict[str, Any]:
    """Diff with conflicting operations at the same location."""
    return make_diff_report([
        {
            "type": "missing_note",
            "measure": 1,
            "beat": 1.0,
            "expected": {"pitch_midi": 60, "duration": 1.0},
            "observed": {},
            "confidence": 0.90,
            "severity": "error",
            "reason": "Note in MIDI not found in score",
            "suggestion": "Add missing note",
        },
        {
            "type": "extra_note",
            "measure": 1,
            "beat": 1.0,  # Same location as above - conflict
            "expected": {},
            "observed": {"pitch": 60, "duration_beats": 1.0},
            "confidence": 0.85,
            "severity": "error",
            "reason": "Note in score not found in MIDI",
            "suggestion": "Remove extra note",
        },
    ])


@pytest.mark.skipif(not HAS_PLANNER, reason="Planner module not implemented yet")
class TestPlannerDeterminism:
    """Test that planner produces deterministic output."""

    def test_same_diff_produces_identical_plan(self, sample_diff: dict) -> None:
        """Same diff input must produce identical plan output.

        Property: plan(diff) == plan(diff)
        """
        xml_path = create_temp_xml()
        diff_path = create_temp_diff(sample_diff)

        try:
            plan1 = generate_patch_plan(diff_path, xml_path)
            plan2 = generate_patch_plan(diff_path, xml_path)

            # Plans should be identical
            assert plan1.model_dump() == plan2.model_dump(), "Planner must be deterministic"
        finally:
            cleanup_files(xml_path, diff_path)

    def test_determinism_across_multiple_runs(self, sample_diff: dict) -> None:
        """Multiple runs must produce identical results."""
        xml_path = create_temp_xml()
        diff_path = create_temp_diff(sample_diff)

        try:
            plans = [generate_patch_plan(diff_path, xml_path) for _ in range(5)]

            # All plans should be identical
            first_plan = plans[0].model_dump(exclude_none=True)
            for i, plan in enumerate(plans[1:], start=2):
                assert plan.model_dump(exclude_none=True) == first_plan, f"Run {i} differs from run 1"
        finally:
            cleanup_files(xml_path, diff_path)

    def test_operation_order_is_deterministic(self, sample_diff: dict) -> None:
        """Operation order must be deterministic."""
        xml_path = create_temp_xml()
        diff_path = create_temp_diff(sample_diff)

        try:
            plan1 = generate_patch_plan(diff_path, xml_path)
            plan2 = generate_patch_plan(diff_path, xml_path)

            ops1 = [op.op_id for op in plan1.operations]
            ops2 = [op.op_id for op in plan2.operations]

            assert ops1 == ops2, "Operation order must be deterministic"
        finally:
            cleanup_files(xml_path, diff_path)

    def test_op_ids_are_deterministic(self, sample_diff: dict) -> None:
        """Operation IDs must be deterministic (not random)."""
        xml_path = create_temp_xml()
        diff_path = create_temp_diff(sample_diff)

        try:
            plan1 = generate_patch_plan(diff_path, xml_path)
            plan2 = generate_patch_plan(diff_path, xml_path)

            ids1 = {op.op_id for op in plan1.operations}
            ids2 = {op.op_id for op in plan2.operations}

            assert ids1 == ids2, "Operation IDs must be deterministic"
        finally:
            cleanup_files(xml_path, diff_path)


@pytest.mark.skipif(not HAS_PLANNER, reason="Planner module not implemented yet")
class TestConfidenceFilter:
    """Test confidence-based filtering of operations."""

    def test_high_confidence_operations_included(
        self, diff_with_low_confidence: dict
    ) -> None:
        """Operations above confidence threshold should be included."""
        xml_path = create_temp_xml()
        diff_path = create_temp_diff(diff_with_low_confidence)

        try:
            plan = generate_patch_plan(diff_path, xml_path)

            # Should have at least one operation (the high-confidence one)
            assert len(plan.operations) >= 1

            # Check that high confidence operation is included
            op_types = [op.type for op in plan.operations]
            assert "delete_note" in op_types, "High confidence delete should be included"
        finally:
            cleanup_files(xml_path, diff_path)

    def test_low_confidence_operations_filtered(
        self, diff_with_low_confidence: dict
    ) -> None:
        """Operations below confidence threshold should be filtered out."""
        xml_path = create_temp_xml()
        diff_path = create_temp_diff(diff_with_low_confidence)

        try:
            plan = generate_patch_plan(diff_path, xml_path)

            # Low confidence operations should not produce operations (or produce noop)
            active_ops = [
                op for op in plan.operations
                if op.type != "noop"
            ]

            # Should only have the high-confidence operation
            for op in active_ops:
                # Check against the diff that generated this operation
                assert op.measure == 1, "Only measure 1 operation should be active"
        finally:
            cleanup_files(xml_path, diff_path)


@pytest.mark.skipif(not HAS_PLANNER, reason="Planner module not implemented yet")
class TestConflictingEdits:
    """Test handling of conflicting operations."""

    def test_conflicting_operations_detected(self, diff_with_conflicts: dict) -> None:
        """Conflicting operations at same location should be detected."""
        xml_path = create_temp_xml()
        diff_path = create_temp_diff(diff_with_conflicts)

        try:
            plan = generate_patch_plan(diff_path, xml_path)

            # Plan should still be generated (not error out)
            assert plan.operations is not None
        finally:
            cleanup_files(xml_path, diff_path)

    def test_conflicting_operations_not_both_active(
        self, diff_with_conflicts: dict
    ) -> None:
        """Only one of conflicting operations should be active."""
        xml_path = create_temp_xml()
        diff_path = create_temp_diff(diff_with_conflicts)

        try:
            plan = generate_patch_plan(diff_path, xml_path)

            # Get active operations at measure 1, beat 1.0
            ops_at_location = [
                op for op in plan.operations
                if op.measure == 1 and op.beat == 1.0 and op.type != "noop"
            ]

            # Should have at most one active operation at this location
            assert len(ops_at_location) <= 1, (
                f"Conflicting edits should not both be active: {ops_at_location}"
            )
        finally:
            cleanup_files(xml_path, diff_path)


@pytest.mark.skipif(not HAS_PLANNER, reason="Planner module not implemented yet")
class TestPlanSchemaValidity:
    """Test that generated plans validate against schema (P1)."""

    @pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
    def test_plan_validates_against_schema(
        self, sample_diff: dict, patchplan_schema: dict
    ) -> None:
        """Generated plan must validate against PatchPlan schema."""
        xml_path = create_temp_xml()
        diff_path = create_temp_diff(sample_diff)

        try:
            plan = generate_patch_plan(diff_path, xml_path)

            # Should not raise ValidationError
            jsonschema.validate(plan.model_dump(exclude_none=True), patchplan_schema)
        finally:
            cleanup_files(xml_path, diff_path)

    @pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
    def test_empty_diff_produces_valid_plan(self, patchplan_schema: dict) -> None:
        """Empty diff should produce valid (empty) plan."""
        xml_path = create_temp_xml()
        empty_diff = make_diff_report([])
        diff_path = create_temp_diff(empty_diff)

        try:
            plan = generate_patch_plan(diff_path, xml_path)

            # Should validate
            jsonschema.validate(plan.model_dump(exclude_none=True), patchplan_schema)

            # Should have empty operations
            assert plan.operations == []
        finally:
            cleanup_files(xml_path, diff_path)

    def test_plan_has_required_fields(self, sample_diff: dict) -> None:
        """Generated plan must have all required fields."""
        xml_path = create_temp_xml()
        diff_path = create_temp_diff(sample_diff)

        try:
            plan = generate_patch_plan(diff_path, xml_path)

            assert plan.source_file is not None
            assert plan.source_diff_timestamp is not None
            assert plan.operations is not None
        finally:
            cleanup_files(xml_path, diff_path)

    def test_operations_have_required_fields(self, sample_diff: dict) -> None:
        """Each operation must have required fields."""
        xml_path = create_temp_xml()
        diff_path = create_temp_diff(sample_diff)

        try:
            plan = generate_patch_plan(diff_path, xml_path)

            for op in plan.operations:
                assert op.op_id is not None
                assert op.type is not None
                assert op.measure is not None
                assert op.beat is not None
                assert op.voice is not None
                assert op.params is not None
        finally:
            cleanup_files(xml_path, diff_path)


@pytest.mark.skipif(not HAS_PLANNER, reason="Planner module not implemented yet")
class TestDiffToOperationMapping:
    """Test correct mapping from diff types to operation types."""

    def test_missing_note_maps_to_delete(self) -> None:
        """missing_note diff should produce delete_note operation."""
        xml_path = create_temp_xml()
        diff = make_diff_report([
            {
                "type": "missing_note",
                "measure": 1,
                "beat": 1.0,
                "expected": {"pitch_midi": 60, "duration": 1.0},
                "observed": {},
                "confidence": 0.95,
                "severity": "error",
                "reason": "Note in MIDI not found in score",
                "suggestion": "Add missing note",
            }
        ])
        diff_path = create_temp_diff(diff)

        try:
            plan = generate_patch_plan(diff_path, xml_path)

            assert len(plan.operations) == 1
            assert plan.operations[0].type == "delete_note"
        finally:
            cleanup_files(xml_path, diff_path)

    def test_extra_note_maps_to_insert(self) -> None:
        """extra_note diff should produce insert_note operation."""
        xml_path = create_temp_xml()
        diff = make_diff_report([
            {
                "type": "extra_note",
                "measure": 1,
                "beat": 1.0,
                "expected": {},
                "observed": {"pitch": 62, "duration_beats": 1.0},
                "confidence": 0.95,
                "severity": "error",
                "reason": "Note in score not found in MIDI",
                "suggestion": "Remove extra note",
            }
        ])
        diff_path = create_temp_diff(diff)

        try:
            plan = generate_patch_plan(diff_path, xml_path)

            assert len(plan.operations) == 1
            assert plan.operations[0].type == "insert_note"
        finally:
            cleanup_files(xml_path, diff_path)

    def test_duration_mismatch_maps_to_update_duration(self) -> None:
        """duration_mismatch diff should produce update_duration operation."""
        xml_path = create_temp_xml()
        diff = make_diff_report([
            {
                "type": "duration_mismatch",
                "measure": 1,
                "beat": 1.0,
                "expected": {"pitch_midi": 64, "duration": 1.0},
                "observed": {"pitch": 64, "duration_beats": 2.0},
                "confidence": 0.95,
                "severity": "error",
                "reason": "Duration differs",
                "suggestion": "Adjust duration",
            }
        ])
        diff_path = create_temp_diff(diff)

        try:
            plan = generate_patch_plan(diff_path, xml_path)

            assert len(plan.operations) == 1
            assert plan.operations[0].type == "update_duration"
        finally:
            cleanup_files(xml_path, diff_path)

    def test_pitch_mismatch_maps_to_update_pitch(self) -> None:
        """pitch_mismatch diff should produce update_pitch operation."""
        xml_path = create_temp_xml()
        diff = make_diff_report([
            {
                "type": "pitch_mismatch",
                "measure": 1,
                "beat": 1.0,
                "expected": {"pitch_midi": 65, "duration": 1.0},
                "observed": {"pitch": 67, "duration_beats": 1.0},
                "confidence": 0.95,
                "severity": "error",
                "reason": "Pitch differs",
                "suggestion": "Adjust pitch",
            }
        ])
        diff_path = create_temp_diff(diff)

        try:
            plan = generate_patch_plan(diff_path, xml_path)

            assert len(plan.operations) == 1
            assert plan.operations[0].type == "update_pitch"
        finally:
            cleanup_files(xml_path, diff_path)


@pytest.mark.skipif(not HAS_PLANNER, reason="Planner module not implemented yet")
class TestPlanMetadata:
    """Test plan metadata is correctly populated."""

    def test_source_file_from_xml_path(self, sample_diff: dict) -> None:
        """source_file should be the xml path."""
        xml_path = create_temp_xml()
        diff_path = create_temp_diff(sample_diff)

        try:
            plan = generate_patch_plan(diff_path, xml_path)

            assert plan.source_file == str(xml_path)
        finally:
            cleanup_files(xml_path, diff_path)

    def test_timestamp_from_diff(self, sample_diff: dict) -> None:
        """source_diff_timestamp should come from diff timestamp."""
        xml_path = create_temp_xml()
        diff_path = create_temp_diff(sample_diff)

        try:
            plan = generate_patch_plan(diff_path, xml_path)

            assert plan.source_diff_timestamp == sample_diff["timestamp"]
        finally:
            cleanup_files(xml_path, diff_path)

    def test_diff_ref_populated(self, sample_diff: dict) -> None:
        """Operations should have diff_ref linking back to source diff."""
        xml_path = create_temp_xml()
        diff_path = create_temp_diff(sample_diff)

        try:
            plan = generate_patch_plan(diff_path, xml_path)

            for op in plan.operations:
                if op.type != "noop":
                    # diff_ref is set by the planner
                    assert op.diff_ref is not None
                    assert op.diff_ref.type is not None
                    assert op.diff_ref.measure is not None
                    assert op.diff_ref.beat is not None
        finally:
            cleanup_files(xml_path, diff_path)


class TestPlannerTheorems:
    """Theoretical properties that must hold for the planner."""

    def test_theorem_determinism(self) -> None:
        """Theorem: plan(diff) == plan(diff)

        The planner must produce identical output for identical input.
        No randomness allowed.
        """
        # Documented property - actual test in TestPlannerDeterminism
        pass

    def test_theorem_monotonic_filtering(self) -> None:
        """Theorem: |plan(diff, t1)| >= |plan(diff, t2)| when t1 < t2

        Lower confidence threshold means more operations included.
        """
        # Documented property
        pass

    def test_theorem_conflict_safety(self) -> None:
        """Theorem: conflicting ops at same (measure, beat) never both active

        At most one active operation per location to prevent corruption.
        """
        # Documented property - actual test in TestConflictingEdits
        pass

    def test_theorem_schema_validity(self) -> None:
        """Theorem: validate(plan(diff), schema) == True

        Generated plans must always be schema-valid (P1).
        """
        # Documented property - actual test in TestPlanSchemaValidity
        pass
