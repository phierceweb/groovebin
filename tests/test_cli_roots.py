"""`groovebin roots`: the chords a bassline implies, as a chart."""

import json

from groovebin.cli import main
from groovebin.events import Event, Note
from groovebin.midi import write
from groovebin.song import Part, Song

BAR = 3840
METER = Event(0, bytes([0xFF, 0x58, 4, 4, 2, 24, 8]))


def run(capsys, *argv):
    rc = main([str(a) for a in argv])
    out, err = capsys.readouterr()
    return rc, out, err


def line(path, *notes, tracks=1):
    parts = tuple(Part(960, tuple(Note(t, n, 1, p, 90) for t, n, p in notes) if k == 0 else (), (METER,))
                  for k in range(tracks))
    path.write_bytes(write(Song(960, 1, parts)))
    return path


def test_a_bassline_as_a_chart(tmp_path, capsys):
    f = line(tmp_path / "b.mid", (0, BAR, 45), (BAR, 1920, 41), (BAR + 1920, 1920, 43), (2 * BAR, 2880, 45),
             (2 * BAR + 2880, 960, 48))
    rc, out, err = run(capsys, "roots", f)
    assert (rc, err) == (0, "")
    assert out.splitlines() == ["b.mid: 3 bar(s), 5 note(s)", "| A5 | F5 G5 | Am |", "scale  C major / A minor"]


def test_json_gives_each_chord_its_ticks_and_bar(tmp_path, capsys):
    f = line(tmp_path / "b.mid", (0, BAR, 45), (BAR, BAR, 41))
    rc, out, _err = run(capsys, "roots", f, "--json")
    assert json.loads(out) == [{"start": 0, "end": BAR, "bar": 1, "chord": "A5"},
                               {"start": BAR, "end": 2 * BAR, "bar": 2, "chord": "F5"}]


def test_a_bass_map_leaves_its_keyswitches_out(tmp_path, capsys):
    f = line(tmp_path / "b.mid", (0, 1920, 16), (0, BAR, 45))
    rc, out, _err = run(capsys, "roots", f, "--map", "ezbass")
    assert rc == 0 and out.splitlines()[:2] == ["b.mid: 1 bar(s), 1 note(s), 1 keyswitch(es) left out", "| A5 |"]


def test_a_drum_map_is_refused_and_so_is_a_file_with_no_notes(tmp_path, capsys):
    f = line(tmp_path / "b.mid", (0, BAR, 45))
    rc, _out, err = run(capsys, "roots", f, "--map", "gm")
    assert rc == 1 and "gm is a drum map" in err
    empty = line(tmp_path / "e.mid")
    rc, _out, err = run(capsys, "roots", empty)
    assert rc == 1 and "no notes" in err


def test_tracks_can_be_named(tmp_path, capsys):
    f = line(tmp_path / "b.mid", (0, BAR, 45), tracks=2)
    rc, _out, err = run(capsys, "roots", f, "--track", 2)
    assert rc == 1 and "no notes" in err
    rc, out, _err = run(capsys, "roots", f, "--track", 1)
    assert rc == 0 and out.splitlines()[1] == "| A5 |"
