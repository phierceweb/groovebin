import json
import os
import sqlite3
from pathlib import Path

import pytest
from smf_bytes import BARE, CSV_HEADER, EOT, FORMAT_1, TWO_BARS, csv_row, smf, write_csv

from groovebin.events import Note
from groovebin.library.index import build, unpack_notes
from groovebin.library.search import search

TWO_BAR_NOTES = [Note(0, 120, 10, 36, 100, 64), Note(0, 60, 10, 42, 80), Note(480, 60, 10, 38, 90),
                 Note(1200, 60, 10, 42, 48), Note(1860, 40, 10, 36, 127)]


def rows(db, where="1"):
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in con.execute(f"SELECT * FROM beats WHERE {where} ORDER BY file")]
    finally:
        con.close()


@pytest.fixture
def csv_index(tmp_path):
    lines = [csv_row("a.mid", "Alpha", "Verse 01", "Rock", "4/4", "97.999985", True, "0.5", "0.72", TWO_BARS),
             csv_row("b.mid", "Beta", "Fills 02", "jazz", "3/4", "125.0", False, "0.66", "0.4", FORMAT_1),
             csv_row("c.mid", "Gamma", "Chorus", "Rock", "4/4", "140.0", True, "0.5", "0.9", "4D546864")]
    source = write_csv(tmp_path / "acct" / "MidiDb.csv", [*lines, lines[0]])
    db = tmp_path / "cache" / "library.sqlite"
    return source, db, build(db, csv_path=source, map_name="addictive-drums-2")


def test_a_meter_change_after_bar_1_labels_the_row_with_bar_1s_meter(tmp_path):
    from groovebin.events import Event
    from groovebin.midi import write
    from groovebin.song import Part, Song
    six_eight_at_bar_2 = Event(3840, bytes([0xFF, 0x58, 4, 6, 3, 24, 8]))
    notes = tuple(Note(t, 240, 10, 36, 100) for t in range(0, 7680, 480))
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "a.mid").write_bytes(write(Song(960, 1, (Part(960, notes, (six_eight_at_bar_2,), None),))))
    db = tmp_path / "library.sqlite"
    build(db, folder=tmp_path / "lib", map_name="gm")
    (row,) = rows(db)
    assert (row["meter"], json.loads(row["meters"])) == ("4/4", [[0, 4, 4], [3840, 6, 8]])


def test_a_csv_index_counts_rows_and_keeps_the_csvs_columns_and_the_parsed_file(csv_index):
    _source, db, counts = csv_index
    assert counts == {"rows": 4, "parsed": 2, "failed": 1, "duplicates": 1}
    a, b, c = rows(db)
    assert (a["ppq"], a["bars"], a["meter"], a["tempo"], a["is_beat"], a["is_fill"], a["role"], a["map"]) == \
           (240, 2, "4/4", 97.999985, 1, 0, "verse", "addictive-drums-2")
    assert json.loads(a["histogram"]) == {"36": 2, "38": 1, "42": 2}
    assert unpack_notes(a["notes"]) == [Note(n.tick * 4, n.length * 4, n.channel, n.pitch, n.velocity) for n in TWO_BAR_NOTES]
    assert (b["ppq"], b["bars"], json.loads(b["meters"]), b["is_fill"], b["role"]) == (480, 1, [[0, 3, 4]], 1, None)
    assert unpack_notes(b["notes"]) == [Note(0, 480, 1, 60, 100), Note(480, 960, 10, 36, 112)]
    assert (len(a["id"]), c["group_name"], c["notes"]) == (10, "Gamma", None)
    assert c["error"].startswith("the MThd header ends")


def test_a_folder_index_takes_labels_from_the_path_and_meter_and_tempo_from_the_file(tmp_path):
    folder = tmp_path / "pack"
    (folder / "Rock" / "Verse").mkdir(parents=True)
    (folder / "Rock" / "Verse" / "Kit_V_Verse 02_C_Hard Rock.mid").write_bytes(TWO_BARS)
    (folder / "Swing 6-8 at 90bpm").mkdir()
    (folder / "Swing 6-8 at 90bpm" / "Tom Fill.mid").write_bytes(BARE)
    (folder / "notes.txt").write_text("not midi")
    db = tmp_path / "folder.sqlite"
    assert build(db, folder=folder, map_name="gm") == {"rows": 2, "parsed": 2, "failed": 0, "duplicates": 0}
    verse, fill = rows(db)
    assert (verse["file"], verse["group_name"], verse["variant"], verse["category"], verse["role"], verse["is_fill"],
            verse["is_beat"], verse["meter"], verse["tempo"], verse["map"], verse["source"]) == \
           ("Rock/Verse/Kit_V_Verse 02_C_Hard Rock.mid", "Kit", "Verse 02", "Hard Rock", "verse", 0, 1, "4/4", 120.0,
            "gm", "folder")
    assert (fill["is_fill"], fill["meter"], fill["tempo"], fill["bars"], json.loads(fill["meters"])) == \
           (1, "6/8", 90.0, 1, [[0, 6, 8]])


