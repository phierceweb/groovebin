"""The chord files EZbass keeps beside its grooves, read into chords. Each test writes its own."""

import json

import pytest

from groovebin.harmony import Chord
from groovebin.library.sidecar import SIDECAR, chords, columns, read_beside


def chord_block(root, bass, flag, time, parts=""):
    return f"Chord {{\nNote {root} {bass} {flag}\n{time}\nChordParts {parts}\n}}\n"


def test_time_in_quarters_and_the_flag_as_major_or_minor():
    text = "ChordList {\n" + chord_block(9, 9, 1, "Time 0 4", "6") + chord_block(5, 5, 0, "Time 4 6") + \
           chord_block(0, 7, 0, "Time 6 8") + "}\n"
    assert chords(text) == ((0.0, 4.0, Chord(9, "min")), (4.0, 6.0, Chord(5, "maj")), (6.0, 8.0, Chord(0, "maj", 7)))


def test_ttime_adds_ticks_at_96000_a_quarter():
    text = "ChordList {\n" + chord_block(2, 2, 0, "TTime 0 48000 3 0") + "}\n"
    assert chords(text) == ((0.5, 3.0, Chord(2, "maj")),)


def test_windows_line_ends_and_fractional_quarters_read():
    text = ("ChordList {\n" + chord_block(4, 4, 1, "Time 0 27.875") + "}\n").replace("\n", "\r\n")
    assert chords(text) == ((0.0, 27.875, Chord(4, "min")),)


def test_an_empty_list_has_no_chords():
    assert chords("ChordList {\n}\n") == ()


OLDER = """ClearChordLists
OrgChord 9 9 1 0 1 0 -1 -1 0 1 2
OrgChordParts 6
Chord 0 0 0 0 1 0 45 2 0 1 2
ChordStyle 0.5 0 0 0 0

OrgChord 5 5 0 2 1 0 -1 -1 0 1 4
OrgChordParts
Chord 5 5 0 2 1 0 -1 -1 0 1 4
"""


def test_the_older_layout_reads_its_orgchord_lines():
    """root bass flag start, six fields, end: the OrgChord line, which agrees with the notes; Chord lines are not
    read."""
    assert chords(OLDER) == ((0.0, 2.0, Chord(9, "min")), (2.0, 4.0, Chord(5, "maj")))


@pytest.mark.parametrize("bad", ["Note 12 0 0\nTime 0 4", "Note 0 0 2\nTime 0 4", "Note 0 0 0\nTime 4 2",
                                 "Note 0 0\nTime 0 4", "Note 0 0 0\nTime x 4"])
def test_a_chord_the_reader_cannot_trust_is_refused(bad):
    with pytest.raises(ValueError, match="chord file"):
        chords("ChordList {\nChord {\n" + bad + "\n}\n}\n")


def test_the_file_beside_a_groove(tmp_path):
    groove = tmp_path / "Verse 01.mid"
    groove.write_bytes(b"")
    assert read_beside(groove) is None
    (tmp_path / f"Verse 01{SIDECAR}").write_text("ChordList {\n" + chord_block(7, 7, 0, "Time 0 4") + "}\n")
    assert read_beside(groove) == ((0.0, 4.0, Chord(7, "maj")),)


def test_a_last_orgchord_ending_at_0_runs_to_the_end_of_the_groove():
    text = "OrgChord 9 9 1 0 1 0 -1 -1 0 1 4\nOrgChord 7 7 0 4 1 0 -1 -1 0 1 0\n"
    assert chords(text) == ((0.0, 4.0, Chord(9, "min")), (4.0, None, Chord(7, "maj")))
    with pytest.raises(ValueError, match="start before its end"):
        chords("OrgChord 9 9 1 0 1 0 -1 -1 0 1 0\nOrgChord 7 7 0 4 1 0 -1 -1 0 1 8\n")


def test_an_open_last_chord_closes_at_the_grooves_length():
    found = ((0.0, 4.0, Chord(9, "min")), (4.0, None, Chord(7, "maj")))
    assert json.loads(columns(found, 3, 960, 12.0)["chords"]) == [[0, 3840, "Am"], [3840, 11520, "G"]]


@pytest.mark.parametrize("bad", ["Note inf 9 1\nTime 0 4", "Note 9 9 1\nTime 4 1e400", "Note 9 9 1\nTime nan 4"])
def test_a_number_that_is_not_finite_is_refused(bad):
    with pytest.raises(ValueError, match="chord file"):
        chords("ChordList {\nChord {\n" + bad + "\n}\n}\n")
    with pytest.raises(ValueError, match="chord file"):
        chords("OrgChord 9 9 1 0 1 0 -1 -1 0 1 inf\n")


@pytest.mark.parametrize("text", ["", "hello", "\ufeffC\x00h\x00o\x00r\x00d\x00", "OrgChordParts 6\n"])
def test_text_that_is_not_a_chord_file_is_refused(text):
    with pytest.raises(ValueError, match="not a chord file|no OrgChord line"):
        chords(text)


def test_an_indented_orgchord_line_reads():
    assert chords("  OrgChord 9 9 1 0 1 0 -1 -1 0 1 4\n") == ((0.0, 4.0, Chord(9, "min")),)


def test_an_open_last_chord_that_starts_at_the_grooves_end_is_left_out():
    found = ((0.0, 4.0, Chord(9, "min")), (12.0, None, Chord(7, "maj")))
    assert json.loads(columns(found, 3, 960, 12.0)["chords"]) == [[0, 3840, "Am"]]
    assert json.loads(columns(((10.0, None, Chord(5, "maj")),) + found[:1], 2, 960, 8.0)["chords"]) == [[0, 3840, "Am"]]
