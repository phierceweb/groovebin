"""`groovebin bass`: a bassline written over a drum file's kicks and a chord chart."""

import pytest

from groovebin.cli import main
from groovebin.events import Event, Note
from groovebin.harmony import note_number
from groovebin.midi import read, write
from groovebin.song import Part, Song

BAR = 3840
TEMPO = Event(0, b"\xff\x51\x03" + (600000).to_bytes(3, "big"))
METER = Event(0, bytes([0xFF, 0x58, 4, 4, 2, 24, 8]))


def run(capsys, *argv):
    rc = main([str(a) for a in argv])
    out, err = capsys.readouterr()
    return rc, out, err


def drums(path, bars=2, ppq=960):
    scale = ppq / 960
    notes = tuple(Note(round((b * BAR + t) * scale), round(120 * scale), 10, p, 100)
                  for b in range(bars) for t, p in ((0, 36), (1920, 36), (960, 38), (2880, 38)))
    path.write_bytes(write(Song(ppq, 0, (Part(ppq, notes, (TEMPO, METER)),))))
    return path


def bass_notes(path):
    (track,) = [t for t in read(path.read_bytes()).tracks if t.notes]
    return track.notes


def test_a_line_over_the_kicks_in_the_drums_tempo_and_meter(tmp_path, capsys):
    out = tmp_path / "bass.mid"
    rc, text, err = run(capsys, "bass", "--drums", drums(tmp_path / "d.mid"), "--drum-map", "gm",
                        "--chords", "| Am | F |", "--seed", 4, "--approach", 0, "-o", out)
    assert (rc, err) == (0, "")
    assert text.splitlines()[0] == "bass over 2 bar(s) of d.mid: 4 note(s), 4 on a kick, 1 chord change(s), 0 approach note(s)"
    assert text.splitlines()[-2:] == ["seed 4", f"out : {out}"]
    notes = bass_notes(out)
    assert [n.tick for n in notes] == [0, 1920, BAR, BAR + 1920]
    assert (notes[0].pitch % 12, notes[2].pitch % 12) == (9, 5)
    song = read(out.read_bytes())
    metas = {e.data[:2] for t in song.tracks for e in t.events}
    assert {b"\xff\x51", b"\xff\x58"} <= metas


def test_the_same_seed_writes_the_same_file(tmp_path, capsys):
    d = drums(tmp_path / "d.mid")
    base = ("bass", "--drums", d, "--drum-map", "gm", "--chords", "| Am F | G C |", "--seed", 7)
    run(capsys, *base, "-o", tmp_path / "a.mid")
    run(capsys, *base, "-o", tmp_path / "b.mid")
    assert (tmp_path / "a.mid").read_bytes() == (tmp_path / "b.mid").read_bytes()