def test_a_row_that_does_not_parse_or_runs_out_of_range_is_a_failed_row_not_a_failed_build(tmp_path):
    folder = tmp_path / "odd"
    folder.mkdir()
    (folder / "a.mid").write_bytes(TWO_BARS)
    far = smf(0, 1, [(0, b"\xff\x58\x04\xff\x00\x18\x08"), (4_500_000, b"\x99\x24\x64"), (1, b"\x24\x00"), (0, EOT)])
    (folder / "far.mid").write_bytes(far)
    db = tmp_path / "odd.sqlite"
    assert build(db, folder=folder, map_name="gm") == {"rows": 2, "parsed": 1, "failed": 1, "duplicates": 0}
    assert "past the index's 32-bit tick range" in rows(db, "file = 'far.mid'")[0]["error"]
    lines = [csv_row(f"{n}.mid", "G", n, "Rock", "4/4", "120", True, "0.5", "0.5", TWO_BARS) for n in ("ok", "inf", "big")]
    lines[1][CSV_HEADER.index("HH_Type")], lines[2][CSV_HEADER.index("KK_Vel")] = "inf", "1e30"
    db = tmp_path / "odd-csv.sqlite"
    assert build(db, csv_path=write_csv(tmp_path / "odd" / "MidiDb.csv", lines), map_name="gm")["failed"] == 2
    errors = {r["file"]: r["error"] for r in rows(db)}
    assert (errors["ok.mid"], errors["inf.mid"][:14], errors["big.mid"][:13]) == (None, "HH_Type 'inf':", "KK_Vel '1e30'")


def test_a_rebuild_is_identical_and_a_failed_build_keeps_the_old_index(csv_index, tmp_path):
    source, db, counts = csv_index
    before = rows(db)
    assert build(db, csv_path=source, map_name="addictive-drums-2") == counts
    assert rows(db) == before
    bad = tmp_path / "bad.csv"
    bad.write_text("FileName,Group\nx,y\n")
    with pytest.raises(ValueError, match="bad.csv has no MidiData column"):
        build(db, csv_path=bad, map_name="gm")
    assert rows(db) == before and sorted(p.name for p in db.parent.iterdir()) == ["library.sqlite"]


def test_the_index_never_replaces_its_source_or_a_file_that_is_not_an_index(csv_index, tmp_path):
    source, _db, _ = csv_index
    folder, text, empty = tmp_path / "pack", tmp_path / "notes.txt", tmp_path / "other.sqlite"
    (folder / "sub").mkdir(parents=True)
    (folder / "a.mid").write_bytes(TWO_BARS)
    text.write_text("keep")
    sqlite3.connect(empty).close()
    cases = [(source, {"csv_path": source}, "is the CSV it reads"),
             (folder / "sub" / "x.sqlite", {"folder": folder}, "inside the folder it reads"),
             (text, {"csv_path": source}, "exists and is not a pattern library index"),
             (empty, {"folder": folder}, "exists and is not a pattern library index")]
    for db, kwargs, message in cases:
        with pytest.raises(ValueError, match=message):
            build(db, map_name="gm", **kwargs)
    assert (text.read_text(), empty.stat().st_size, sorted(p.name for p in folder.rglob("*"))) == ("keep", 0, ["a.mid", "sub"])


def test_build_refusals(tmp_path):
    with pytest.raises(ValueError, match="index one source: a MidiDb.csv or a folder of .mid files"):
        build(tmp_path / "x.sqlite", map_name="gm")
    with pytest.raises(FileNotFoundError, match="no folder at"):
        build(tmp_path / "x.sqlite", folder=tmp_path / "missing", map_name="gm")
    with pytest.raises(ValueError, match="no note map 'sd3'"):
        build(tmp_path / "x.sqlite", folder=tmp_path, map_name="sd3")


def test_a_csv_with_a_byte_order_mark_reads(tmp_path):
    lines = [csv_row("a.mid", "G", "V", "Rock", "4/4", "120", True, "0.5", "0.5", TWO_BARS)]
    source = write_csv(tmp_path / "bom" / "MidiDb.csv", lines, encoding="utf-8-sig")
    assert build(tmp_path / "bom.sqlite", csv_path=source, map_name="gm")["parsed"] == 1


def test_a_file_with_no_meter_in_it_or_its_path_is_indexed_in_the_default_4_4(tmp_path):
    folder = tmp_path / "pack"
    folder.mkdir()
    (folder / "loop.mid").write_bytes(BARE)
    build(tmp_path / "folder.sqlite", folder=folder, map_name="gm")
    assert rows(tmp_path / "folder.sqlite")[0]["meter"] == "4/4"
    lines = [csv_row("bare.mid", "G", "V", "Rock", "", "120", True, "0.5", "0.5", BARE),
             csv_row("waltz.mid", "G", "W", "Rock", "", "120", True, "0.5", "0.5", FORMAT_1)]
    build(tmp_path / "csv.sqlite", csv_path=write_csv(tmp_path / "csv" / "MidiDb.csv", lines), map_name="gm")
    assert [r["meter"] for r in rows(tmp_path / "csv.sqlite")] == ["4/4", "3/4"]


