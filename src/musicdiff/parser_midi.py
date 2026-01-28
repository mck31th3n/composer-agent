"""MIDI parser using mido."""

from __future__ import annotations

from pathlib import Path

import mido

from .exceptions import ParseError
from .models import MidiEvent, MidiMetadata, TempoEvent


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
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"MIDI file not found: {path}")

    try:
        mid = mido.MidiFile(str(path))
    except Exception as e:
        raise ParseError(f"Failed to parse MIDI: {e}", "midi") from e

    # Extract tempo events
    tempo_events: list[TempoEvent] = []
    ticks_per_beat = mid.ticks_per_beat
    tempo_map_ticks: list[tuple[int, float]] = []

    # First pass: collect tempo events (ticks)
    for track in mid.tracks:
        abs_ticks = 0
        for msg in track:
            abs_ticks += msg.time
            if msg.type == "set_tempo":
                tempo_bpm = mido.tempo2bpm(msg.tempo)
                tempo_map_ticks.append((abs_ticks, tempo_bpm))

    tempo_map_ticks.sort(key=lambda x: x[0])
    tempo_map_ticks = _dedupe_tempo_map(tempo_map_ticks)

    tempo_events = _tempo_map_ticks_to_events(tempo_map_ticks, ticks_per_beat)

    has_tempo_map = len(tempo_map_ticks) > 0
    if tempo_map_ticks and tempo_map_ticks[0][0] == 0:
        initial_tempo_bpm = tempo_map_ticks[0][1]
    else:
        initial_tempo_bpm = 120.0

    # Second pass: extract note events
    events: list[MidiEvent] = []
    event_counts: dict[tuple[float, int, int], int] = {}  # For unique event_id idx

    for _track_idx, track in enumerate(mid.tracks):
        abs_ticks = 0

        # Track active notes: (pitch, channel) -> (start_time_sec, velocity)
        active_notes: dict[tuple[int, int], tuple[float, int]] = {}

        for msg in track:
            abs_ticks += msg.time

            # Convert ticks to seconds using tempo map if present
            time_sec = _ticks_to_seconds_with_map(
                abs_ticks, ticks_per_beat, tempo_map_ticks
            )

            if msg.type == "set_tempo":
                pass  # Tempo changes handled in _ticks_to_seconds

            elif msg.type == "note_on" and msg.velocity > 0:
                key = (msg.note, msg.channel)
                active_notes[key] = (time_sec, msg.velocity)

            elif msg.type == "note_off" or (msg.type == "note_on" and msg.velocity == 0):
                key = (msg.note, msg.channel)
                if key in active_notes:
                    start_sec, velocity = active_notes.pop(key)
                    end_sec = time_sec

                    # Ensure end > start
                    if end_sec <= start_sec:
                        end_sec = start_sec + 0.001

                    # Generate unique event_id
                    id_key = (round(start_sec, 3), msg.note, msg.channel)
                    idx = event_counts.get(id_key, 0)
                    event_counts[id_key] = idx + 1

                    event = MidiEvent(
                        event_id=f"t{start_sec:.3f}-p{msg.note}-c{msg.channel}-i{idx}",
                        start_sec=start_sec,
                        end_sec=end_sec,
                        pitch=msg.note,
                        velocity=velocity,
                        channel=msg.channel,
                    )
                    events.append(event)

    # Sort events by start time then pitch
    events.sort(key=lambda e: (e.start_sec, e.pitch))

    metadata = MidiMetadata(
        has_tempo_map=has_tempo_map,
        tempo_events=tempo_events,
        initial_tempo_bpm=initial_tempo_bpm,
    )

    return events, metadata


def _bpm_to_us(tempo_bpm: float) -> int:
    """Convert BPM to microseconds per beat."""
    return int(60_000_000 / tempo_bpm)


def _dedupe_tempo_map(
    tempo_map_ticks: list[tuple[int, float]],
) -> list[tuple[int, float]]:
    """Deduplicate tempo events by tick, keeping the last at each tick."""
    if not tempo_map_ticks:
        return []
    deduped: list[tuple[int, float]] = []
    last_tick = None
    for tick, tempo_bpm in tempo_map_ticks:
        if last_tick is None or tick != last_tick:
            deduped.append((tick, tempo_bpm))
        else:
            deduped[-1] = (tick, tempo_bpm)
        last_tick = tick
    return deduped


def _tempo_map_ticks_to_events(
    tempo_map_ticks: list[tuple[int, float]],
    ticks_per_beat: int,
) -> list[TempoEvent]:
    """Convert tempo map in ticks to TempoEvent list with time_sec."""
    if not tempo_map_ticks:
        return []

    events: list[TempoEvent] = []
    prev_tick = 0
    prev_tempo_bpm = 120.0
    elapsed_sec = 0.0

    for tick, tempo_bpm in tempo_map_ticks:
        if tick < prev_tick:
            continue
        delta_ticks = tick - prev_tick
        if delta_ticks > 0:
            elapsed_sec += mido.tick2second(
                delta_ticks, ticks_per_beat, _bpm_to_us(prev_tempo_bpm)
            )
        events.append(TempoEvent(time_sec=elapsed_sec, tempo_bpm=tempo_bpm))
        prev_tick = tick
        prev_tempo_bpm = tempo_bpm

    return events


def _ticks_to_seconds_with_map(
    ticks: int,
    ticks_per_beat: int,
    tempo_map_ticks: list[tuple[int, float]],
) -> float:
    """Convert absolute ticks to seconds using tempo map."""
    if not tempo_map_ticks:
        return mido.tick2second(ticks, ticks_per_beat, 500000)

    prev_tick = 0
    prev_tempo_bpm = 120.0
    elapsed_sec = 0.0

    for tick, tempo_bpm in tempo_map_ticks:
        if ticks <= tick:
            break
        delta_ticks = tick - prev_tick
        elapsed_sec += mido.tick2second(
            delta_ticks, ticks_per_beat, _bpm_to_us(prev_tempo_bpm)
        )
        prev_tick = tick
        prev_tempo_bpm = tempo_bpm

    if ticks > prev_tick:
        elapsed_sec += mido.tick2second(
            ticks - prev_tick, ticks_per_beat, _bpm_to_us(prev_tempo_bpm)
        )

    return elapsed_sec
