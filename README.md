# Float

**Privacy-first music intelligence platform.**

Float combines deterministic compositional analysis with local LLM-powered mentoring. Everything runs offline — your music stays on your machine.

## Modules

### Float Core (`float_core`)
Composition analysis and feedback engine. Analyzes note-list inputs and returns deterministic, auditable JSON with findings, evidence, and constrained revision suggestions. Does **not** generate full compositions by default.

Inputs supported: note-list text/JSON, MusicXML, and MIDI (via music21 import).

MIDI/MusicXML cleanup (notation-friendly defaults):
- Quantizes to `1/16` grid
- Drops ultra-short notes (`< 0.125` quarter length)
- Can be adjusted via CLI:
```bash
python3 -m float_core --input inputs/example_bass.mid --quantize-grid 1/8 --min-duration-ql 0.25
```

Audio transcription (offline):
- Uses BasicPitch for audio → MIDI (optional dependency).
- Install: `python3 -m pip install -e ".[audio]"`
- Run:
```bash
python3 -m float_core --audio path/to/audio.wav --quantize-grid 1/16
```

### Float Diff (`float_diff`)
Notation-MIDI measure-aware diff tool. Compares MusicXML scores with MIDI performances and generates detailed difference reports.

```bash
python -m float_diff --xml <path-to-musicxml> --midi <path-to-midi> --out <output.json>
```

Includes a repair module for MusicXML → MIDI alignment:
```bash
float-diff patch --diff diff.json --xml score.xml --out plan.json
float-diff apply --xml score.xml --patch plan.json --out repaired.musicxml
```

## Quick Start

```bash
python3 -m pip install -e .
```

For development (includes pytest, ruff, mypy):
```bash
pip install -e ".[dev]"
```

**Requires Python 3.11+.**

### Demo

```bash
make demo
```

Local web demo:
```bash
PYTHONPATH=src python3 demo/demo_web.py
```

### CLI

```bash
python3 -m float_core --input examples/example_1.txt
python3 -m float_core --input examples/example_1.txt --profile default --include-timestamp
FLOAT_HMAC_KEY=secret python3 -m float_core --input examples/example_1.txt
```

### Diff

```bash
python -m float_diff --xml score.xml --midi performance.mid --out diff.json
```

Arguments:

| Argument | Required | Description |
|----------|----------|-------------|
| `--xml`  | Yes      | Path to MusicXML file (.xml or .musicxml) |
| `--midi` | Yes      | Path to MIDI file (.mid or .midi) |
| `--out`  | Yes      | Path to output JSON file |
| `--tempo`| No       | Override tempo in BPM (default: infer from MusicXML or 120) |

### Validating Output

```bash
python -m float_diff.validate diff.json
```

## Output Format (diff.json)

```json
{
  "source_xml": "path/to/score.xml",
  "source_midi": "path/to/performance.mid",
  "timestamp": "2026-01-21T12:00:00+00:00",
  "tempo_bpm": 120.0,
  "total_measures": 32,
  "alignment_summary": {
    "tempo_source": "musicxml",
    "alignment_confidence": "high"
  },
  "diffs": [...],
  "warnings": []
}
```

### Diff Types

| Type | Description |
|------|-------------|
| `missing_note` | Note in MIDI but missing from MusicXML score |
| `extra_note` | Note in MusicXML but missing from MIDI performance |
| `duration_mismatch` | Note durations differ significantly |
| `duration_mismatch_tie` | Duration differs for a tied note |
| `pitch_mismatch` | Pitch values differ |
| `unsupported_feature` | Unsupported notation feature detected |

### Tempo Resolution

1. `--tempo` CLI override → `tempo_source: "override"`
2. MIDI tempo map → `tempo_source: "midi_tempo_map"`
3. MusicXML tempo marking → `tempo_source: "musicxml"`
4. Default 120 BPM → `tempo_source: "default_120"`

## Known Limitations (MVP)

1. **Single-part scores**: Only the first part in multi-part MusicXML files is analyzed.
2. **Unsupported notation**: Tuplets, grace notes, tremolo, fermata, mid-piece time/key sig changes, cue notes — detected and flagged but not fully handled.
3. **Naive quantization**: Fixed tolerance of 0.125 beats. Complex rubato may produce false positives.
4. **No pedal support**: `pedal_accounted_for: false` always.
5. **Voice handling**: Multiple voices flagged as unsupported; only voice 1 is used.

## Development

```bash
pytest tests/ -v
ruff check src/ tests/
mypy src/
```

## Status

Active development. Core functionality verified: 210 tests passing; 7 known failures remain in the repair-integration suite; 24 tests skipped due to optional dependencies.

## Known Issues

`test_repair_integration.py` contains 7 failing tests due to an API mismatch between the integration test helper (`create_diff_report`) and the current `align_events` signature. The test was written against a prior API that accepted `ScoreMetadata.divisions` and `time_signatures` as positional arguments; the current signature accepts `tempo_bpm` and `time_signature` directly. Core diff, alignment, and analysis functionality is not affected. Fix tracked: update `create_diff_report` helper in the test file to use the current `align_events` signature.

Some tests are skipped due to optional dependencies (audio transcription via BasicPitch, live web server). Run `pip install -e ".[audio]"` for audio tests.

## License

See LICENSE file for details.
