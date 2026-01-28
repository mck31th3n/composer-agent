# Task 001 Walkthrough: MusicDiff MVP

**Date:** 2026-01-21
**Status:** COMPLETE (MVP Shipped)

## Goal
Build a minimal viable tool that compares MusicXML notation against MIDI performance data and outputs measure-aware diffs with suggested edits.

## Accomplishments
- **Core Engine:** Implemented `musicdiff` package with MusicXML/MIDI parsing, deterministic alignment, and diff generation.
- **Interfaces:** Strict Pydantic models with `event_id` tracking for every note.
- **Alignment:** Greedy nearest-onset algorithm with 0.125 beat tolerance, tie merging, and **full MIDI tempo map support**.
- **Reliability:** 100% type coverage (mypy), formatting (ruff), and **74 unit tests** (pytest).
- **Validation:** JSON Schema validation for all outputs.

## Usage Proof

### 1. Installation
```bash
pip install -e .
```

### 2. Running Verification
```bash
# Run full test suite
pytest tests/ -v
# Output: 74 passed in 0.94s
```

### 3. Generating a Diff
```bash
python -m musicdiff --xml samples/sample.xml --midi samples/sample.mid --out diff.json
```

### 4. Sample Output
The tool correctly identifies missing/extra notes when alignment fails (e.g. due to offset):
```json
{
  "alignment_summary": {
    "tempo_source": "musicxml",
    "alignment_confidence": "high",
    "estimated_beat_error_mean": 0.0,
    "midi_has_tempo_map": true
  },
  "diffs": [
    {
      "type": "missing_note",
      "measure": 1,
      "beat": 3.0,
      "expected": { "pitch_spelled": "E4", "duration": 1.0 },
      "severity": "error",
      "reason": "no_matching_midi_event"
    }
  ]
}
```

### 5. Auto-Repair (Beta - Dev Release)
The tool can now auto-repair MusicXML files based on the diff report.

#### Step 1: Generate Patch Plan
```bash
python -m musicdiff patch --diff diff.json --xml samples/sample.xml --out patch_plan.json
```
This generates a deterministic JSON plan of operations (`insert_note`, `delete_note`, etc.).

#### Step 2: Apply Patch
```bash
python -m musicdiff apply --xml samples/sample.xml --patch patch_plan.json --out repaired.xml
```

#### Step 3: Verify Fix
```bash
python -m musicdiff --xml repaired.xml --midi samples/sample.mid --out diff_v2.json
# Result should show fewer errors
```

## Known Limitations (MVP)
1. **Single Part:** Only analyses the first part of a score.
2. **No Audio:** Purely symbolic comparison (MusicXML vs MIDI).

## Artifacts
- Source Code: [`src/musicdiff/`](src/musicdiff/)
- Tests: [`tests/`](tests/)
- Contracts: [`contracts/`](contracts/)
