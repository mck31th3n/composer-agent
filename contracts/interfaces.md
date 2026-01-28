# I/O Contracts + Interface Specifications

> **Owner:** Antigravity  
> **Status:** LOCKED (no modifications by workers)  
> **Version:** 1.1 (patched per GPT sanity check)

---

## 1. Function Signatures (Codex Must Implement)

### `parser_xml.py`

```python
def parse_musicxml(path: str | Path) -> tuple[list[ScoreEvent], ScoreMetadata]:
    """
    Parse MusicXML file into score events.
    
    Args:
        path: Path to .xml or .musicxml file
        
    Returns:
        Tuple of (events, metadata)
        
    Raises:
        FileNotFoundError: If file doesn't exist
        ParseError: If file is not valid MusicXML
        
    IMPORTANT:
        - Measure numbers MUST be taken from MusicXML <measure number="X">, not inferred sequentially
        - Pickup measures should use measure=0 or the actual MusicXML measure number
        - Ties must be tracked via tie_start/tie_end flags
        - Also produce merged "logical duration" events for tied notes
        - Detect and flag unsupported features (tuplets, grace notes, etc.)
    """

def detect_unsupported_features(score: Score) -> list[UnsupportedFeature]:
    """
    Scan parsed score for features not fully supported in MVP.
    
    Returns:
        List of UnsupportedFeature objects with measure location and description
    """
```

### `parser_midi.py`

```python
def parse_midi(path: str | Path) -> tuple[list[MidiEvent], MidiMetadata]:
    """
    Parse MIDI file into performance events.
    
    Args:
        path: Path to .mid or .midi file
        
    Returns:
        Tuple of (events, metadata)
        
    Raises:
        FileNotFoundError: If file doesn't exist
        ParseError: If file is not valid MIDI
        
    IMPORTANT:
        - If MIDI contains tempo map events, extract and expose them in MidiMetadata
        - Track whether MIDI has tempo changes (midi_has_tempo_map field)
    """
```

### `align.py`

```python
def align_events(
    score_events: list[ScoreEvent],
    midi_events: list[MidiEvent],
    tempo_bpm: float,
    time_signature: tuple[int, int],
    midi_tempo_map: list[TempoEvent] | None = None,
    has_pickup: bool = False,
    pickup_beats: float = 0.0
) -> tuple[list[AlignedPair], AlignmentSummary]:
    """
    Align MIDI events to score events using beat-grid quantization.
    
    Args:
        score_events: Parsed notation events (including logical duration events for ties)
        midi_events: Parsed performance events
        tempo_bpm: Base tempo for time-to-beat conversion
        time_signature: (numerator, denominator)
        midi_tempo_map: Optional tempo change events from MIDI
        has_pickup: Whether score starts with pickup measure
        pickup_beats: Duration of pickup in beats
        
    Returns:
        Tuple of (aligned_pairs, alignment_summary)
        
    IMPORTANT:
        - If MIDI has tempo map, USE IT for alignment (more accurate)
        - If no tempo map, use constant tempo and record lower confidence
        - Handle pickup by offsetting beat calculations
        - Produce alignment_summary with confidence metrics
    
    DETERMINISTIC PAIRING ALGORITHM (MANDATORY):
        1. Convert all MIDI event start times to beat positions using tempo
        2. Group score events by pitch_midi
        3. Group MIDI events by pitch
        4. For each pitch:
           a. Sort score events by (measure, beat)
           b. Sort MIDI events by onset beat
           c. Use GREEDY NEAREST-ONSET matching:
              - For each score event, find nearest unmatched MIDI event (same pitch)
              - If within beat_tolerance, create AlignedPair with beat_error
              - Mark both events as "used"
           d. Ties broken by: earlier onset wins
        5. Unmatched score events → AlignedPair(score_event=X, midi_event=None)
        6. Unmatched MIDI events → AlignedPair(score_event=None, midi_event=X)
        7. Record beat_error for each matched pair
        8. Compute estimated_beat_error_mean and max for AlignmentSummary
        
    This ensures identical inputs produce identical outputs across runs.
    """
```

### `diff.py`

