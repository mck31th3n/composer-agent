"""Tests for PatchPlan schema validity (P1).

These tests verify that:
1. Valid PatchPlans pass schema validation
2. Invalid PatchPlans are rejected
3. All operation types have correct required fields
4. Edge cases are handled correctly

These tests serve as acceptance criteria for the repair system implementation.
"""

import json
from pathlib import Path

import pytest

# Schema validation requires jsonschema
try:
    import jsonschema
    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False


@pytest.fixture
def patchplan_schema() -> dict:
    """Load the PatchPlan schema."""
    schema_path = Path(__file__).parent.parent / "contracts" / "patchplan.schema.json"
    with open(schema_path) as f:
        return json.load(f)


def validate_patchplan(plan: dict, schema: dict) -> None:
    """Validate a PatchPlan against the schema."""
    if not HAS_JSONSCHEMA:
        pytest.skip("jsonschema not installed")
    jsonschema.validate(plan, schema)


class TestValidPatchPlans:
    """Tests for valid PatchPlan structures."""

    def test_minimal_valid_plan(self, patchplan_schema: dict) -> None:
        """Minimal valid PatchPlan with empty operations."""
        plan = {
            "source_file": "test.xml",
            "source_diff_timestamp": "2026-01-21T12:00:00Z",
            "operations": [],
        }
        validate_patchplan(plan, patchplan_schema)

    def test_insert_note_operation(self, patchplan_schema: dict) -> None:
        """Valid insert_note operation."""
        plan = {
            "source_file": "test.xml",
            "source_diff_timestamp": "2026-01-21T12:00:00Z",
            "operations": [
                {
                    "op_id": "op-001",
                    "type": "insert_note",
                    "measure": 1,
                    "beat": 1.0,
                    "voice": 1,
                    "params": {
                        "pitch_midi": 60,
                        "duration": 1.0,
                    },
                    "diff_ref": {
                        "type": "missing_note",
                        "measure": 1,
                        "beat": 1.0,
                    },
                }
            ],
        }
        validate_patchplan(plan, patchplan_schema)

    def test_delete_note_operation(self, patchplan_schema: dict) -> None:
        """Valid delete_note operation."""
        plan = {
            "source_file": "test.xml",
            "source_diff_timestamp": "2026-01-21T12:00:00Z",
            "operations": [
                {
                    "op_id": "op-002",
                    "type": "delete_note",
                    "measure": 2,
                    "beat": 3.0,
                    "voice": 1,
                    "params": {
                        "pitch_midi": 62,
                        "duration": 1.0,  # Required when pitch_midi is present
                    },
                    "diff_ref": {
                        "type": "extra_note",
                        "measure": 2,
                        "beat": 3.0,
                    },
                }
            ],
        }
        validate_patchplan(plan, patchplan_schema)

    def test_update_duration_operation(self, patchplan_schema: dict) -> None:
        """Valid update_duration operation."""
        plan = {
            "source_file": "test.xml",
            "source_diff_timestamp": "2026-01-21T12:00:00Z",
            "operations": [
                {
                    "op_id": "op-003",
                    "type": "update_duration",
                    "measure": 3,
                    "beat": 1.0,
                    "voice": 1,
                    "params": {
                        "pitch_midi": 64,
                        "duration": 2.0,
                        "old_duration": 1.0,
                    },
                    "diff_ref": {
                        "type": "duration_mismatch",
                        "measure": 3,
                        "beat": 1.0,
                    },
                }
            ],
        }
        validate_patchplan(plan, patchplan_schema)

    def test_update_pitch_operation(self, patchplan_schema: dict) -> None:
        """Valid update_pitch operation."""
        plan = {
            "source_file": "test.xml",
            "source_diff_timestamp": "2026-01-21T12:00:00Z",
            "operations": [
                {
                    "op_id": "op-004",
                    "type": "update_pitch",
                    "measure": 4,
                    "beat": 2.0,
                    "voice": 1,
                    "params": {
                        "pitch_midi": 67,
                        "duration": 1.0,
                        "old_pitch_midi": 65,
                    },
                    "diff_ref": {
                        "type": "pitch_mismatch",
                        "measure": 4,
                        "beat": 2.0,
                    },
                }
            ],
        }
        validate_patchplan(plan, patchplan_schema)

    def test_noop_operation(self, patchplan_schema: dict) -> None:
        """Valid noop operation (for skipped diffs)."""
        plan = {
            "source_file": "test.xml",
            "source_diff_timestamp": "2026-01-21T12:00:00Z",
            "operations": [
                {
                    "op_id": "op-005",
                    "type": "noop",
                    "measure": 1,
                    "beat": 1.0,
                    "voice": 1,
                    "params": {},
                    "diff_ref": {
                        "type": "unsupported_feature",
                        "measure": 1,
                        "beat": 1.0,
                    },
                }
            ],
        }
        validate_patchplan(plan, patchplan_schema)

    def test_multiple_operations(self, patchplan_schema: dict) -> None:
        """Valid PatchPlan with multiple operations."""
        plan = {
            "source_file": "test.xml",
            "source_diff_timestamp": "2026-01-21T12:00:00Z",
            "operations": [
                {
                    "op_id": "op-001",
                    "type": "insert_note",
                    "measure": 1,
                    "beat": 1.0,
                    "voice": 1,
                    "params": {"pitch_midi": 60, "duration": 1.0},
                },
                {
                    "op_id": "op-002",
                    "type": "update_pitch",
                    "measure": 2,
                    "beat": 1.0,
                    "voice": 1,
                    "params": {"pitch_midi": 62, "duration": 1.0, "old_pitch_midi": 60},
                },
                {
                    "op_id": "op-003",
                    "type": "delete_note",
                    "measure": 3,
                    "beat": 1.0,
                    "voice": 1,
                    "params": {"pitch_midi": 64, "duration": 1.0},
                },
            ],
        }
        validate_patchplan(plan, patchplan_schema)


