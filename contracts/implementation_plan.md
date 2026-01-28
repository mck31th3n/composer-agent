# Task 001: MVP Notation↔MIDI Measure-Aware Diff Tool

> **Role:** Antigravity (Planner + Judge)  
> **Mode:** Contract generation only. No code authorship.

---

## 1. Acceptance Criteria (Executable)

All criteria MUST be verified by command output, not by assertion.

| # | Criterion | Verification Command | Expected Result |
|---|-----------|---------------------|-----------------|
| AC-1 | CLI runs without error on valid inputs | `python -m musicdiff --xml sample.xml --midi sample.mid --out diff.json` | Exit code 0, `diff.json` created |
| AC-2 | Output validates against JSON schema | `python -m musicdiff.validate diff.json` | Exit code 0, "Valid" printed |
| AC-3 | Detects **duration mismatch** | Inspect `diff.json` | At least 1 diff with `type: "duration_mismatch"` or `"duration_mismatch_tie"` |
| AC-4 | Detects **missing note** (in score, not in MIDI) | Inspect `diff.json` | At least 1 diff with `type: "missing_note"` |
| AC-5 | Detects **extra note** (in MIDI, not in score) | Inspect `diff.json` | At least 1 diff with `type: "extra_note"` |
| AC-6 | Detects **pitch mismatch** | Inspect `diff.json` | At least 1 diff with `type: "pitch_mismatch"` |
| AC-7 | All diffs include measure + beat reference | Inspect `diff.json` | Every diff object has `measure`, `beat`, `severity`, `reason` fields |
| AC-8 | Unit tests exist and pass | `pytest tests/ -v` | Exit code 0, all tests pass |
| AC-9 | Lint/format passes | `ruff check src/ tests/` | Exit code 0, no violations |
| AC-10 | Type checks pass | `mypy src/` | Exit code 0, no errors |
| AC-11 | **alignment_summary present** | Inspect `diff.json` | `alignment_summary` object exists with `tempo_source`, `alignment_confidence` |
| AC-12 | **Unsupported features flagged** | Run on sample with triplet/grace | `unsupported_features` array populated OR empty if none |

### Failure Modes That Block Ship
- Any AC not met → **REJECT**
- `diff.json` contains hallucinated measures (measure numbers outside score range) → **REJECT**
- CLI silently swallows errors → **REJECT**
- `alignment_summary` missing → **REJECT**
- Pitch comparison uses spelling instead of MIDI number → **REJECT**
- Measure numbers don't match MusicXML source → **REJECT**

---

## 2. Repository Skeleton + File Ownership

```
ComposerAgent/
├── contracts/                 # OWNER: Antigravity (immutable during task)
│   ├── schema.json            # JSON Schema for diff.json
│   └── interfaces.md          # Data structure contracts
│
├── src/                       # OWNER: Codex
│   └── musicdiff/
│       ├── __init__.py
│       ├── __main__.py        # CLI entrypoint
│       ├── parser_xml.py      # MusicXML → ScoreEvent[]
│       ├── parser_midi.py     # MIDI → MidiEvent[]
│       ├── align.py           # Alignment logic
│       ├── diff.py            # Diff generation
│       ├── validate.py        # Schema validation CLI
│       └── models.py          # Pydantic models for events/diffs
│
├── tests/                     # OWNER: Claude
│   ├── __init__.py
│   ├── test_parser_xml.py
│   ├── test_parser_midi.py
│   ├── test_align.py
│   ├── test_diff.py
│   └── fixtures/              # Test MusicXML + MIDI files
│       ├── simple_match.xml
│       ├── simple_match.mid
│       ├── duration_mismatch.xml
│       ├── duration_mismatch.mid
│       └── ...
│
├── docs/                      # OWNER: Claude
│   └── README.md
│
├── samples/                   # Shared (demo inputs)
│   ├── sample.xml
│   └── sample.mid
│
├── pyproject.toml             # OWNER: Codex (deps), Claude (test deps)
└── task.md                    # Task tracking
```

### Ownership Rules (ENFORCED)
- **Codex** may ONLY modify files in `/src/` and `pyproject.toml` (main deps)
- **Claude** may ONLY modify files in `/tests/`, `/docs/`, and `pyproject.toml` (test deps)
- **Antigravity** owns `/contracts/` — no worker may modify
- **Violation = Rejection** at final audit

---

## 3. I/O Contracts + Schema

### 3.1 Core Data Structures

```python
# All models use Pydantic for validation

class ScoreEvent:
    """A note event extracted from MusicXML notation."""
    measure: int          # 1-indexed measure number
    beat: float           # Beat within measure (1.0 = beat 1)
    pitch: int            # MIDI pitch number (60 = middle C)
    duration: float       # Duration in beats
    voice: int = 1        # Voice number (for polyphonic parts)
    tie_start: bool = False
    tie_end: bool = False


class MidiEvent:
    """A note event extracted from MIDI performance."""
    start_sec: float      # Start time in seconds
    end_sec: float        # End time in seconds
    pitch: int            # MIDI pitch number
    velocity: int         # 0-127
    channel: int = 0


class AlignedPair:
    """A matched pair of score event and MIDI event."""
    score_event: ScoreEvent | None
    midi_event: MidiEvent | None
    confidence: float     # 0.0-1.0 alignment confidence


class Diff:
    """A detected mismatch between score and performance."""
    type: Literal[
        "duration_mismatch",
        "duration_mismatch_tie",  # Subtype for tie-related duration issues
        "missing_note",
        "extra_note",
        "pitch_mismatch",
        "unsupported_feature"     # Alignment affected by unsupported notation
    ]
    measure: int          # 0 for pickup, 1+ for normal measures
    beat: float
    expected: dict        # What the score says (uses pitch_midi, not spelling)
    observed: dict        # What the MIDI shows
    confidence: float     # 0.0-1.0
    severity: Literal["info", "warn", "error"]  # How critical
    reason: str           # Technical reason (e.g., "tie_merge", "tempo_map_missing")
    suggestion: str       # Human-readable fix suggestion


class DiffReport:
    """Complete output of a comparison run."""
    source_xml: str       # Path to input MusicXML
    source_midi: str      # Path to input MIDI
    timestamp: str        # ISO 8601
    tempo_bpm: float      # Inferred or default tempo
    total_measures: int
    alignment_summary: AlignmentSummary  # REQUIRED even if diffs empty
    unsupported_features: list[UnsupportedFeature] = []  # Detected but not fully handled
    diffs: list[Diff]
    warnings: list[str]   # Non-fatal issues (e.g., "tempo not specified, defaulted to 120")
```

