"""The index keeps each pattern's channel events — controllers, aftertouch, pitch bend — beside its notes."""

import sqlite3

from groovebin.events import Event, Note
from groovebin.library.blobs import unpack_events
from groovebin.library.index import SCHEMA, build
from groovebin.library.pattern import pattern
from groovebin.library.search import get, search
from groovebin.midi import write
from groovebin.song import Part, Song

TEMPO = Event(0, b"\xff\x51\x03\x07\xa1\x20")
EVENTS = (Event(50, b"\xb0\x43\x40"), Event(60, b"\xa0\x2d\x30"), Event(2000, b"\xe0\x00\x50"), Event(2100, b"\xc0\x05"))


def indexed(tmp_path):
    lib = tmp_path / "lib"
    lib.mkdir()
    notes = (Note(0, 400, 1, 45, 90), Note(1920, 400, 1, 40, 90))
    (lib / "line.mid").write_bytes(write(Song(480, 0, (Part(480, notes, (TEMPO, *EVENTS)),))))
    db = tmp_path / "bass.sqlite"
    build(db, folder=lib, map_name="ezbass")
    return db


def test_a_row_keeps_its_channel_events_at_960_and_no_meta(tmp_path):
    db = indexed(tmp_path)
    (row,) = search(db)
    events = unpack_events(get(db, row["id"])["events"])
    assert events == [Event(100, b"\xb0\x43\x40"), Event(120, b"\xa0\x2d\x30"), Event(4000, b"\xe0\x00\x50"),
                      Event(4200, b"\xc0\x05")]


def test_a_pattern_gives_each_bar_its_events(tmp_path):
    db = indexed(tmp_path)
    (row,) = search(db)
    p = pattern(get(db, row["id"]))
    assert [e.tick for e in p.bar_events(0)] == [100, 120] and [e.tick for e in p.bar_events(1)] == [160, 360]


def test_the_index_is_schema_4(tmp_path):
    con = sqlite3.connect(indexed(tmp_path))
    try:
        assert con.execute("SELECT value FROM meta WHERE name = 'schema'").fetchone() == (str(SCHEMA),)
    finally:
        con.close()
    assert SCHEMA == 4