```python
def generate_diffs(
    aligned_pairs: list[AlignedPair],
    unsupported_features: list[UnsupportedFeature]
) -> list[Diff]:
    """
    Generate diff objects from aligned pairs.
    
    Rules:
        - score_event exists, midi_event is None → missing_note
        - midi_event exists, score_event is None → extra_note
        - both exist, pitch differs → pitch_mismatch
        - both exist, duration differs significantly → duration_mismatch
        - duration differs AND score has tie → duration_mismatch_tie (subtype)
        - unsupported feature affects alignment → unsupported_feature
        
    IMPORTANT:
        - Compare using logical_duration for tied notes, not individual note durations
        - Pitch comparison uses MIDI pitch number only (0-127), not spelling
        - Include severity and reason for each diff
        - Tolerance is relative to smallest notated duration OR fixed 0.25 beats (whichever smaller)
        
    Returns:
        List of Diff objects with measure/beat localization
    """

def generate_report(
    xml_path: str,
    midi_path: str,
    diffs: list[Diff],
    metadata: ScoreMetadata,
    alignment_summary: AlignmentSummary,
    unsupported_features: list[UnsupportedFeature],
    warnings: list[str]
) -> DiffReport:
    """
    Assemble final report for JSON output.
    
    INVARIANT: alignment_summary MUST always be present, even if diffs is empty.
    """
```

---

## 2. Data Models (Pydantic)

### ScoreEvent
```python
class ScoreEvent(BaseModel):
    event_id: str = Field(..., description="Unique ID: 'm{measure}-b{beat}-p{pitch}-v{voice}-i{idx}'")
    measure: int = Field(..., ge=0, description="Measure number from MusicXML (0 for pickup)")
    beat: float = Field(..., ge=1.0, description="Beat within measure")
    pitch_midi: int = Field(..., ge=0, le=127, description="MIDI pitch number (used for comparison)")
    pitch_spelled: str = Field(..., description="Notated spelling e.g. 'C#4' (for display only)")
    duration: float = Field(..., gt=0, description="Duration in beats (individual note)")
    logical_duration: float = Field(..., gt=0, description="Duration including tied notes")
    voice: int = Field(default=1, ge=1, description="Voice number")
    staff: int = Field(default=1, ge=1, description="Staff number (for grand staff)")
    tie_start: bool = Field(default=False, description="This note starts a tie")
    tie_end: bool = Field(default=False, description="This note ends a tie")
    is_logical_merged: bool = Field(default=False, description="True if this represents merged tied notes")
```

### MidiEvent
```python
class MidiEvent(BaseModel):
    event_id: str = Field(..., description="Unique ID: 't{start_sec:.3f}-p{pitch}-c{channel}-i{idx}'")
    start_sec: float = Field(..., ge=0, description="Start time in seconds")
    end_sec: float = Field(..., gt=0, description="End time in seconds")
    pitch: int = Field(..., ge=0, le=127)
    velocity: int = Field(..., ge=0, le=127)
    channel: int = Field(default=0, ge=0, le=15)
    
    @property
    def duration_sec(self) -> float:
        return self.end_sec - self.start_sec
```

### MidiMetadata
```python
class MidiMetadata(BaseModel):
    has_tempo_map: bool = Field(..., description="Whether MIDI contains tempo changes")
    tempo_events: list[TempoEvent] = Field(default_factory=list)
    initial_tempo_bpm: float | None = None

class TempoEvent(BaseModel):
    time_sec: float
    tempo_bpm: float
```

### AlignedPair
```python
class AlignedPair(BaseModel):
    score_event: ScoreEvent | None
    midi_event: MidiEvent | None
    confidence: float = Field(..., ge=0, le=1)
    beat_error: float = Field(default=0.0, description="Alignment error in beats")
```

### AlignmentSummary
```python
class AlignmentSummary(BaseModel):
    tempo_source: Literal["musicxml", "midi_tempo_map", "override", "default_120"]
    time_signature_map_used: bool
    has_pickup: bool
    pickup_beats: float = 0.0
    alignment_confidence: Literal["high", "medium", "low"]
    estimated_beat_error_mean: float = 0.0
    estimated_beat_error_max: float = 0.0
    midi_has_tempo_map: bool
    pedal_accounted_for: bool = Field(default=False, description="Always False for MVP")
```

