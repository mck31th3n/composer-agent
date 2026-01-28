"""Tests for repair models - schema parity, enums, required fields.

Verifies that Pydantic models match the JSON schema exactly.
"""

import json
from pathlib import Path
from typing import get_args

import pytest

# Schema validation
try:
    import jsonschema
    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False

# Repair models (implemented by Codex)
try:
    from musicdiff.repair.models_repair import (
        PatchPlan,
        PatchOperation,
        PatchParams,
        DiffRef,
    )
    HAS_REPAIR_MODELS = True
except ImportError:
    HAS_REPAIR_MODELS = False


@pytest.fixture
def patchplan_schema() -> dict:
    """Load the PatchPlan JSON schema."""
    schema_path = Path(__file__).parent.parent / "contracts" / "patchplan.schema.json"
    with open(schema_path) as f:
        return json.load(f)


class TestSchemaEnums:
    """Test that model enums match schema enums exactly."""

    def test_operation_type_enum_matches_schema(self, patchplan_schema: dict) -> None:
        """OperationType enum must match schema's operation types."""
        schema_types = patchplan_schema["definitions"]["PatchOperation"]["properties"]["type"]["enum"]
        expected = {"insert_note", "delete_note", "update_duration", "update_pitch", "noop"}

        assert set(schema_types) == expected, f"Schema has {schema_types}"

    @pytest.mark.skipif(not HAS_REPAIR_MODELS, reason="Repair models not implemented")
    def test_operation_type_literal_matches_schema(self, patchplan_schema: dict) -> None:
        """PatchOperation.type Literal must match schema's operation types."""
        schema_types = set(patchplan_schema["definitions"]["PatchOperation"]["properties"]["type"]["enum"])

        # Get the Literal args from the type annotation
        type_field = PatchOperation.model_fields["type"]
        literal_args = set(get_args(type_field.annotation))

        assert literal_args == schema_types, f"Model has {literal_args}, schema has {schema_types}"

    @pytest.mark.skipif(not HAS_REPAIR_MODELS, reason="Repair models not implemented")
    def test_operation_type_values_are_strings(self) -> None:
        """PatchOperation type values must be strings for JSON serialization."""
        type_field = PatchOperation.model_fields["type"]
        literal_args = get_args(type_field.annotation)

        for op_type in literal_args:
            assert isinstance(op_type, str)


class TestSchemaRequiredFields:
    """Test that model required fields match schema required fields."""

    def test_patchplan_required_fields(self, patchplan_schema: dict) -> None:
        """PatchPlan required fields must match schema."""
        schema_required = set(patchplan_schema["required"])
        expected = {"source_file", "source_diff_timestamp", "operations"}

        assert schema_required == expected

    def test_operation_required_fields(self, patchplan_schema: dict) -> None:
        """PatchOperation required fields must match schema."""
        schema_required = set(patchplan_schema["definitions"]["PatchOperation"]["required"])
        expected = {"op_id", "type", "measure", "beat", "voice", "params"}

        assert schema_required == expected

    @pytest.mark.skipif(not HAS_REPAIR_MODELS, reason="Repair models not implemented")
    def test_patchplan_model_has_required_fields(self) -> None:
        """PatchPlan Pydantic model must have required fields."""
        # Try to create without required fields - should fail
        with pytest.raises(Exception):  # ValidationError
            PatchPlan()

        # With required fields - should succeed
        plan = PatchPlan(
            source_file="test.xml",
            source_diff_timestamp="2026-01-21T12:00:00Z",
            operations=[],
        )
        assert plan.source_file == "test.xml"

    @pytest.mark.skipif(not HAS_REPAIR_MODELS, reason="Repair models not implemented")
    def test_operation_model_has_required_fields(self) -> None:
        """PatchOperation Pydantic model must have required fields."""
        # Try to create without required fields - should fail
        with pytest.raises(Exception):  # ValidationError
            PatchOperation()

        # With required fields - should succeed
        op = PatchOperation(
            op_id="op-001",
            type="insert_note",
            measure=1,
            beat=1.0,
            voice=1,
            params=PatchParams(pitch_midi=60, duration=1.0),
        )
        assert op.op_id == "op-001"


class TestFieldConstraints:
    """Test field constraints match schema constraints."""

    def test_pitch_midi_constraints(self, patchplan_schema: dict) -> None:
        """pitch_midi must have min 0, max 127."""
        params = patchplan_schema["definitions"]["PatchOperation"]["properties"]["params"]["properties"]
        pitch = params["pitch_midi"]

        assert pitch.get("minimum") == 0
        assert pitch.get("maximum") == 127

    def test_duration_constraint(self, patchplan_schema: dict) -> None:
        """duration must be > 0 (exclusiveMinimum)."""
        params = patchplan_schema["definitions"]["PatchOperation"]["properties"]["params"]["properties"]
        duration = params["duration"]

        assert duration.get("exclusiveMinimum") == 0

    @pytest.mark.skipif(not HAS_REPAIR_MODELS, reason="Repair models not implemented")
    def test_model_validates_pitch_range(self) -> None:
        """Model must reject pitch outside 0-127."""
        with pytest.raises(Exception):  # ValidationError
            PatchParams(pitch_midi=200, duration=1.0)

    @pytest.mark.skipif(not HAS_REPAIR_MODELS, reason="Repair models not implemented")
    def test_model_validates_duration_positive(self) -> None:
        """Model must reject duration <= 0."""
        with pytest.raises(Exception):  # ValidationError
            PatchParams(pitch_midi=60, duration=0)


