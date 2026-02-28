# musicdiff

A notation-to-MIDI measure-aware diff tool that compares MusicXML scores with MIDI performances and generates detailed difference reports.

## Overview

`musicdiff` parses a MusicXML file and a MIDI file, aligns the notation events with the performance events using beat-grid quantization, and generates a JSON report of any mismatches found. This is useful for:

- Validating MIDI performances against the original score
- Identifying where a performer deviated from the written music
- Quality assurance for music notation and MIDI production workflows

## Status

This project is a functional MVP. Handles basic score-to-performance comparison use cases. Known limitations are documented below.

## Installation

```bash
pip install -e .
```

For development (includes pytest, ruff, mypy):

```bash
pip install -e ".[dev]"
```

**Note:** Requires Python 3.11 or higher.

## Usage

### Basic Usage

```bash
python -m musicdiff --xml <path-to-musicxml> --midi <path-to-midi> --out <output.json>
```

### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `--xml`  | Yes      | Path to MusicXML file (.xml or .musicxml) |
| `--midi` | Yes      | Path to MIDI file (.mid or .midi) |
| `--out`  | Yes      | Path to output JSON file |
| `--tempo`| No       | Override tempo in BPM (default: infer from MusicXML or 120) |

### Example

```bash
python -m musicdiff --xml samples/sample.xml --midi samples/sample.mid --out diff.json
```

### Validating Output

To validate a diff.json file against the schema:

```bash
python -m musicdiff.validate diff.json
```

Returns exit code 0 and prints "Valid" if the file is valid, or exit code 1 with error details if invalid.

## Output Format (diff.json)

The output is a JSON file with the following structure:

```json
{
  "source_xml": "path/to/score.xml",
  "source_midi": "path/to/performance.mid",
  "timestamp": "2026-01-21T12:00:00+00:00",
  "tempo_bpm": 120.0,
  "total_measures": 32,
  "alignment_summary": {
    "tempo_source": "musicxml",
    "time_signature_map_used": false,
    "has_pickup": false,
    "pickup_beats": 0.0,
    "alignment_confidence": "high",
    "estimated_beat_error_mean": 0.02,
    "estimated_beat_error_max": 0.05,
    "midi_has_tempo_map": false,
    "pedal_accounted_for": false
  },
  "unsupported_features": [],
  "diffs": [...],
  "warnings": []
}
```

### Diff Types

Each diff object in the `diffs` array has a `type` field indicating the kind of mismatch:

| Type | Description |
|------|-------------|
| `missing_note` | Note exists in the MIDI performance but is missing from the MusicXML score. |
| `extra_note` | Note exists in the MusicXML score but is missing from the MIDI performance. |
| `duration_mismatch` | Note durations differ significantly between score and performance. |
| `duration_mismatch_tie` | Duration differs for a tied note. |
| `pitch_mismatch` | Pitch values differ between score and performance. |
| `unsupported_feature` | An unsupported notation feature was detected. |

## MusicXML Repair

`musicdiff` includes a repair module that can modify a MusicXML file to match a MIDI performance based on a diff report.

**Note:** The repair process modifies the MusicXML score to align with the MIDI performance (e.g., adding missing notes found in MIDI, removing notes not found in MIDI). Patch plans are intended for single application against the score used to generate them. Re-applying a plan to an already repaired score is undefined behavior.

### Repair Workflow

1. **Generate Plan**: Create a repair plan from a diff report.
   ```bash
   python -m musicdiff.repair --diff diff.json --xml score.xml --out plan.json --dry-run
   ```
2. **Apply Repairs**: Apply the generated plan to create a repaired MusicXML file.
   ```bash
   python -m musicdiff.repair --diff diff.json --xml score.xml --out plan.json --apply --patched-out repaired.musicxml
   ```

See [docs/patchplan.md](docs/patchplan.md) for detailed technical documentation on the repair system.

## Validating Output

```json
{
  "type": "duration_mismatch",
  "measure": 1,
  "beat": 2.0,
  "expected": {
    "pitch_midi": 60,
    "pitch_spelled": "C4",
    "duration": 1.0
  },
  "observed": {
    "pitch": 60,
    "duration_beats": 0.75,
    "duration_sec": 0.375
  },
  "confidence": 0.85,
  "severity": "warn",
  "reason": "duration_differs",
  "suggestion": "m.1 beat 2.0: notated 1.0 beats, performed ~0.75 beats"
}
```

### Severity Levels

- `error`: Critical mismatch (missing/extra notes, pitch differences)
- `warn`: Significant deviation (duration mismatches)
- `info`: Informational (unsupported features detected)

### Alignment Summary

The `alignment_summary` object provides metadata about the alignment process:

- `tempo_source`: Where tempo was sourced from (see Tempo Resolution below)
- `alignment_confidence`: Overall confidence level (`high`, `medium`, `low`)
- `estimated_beat_error_mean`/`max`: Statistics on alignment accuracy
- `has_pickup`: Whether the score starts with a pickup measure
- `midi_has_tempo_map`: Whether the MIDI file contained tempo events (informational only in MVP)

### Tempo Resolution

Tempo for alignment is resolved in this priority order:

1. `--tempo` CLI override → `tempo_source: "override"`
2. MIDI tempo map (if tempo events exist) → `tempo_source: "midi_tempo_map"`
3. MusicXML tempo marking → `tempo_source: "musicxml"`
4. Default 120 BPM → `tempo_source: "default_120"`

When MIDI contains tempo events, the tool uses the MIDI tempo map for more accurate alignment by integrating tempo over time segments.

## Known Limitations (MVP)

1. **Single-part scores**: Only the first part in multi-part MusicXML files is analyzed.

2. **Unsupported notation features**: The following are detected and flagged but not fully handled:
   - Tuplets (triplets, etc.) - treated as straight rhythm
   - Grace notes - timing is ambiguous
   - Tremolo
   - Fermata
   - Time signature changes mid-piece
   - Key signature changes
   - Cue notes

3. **Naive quantization**: The alignment uses simple beat-grid quantization with a fixed tolerance of 0.125 beats. Complex rubato or expressive timing may produce false positives.

4. **No pedal support**: Sustain pedal is not accounted for (`pedal_accounted_for: false` always).

5. **Voice handling**: Multiple voices in a single part are flagged as unsupported; only voice 1 is used.

## Development

### Running Tests

```bash
pytest tests/ -v
```

### Linting

```bash
ruff check src/ tests/
```

### Type Checking

```bash
mypy src/
```

## License

See LICENSE file for details.
