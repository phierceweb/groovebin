"""`groovebin generate --rhythm`: a phrase picked to a typed kick and snare."""

import pytest
from test_drum_picker import TYPED, library

from groovebin.cli import main
from groovebin.library.groove import rhythm
from groovebin.midi import read
from groovebin.song import merged, meter_map


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    return library(tmp_path_factory.mktemp("cli-generate-rhythm"))


def run(capsys, *argv):
    rc = main([str(a) for a in argv])
    out, err = capsys.readouterr()
    return rc, out, err


def test_the_phrase_plays_the_typed_kick_and_snare_and_says_how_near_it_came(db, tmp_path, capsys):
    out = tmp_path / "verse.mid"
    rc, text, err = run(capsys, "generate", "--meter", "4/4", "--bars", 4, "--rhythm", TYPED, "--seed", 3, "--db", db, "-o", out)
    assert (rc, err) == (0, "")
    lines = text.splitlines()
    assert lines[2] == "  typed rhythm: 4 of 4 bar(s) exact, 0 step(s) off, 0 change(s) of pattern"
    song = read(out.read_bytes())
    grid = rhythm(merged(song).notes, meter_map(song), 4, "addictive-drums-2")
    assert [(b.kick, b.snare) for b in grid] == [(0b100000100, 0b1000000010000), (0b100010100000001, 0b1000000010000)] * 2
    assert run(capsys, "generate", "--meter", "4/4", "--bars", 4, "--rhythm", TYPED, "--seed", 3, "--db", db, "-o", out,
               "--force")[1] == text


def test_a_bar_that_is_off_is_marked_and_fills_are_left_out_of_the_count(db, tmp_path, capsys):
    rc, text, _err = run(capsys, "generate", "--meter", "4/4", "--bars", 4, "--fills", "--seed", 3, "--db", db,
                         "--rhythm", "kick=x.......x....... snare=....x.......x...", "-o", tmp_path / "x.mid")
    lines = text.splitlines()
    assert rc == 0 and lines[2] == "  typed rhythm: 0 of 3 bar(s) exact, 6 step(s) off, 0 change(s) of pattern"
    assert all(line.endswith(", 2 step(s) off") for line in lines[3:6]) and "replaces" in lines[6]
    assert not lines[6].endswith("step(s) off")


@pytest.mark.parametrize(("lanes", "message"), [
    ("kick=x...x...x...", "12 step"),
    ("hands=x.x.x.x.x.x.x.x.", "kick and snare"),
    ("kick=x..y", "only x and ."),
])
def test_refusals(db, tmp_path, capsys, lanes, message):
    rc, _text, err = run(capsys, "generate", "--meter", "4/4", "--bars", 4, "--rhythm", lanes, "--db", db, "-o", tmp_path / "x.mid")
    assert rc == 1 and message in err and not (tmp_path / "x.mid").exists()
