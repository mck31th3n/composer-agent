"""Script to generate sample MIDI file for testing."""

import mido

# Create MIDI file
mid = mido.MidiFile()
track = mido.MidiTrack()
mid.tracks.append(track)

# Set tempo: 120 BPM = 500000 microseconds per beat
track.append(mido.MetaMessage('set_tempo', tempo=500000, time=0))

# Time signature: 4/4
track.append(mido.MetaMessage('time_signature', numerator=4, denominator=4, time=0))

# Ticks per beat = 480 (standard)
mid.ticks_per_beat = 480

# Quarter note = 480 ticks, half note = 960 ticks, whole = 1920 ticks

# Measure 1: C4, D4, E4, F4 (quarters) - matches score
notes_m1 = [60, 62, 64, 65]  # C4, D4, E4, F4
for i, pitch in enumerate(notes_m1):
    track.append(mido.Message('note_on', note=pitch, velocity=80, time=0 if i == 0 else 480))
    track.append(mido.Message('note_off', note=pitch, velocity=0, time=480))

# Measure 2: G4 held for half, A4 half - but let's make G4 slightly short (duration mismatch)
# G4 should be half (960 ticks) but we make it 800 ticks
track.append(mido.Message('note_on', note=67, velocity=80, time=0))  # G4
track.append(mido.Message('note_off', note=67, velocity=0, time=800))  # Short!
# A4 half
track.append(mido.Message('note_on', note=69, velocity=80, time=160))  # A4 starts after gap
track.append(mido.Message('note_off', note=69, velocity=0, time=960))

# Measure 3: G4 continuation (but already ended above - this is a missing note scenario)
# G4 should continue from m2, but MIDI cut it short - so the tied G4 in m3 won't match
# B4 half
track.append(mido.Message('note_on', note=71, velocity=80, time=0))  # B4
track.append(mido.Message('note_off', note=71, velocity=0, time=960))

# Extra note not in score: D5 quarter
track.append(mido.Message('note_on', note=74, velocity=80, time=0))  # D5 - EXTRA
track.append(mido.Message('note_off', note=74, velocity=0, time=480))

# Measure 4: C5 whole
track.append(mido.Message('note_on', note=72, velocity=80, time=480))  # C5
track.append(mido.Message('note_off', note=72, velocity=0, time=1920))

# End of track
track.append(mido.MetaMessage('end_of_track', time=0))

# Save
mid.save('samples/sample.mid')
print("Created samples/sample.mid")
print(f"  Ticks per beat: {mid.ticks_per_beat}")
print(f"  Tracks: {len(mid.tracks)}")