class TestSchemaParity:
    """Test overall schema parity between JSON schema and Pydantic models."""

    @pytest.mark.skipif(not HAS_REPAIR_MODELS, reason="Repair models not implemented")
    @pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
    def test_model_serializes_to_valid_schema(self, patchplan_schema: dict) -> None:
        """Serialized model must validate against JSON schema."""
        plan = PatchPlan(
            source_file="test.xml",
            source_diff_timestamp="2026-01-21T12:00:00Z",
            operations=[
                PatchOperation(
                    op_id="op-001",
                    type="insert_note",
                    measure=1,
                    beat=1.0,
                    voice=1,
                    params=PatchParams(pitch_midi=60, duration=1.0),
                )
            ],
        )

        # Serialize to dict (exclude None to match schema)
        plan_dict = plan.model_dump(exclude_none=True)

        # Validate against schema
        jsonschema.validate(plan_dict, patchplan_schema)

    @pytest.mark.skipif(not HAS_REPAIR_MODELS, reason="Repair models not implemented")
    @pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
    def test_schema_validates_model_output(self, patchplan_schema: dict) -> None:
        """All operation types serialize correctly."""
        operations = [
            PatchOperation(
                op_id="op-001",
                type="insert_note",
                measure=1,
                beat=1.0,
                voice=1,
                params=PatchParams(pitch_midi=60, duration=1.0),
            ),
            PatchOperation(
                op_id="op-002",
                type="delete_note",
                measure=2,
                beat=1.0,
                voice=1,
                params=PatchParams(old_pitch_midi=62, old_duration=1.0),
            ),
            PatchOperation(
                op_id="op-003",
                type="update_duration",
                measure=3,
                beat=1.0,
                voice=1,
                params=PatchParams(duration=2.0, old_duration=1.0),
            ),
            PatchOperation(
                op_id="op-004",
                type="update_pitch",
                measure=4,
                beat=1.0,
                voice=1,
                params=PatchParams(pitch_midi=67, duration=1.0, old_pitch_midi=65),
            ),
            PatchOperation(
                op_id="op-005",
                type="noop",
                measure=5,
                beat=1.0,
                voice=1,
                params=PatchParams(),
            ),
        ]

        plan = PatchPlan(
            source_file="test.xml",
            source_diff_timestamp="2026-01-21T12:00:00Z",
            operations=operations,
        )

        jsonschema.validate(plan.model_dump(exclude_none=True), patchplan_schema)


class TestDiffRefField:
    """Test diff_ref optional field."""

    def test_diff_ref_is_optional(self, patchplan_schema: dict) -> None:
        """diff_ref should not be in required fields."""
        required = patchplan_schema["definitions"]["PatchOperation"]["required"]
        assert "diff_ref" not in required

    def test_diff_ref_structure(self, patchplan_schema: dict) -> None:
        """diff_ref has type, measure, beat fields."""
        diff_ref = patchplan_schema["definitions"]["PatchOperation"]["properties"]["diff_ref"]
        props = diff_ref["properties"]

        assert "type" in props
        assert "measure" in props
        assert "beat" in props

    @pytest.mark.skipif(not HAS_REPAIR_MODELS, reason="Repair models not implemented")
    def test_model_accepts_diff_ref(self) -> None:
        """Model should accept diff_ref field."""
        op = PatchOperation(
            op_id="op-001",
            type="insert_note",
            measure=1,
            beat=1.0,
            voice=1,
            params=PatchParams(pitch_midi=60, duration=1.0),
            diff_ref=DiffRef(type="missing_note", measure=1, beat=1.0),
        )
        assert op.diff_ref is not None
        assert op.diff_ref.type == "missing_note"


class TestParamsField:
    """Test params field structure."""

    def test_params_has_expected_properties(self, patchplan_schema: dict) -> None:
        """params should define pitch_midi, duration, old_pitch_midi, old_duration."""
        params = patchplan_schema["definitions"]["PatchOperation"]["properties"]["params"]["properties"]

        assert "pitch_midi" in params
        assert "duration" in params
        assert "old_pitch_midi" in params
        assert "old_duration" in params

    def test_params_has_dependency(self, patchplan_schema: dict) -> None:
        """params should have pitch_midi -> duration dependency."""
        params = patchplan_schema["definitions"]["PatchOperation"]["properties"]["params"]
        deps = params.get("dependencies", {})

        assert "pitch_midi" in deps
        assert "duration" in deps["pitch_midi"]