class TestInvalidPatchPlans:
    """Tests for invalid PatchPlan structures that must be rejected."""

    def test_missing_source_file(self, patchplan_schema: dict) -> None:
        """Plan without source_file must fail validation."""
        plan = {
            "source_diff_timestamp": "2026-01-21T12:00:00Z",
            "operations": [],
        }
        with pytest.raises(jsonschema.ValidationError):
            validate_patchplan(plan, patchplan_schema)

    def test_missing_timestamp(self, patchplan_schema: dict) -> None:
        """Plan without source_diff_timestamp must fail validation."""
        plan = {
            "source_file": "test.xml",
            "operations": [],
        }
        with pytest.raises(jsonschema.ValidationError):
            validate_patchplan(plan, patchplan_schema)

    def test_missing_operations(self, patchplan_schema: dict) -> None:
        """Plan without operations array must fail validation."""
        plan = {
            "source_file": "test.xml",
            "source_diff_timestamp": "2026-01-21T12:00:00Z",
        }
        with pytest.raises(jsonschema.ValidationError):
            validate_patchplan(plan, patchplan_schema)

    def test_invalid_operation_type(self, patchplan_schema: dict) -> None:
        """Operation with invalid type must fail validation."""
        plan = {
            "source_file": "test.xml",
            "source_diff_timestamp": "2026-01-21T12:00:00Z",
            "operations": [
                {
                    "op_id": "op-001",
                    "type": "invalid_type",
                    "measure": 1,
                    "beat": 1.0,
                    "voice": 1,
                    "params": {},
                }
            ],
        }
        with pytest.raises(jsonschema.ValidationError):
            validate_patchplan(plan, patchplan_schema)

    def test_operation_missing_op_id(self, patchplan_schema: dict) -> None:
        """Operation without op_id must fail validation."""
        plan = {
            "source_file": "test.xml",
            "source_diff_timestamp": "2026-01-21T12:00:00Z",
            "operations": [
                {
                    "type": "insert_note",
                    "measure": 1,
                    "beat": 1.0,
                    "voice": 1,
                    "params": {"pitch_midi": 60, "duration": 1.0},
                }
            ],
        }
        with pytest.raises(jsonschema.ValidationError):
            validate_patchplan(plan, patchplan_schema)

    def test_operation_missing_measure(self, patchplan_schema: dict) -> None:
        """Operation without measure must fail validation."""
        plan = {
            "source_file": "test.xml",
            "source_diff_timestamp": "2026-01-21T12:00:00Z",
            "operations": [
                {
                    "op_id": "op-001",
                    "type": "insert_note",
                    "beat": 1.0,
                    "voice": 1,
                    "params": {"pitch_midi": 60, "duration": 1.0},
                }
            ],
        }
        with pytest.raises(jsonschema.ValidationError):
            validate_patchplan(plan, patchplan_schema)

    def test_operation_missing_beat(self, patchplan_schema: dict) -> None:
        """Operation without beat must fail validation."""
        plan = {
            "source_file": "test.xml",
            "source_diff_timestamp": "2026-01-21T12:00:00Z",
            "operations": [
                {
                    "op_id": "op-001",
                    "type": "insert_note",
                    "measure": 1,
                    "voice": 1,
                    "params": {"pitch_midi": 60, "duration": 1.0},
                }
            ],
        }
        with pytest.raises(jsonschema.ValidationError):
            validate_patchplan(plan, patchplan_schema)

    def test_invalid_pitch_midi_too_high(self, patchplan_schema: dict) -> None:
        """Pitch MIDI > 127 must fail validation."""
        plan = {
            "source_file": "test.xml",
            "source_diff_timestamp": "2026-01-21T12:00:00Z",
            "operations": [
                {
                    "op_id": "op-001",
                    "type": "insert_note",
                    "measure": 1,
                    "beat": 1.0,
                    "voice": 1,
                    "params": {"pitch_midi": 200, "duration": 1.0},
                }
            ],
        }
        with pytest.raises(jsonschema.ValidationError):
            validate_patchplan(plan, patchplan_schema)

    def test_invalid_pitch_midi_negative(self, patchplan_schema: dict) -> None:
        """Negative pitch MIDI must fail validation."""
        plan = {
            "source_file": "test.xml",
            "source_diff_timestamp": "2026-01-21T12:00:00Z",
            "operations": [
                {
                    "op_id": "op-001",
                    "type": "insert_note",
                    "measure": 1,
                    "beat": 1.0,
                    "voice": 1,
                    "params": {"pitch_midi": -1, "duration": 1.0},
                }
            ],
        }
        with pytest.raises(jsonschema.ValidationError):
            validate_patchplan(plan, patchplan_schema)

    def test_invalid_duration_zero(self, patchplan_schema: dict) -> None:
        """Duration of 0 must fail validation (exclusiveMinimum)."""
        plan = {
            "source_file": "test.xml",
            "source_diff_timestamp": "2026-01-21T12:00:00Z",
            "operations": [
                {
                    "op_id": "op-001",
                    "type": "insert_note",
                    "measure": 1,
                    "beat": 1.0,
                    "voice": 1,
                    "params": {"pitch_midi": 60, "duration": 0},
                }
            ],
        }
        with pytest.raises(jsonschema.ValidationError):
            validate_patchplan(plan, patchplan_schema)

    def test_invalid_duration_negative(self, patchplan_schema: dict) -> None:
        """Negative duration must fail validation."""
        plan = {
            "source_file": "test.xml",
            "source_diff_timestamp": "2026-01-21T12:00:00Z",
            "operations": [
                {
                    "op_id": "op-001",
                    "type": "insert_note",
                    "measure": 1,
                    "beat": 1.0,
                    "voice": 1,
                    "params": {"pitch_midi": 60, "duration": -1.0},
                }
            ],
        }
        with pytest.raises(jsonschema.ValidationError):
            validate_patchplan(plan, patchplan_schema)


