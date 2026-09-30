import json
import sqlite3

import pytest
from smf_bytes import csv_row, pattern_file, write_csv

from groovebin.library.index import SCHEMA, build

KICK, SNARE, HAT = 36, 38, 42
BACKBEAT = [(t, p, 100, 60) for bar in (0, 3840) for t, p in
            [(bar, KICK), (bar + 1920, KICK), (bar + 960, SNARE), (bar + 2880, SNARE),
             *((bar + h, HAT) for h in range(0, 3840, 480))]]
SHUFFLE = [(t, p, 100, 60) for bar in (0, 3840) for t, p in
           [(bar, KICK), (bar + 960, SNARE), (bar + 1920, KICK), (bar + 2880, SNARE),
            *((bar + beat + o, HAT) for beat in range(0, 3840, 960) for o in (0, 640))]]
GROOVE = ("rhythm", "density", "syncopation", "subdivision", "swing8", "swing16", "lag")


def rows(db):
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    try:
        return {r["file"]: dict(r) for r in con.execute("SELECT * FROM beats")}
    finally:
        con.close()


def folder_index(tmp_path, map_name="gm"):
    lib = tmp_path / "lib"
    lib.mkdir()
    (lib / "backbeat.mid").write_bytes(pattern_file(960, BACKBEAT))
    (lib / "shuffle.mid").write_bytes(pattern_file(480, [(t // 2, p, v, n // 2) for t, p, v, n in SHUFFLE]))
    (lib / "broken.mid").write_bytes(b"MThd")
    db = tmp_path / "library.sqlite"
    build(db, folder=lib, map_name=map_name)
    return db


def test_a_mapped_row_records_its_rhythm_and_feel(tmp_path):
    row = rows(folder_index(tmp_path))["backbeat.mid"]
    eighths = sum(1 << s for s in range(0, 16, 2))
    assert json.loads(row["rhythm"]) == [[16, 1 | 1 << 8, 1 << 4 | 1 << 12, eighths]] * 2
    assert {k: row[k] for k in GROOVE[1:]} == {"density": 12.0, "syncopation": 0.0, "subdivision": "8ths",
                                               "swing8": 0.5, "swing16": None, "lag": 0.0}


def test_the_feel_is_read_at_the_files_own_ppq(tmp_path):
    row = rows(folder_index(tmp_path))["shuffle.mid"]
    assert (row["subdivision"], row["swing8"]) == ("triplets", 0.667)


def test_a_library_that_is_not_drums_records_no_feel(tmp_path):
    for row in rows(folder_index(tmp_path, map_name=None)).values():
        assert {k: row[k] for k in GROOVE} == dict.fromkeys(GROOVE)


def test_a_row_that_did_not_parse_records_no_feel(tmp_path):
    row = rows(folder_index(tmp_path))["broken.mid"]
    assert row["error"] and {k: row[k] for k in GROOVE} == dict.fromkeys(GROOVE)


def test_the_sources_own_swing_label_is_kept_beside_the_measure(tmp_path):
    line = csv_row("s.mid", "Kit", "Shuffle", "Blues", "4/4", "90", True, "0.2", "0.5", pattern_file(960, SHUFFLE))
    db = tmp_path / "library.sqlite"
    build(db, csv_path=write_csv(tmp_path / "csv" / "MidiDb.csv", [line]), map_name="gm")
    (row,) = rows(db).values()
    assert (row["swing"], row["swing8"]) == (0.2, 0.667)


def test_the_index_records_its_schema(tmp_path):
    con = sqlite3.connect(folder_index(tmp_path))
    try:
        assert con.execute("SELECT value FROM meta WHERE name = 'schema'").fetchone() == (str(SCHEMA),)
    finally:
        con.close()


@pytest.mark.parametrize("column", GROOVE)
def test_every_feel_column_exists_even_when_empty(tmp_path, column):
    assert column in rows(folder_index(tmp_path, map_name=None))["backbeat.mid"]
