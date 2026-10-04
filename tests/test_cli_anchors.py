"""`groovebin anchors`: where a drum file's kick, snare and hands strike, bar by bar."""

import json

from groovebin.cli import main
from groovebin.events import Event, Note
from groovebin.midi import write
from groovebin.song import Part, Song

KICK, SNARE, HAT = 36, 38, 42
FOUR_FOUR = b"\xff\x58\x04\x04\x02\x18\x08"
BEAT = [(0, KICK), (1920, KICK), (960, SNARE), (2880, SNARE), *((t, HAT) for t in range(0, 3840, 480))]
LANES = "kick=x.......x....... snare=....x.......x... hands=x.x.x.x.x.x.x.x."


def drums(path, hits, meter=FOUR_FOUR):
    notes = tuple(Note(t, 60, 10, p, 100) for t, p in hits)
    path.write_bytes(write(Song(960, 1, (Part(960, (), (Event(0, meter),)), Part(960, notes)))))
    return path


def run(capsys, *argv):
    rc = main([str(a) for a in argv])
    out, err = capsys.readouterr()
    return rc, out, err


def test_each_bar_prints_its_lanes_and_the_file_prints_as_rhythm(tmp_path, capsys):
    f = drums(tmp_path / "in.mid", BEAT + [(3840 + t, p) for t, p in BEAT])
    rc, out, err = run(capsys, "anchors", f, "--map", "gm")
    assert (rc, err) == (0, "")
    assert out.splitlines() == [
        "in.mid: 2 bar(s), a sixteenth a step", f"bar 1  {LANES}", f"bar 2  {LANES}",
        "kick=x.......x.......|x.......x....... snare=....x.......x...|....x.......x... "
        "hands=x.x.x.x.x.x.x.x.|x.x.x.x.x.x.x.x."]


def test_bars_and_json(tmp_path, capsys):
    f = drums(tmp_path / "in.mid", BEAT + [(3840 + t, p) for t, p in BEAT])
    rc, out, _err = run(capsys, "anchors", f, "--map", "gm", "--bars", "1", "--json")
    assert rc == 0 and json.loads(out) == [{"bar": 1, "steps": 16, "kick": "x.......x.......",
                                            "snare": "....x.......x...", "hands": "x.x.x.x.x.x.x.x."}]


def test_a_bar_with_no_whole_sixteenths_says_so(tmp_path, capsys):
    f = drums(tmp_path / "in.mid", [(0, KICK)], meter=b"\xff\x58\x04\x03\x05\x18\x08")
    rc, out, _err = run(capsys, "anchors", f, "--map", "gm")
    assert rc == 0 and out.splitlines() == ["in.mid: 1 bar(s), a sixteenth a step",
                                            "bar 1  - (3/32 holds no whole number of sixteenths)",
                                            "no lanes for search --rhythm: a bar holds no whole number of sixteenths"]


def test_no_notes_and_no_bars_are_refused(tmp_path, capsys):
    f = drums(tmp_path / "in.mid", BEAT)
    rc, _out, err = run(capsys, "anchors", f, "--map", "gm", "--bars", "0")
    assert rc == 1 and "--bars 0: 1 or more" in err
    rc, _out, err = run(capsys, "anchors", f, "--map", "gm", "--track", "1")
    assert rc == 1 and "in.mid has no notes on the tracks read" in err


def test_bars_past_the_last_note_are_not_built(tmp_path, capsys):
    f = drums(tmp_path / "in.mid", BEAT)
    rc, out, _err = run(capsys, "anchors", f, "--map", "gm", "--bars", "100000000")
    assert rc == 0 and out.splitlines()[0] == "in.mid: 1 bar(s), a sixteenth a step"


def test_a_last_note_rounding_onto_the_next_bar_line_starts_that_bar(tmp_path, capsys):
    f = drums(tmp_path / "in.mid", BEAT + [(3840 - 10, KICK)])
    for argv in ((), ("--bars", "2")):
        rc, out, _err = run(capsys, "anchors", f, "--map", "gm", *argv)
        assert rc == 0 and out.splitlines()[2] == "bar 2  kick=x............... snare=................ hands=................"


def test_a_file_with_no_kick_snare_or_hands_has_no_lanes_to_search_with(tmp_path, capsys):
    rc, out, _err = run(capsys, "anchors", drums(tmp_path / "in.mid", [(0, 45), (960, 47)]), "--map", "gm")
    assert rc == 0 and out.splitlines()[-1] == "no lanes for search --rhythm: no kick, snare or hands note"
