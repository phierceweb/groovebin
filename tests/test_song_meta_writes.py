"""Tempo and key signatures written into a song, every other event kept."""

import pytest

from groovebin.events import Event, Note
from groovebin.midi import read, write
from groovebin.song import Part, Song, key_map, tempo_map, with_keys, with_tempo
from groovebin.timing import KeyMap, TempoMap

METER = Event(0, b"\xff\x58\x04\x04\x02\x18\x08")
NAME = Event(0, b"\xff\x03\x03Kit")
VOLUME = Event(10, b"\xb9\x07\x64")


def test_with_tempo_moves_every_tempo_to_track_1_and_keeps_every_other_event():
    stray = Event(0, b"\xff\x51\x03\x07\xa1\x20")
    song = Song(960, 1, (Part(960, (), (METER,)), Part(960, (Note(0, 240, 10, 36, 100),), (NAME, stray, VOLUME))))
    out = read(write(with_tempo(song, TempoMap(((0, 600_000), (3840, 500_000))))))
    assert tempo_map(out).points == ((0, 600_000), (3840, 500_000))
    assert list(out.tracks[1].events) == [NAME, VOLUME]
    assert out.tracks[1].notes == song.tracks[1].notes
    assert [e.meta_type for e in out.tracks[0].events] == [0x58, 0x51, 0x51]


def test_a_defaulted_map_writes_no_tempo():
    song = Song(960, 0, (Part(960, (), (Event(0, b"\xff\x51\x03\x07\xa1\x20"),)),))
    assert tempo_map(read(write(with_tempo(song, TempoMap(()))))).defaulted


def test_with_keys_writes_signatures_that_key_map_reads_back():
    song = Song(960, 0, (Part(960, (Note(0, 240, 1, 60, 90),), (Event(0, bytes([0xFF, 0x59, 2, 1, 0])), METER)),))
    out = read(write(with_keys(song, KeyMap(((0, -6, False), (3840, 3, True))))))
    assert key_map(out).points == ((0, -6, False), (3840, 3, True))
    assert out.tracks[0].notes == song.tracks[0].notes and METER in out.tracks[0].events


def test_a_song_with_no_tracks_has_nowhere_to_write():
    with pytest.raises(ValueError, match="a song with no tracks has nowhere to write"):
        with_tempo(Song(960, 1, ()), TempoMap(()))
