import json
import sqlite3

from smf_bytes import TWO_BARS, csv_row, pattern_file, write_csv

from groovebin.library.index import build
from groovebin.library.search import get
from groovebin.library.show import accents, show
from groovebin.maps import stroke


def one_row(tmp_path, data, map_name):
    db = tmp_path / "library.sqlite"
    lines = [csv_row("a.mid", "Alpha 50% Mix", "Verse 01", "Rock", "4/4", "97.999985", True, "0.5", "0.72", data)]
    build(db, csv_path=write_csv(tmp_path / "csv" / "MidiDb.csv", lines), map_name=map_name)
    con = sqlite3.connect(db)
    (pattern_id,) = con.execute("SELECT id FROM beats").fetchone()
    con.close()
    return get(db, pattern_id)


def test_a_drum_row_shows_a_lane_per_note_number_and_a_cell_per_sixteenth(tmp_path):
    r = one_row(tmp_path, TWO_BARS, "gm")
    lines = show(r).splitlines()
    assert lines[0] == f"{r['id']}  Lib One / Rock / Alpha 50% Mix / Verse 01  4/4  98 bpm  2 bar(s)"
    assert lines[1] == "feel  density 2.5  syncopation 2  subdivision quarters  swing8 -  swing16 -  lag 0  accent -"
    assert [line.split()[:2] for line in lines[2:5]] == [["accent", "kick"], ["accent", "snare"], ["accent", "hands"]]
    assert lines[5:] == [" 42 |x...............|....o...........|",
                         " 38 |........x.......|................|",
                         " 36 |X...............|...............X|"]


def test_lanes_can_name_their_strokes(tmp_path):
    r = one_row(tmp_path, TWO_BARS, "gm")
    assert show(r, lambda pitch: stroke("gm", pitch)).splitlines()[5] == " 42 Closed Hi Hat  |x...............|....o...........|"


def test_a_row_without_a_drum_map_shows_a_piano_roll_with_sustain(tmp_path):
    r = one_row(tmp_path, pattern_file(960, [(0, 60, 100, 480), (480, 64, 70, 240)]), None)
    assert show(r).splitlines()[1:] == ["  E4 |..x.............|",
                                        " D#4 |................|",
                                        "  D4 |................|",
                                        " C#4 |................|",
                                        "  C4 |X=..............|"]


def test_a_row_that_did_not_parse_says_so(tmp_path):
    r = one_row(tmp_path, "4D546864", "gm")
    assert show(r) == f"{r['id']}  a.mid: not parsed (the MThd header ends 10 bytes short)"


def test_accents_print_each_voices_profile_in_percent():
    row = {"accents": json.dumps({"kick": {"16": [1.33, *[None] * 7, 0.67, *[None] * 7]}})}
    assert accents(row) == ["accent kick  " + " ".join(["133", *["  ."] * 7, " 67", *["  ."] * 7])]
    assert accents({"accents": None}) == []