### UnsupportedFeature
```python
class UnsupportedFeature(BaseModel):
    feature: Literal["tuplet", "grace_note", "tremolo", "fermata", "multi_voice", "time_sig_change", "key_sig_change", "cue_note"]
    measure: int = Field(..., ge=0)
    description: str
```

### Diff
```python
class Diff(BaseModel):
    type: Literal[
        "duration_mismatch",
        "duration_mismatch_tie",
        "missing_note",
        "extra_note",
        "pitch_mismatch",
        "unsupported_feature"
    ]
    measure: int = Field(..., ge=0, description="0 for pickup, 1+ for normal")
    beat: float = Field(..., ge=1)
    expected: dict
    observed: dict
    confidence: float = Field(..., ge=0, le=1)
    severity: Literal["info", "warn", "error"]
    reason: str = Field(..., description="Technical reason e.g. 'tie_merge', 'tempo_map_missing'")
    suggestion: str
```

### ScoreMetadata
```python
class ScoreMetadata(BaseModel):
    total_measures: int
    tempo_bpm: float
    time_signature: tuple[int, int]
    time_signature_changes: list[tuple[int, tuple[int, int]]] = Field(
        default_factory=list,
        description="List of (measure, (num, denom)) for time sig changes"
    )
    has_pickup: bool = False
    pickup_beats: float = 0.0
    smallest_notated_duration: float = Field(
        default=0.25,
        description="Smallest note duration in beats (for tolerance calculation)"
    )
    title: str | None = None
    part_name: str | None = None
```

### DiffReport
```python
class DiffReport(BaseModel):
    source_xml: str
    source_midi: str
    timestamp: str
    tempo_bpm: float
    total_measures: int
    alignment_summary: AlignmentSummary  # REQUIRED even if diffs empty
    unsupported_features: list[UnsupportedFeature] = Field(default_factory=list)
    diffs: list[Diff]
    warnings: list[str] = Field(default_factory=list)
```

---

## 3. CLI Interface

### Main command
```bash
python -m musicdiff --xml <path> --midi <path> --out <path> [--tempo <bpm>]
```

| Argument | Required | Description |
|----------|----------|-------------|
| `--xml` | Yes | Path to MusicXML file |
| `--midi` | Yes | Path to MIDI file |
| `--out` | Yes | Path to output JSON file |
| `--tempo` | No | Override tempo (default: infer from MusicXML or 120) |

### Validation command
```bash
python -m musicdiff.validate <diff.json>
```

Exit codes:
- `0` = Valid, prints "Valid"
- `1` = Invalid, prints error details

---

## 4. Error Handling Contract

### Custom Exceptions
```python
class MusicDiffError(Exception):
    """Base exception for musicdiff."""
    code: str  # Error code for programmatic handling

class ParseError(MusicDiffError):
    """Failed to parse input file."""
    # code = "E_XML_PARSE" or "E_MIDI_PARSE"

class AlignmentError(MusicDiffError):
    """Failed to align events."""
    # code = "E_ALIGNMENT"

class ValidationError(MusicDiffError):
    """Output failed schema validation."""
    # code = "E_VALIDATION"
```

### Standard Error Codes
| Code | Meaning |
|------|---------|
| `E_XML_PARSE` | MusicXML parsing failed |
| `E_MIDI_PARSE` | MIDI parsing failed |
| `E_TIMESIG_MISSING` | Time signature not found (warn, use default) |
| `E_TEMPO_MISSING` | Tempo not found (warn, use 120 BPM) |
| `E_ALIGNMENT` | Alignment algorithm failed |
| `E_VALIDATION` | Output failed schema validation |

### Error Behavior
- CLI must catch all exceptions and exit with non-zero code
- Error messages must include file path and specific location if available
- CLI must NOT silently swallow errors
- Missing tempo/time sig → warn and continue with defaults (not fatal)

---

## 5. Invariants (Must Always Be True)

