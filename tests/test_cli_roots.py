"""`groovebin roots`: the chords a bassline implies, as a chart."""

import json

from groovebin.cli import main
from groovebin.events import Event, Note
from groovebin.midi import read, write
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


def test_out_writes_a_root_note_per_chord_with_the_sources_conductor(tmp_path, capsys):
    f = line(tmp_path / "b.mid", (0, BAR, 45), (BAR, 1920, 41), (BAR + 1920, 1920, 43))
    out = tmp_path / "roots.mid"
    rc, text, err = run(capsys, "roots", f, "-o", out)
    assert (rc, err) == (0, "") and text.splitlines()[-1] == f"out : {out}"
    song = read(out.read_bytes())
    assert [(n.tick, n.length, n.pitch) for n in song.tracks[1].notes] == \
        [(0, BAR, 45), (BAR, 1920, 41), (BAR + 1920, 1920, 43)]
    assert METER in song.tracks[0].events


def test_octave_moves_the_roots_and_goes_with_out(tmp_path, capsys):
    f, out = line(tmp_path / "b.mid", (0, BAR, 45)), tmp_path / "roots.mid"
    assert run(capsys, "roots", f, "-o", out, "--octave", "1")[0] == 0
    assert [n.pitch for n in read(out.read_bytes()).tracks[1].notes] == [33]
    rc, _text, err = run(capsys, "roots", f, "-o", tmp_path / "high.mid", "--octave", "9")
    assert rc == 1 and "octave 9 puts A at 129" in err and not (tmp_path / "high.mid").exists()
    rc, _text, err = run(capsys, "roots", f, "--octave", "1")
    assert rc == 1 and "--octave and --force go with -o" in err


def test_json_with_out_prints_only_json(tmp_path, capsys):
    f = line(tmp_path / "b.mid", (0, BAR, 45))
    rc, text, _err = run(capsys, "roots", f, "--json", "-o", tmp_path / "roots.mid")
    assert rc == 0 and json.loads(text)[0]["chord"] == "A5"


def test_a_bassline_of_zero_length_notes_names_no_root(tmp_path, capsys):
    f = line(tmp_path / "b.mid", (0, 0, 45), (960, 0, 48))
    for extra in ([], ["-o", tmp_path / "roots.mid"]):
        rc, _out, err = run(capsys, "roots", f, *extra)
        assert rc == 1 and "no note is held long enough to name a root" in err and "division" not in err


def test_an_octave_that_puts_a_root_on_a_bass_maps_keyswitch_is_refused(tmp_path, capsys):
    f, out = line(tmp_path / "b.mid", (0, BAR, 45), (BAR, BAR, 41)), tmp_path / "roots.mid"
    rc, _text, err = run(capsys, "roots", f, "--map", "ezbass", "-o", out, "--octave", "0")
    assert rc == 1 and "--octave 0 puts roots on ezbass keyswitches: 17;" in err and not out.exists()
    assert run(capsys, "roots", f, "--map", "ezbass", "-o", out, "--octave", "1")[0] == 0