def test_roots_from_another_bassline(tmp_path, capsys):
    line = tmp_path / "line.mid"
    notes = (Note(0, BAR, 1, 40, 90), Note(BAR, BAR, 1, 45, 90))
    line.write_bytes(write(Song(480, 0, (Part(480, tuple(Note(n.tick // 2, n.length // 2, 1, n.pitch, 90) for n in notes),
                                             (METER,)),))))
    rc, text, _err = run(capsys, "bass", "--drums", drums(tmp_path / "d.mid"), "--drum-map", "gm",
                         "--roots-from", line, "--approach", 0, "--seed", 1, "-o", tmp_path / "out.mid")
    assert rc == 0 and "chords from line.mid: | E5 | A5 |" in text.splitlines()
    assert [n.pitch % 12 for n in bass_notes(tmp_path / "out.mid") if n.tick in (0, BAR)] == [4, 9]


def test_the_register_and_mutes_with_the_ezbass_map(tmp_path, capsys):
    out = tmp_path / "bass.mid"
    rc, text, _err = run(capsys, "bass", "--drums", drums(tmp_path / "d.mid"), "--drum-map", "gm", "--chords", "Am",
                         "--map", "ezbass", "--mute", "--low", "E1", "--high", "E2", "--seed", 2, "-o", out)
    notes = bass_notes(out)
    played = [n for n in notes if n.pitch >= 21]
    assert rc == 0 and all(28 <= n.pitch <= 40 for n in played)
    assert sorted(n.tick for n in notes if n.pitch == 15) == [960, 2880, BAR + 960, BAR + 2880]
    assert "4 snare mute(s)" in text.splitlines()[0]


@pytest.mark.parametrize(("extra", "message"), [
    (("--chords", "Am", "--mute"), "--mute needs --map ezbass"),
    (("--chords", "Am", "--low", "E2", "--high", "G2"), "at least an octave"),
    (("--chords", "Am", "--approach", "150"), "--approach 150: 0 to 100"),
    ((), "--chords or --roots-from"),
    (("--chords", "Am", "--roots-from", "x.mid"), "--chords or --roots-from, not both"),
    (("--chords", ""), "a chart with no chords"),
    (("--chords", "", "--roots-from", "x.mid"), "--chords or --roots-from, not both"),
    (("--chords", "Am", "--map", "gm"), "gm is a drum map"),
    (("--chords", "Am", "--map", "ezbass", "--low", "E0", "--high", "E1"), "ezbass's keyswitches"),
])
def test_refusals(tmp_path, capsys, extra, message):
    rc, _text, err = run(capsys, "bass", "--drums", drums(tmp_path / "d.mid"), "--drum-map", "gm", *extra,
                         "-o", tmp_path / "x2.mid")
    assert rc == 1 and message in err and not (tmp_path / "x2.mid").exists()


@pytest.mark.parametrize(("text", "number"), [("E1", 28), ("C4", 60), ("Bb0", 22), ("c#2", 37), ("40", 40)])
def test_note_numbers(text, number):
    assert note_number(text) == number


def test_a_note_number_out_of_range_is_refused():
    with pytest.raises(ValueError, match="0-127"):
        note_number("C10")


def test_the_note_count_leaves_the_mutes_out(tmp_path, capsys):
    rc, text, _err = run(capsys, "bass", "--drums", drums(tmp_path / "d.mid"), "--drum-map", "gm", "--chords", "Am",
                         "--map", "ezbass", "--mute", "--approach", 0, "--seed", 2, "-o", tmp_path / "m.mid")
    assert text.splitlines()[0].startswith("bass over 2 bar(s) of d.mid: 4 note(s), 4 on a kick")


@pytest.fixture
def bass_library(tmp_path):
    lib = tmp_path / "lib"
    lib.mkdir()
    notes = (Note(0, 900, 1, 45, 100), Note(1920, 900, 1, 40, 90), Note(1000, 5, 1, 16, 100))
    (lib / "beats.mid").write_bytes(write(Song(960, 0, (Part(960, notes, (METER, Event(0, b"\xb0\x43\x5a"))),))))
    (lib / "beats.midchordinfo").write_text("ChordList {\nChord {\nNote 9 9 1\nTime 0 4\nChordParts 6\n}\n}\n")
    db = tmp_path / "bass.sqlite"
    run_quiet = main(["index", str(lib), "--map", "ezbass", "--db", str(db)])
    assert run_quiet == 0
    return db


def test_a_line_from_the_library_re_voiced_onto_the_chart(tmp_path, capsys, bass_library):
    capsys.readouterr()
    out = tmp_path / "lib.mid"
    rc, text, err = run(capsys, "bass", "--drums", drums(tmp_path / "d.mid"), "--drum-map", "gm", "--chords", "| Am | F |",
                        "--library", bass_library, "--seed", 1, "-o", out)
    assert (rc, err) == (0, "")
    lines = text.splitlines()
    assert lines[0] == "bass over 2 bar(s) of d.mid from the library: 4 note(s), 2 keyswitch(es)"
    assert lines[1].startswith("  bar 1  ") and "0 onset step(s) from the kicks" in lines[1]
    played = [(n.tick, n.pitch) for n in bass_notes(out) if n.pitch >= 21]
    assert played == [(0, 45), (1920, 40), (BAR, 41), (BAR + 1920, 36)]
    (track,) = [t for t in read(out.read_bytes()).tracks if t.notes]
    assert [e.tick for e in track.events if e.kind == "control"] == [0, BAR]


def test_the_library_brings_its_own_approaches_and_articulations(tmp_path, capsys, bass_library):
    capsys.readouterr()
    for extra in (("--mute", "--map", "ezbass"), ("--approach", "50")):
        rc, _text, err = run(capsys, "bass", "--drums", drums(tmp_path / "d.mid"), "--drum-map", "gm", "--chords", "Am",
                             "--library", bass_library, *extra, "-o", tmp_path / "y.mid")
        assert rc == 1 and "--library" in err


def test_it_never_writes_over_the_library(tmp_path, capsys, bass_library):
    capsys.readouterr()
    before = bass_library.read_bytes()
    rc, _text, err = run(capsys, "bass", "--drums", drums(tmp_path / "d.mid"), "--drum-map", "gm", "--chords", "Am",
                         "--library", bass_library, "-o", bass_library, "--force")
    assert rc == 1 and "would overwrite the input" in err and bass_library.read_bytes() == before


def test_a_library_register_starts_above_its_keyswitches(tmp_path, capsys, bass_library):
    rc, _text, err = run(capsys, "bass", "--drums", drums(tmp_path / "d.mid"), "--drum-map", "gm", "--chords", "Am",
                         "--library", bass_library, "--low", "A-1", "--high", "A0", "-o", tmp_path / "x.mid")
    assert rc == 1 and "ezbass's keyswitches" in err and not (tmp_path / "x.mid").exists()