class TestOperationTypes:
    """Tests ensuring each operation type is correctly defined."""

    def test_all_operation_types_defined(self, patchplan_schema: dict) -> None:
        """Schema must define all expected operation types."""
        op_types = patchplan_schema["definitions"]["PatchOperation"]["properties"]["type"]["enum"]
        expected = ["insert_note", "delete_note", "update_duration", "update_pitch", "noop"]
        assert set(op_types) == set(expected), f"Schema defines {op_types}, expected {expected}"

    def test_schema_has_required_fields(self, patchplan_schema: dict) -> None:
        """Schema must define required fields for operations."""
        required = patchplan_schema["definitions"]["PatchOperation"]["required"]
        expected_required = ["op_id", "type", "measure", "beat", "voice", "params"]
        assert set(required) == set(expected_required)


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_measure_zero_for_pickup(self, patchplan_schema: dict) -> None:
        """Measure 0 (pickup) should be valid."""
        plan = {
            "source_file": "test.xml",
            "source_diff_timestamp": "2026-01-21T12:00:00Z",
            "operations": [
                {
                    "op_id": "op-001",
                    "type": "insert_note",
                    "measure": 0,  # Pickup measure
                    "beat": 4.0,
                    "voice": 1,
                    "params": {"pitch_midi": 60, "duration": 1.0},
                }
            ],
        }
        validate_patchplan(plan, patchplan_schema)

    def test_fractional_beat(self, patchplan_schema: dict) -> None:
        """Fractional beat values should be valid."""
        plan = {
            "source_file": "test.xml",
            "source_diff_timestamp": "2026-01-21T12:00:00Z",
            "operations": [
                {
                    "op_id": "op-001",
                    "type": "insert_note",
                    "measure": 1,
                    "beat": 2.5,  # Fractional beat
                    "voice": 1,
                    "params": {"pitch_midi": 60, "duration": 0.5},
                }
            ],
        }
        validate_patchplan(plan, patchplan_schema)

    def test_voice_2_operation(self, patchplan_schema: dict) -> None:
        """Operations in voice 2 should be valid."""
        plan = {
            "source_file": "test.xml",
            "source_diff_timestamp": "2026-01-21T12:00:00Z",
            "operations": [
                {
                    "op_id": "op-001",
                    "type": "insert_note",
                    "measure": 1,
                    "beat": 1.0,
                    "voice": 2,  # Secondary voice
                    "params": {"pitch_midi": 60, "duration": 1.0},
                }
            ],
        }
        validate_patchplan(plan, patchplan_schema)

    def test_pitch_midi_boundary_low(self, patchplan_schema: dict) -> None:
        """Pitch MIDI 0 (lowest) should be valid."""
        plan = {
            "source_file": "test.xml",
            "source_diff_timestamp": "2026-01-21T12:00:00Z",
            "operations": [
                {
                    "op_id": "op-001",
                    "type": "insert_note",
                    "measure": 1,
                    "beat": 1.0,
                    "voice": 1,
                    "params": {"pitch_midi": 0, "duration": 1.0},
                }
            ],
        }
        validate_patchplan(plan, patchplan_schema)

    def test_pitch_midi_boundary_high(self, patchplan_schema: dict) -> None:
        """Pitch MIDI 127 (highest) should be valid."""
        plan = {
            "source_file": "test.xml",
            "source_diff_timestamp": "2026-01-21T12:00:00Z",
            "operations": [
                {
                    "op_id": "op-001",
                    "type": "insert_note",
                    "measure": 1,
                    "beat": 1.0,
                    "voice": 1,
                    "params": {"pitch_midi": 127, "duration": 1.0},
                }
            ],
        }
        validate_patchplan(plan, patchplan_schema)

    def test_very_short_duration(self, patchplan_schema: dict) -> None:
        """Very short duration (e.g., grace note equivalent) should be valid."""
        plan = {
            "source_file": "test.xml",
            "source_diff_timestamp": "2026-01-21T12:00:00Z",
            "operations": [
                {
                    "op_id": "op-001",
                    "type": "insert_note",
                    "measure": 1,
                    "beat": 1.0,
                    "voice": 1,
                    "params": {"pitch_midi": 60, "duration": 0.0625},  # 64th note
                }
            ],
        }
        validate_patchplan(plan, patchplan_schema)

    def test_long_duration(self, patchplan_schema: dict) -> None:
        """Long duration (tied notes) should be valid."""
        plan = {
            "source_file": "test.xml",
            "source_diff_timestamp": "2026-01-21T12:00:00Z",
            "operations": [
                {
                    "op_id": "op-001",
                    "type": "insert_note",
                    "measure": 1,
                    "beat": 1.0,
                    "voice": 1,
                    "params": {"pitch_midi": 60, "duration": 8.0},  # 2 whole notes tied
                }
            ],
        }
        validate_patchplan(plan, patchplan_schema)
