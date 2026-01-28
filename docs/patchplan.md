# PatchPlan Documentation

## Overview

The `PatchPlan` is a declarative JSON document that describes a sequence of repair operations to apply to a MusicXML file. It is generated from a `diff.json` report and serves as an intermediate representation that can be reviewed before application.

## Schema Location

`contracts/patchplan.schema.json`

## Purpose

The PatchPlan system enables:

1. **Declarative repairs**: Operations are described, not immediately executed
2. **Review before apply**: Human or automated review of proposed changes
3. **Deterministic application**: Same plan always produces same result
4. **Rollback safety**: Original file is preserved; repairs create new output

Patch plans are intended for single application against the score used to generate them. Re-applying a plan to an already repaired score is undefined behavior.

## PatchPlan Structure

```json
{
  "source_file": "path/to/score.xml",
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
        "duration": 1.0
      },
      "diff_ref": {
        "type": "missing_note",
        "measure": 1,
        "beat": 1.0
      }
    }
  ]
}
```

### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `source_file` | string | Path to the MusicXML file to repair |
| `source_diff_timestamp` | string | ISO 8601 timestamp from the diff.json used |
| `operations` | array | List of PatchOperation objects |

## Operation Types

### `insert_note`

**Purpose**: Resolve `missing_note` diffs by adding a note to the score.

**Parameters**:
- `pitch_midi` (required): MIDI pitch number (0-127)
- `duration` (required): Duration in beats

**Rules**:
- If target location contains a Rest, replace or shorten the rest
- If target location contains a Note (collision), insert in a new voice
- Must not cause measure duration overflow

**Example**:
```json
{
  "op_id": "op-001",
  "type": "insert_note",
  "measure": 2,
  "beat": 3.0,
  "voice": 1,
  "params": {
    "pitch_midi": 64,
    "duration": 1.0
  }
}
```

### `delete_note`

**Purpose**: Resolve `extra_note` diffs by removing a note from the score.

**Parameters**:
- `pitch_midi` (required): Pitch of note to delete

**Rules**:
- Target note identified by measure, beat, pitch
- **MUST** leave a Rest of equivalent duration in place
- **NEVER** shift subsequent notes (prevents cascading desync)

**Example**:
```json
{
  "op_id": "op-002",
  "type": "delete_note",
  "measure": 1,
  "beat": 2.0,
  "voice": 1,
  "params": {
    "pitch_midi": 62
  }
}
```

### `update_duration`

**Purpose**: Resolve `duration_mismatch` diffs by changing note duration.

**Parameters**:
- `pitch_midi` (required): Pitch of note to modify
- `duration` (required): New duration in beats
- `old_duration` (optional): Previous duration for verification

**Rules**:
- Extending duration must not overwrite subsequent notes
- Shortening duration must fill the gap with a Rest

**Example**:
```json
{
  "op_id": "op-003",
  "type": "update_duration",
  "measure": 3,
  "beat": 1.0,
  "voice": 1,
  "params": {
    "pitch_midi": 60,
    "duration": 2.0,
    "old_duration": 1.0
  }
}
```

### `update_pitch`

**Purpose**: Resolve `pitch_mismatch` diffs by changing note pitch.

**Parameters**:
- `pitch_midi` (required): New MIDI pitch number
- `duration` (required): Duration to identify the note
- `old_pitch_midi` (optional): Previous pitch for verification

**Rules**:
- Simplest operation: only pitch changes
- Position and duration remain constant

**Example**:
```json
{
  "op_id": "op-004",
  "type": "update_pitch",
  "measure": 4,
  "beat": 2.0,
  "voice": 1,
  "params": {
    "pitch_midi": 67,
    "duration": 1.0,
    "old_pitch_midi": 65
  }
}
```

### `noop`

**Purpose**: Explicitly skip a diff (e.g., unsupported feature).

**Parameters**: None required

**Rules**:
- Does not modify the score
- Documents that a diff was intentionally not repaired

**Example**:
```json
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
    "beat": 1.0
  }
}
```

## Forbidden Operations

The following operations are **never** allowed:

