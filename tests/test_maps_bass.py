"""The EZbass map: a bass map is a note map with a playable range, keyswitches and controllers."""

import json

import pytest

from groovebin.cli import main
from groovebin.events import Note
from groovebin.maps import ALL_NAMES, BASS_NAMES, NAMES, drum_map, maps, note_map, remap, stroke
from groovebin.midi import write
from groovebin.song import Part, Song

KEYSWITCHES = range(9, 21)


def test_drum_names_are_unchanged_and_bass_names_join_them():
    assert NAMES == ("gm", "addictive-drums-2", "drum-kit-designer", "drum-kit-designer-brushes")
    assert BASS_NAMES == ("ezbass",)
    assert ALL_NAMES == NAMES + BASS_NAMES
    assert list(maps()) == list(NAMES)


def test_the_bass_map_has_a_range_keyswitches_and_controllers():
    m = note_map("ezbass")
    assert (m.kind, m.range) == ("bass", (21, 64))
    assert dict(m.controllers) == {1: "vibrato", 64: "sustain", 67: "damping"}
    assert sorted(m.notes) == list(KEYSWITCHES)
    assert all(m.term(n).startswith("keyswitch ") for n in KEYSWITCHES)
    assert m.family("keyswitch") == tuple(KEYSWITCHES)


@pytest.mark.parametrize(("term", "note"), [("keyswitch repeat loud mute", 15), ("keyswitch repeat ghost", 16),
                                            ("keyswitch slide down", 17), ("keyswitch slide up", 19),
                                            ("keyswitch legato", 20), ("keyswitch polyphony", 9)])
def test_keyswitches_by_term(term, note):
    assert note_map("ezbass").find(term) == note


def test_a_keyswitch_is_named_from_the_vendors_layout_and_a_played_note_is_not_a_stroke():
    assert stroke("ezbass", 16) == "Ghost Note (press). Repeat the last played note as a ghost note."
    assert stroke("ezbass", 40) is None


def test_playable_is_the_range_and_a_keyswitch_is_not():
    m = note_map("ezbass")
    assert [m.playable(p) for p in (20, 21, 64, 65)] == [False, True, True, False]
    assert m.is_keyswitch(15) and not m.is_keyswitch(21) and not note_map("gm").is_keyswitch(36)


def test_a_drum_map_has_no_range():
    assert (note_map("gm").kind, note_map("gm").range) == ("drums", None)
    assert not note_map("gm").playable(36)


def test_drum_map_refuses_a_bass_map_and_names_it():
    with pytest.raises(ValueError, match="ezbass is a bass map, not a drum map"):
        drum_map("ezbass")
    with pytest.raises(ValueError, match="no note map 'tuba'"):
        note_map("tuba")


def test_a_remap_does_not_cross_from_bass_to_drums():
    part = Part(960, (Note(0, 120, 1, 40, 90),))
    for src, dst in (("ezbass", "gm"), ("gm", "ezbass")):
        with pytest.raises(ValueError, match="a bass map and a drum map do not translate"):
            remap(part, src, dst)


def test_the_source_names_the_document_and_the_measured_notes():
    source = note_map("ezbass").source
    assert "EZbass Key Switch Layout" in source and "1.3.4" in source and "7,097" in source


def run(capsys, *argv):
    rc = main([str(a) for a in argv])
    out, err = capsys.readouterr()
    return rc, out, err


def bass_file(path):
    notes = (Note(0, 400, 1, 16, 90), Note(0, 400, 1, 40, 90), Note(480, 400, 1, 47, 80))
    path.write_bytes(write(Song(960, 0, (Part(960, notes),))))
    return path


def test_notes_names_the_keyswitches(tmp_path, capsys):
    rc, out, _err = run(capsys, "notes", bass_file(tmp_path / "b.mid"), "--map", "ezbass")
    lines = [line for line in out.splitlines() if "note " in line]
    assert rc == 0
    assert lines[0].endswith("Ghost Note (press). Repeat the last played note as a ghost note.")
    assert all(line.endswith("-") for line in lines[1:])


def test_remap_offers_only_drum_maps(tmp_path, capsys):
    with pytest.raises(SystemExit) as e:
        main(["remap", str(bass_file(tmp_path / "b.mid")), "--from", "ezbass", "--to", "gm", "-o", str(tmp_path / "x.mid")])
    assert e.value.code == 2 and "invalid choice: 'ezbass'" in capsys.readouterr().err
    assert not (tmp_path / "x.mid").exists()


def test_a_remap_from_a_bass_map_to_itself_says_only_that():
    with pytest.raises(ValueError, match="to ezbass: name two different maps") as caught:
        remap(Part(960, (Note(0, 120, 1, 40, 90),)), "ezbass", "ezbass")
    assert "duplicates" not in str(caught.value)


def test_a_bass_library_keeps_its_map_records_no_feel_and_shows_a_piano_roll(tmp_path, capsys):
    lib = tmp_path / "lib"
    lib.mkdir()
    bass_file(lib / "line.mid")
    db = tmp_path / "bass.sqlite"
    assert run(capsys, "index", lib, "--map", "ezbass", "--db", db)[0] == 0
    (row,) = json.loads(run(capsys, "search", "--json", "--db", db)[1])
    assert (row["map"], row["density"], row["subdivision"]) == ("ezbass", None, None)
    rc, out, _err = run(capsys, "show", row["id"], "--db", db)
    assert rc == 0 and "feel" not in out and out.splitlines()[1].strip().startswith("B2")
