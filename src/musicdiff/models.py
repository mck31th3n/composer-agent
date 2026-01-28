"""Pydantic models per /contracts/interfaces.md."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class TempoEvent(BaseModel):
    """A tempo change event from MIDI."""

    time_sec: float
    tempo_bpm: float


class ScoreEvent(BaseModel):
    """A note event extracted from MusicXML notation."""

    event_id: str = Field(
        ..., description="Unique ID: 'm{measure}-b{beat}-p{pitch}-v{voice}-i{idx}'"
    )
    measure: int = Field(
        ..., ge=0, description="Measure number from MusicXML (0 for pickup)"
    )
    beat: float = Field(..., ge=1.0, description="Beat within measure")
    pitch_midi: int = Field(
        ..., ge=0, le=127, description="MIDI pitch number (used for comparison)"
    )
    pitch_spelled: str = Field(..., description="Notated spelling e.g. 'C#4' (for display only)")
    duration: float = Field(..., gt=0, description="Duration in beats (individual note)")
    logical_duration: float = Field(..., gt=0, description="Duration including tied notes")
    voice: int = Field(default=1, ge=1, description="Voice number")
    staff: int = Field(default=1, ge=1, description="Staff number (for grand staff)")
    tie_start: bool = Field(default=False, description="This note starts a tie")
    tie_end: bool = Field(default=False, description="This note ends a tie")
    is_logical_merged: bool = Field(
        default=False, description="True if this represents merged tied notes"
    )


class MidiEvent(BaseModel):
    """A note event extracted from MIDI performance."""

    event_id: str = Field(
        ..., description="Unique ID: 't{start_sec:.3f}-p{pitch}-c{channel}-i{idx}'"
    )
    start_sec: float = Field(..., ge=0, description="Start time in seconds")
    end_sec: float = Field(..., description="End time in seconds")
    pitch: int = Field(..., ge=0, le=127)
    velocity: int = Field(..., ge=0, le=127)
    channel: int = Field(default=0, ge=0, le=15)

    @property
    def duration_sec(self) -> float:
        """Duration in seconds."""
        return self.end_sec - self.start_sec


class MidiMetadata(BaseModel):
    """Metadata extracted from MIDI file."""

    has_tempo_map: bool = Field(..., description="Whether MIDI contains tempo changes")
    tempo_events: list[TempoEvent] = Field(default_factory=list)
    initial_tempo_bpm: float | None = None


class ScoreMetadata(BaseModel):
    """Metadata extracted from MusicXML."""

    total_measures: int
    tempo_bpm: float
    time_signature: tuple[int, int]
    time_signature_changes: list[tuple[int, tuple[int, int]]] = Field(
        default_factory=list, description="List of (measure, (num, denom)) for time sig changes"
    )
    has_pickup: bool = False
    pickup_beats: float = 0.0
    smallest_notated_duration: float = Field(
        default=0.25, description="Smallest note duration in beats (for tolerance calculation)"
    )
    title: str | None = None
    part_name: str | None = None


class AlignedPair(BaseModel):
    """A matched pair of score event and MIDI event."""

    score_event: ScoreEvent | None
    midi_event: MidiEvent | None
    confidence: float = Field(..., ge=0, le=1)
    beat_error: float = Field(default=0.0, description="Alignment error in beats")


class AlignmentSummary(BaseModel):
    """Summary of alignment quality and assumptions."""

    tempo_source: Literal["musicxml", "midi_tempo_map", "override", "default_120"]
    time_signature_map_used: bool
    has_pickup: bool
    pickup_beats: float = 0.0
    alignment_confidence: Literal["high", "medium", "low"]
    estimated_beat_error_mean: float = 0.0
    estimated_beat_error_max: float = 0.0
    midi_has_tempo_map: bool
    pedal_accounted_for: bool = Field(default=False, description="Always False for MVP")


class UnsupportedFeature(BaseModel):
    """A notation feature detected but not fully supported."""

    feature: Literal[
        "tuplet",
        "grace_note",
        "tremolo",
        "fermata",
        "multi_voice",
        "time_sig_change",
        "key_sig_change",
        "cue_note",
    ]
    measure: int = Field(..., ge=0)
    description: str


class Diff(BaseModel):
    """A detected mismatch between score and performance."""

    type: Literal[
        "duration_mismatch",
        "duration_mismatch_tie",
        "missing_note",
        "extra_note",
        "pitch_mismatch",
        "unsupported_feature",
    ]
    measure: int = Field(..., ge=0, description="0 for pickup, 1+ for normal")
    beat: float = Field(..., ge=1)
    expected: dict[str, object]
    observed: dict[str, object]
    confidence: float = Field(..., ge=0, le=1)
    severity: Literal["info", "warn", "error"]
    reason: str = Field(..., description="Technical reason e.g. 'tie_merge', 'tempo_map_missing'")
    suggestion: str


class DiffReport(BaseModel):
    """Complete output of a comparison run."""

    source_xml: str
    source_midi: str
    timestamp: str
    tempo_bpm: float
    total_measures: int
    alignment_summary: AlignmentSummary
    unsupported_features: list[UnsupportedFeature] = Field(default_factory=list)
    diffs: list[Diff]
    warnings: list[str] = Field(default_factory=list)
