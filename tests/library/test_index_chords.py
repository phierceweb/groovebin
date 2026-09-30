"""A folder index reads the chord file beside each groove: its chords, changes per bar and quality."""

import json
import sqlite3

import pytest
from smf_bytes import csv_row, pattern_file, write_csv

from groovebin.cli import main
from groovebin.library.index import build
from groovebin.library.search import search

LINE = pattern_file(960, [(0, 45, 90, 900), (3840, 41, 90, 900), (5760, 43, 90, 900)])


def chord_file(*chords):
    blocks = "".join(f"Chord {{\nNote {r} {b} {q}\nTime {s} {e}\nChordParts \n}}\n" for r, b, q, s, e in chords)
    return "ChordList {\n" + blocks + "}\n"


def rows(db):
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    try:
        return {r["file"]: dict(r) for r in con.execute("SELECT * FROM beats")}
    finally:
        con.close()


@pytest.fixture
def indexed(tmp_path):
    lib = tmp_path / "lib"
    lib.mkdir()
    for name in ("minor", "single", "bare", "older", "broken"):
        (lib / f"{name}.mid").write_bytes(LINE)
    (lib / "minor.midchordinfo").write_text(chord_file((9, 9, 1, 0, 4), (5, 5, 0, 4, 6), (7, 7, 0, 6, 8)))
    (lib / "single.midchordinfo").write_text(chord_file((0, 0, 0, 0, 8)))
    (lib / "older.midchordinfo").write_text("ClearChordLists\nOrgChord 7 7 0 0 1 0 -1 -1 0 1 8\n")
    (lib / "broken.midchordinfo").write_text("ChordList {\nChord {\nNote 14 0 0\nTime 0 4\n}\n}\n")
    db = tmp_path / "bass.sqlite"
    return db, build(db, folder=lib, map_name="ezbass")


def test_a_groove_keeps_its_chords_in_ticks_at_960(indexed):
    db, _counts = indexed
    row = rows(db)["minor.mid"]
    assert json.loads(row["chords"]) == [[0, 3840, "Am"], [3840, 5760, "F"], [5760, 7680, "G"]]
    assert (row["changes"], row["quality"]) == (1.0, "minor")
    single = rows(db)["single.mid"]
    assert (single["changes"], single["quality"]) == (0.0, "major")


def test_a_groove_without_a_readable_chord_file_has_none_and_is_counted(indexed):
    db, counts = indexed
    for name in ("bare", "broken"):
        row = rows(db)[f"{name}.mid"]
        assert (row["chords"], row["changes"], row["quality"], row["error"]) == (None, None, None, None)
    assert json.loads(rows(db)["older.mid"]["chords"]) == [[0, 7680, "G"]]
    assert (counts["chords"], counts["unread_chords"]) == (3, 1)


def test_search_by_changes_and_quality(indexed):
    db, _counts = indexed
    assert [r["file"] for r in search(db, quality="minor")] == ["minor.mid"]
    assert [r["file"] for r in search(db, changes="0")] == ["older.mid", "single.mid"]
    assert [r["file"] for r in search(db, changes=">0.5")] == ["minor.mid"]
    with pytest.raises(ValueError, match="major or minor"):
        search(db, quality="dorian")


def test_a_csv_index_reads_no_chord_files(tmp_path):
    db = tmp_path / "csv.sqlite"
    counts = build(db, csv_path=write_csv(tmp_path / "c" / "MidiDb.csv",
                                          [csv_row("a.mid", "G", "V", "Rock", "4/4", "100", True, "0.5", "0.5", LINE)]),
                   map_name="gm")
    assert (counts["chords"], counts["unread_chords"]) == (0, 0)


def run(capsys, *argv):
    rc = main([str(a) for a in argv])
    out, err = capsys.readouterr()
    return rc, out, err


def test_the_command_line_counts_shows_and_filters_chords(tmp_path, capsys):
    lib = tmp_path / "lib"
    lib.mkdir()
    (lib / "minor.mid").write_bytes(LINE)
    (lib / "minor.midchordinfo").write_text(chord_file((9, 9, 1, 0, 4), (5, 5, 0, 4, 6), (7, 7, 0, 6, 8)))
    (lib / "older.mid").write_bytes(LINE)
    (lib / "older.midchordinfo").write_text("ChordList {\nChord {\nNote 14 0 0\nTime 0 4\n}\n}\n")
    db = tmp_path / "bass.sqlite"
    rc, out, _err = run(capsys, "index", lib, "--map", "ezbass", "--db", db)
    assert rc == 0 and "  1 with chord labels beside it, 1 chord file(s) not read" in out.splitlines()
    rc, out, _err = run(capsys, "search", "--quality", "minor", "--changes", "1", "--json", "--db", db)
    (row,) = json.loads(out)
    rc, out, _err = run(capsys, "show", row["id"], "--db", db)
    assert "chords  Am (bar 1), F (bar 2), G (bar 2.5)" in out.splitlines()


def test_a_chord_file_that_does_not_read_is_counted_and_the_rest_are_indexed(tmp_path):
    lib = tmp_path / "lib"
    lib.mkdir()
    for name in ("good", "infinite", "utf16"):
        (lib / f"{name}.mid").write_bytes(LINE)
    (lib / "good.midchordinfo").write_text(chord_file((9, 9, 1, 0, 8)))
    (lib / "infinite.midchordinfo").write_text(chord_file((9, 9, 1, 0, "1e400")))
    (lib / "utf16.midchordinfo").write_text(chord_file((9, 9, 1, 0, 8)), encoding="utf-16")
    counts = build(tmp_path / "i.sqlite", folder=lib, map_name="ezbass")
    assert (counts["parsed"], counts["chords"], counts["unread_chords"]) == (3, 1, 2)
