"""`groovebin feel` on files the test builds: a reference's feel lands on the tracks named, everything else
comes back as it was, and the refusals name their rule."""

import json

import pytest

from groovebin.cli import main
from groovebin.events import Event, Note
from groovebin.library.index import build
from groovebin.midi import read, write
from groovebin.song import Part, Song

PPQ = 960
KICK, SNARE, HAT = 36, 38, 42
METER = Event(0, bytes([0xFF, 0x58, 4, 4, 2, 24, 8]))


def hits(pairs, velocity=80):
    return tuple(Note(t, 120, 10, p, velocity) for t, p in pairs)


def swung():
    pairs = [(b + t, p) for b in (0, 3840) for t, p in ((0, KICK), (1920, KICK), (980, SNARE), (2900, SNARE))]
    notes = hits(pairs, 100) + tuple(Note(b + beat * PPQ + o, 120, 10, HAT, v)
                                     for b in (0, 3840) for beat in range(4) for o, v in ((0, 110), (640, 60)))
    return write(Song(PPQ, 0, (Part(PPQ, notes, (METER,)),)))


def straight(tracks=1):
    notes = hits([(0, KICK), (1920, KICK), (960, SNARE), (2880, SNARE)] + [(t, HAT) for t in range(0, 3840, 480)])
    cc = Event(0, bytes([0xB9, 7, 100]))
    return Song(PPQ, 1, tuple(Part(PPQ, notes, (METER, cc) if k == 0 else ()) for k in range(tracks)))


def run(capsys, *argv):
    rc = main([str(a) for a in argv])
    out, err = capsys.readouterr()
    return rc, out, err


@pytest.fixture
def files(tmp_path):
    (tmp_path / "ref.mid").write_bytes(swung())
    (tmp_path / "in.mid").write_bytes(write(straight(tracks=2)))
    return tmp_path


def hat_ticks(part):
    return sorted(n.tick for n in part.notes if n.pitch == HAT)


def test_the_references_feel_lands_and_the_rest_comes_back(files, capsys):
    out = files / "out.mid"
    rc, text, err = run(capsys, "feel", files / "in.mid", "--from", files / "ref.mid", "--map", "gm", "-o", out)
    assert (rc, err) == (0, "")
    assert text.splitlines() == ["feel of ref.mid on an eighth-note grid: 12 of 24 note(s) moved", f"out : {out}"]
    song, before = read(out.read_bytes()), straight(tracks=2)
    assert all(hat_ticks(t) == [0, 640, 960, 1600, 1920, 2560, 2880, 3520] for t in song.tracks)
    assert [t.events for t in song.tracks] == [t.events for t in before.tracks]


def test_shares_and_a_track(files, capsys):
    out = files / "half.mid"
    rc, _text, _err = run(capsys, "feel", files / "in.mid", "--from", files / "ref.mid", "--map", "gm",
                          "--timing", 50, "--velocity", 0, "--track", 2, "-o", out)
    first, second = read(out.read_bytes()).tracks
    assert rc == 0
    assert hat_ticks(first) == list(range(0, 3840, 480))
    assert hat_ticks(second)[:2] == [0, 560] and {n.velocity for n in second.notes} == {80}


def test_a_grid_can_be_named(files, capsys):
    rc, text, _err = run(capsys, "feel", files / "in.mid", "--from", files / "ref.mid", "--map", "gm",
                         "--grid", 16, "-o", files / "g.mid")
    assert rc == 0
    assert text.splitlines()[0] == ("feel of ref.mid on a sixteenth-note grid: 4 of 24 note(s) moved, "
                                     "8 left as they were, with no reference feel at their place")


def test_the_feel_of_a_library_pattern(files, capsys):
    lib = files / "lib"
    lib.mkdir()
    (lib / "swung.mid").write_bytes(swung())
    db = files / "library.sqlite"
    build(db, folder=lib, map_name="gm")
    _rc, out, _err = run(capsys, "search", "--json", "--db", db)
    pattern_id = json.loads(out)[0]["id"]
    rc, text, err = run(capsys, "feel", files / "in.mid", "--from", pattern_id, "--map", "gm", "--db", db,
                        "-o", files / "lib.mid")
    assert (rc, err) == (0, "") and text.startswith(f"feel of pattern {pattern_id} on an eighth-note grid")
    assert hat_ticks(read((files / "lib.mid").read_bytes()).tracks[0])[:2] == [0, 640]


@pytest.mark.parametrize(("extra", "message"), [
    (("--timing", "150"), "--timing 150: 0 to 100"),
    (("--velocity", "-1"), "--velocity -1: 0 to 100"),
    (("--track", "3"), "track 3 is not in in.mid"),
])
def test_refusals(files, capsys, extra, message):
    rc, _text, err = run(capsys, "feel", files / "in.mid", "--from", files / "ref.mid", "--map", "gm", *extra,
                         "-o", files / "x.mid")
    assert rc == 1 and message in err and not (files / "x.mid").exists()


def test_it_never_writes_over_its_input_or_its_reference(files, capsys):
    for target in ("in.mid", "ref.mid"):
        rc, _text, err = run(capsys, "feel", files / "in.mid", "--from", files / "ref.mid", "-o", files / target)
        assert rc == 1 and "would overwrite the input" in err


@pytest.mark.parametrize("missing", ["nope.mid", "sub/ref.mid"])
def test_a_reference_that_looks_like_a_file_and_is_not_there_is_named(files, capsys, missing):
    rc, _text, err = run(capsys, "feel", files / "in.mid", "--from", missing, "-o", files / "x.mid", "--db", files / "db")
    assert rc == 1 and f"no file at {missing}" in err
    rc, _text, err = run(capsys, "search", "--like", missing, "--db", files / "db")
    assert rc == 1 and f"no file at {missing}" in err