### 3.2 JSON Schema for `diff.json`

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["source_xml", "source_midi", "timestamp", "tempo_bpm", "total_measures", "diffs"],
  "properties": {
    "source_xml": { "type": "string" },
    "source_midi": { "type": "string" },
    "timestamp": { "type": "string", "format": "date-time" },
    "tempo_bpm": { "type": "number", "minimum": 1 },
    "total_measures": { "type": "integer", "minimum": 1 },
    "diffs": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["type", "measure", "beat", "expected", "observed", "confidence", "suggestion"],
        "properties": {
          "type": {
            "type": "string",
            "enum": ["duration_mismatch", "missing_note", "extra_note", "pitch_mismatch"]
          },
          "measure": { "type": "integer", "minimum": 1 },
          "beat": { "type": "number", "minimum": 1 },
          "expected": { "type": "object" },
          "observed": { "type": "object" },
          "confidence": { "type": "number", "minimum": 0, "maximum": 1 },
          "suggestion": { "type": "string" }
        }
      }
    },
    "warnings": {
      "type": "array",
      "items": { "type": "string" }
    }
  }
}
```

---

## 4. Reality Gates

These commands MUST be executed and output pasted in final audit.

| Gate | Command | Pass Condition |
|------|---------|----------------|
| **G1: Install** | `pip install -e .` | Exit 0 |
| **G2: Lint** | `ruff check src/ tests/` | Exit 0, no violations |
| **G3: Type** | `mypy src/` | Exit 0, no errors |
| **G4: Unit Tests** | `pytest tests/ -v` | Exit 0, all pass |
| **G5: CLI Smoke** | `python -m musicdiff --xml samples/sample.xml --midi samples/sample.mid --out diff.json` | Exit 0, `diff.json` exists |
| **G6: Schema Validation** | `python -m musicdiff.validate diff.json` | Exit 0, prints "Valid" |
| **G7: Diff Sanity** | Manual inspection of `diff.json` | All `measure` values ≤ `total_measures` |

---

## 5. Constraints + Assumptions

### In Scope (MVP)
- Single-part MusicXML (monophonic or homophonic)
- Standard MIDI file (Type 0 or 1)
- Tempo: inferred from MusicXML or default 120 BPM
- Time signature: read from MusicXML
- Basic quantization alignment (snap MIDI to nearest beat grid)

### Out of Scope (MVP) — But Flagged
- Audio input
- Multi-part scores (will ignore non-first part, **flag as unsupported**)
- Tuplets/triplets (treat as straight rhythm, **flag as unsupported_feature**)
- Grace notes (**flag as unsupported_feature**)
- Pedaling / sustain inference (`pedal_accounted_for: false` always)
- Dynamic alignment (DTW) — future version
- Real-time / streaming

### Known Limitations to Document
- Alignment is naive; complex rubato will produce false positives → **lower alignment_confidence**
- Polyphonic MIDI on single channel may misalign voices → **flag multi_voice**
- Large tempo variance will break quantization → **check midi_has_tempo_map**
- Pickup measures must use MusicXML measure numbers, not sequential
- Ties produce merged logical events for proper comparison

---

## 6. Dependencies (Pinned Versions)

```toml
[project]
name = "musicdiff"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "music21>=9.1.0,<10",
    "mido>=1.3.0,<2",
    "pydantic>=2.0.0,<3",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0,<9",
    "ruff>=0.4.0",
    "mypy>=1.10.0",
]
```

---

## 7. Handoff Instructions

### To Codex (Implementer)
1. Read this contract fully
2. Implement ONLY files in `/src/musicdiff/`
3. Match the Pydantic models exactly
4. CLI must match the command signature in AC-1
5. Output JSON must validate against schema in Section 3.2
6. Do NOT write tests — that's Claude's lane
7. When done, output:
   - List of files created/modified
   - How to run
   - Any assumptions or deviations (must be justified)

### To Claude (Reviewer + Tests)
1. Wait for Codex output
2. Review for spec drift
3. Write tests in `/tests/` covering:
   - All 4 mismatch types
   - Edge cases (empty file, no mismatches, all mismatches)
   - Schema validation
4. Write `/docs/README.md` with usage instructions
5. When done, output:
   - Critique list (what Codex got wrong or fragile)
   - Test coverage summary
   - "What could silently fail?"

---

> **Antigravity Note:**  
> I have produced contracts only. I have not authored code.  
> Ship decision will occur after Gates G1-G7 pass with evidence.