1. Every `Diff.measure` ≤ `DiffReport.total_measures` (or 0 for pickup)
2. Every `Diff.beat` ≤ beats per measure (from time signature at that measure)
3. **Pitch comparison uses `pitch_midi` (0-127), NOT `pitch_spelled`**
4. **`pitch_spelled` is for display only, never used in matching logic**
5. All timestamps in `DiffReport` are ISO 8601 format
6. `diffs` array may be empty (no mismatches is valid)
7. **`alignment_summary` is ALWAYS present, even if diffs is empty**
8. **Measure numbers come from MusicXML, not sequential counting**
9. Tied notes produce BOTH individual events AND a merged logical event
10. Pickup measures use measure=0 (or actual MusicXML number if different)

---

## 6. Tolerance Thresholds

For mismatch detection:

| Check | Tolerance | Notes |
|-------|-----------|-------|
| Duration match | `min(0.25, smallest_notated_duration / 2)` | Relative to score complexity |
| Pitch match | Exact (MIDI pitch number) | No tolerance |
| Beat alignment | ±0.125 beats | For MIDI-to-beat-grid snapping |

### Tolerance Calculation
```python
def get_duration_tolerance(metadata: ScoreMetadata) -> float:
    """Calculate duration tolerance based on score's smallest note value."""
    return min(0.25, metadata.smallest_notated_duration / 2)
```

---

## 7. Tie Handling Rules

### Parsing Phase
1. When parsing MusicXML, track tie start/end via `<tie type="start"/>` and `<tie type="stop"/>`
2. For each tied sequence (e.g., quarter → half):
   - Emit individual `ScoreEvent` for each note with `tie_start`/`tie_end` flags
   - ALSO emit a merged `ScoreEvent` with:
     - `is_logical_merged = True`
     - `logical_duration` = sum of all tied durations
     - Start position = first note's position
3. Alignment uses logical merged events for comparison

### Diff Phase
1. When score has tie and MIDI shows single long note → NOT a mismatch
2. When score has tie and MIDI shows gap between tied notes → `duration_mismatch_tie`
3. Include `reason: "tie_merge"` in diff if tie handling is relevant

---

## 8. Pickup/Anacrusis Handling

### Detection
1. Check if first measure has `<attributes><time>` with different duration than time signature indicates
2. Or check for `implicit="yes"` attribute on first measure
3. Record in `ScoreMetadata.has_pickup` and `ScoreMetadata.pickup_beats`

### Measure Numbering
1. Use MusicXML's actual `<measure number="X">` attribute
2. Do NOT renumber sequentially
3. Pickup may be measure 0, or measure 1 with short duration — honor the source

### Alignment Impact
1. Offset MIDI time calculations to account for pickup
2. Record `has_pickup: true` in alignment_summary

---

## 9. Unsupported Feature Handling

### Features to Detect and Flag
| Feature | Detection Method | Impact |
|---------|-----------------|--------|
| Tuplet | `<time-modification>` element | Rhythm may be misaligned |
| Grace note | `<grace>` element | Timing ambiguous |
| Tremolo | `<tremolo>` element | Duration unclear |
| Fermata | `<fermata>` element | Tempo variance |
| Multi-voice | Multiple `<voice>` in part | May cause false extra notes |
| Time sig change | Multiple `<time>` elements | Affects beat counting |

### Behavior
1. Detect feature during parsing
2. Add to `unsupported_features` list with measure location
3. Add warning to `warnings` list
4. Continue processing (don't abort)
5. Lower `alignment_confidence` if significant
6. Create `unsupported_feature` diff type if it causes alignment issues

---

## 10. Polyphony/Voice Handling (MVP)

### Scope
- MVP supports **single primary voice** only
- If multiple voices detected, use voice 1 and flag as `unsupported_feature`

### Comparison Logic
- Multiple score events at same beat + pitch → treat as one (chord)
- Multiple score events at same beat, different pitch → allow (legitimate polyphony within voice)
- Do NOT treat polyphony as "extra notes" by default

---

> **Antigravity Note:**  
> Contract patched per GPT sanity check.  
> Key additions: alignment_summary (required), tie handling, pickup handling, severity/reason fields, unsupported feature flagging, MIDI pitch vs spelling distinction.  
> No code authored. Ship decision after gates pass with evidence.