| Operation | Reason |
|-----------|--------|
| Measure deletion | Would shift all subsequent content |
| Time signature change | Would invalidate beat calculations |
| Measure reordering | Would desynchronize with MIDI |
| Destructive shifting | Deleting time causes cascading errors |

## Safety Gates

### Pre-Application (Before applying a patch)

1. **P1 Schema Check**: Plan must validate against `patchplan.schema.json`
2. **Bounds Check**: All operations must target valid measures (0 to TotalMeasures)

### Post-Application (After applying a patch)

1. **P2 Idempotency**: Running the repair again must yield no changes
2. **P3 Parse Safety**: Output MusicXML must be parsable by music21
3. **P4 Diff Reduction**: New diff count must be less than original

## Idempotency Guarantees

The repair system guarantees idempotency:

```
apply(apply(xml, plan), plan) == apply(xml, plan)
```

This means:
- Applying a patch twice produces the same result as applying once
- After repair, generating a new PatchPlan should yield empty operations
- Operations check for existing state before modifying

## When Repair Refuses to Act

The repair system will refuse or skip an operation when:

| Condition | Response |
|-----------|----------|
| Target measure doesn't exist | Error or skip with warning |
| Note collision without voice space | Skip, log warning |
| Duration would overflow measure | Clamp or skip with warning |
| Delete would shift content | Must insert rest instead |
| Unsupported feature involved | Generate `noop` operation |

These refusals are **correct behavior**, not bugs. They prevent cascading errors.

## Workflow

1. **Generate Diff**: Run `musicdiff` to produce `diff.json`
2. **Generate Plan**: Run planner to produce `patch_plan.json`
3. **Review Plan**: Human or automated review of proposed changes
4. **Apply Plan**: Run applier to produce `repaired.xml`
5. **Verify**: Re-run `musicdiff` to confirm diff reduction

```bash
# Step 1: Generate diff
python -m musicdiff --xml score.xml --midi perf.mid --out diff.json

# Step 2: Generate repair plan
python -m musicdiff.repair plan --diff diff.json --out patch_plan.json

# Step 3: Review (manual)
cat patch_plan.json

# Step 4: Apply repairs
python -m musicdiff.repair apply --plan patch_plan.json --out repaired.xml

# Step 5: Verify
python -m musicdiff --xml repaired.xml --midi perf.mid --out new_diff.json
```

## Testing

Test files verify correct behavior:

| Test File | Purpose |
|-----------|---------|
| `test_patchplan_schema.py` | P1: Schema validity |
| `test_patch_idempotency.py` | P2: Idempotency guarantees |
| `test_patch_apply.py` | P3: Parse survival, P4: Diff reduction |

Run tests:
```bash
pytest tests/test_patchplan_schema.py tests/test_patch_idempotency.py tests/test_patch_apply.py -v
```

## Diff Type to Operation Mapping

| Diff Type | Description | Recommended Operation |
|-----------|-------------|----------------------|
| `missing_note` | In MIDI, Not in Score | `insert_note` (Adds note to score) |
| `extra_note` | In Score, Not in MIDI | `delete_note` (Removes note from score) |
| `duration_mismatch` | Duration differs | `update_duration` |
| `duration_mismatch_tie` | Tied duration mismatch | `update_duration` (with tie handling) |
| `pitch_mismatch` | Pitch differs | `update_pitch` |
| `unsupported_feature` | Flagged feature | `noop` (cannot auto-repair) |

## Error Handling

The repair system uses these error codes:

| Code | Meaning |
|------|---------|
| `E_SCHEMA_INVALID` | PatchPlan failed schema validation |
| `E_MEASURE_BOUNDS` | Operation targets non-existent measure |
| `E_NOTE_NOT_FOUND` | Target note doesn't exist (for update/delete) |
| `E_COLLISION` | Insert would overwrite without voice space |
| `E_DURATION_OVERFLOW` | Duration extends beyond measure |
| `E_PARSE_FAILED` | Output MusicXML is invalid |

## Version History

- **1.0**: Initial schema with 5 operation types
