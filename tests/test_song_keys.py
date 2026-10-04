"""Key signatures read from every track of a song."""

from groovebin.events import Event
from groovebin.song import Part, Song, key_map, key_signature, skipped_keys


def signature(tick, sharps, minor):
    return Event(tick, bytes([0xFF, 0x59, 2, sharps & 0xFF, minor]))


def test_key_map_reads_every_track_and_skips_what_it_cannot_read():
    bad = (Event(0, b"\xff\x59\x01\x00"), Event(0, b"\xff\x59\x02\x08\x00"), Event(0, b"\xff\x59\x02\x00\x02"))
    song = Song(960, 1, (Part(960, (), (signature(0, -3, 1), *bad)), Part(960, (), (signature(3840, 2, 0),))))
    assert key_map(song).points == ((0, -3, True), (3840, 2, False))
    assert skipped_keys(song) == 3


def test_a_song_with_no_signature_has_an_empty_key_map():
    assert key_map(Song(960, 0, (Part(960),))).defaulted


def test_key_signature_reads_one_event():
    assert (key_signature(signature(0, -3, 1)), key_signature(Event(0, b"\xff\x03\x01K"))) == ((-3, True), None)