def test_a_file_whose_meter_changes_after_bar_1_is_labelled_with_bar_1s_meter(tmp_path):
    later = smf(0, 480, [(0, b"\x99\x24\x64"), (240, b"\x89\x24\x00"), (1680, b"\xff\x58\x04\x03\x02\x18\x08"),
                         (0, b"\x99\x26\x64"), (240, b"\x89\x26\x00"), (0, EOT)])
    folder = tmp_path / "Waltz 3-4"
    folder.mkdir()
    (folder / "later.mid").write_bytes(later)
    build(tmp_path / "folder.sqlite", folder=folder, map_name="gm")
    lines = [csv_row("later.mid", "G", "V", "Rock", "", "120", True, "0.5", "0.5", later)]
    build(tmp_path / "csv.sqlite", csv_path=write_csv(tmp_path / "csv" / "MidiDb.csv", lines), map_name="gm")
    for db in ("folder.sqlite", "csv.sqlite"):
        (row,) = rows(tmp_path / db)
        assert (row["meter"], row["bars"], json.loads(row["meters"])) == ("4/4", 2, [[0, 4, 4], [3840, 3, 4]])


def test_a_file_that_cannot_be_opened_is_a_failed_row_not_a_failed_build(tmp_path, monkeypatch):
    folder = tmp_path / "pack"
    folder.mkdir()
    (folder / "a.mid").write_bytes(TWO_BARS)
    (folder / "locked.mid").write_bytes(TWO_BARS)
    real = Path.read_bytes

    def read_bytes(path):
        if path.name == "locked.mid":
            raise PermissionError(13, "Permission denied", str(path))
        return real(path)

    monkeypatch.setattr(Path, "read_bytes", read_bytes)
    db = tmp_path / "locked.sqlite"
    assert build(db, folder=folder, map_name="gm") == {"rows": 2, "parsed": 1, "failed": 1, "duplicates": 0}
    assert rows(db, "file = 'locked.mid'")[0]["error"] == "not read: Permission denied"


@pytest.mark.skipif(os.geteuid() == 0, reason="root lists a folder whatever its permissions")
def test_a_subfolder_that_cannot_be_listed_is_a_failed_row_and_an_unlistable_folder_fails_the_build(tmp_path):
    folder = tmp_path / "pack"
    (folder / "locked").mkdir(parents=True)
    (folder / "a.mid").write_bytes(TWO_BARS)
    (folder / "locked" / "b.mid").write_bytes(TWO_BARS)
    db = tmp_path / "locked.sqlite"
    try:
        (folder / "locked").chmod(0)
        counts = build(db, folder=folder, map_name="gm")
        folder.chmod(0)
        with pytest.raises(PermissionError):
            build(tmp_path / "root.sqlite", folder=folder, map_name="gm")
    finally:
        folder.chmod(0o755)
        (folder / "locked").chmod(0o755)
    assert counts == {"rows": 2, "parsed": 1, "failed": 1, "duplicates": 0}
    assert rows(db, "file = 'locked'")[0]["error"] == "not listed: Permission denied"
    assert [r["file"] for r in search(db, limit=None)] == ["a.mid"]
    assert not (tmp_path / "root.sqlite").exists()


def test_a_file_whose_only_signature_the_ppq_cannot_hold_is_filed_with_no_meter(tmp_path):
    """4/4 there is the meter map's fallback, not the file's. Recording it would file the pattern
    under a meter it never held, where `search --meter 4/4` would find it."""
    from groovebin.events import Event
    from groovebin.midi import write
    from groovebin.song import Part, Song
    folder = tmp_path / "lib"
    folder.mkdir()
    sixty_fourth = Event(0, b"\xff\x58\x04\x01\x06\x18\x08")
    (folder / "x.mid").write_bytes(write(Song(120, 1, (Part(120, (Note(0, 12, 10, 36, 100),), (sixty_fourth,)),))))
    (folder / "y.mid").write_bytes(write(Song(120, 1, (Part(120, (Note(0, 12, 10, 36, 100),)),))))
    db = tmp_path / "i.db"
    build(db, folder=folder, map_name=None)
    by_file = {Path(r["file"]).name: r["meter"] for r in rows(db)}
    assert by_file["x.mid"] is None
    assert by_file["y.mid"] == "4/4"                     # no signature at all: the format's own default
    assert [r["file"] for r in search(db, meter="4/4")] == [r["file"] for r in rows(db, "file LIKE '%y.mid'")]
