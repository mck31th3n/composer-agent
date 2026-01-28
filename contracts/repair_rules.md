# Repair Agent Rules & Constraints

## 1. Core Philosophy
The Repair Agent is responsible for safely modifying a MusicXML file to resolve differences identified by a `diff.json` report. It operates somewhat like a surgeon: **do no harm**.

## 2. Allowed Operations
The agent may only perform the following operations, defined in the `PatchPlan`:

### `insert_note`
- **Purpose**: Resolve `missing_note` diffs.
- **Rules**:
    - Must specify Pitch, Duration, Measure, Beat.
    - If the target location contains a Rest, the rest should be replaced or shortened.
    - If the target location contains a Note (collision), the new note should be placed in a **new voice** (e.g., Voice 2) to preserve existing content, unless validly replacing a wrong note.
    - Must handle measure duration overflow (warn or error).

### `delete_note`
- **Purpose**: Resolve `extra_note` diffs.
- **Rules**:
    - Target note must be identified by Measure, Beat, Pitch.
    - Deleting a note MUST leave behind a Rest of equivalent duration (unless it was in a secondary voice that is now empty).
    - **NEVER** shift subsequent notes (shifting causes cascading desynchronization).

### `update_duration`
- **Purpose**: Resolve `duration_mismatch`.
- **Rules**:
    - Extending duration must not overwrite subsequent notes.
    - Shortening duration must fill the gap with a Rest.

### `update_pitch`
- **Purpose**: Resolve `pitch_mismatch`.
- **Rules**:
    - Simplest operation. Modify pitch, keep duration/position constant.

## 3. Forbidden Operations
- **Measure Deletion**: Never delete a measure.
- **Time Signature Changes**: Never modify time info.
- **Reordering**: Never reorder measures.
- **Destructive Shifting**: Never delete time from a measure (e.g. `delete_note` without replacing with Rest). This changes the absolute position of all future events.

## 4. Safety Gates (Pre-Application)
Before applying a patch:
1. **Schema Check**: Plan must validate against `patchplan.schema.json`.
2. **Bounds Check**: Operations must be within measure bounds (1 to TotalMeasures).

## 5. Verification Gates (Post-Application)
After applying a patch:
1. **P2 Idempotency**: Running the repair again on the output should yield no changes.
2. **P3 Parse Safety**: The output MusicXML must be validly parsable by `music21`.
3. **P4 Diff Reduction**: Comparing the output MusicXML against the original MIDI using `musicdiff` must show a **reduction** in error count. E.g., `len(new_diffs) < len(old_diffs)`.
