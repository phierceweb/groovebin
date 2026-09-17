"""The reader and the writer against mido, an implementation that shares no code with them.

Every other file test is ``read(write(x)) == x``, which still passes when the reader and the writer
hold the same wrong idea of the format. mido is the outside opinion. F7 escapes and split SysEx
packets stay out: mido cannot represent either, and their byte round trip is pinned in
``test_midi.py``.

Nothing here compares file bytes: mido expands running status as it parses and the writer emits a
full status per event, so the per-message bytes on both sides are the same shape.
"""

from __future__ import annotations

import io
import random
from dataclasses import replace

import mido
import pytest
from mido.midifiles.meta import build_meta_message

from groovebin.events import Event, Note
from groovebin.midi import _controls_before_programs, read, write
from groovebin.song import END_OF_TRACK, Part, Song, unpair

SEEDS = range(40)
PPQS = (96, 192, 480, 960)
METERS = ((4, 2), (3, 2), (6, 3), (12, 3))


def _vlq(length: int) -> bytes:
    out = [length & 0x7F]
    length >>= 7
    while length:
        out.append(0x80 | (length & 0x7F))
        length >>= 7
    return bytes(reversed(out))


def _meta(meta_type: int, payload: bytes) -> bytes:
    return bytes([0xFF, meta_type]) + _vlq(len(payload)) + payload


def _text(rng: random.Random, size: int) -> bytes:
    return bytes(rng.randrange(0x20, 0x7F) for _ in range(size))


def _event_data(rng: random.Random) -> bytes:
    """One event of any kind a file can hold: every channel message, a meta, a complete SysEx."""
    channel = rng.randrange(16)
    match rng.randrange(9):
        case 0:
            return bytes([0xA0 | channel, rng.randrange(128), rng.randrange(128)])
        case 1:
            return bytes([0xB0 | channel, rng.randrange(128), rng.randrange(128)])
        case 2:
            return bytes([0xC0 | channel, rng.randrange(128)])
        case 3:
            return bytes([0xD0 | channel, rng.randrange(128)])
        case 4:
            return bytes([0xE0 | channel, rng.randrange(128), rng.randrange(128)])
        case 5:
            return _meta(0x03, _text(rng, rng.randrange(1, 16)))
        case 6:
            return _meta(0x01, _text(rng, rng.randrange(128, 400)))    # a length past one VLQ byte
        case 7:
            numerator, power = rng.choice(METERS)
            return _meta(0x58, bytes([numerator, power, 24, 8]))
        case _:
            return b"\xf0" + bytes(rng.randrange(128) for _ in range(rng.randrange(1, 12))) + b"\xf7"


def _part(rng: random.Random, ppq: int) -> Part:
    notes, keys = [], set()
    for _ in range(rng.randrange(0, 12)):
        key = (rng.randrange(1, 17), rng.randrange(128))
        if key in keys:                          # one note per channel and pitch: never a nested pair
            continue
        keys.add(key)
        channel, pitch = key
        length = 0 if rng.random() < 0.2 else rng.randrange(1, 500)
        off_velocity = None if rng.random() < 0.5 else rng.randrange(128)
        notes.append(Note(rng.randrange(0, 2000), length, channel, pitch,
                          rng.randrange(1, 128), off_velocity))
    events = [Event(rng.randrange(0, 2000), _event_data(rng)) for _ in range(rng.randrange(0, 12))]
    part = Part(ppq, notes, events)
    return replace(part, end=part.last_tick)     # the tick write puts the end-of-track on


def song_from_seed(seed: int) -> Song:
    rng = random.Random(seed)
    ppq, fmt = rng.choice(PPQS), rng.randrange(2)
    return Song(ppq, fmt, [_part(rng, ppq) for _ in range(1 if fmt == 0 else rng.randrange(1, 4))])


def _absolute(track: mido.MidiTrack) -> list[tuple[int, bytes]]:
    """A mido track as (absolute tick, bytes), without the end-of-track it must end on."""
    out, tick = [], 0
    for message in track:
        tick += message.time
        out.append((tick, bytes(message.bytes())))
    assert out and out[-1][1] == END_OF_TRACK
    return out[:-1]


def _as_mido(data: bytes, delta: int) -> mido.Message | mido.MetaMessage:
    if data[0] != 0xFF:
        return mido.Message.from_bytes(list(data), time=delta)
    position, length = 2, 0
    while True:
        byte = data[position]
        position, length = position + 1, (length << 7) | (byte & 0x7F)
        if not byte & 0x80:
            break
    return build_meta_message(data[1], data[position:position + length], delta)


def test_the_corpus_holds_what_these_tests_claim_to_cover():
    songs = [song_from_seed(seed) for seed in SEEDS]
    parts = [part for song in songs for part in song.tracks]
    notes = [note for part in parts for note in part.notes]
    data = [event.data for part in parts for event in part.events]
    assert {song.format for song in songs} == {0, 1}
    assert {song.ppq for song in songs} == set(PPQS)
    assert any(len(song.tracks) > 1 for song in songs)
    assert any(note.length == 0 for note in notes) and any(note.length > 0 for note in notes)
    assert any(note.off_velocity is None for note in notes)
    assert any(note.off_velocity is not None for note in notes)
    assert {0xA0, 0xB0, 0xC0, 0xD0, 0xE0} <= {d[0] & 0xF0 for d in data if d[0] < 0xF0}
    assert any(d[0] == 0xF0 and d[-1] == 0xF7 for d in data)
    assert any(d[0] == 0xFF and len(d) - 4 > 127 for d in data)   # a meta past a one-byte length


@pytest.mark.parametrize("seed", SEEDS)
def test_mido_reads_back_every_message_the_writer_emits(seed):
    song = song_from_seed(seed)
    parsed = mido.MidiFile(file=io.BytesIO(write(song)))
    assert (parsed.type, parsed.ticks_per_beat) == (song.format, song.ppq)
    assert len(parsed.tracks) == len(song.tracks)
    for part, track in zip(song.tracks, parsed.tracks, strict=True):
        assert _absolute(track) == _controls_before_programs(unpair(part))


@pytest.mark.parametrize("seed", SEEDS)
def test_the_reader_reads_back_a_song_mido_serialized(seed):
    song = song_from_seed(seed)
    out = mido.MidiFile(type=song.format, ticks_per_beat=song.ppq)
    for part in song.tracks:
        track = mido.MidiTrack()
        out.tracks.append(track)
        now = 0
        for tick, data in _controls_before_programs(unpair(part)):
            track.append(_as_mido(data, tick - now))
            now = tick
        track.append(mido.MetaMessage("end_of_track", time=max(part.last_tick, now) - now))
    buffer = io.BytesIO()
    out.save(file=buffer)
    assert read(buffer.getvalue()) == song
