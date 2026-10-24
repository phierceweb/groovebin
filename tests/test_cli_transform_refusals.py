"""`groovebin transform` refusals: each names its rule, writes nothing, and says track where the library
says part — without rewriting the user's own text."""

import pytest
from transform_fixture import NOTES, build, run

from groovebin.transforms import PRESETS


def test_a_value_a_preset_cannot_use_is_a_message_not_a_traceback(tmp_path, capsys):
    src = build(tmp_path / "in.mid", [(0, 36, 1, 120), (480, 38, 40, 120)])
    for argv, message in ((["--preset", "exp-velocity=-1"], "not a number above 0"),
                          (["--preset", "velocity-limit=110..20"], "runs backwards"),
                          (["--preset", "reverse-pitch=200"], "not a note number 0-127"),
                          (["--select", "position=0-1", "--op", "add:velocity=1"], "before bar 1")):
        rc, _, err = run(capsys, "transform", src, "-o", tmp_path / "out.mid", *argv)
        assert rc == 1 and message in err, err
        assert not (tmp_path / "out.mid").exists()


@pytest.mark.parametrize(("argv", "message"), [
    (["--op", "add:velocity=10"], "takes IN.mid and -o"),
    (["--presets", "--force"], "takes nothing else"),
    (["--presets", "--seed", "5"], "takes nothing else"),
    (["--presets", "--chords", "| C |"], "takes nothing else"),
    (["--presets", "--upper"], "takes nothing else"),
    (["in.mid", "-o", "out.mid", "--op", "crescendo:velocity=-5..500"], "not inside 1..127"),
    (["in.mid", "-o", "out.mid", "--select", "pitch=127", "--op", "reverse:channel"], "not channel"),
    (["in.mid", "-o", "out.mid", "--preset", "legato=" + "9" * 308], "not a finite number"),
    (["in.mid", "-o", "out.mid", "--op", "add:position=268435455", "--op", "add:position=268435455"],
     "is past the 268435455 a file can hold"),
    (["in.mid", "-o", "out.mid"], "at least one --op or --preset"),
    (["in.mid", "-o", "out.mid", "--op", "velocity=10"], "OP:FIELD"),
    (["in.mid", "-o", "out.mid", "--preset", "loud"], "no such preset"),
    (["in.mid", "-o", "out.mid", "--preset", "half-speed", "--select", "pitch=36"], "drop --select"),
    (["in.mid", "-o", "out.mid", "--preset", "fixed-velocity"], "needs a value"),
    (["in.mid", "-o", "out.mid", "--op", "grow:velocity=1"], "no operation 'grow'"),
    (["in.mid", "-o", "out.mid", "--op", "add:velocity=1", "--seed", "-1"], "--seed '-1'"),
    (["in.mid", "-o", "out.mid", "--op", "add:position=-9999"], "before the track's start"),
    (["in.mid", "-o", "out.mid", "--op", "add:velocity=1", "--seed", "²"], "--seed '²': 0 or more, or random"),
    (["in.mid", "-o", "out.mid", "--track", "3", "--op", "add:velocity=1"], "track 3 is not in"),
    (["in.mid", "-o", "out.mid", "--select", "position=9-0:30", "--op", "add:velocity=1"], "bars or times at both ends"),
])
def test_refusals_name_the_rule_and_write_nothing(tmp_path, capsys, monkeypatch, argv, message):
    monkeypatch.chdir(tmp_path)
    build(tmp_path / "in.mid", NOTES)
    rc, _, err = run(capsys, "transform", *argv)
    assert rc == 1 and message in err, err
    assert not (tmp_path / "out.mid").exists()


def test_the_input_is_never_overwritten(tmp_path, capsys):
    src = build(tmp_path / "in.mid", NOTES)
    rc, _, err = run(capsys, "transform", src, "-o", src, "--op", "add:velocity=1")
    assert rc == 1 and "would overwrite the input" in err


HOSTILE = {"none": "5", "int": "9" * 310, "int?": "9" * 310, "float": "-1", "ticks": "9" * 310,
           "lo..hi": "-5..500", "percent": "9" * 310, "swing": "9" * 310, "humanize": "pos=" + "9" * 310,
           "key?": "H klingon", "steps": "9" * 310, "key": "Cb klingon",
           "chart": "| H |"}


def test_no_preset_value_reaches_the_user_as_a_traceback(tmp_path, capsys, monkeypatch):
    """Every preset over one file with a value it cannot use: a `groovebin:` line or a clean run,
    never a traceback. A value a field simply holds to its range is not an error."""
    monkeypatch.chdir(tmp_path)
    build(tmp_path / "in.mid", NOTES)
    for preset in PRESETS:
        rc, _, err = run(capsys, "transform", "in.mid", "-o", "out.mid", "--force",
                         "--preset", f"{preset.name}={HOSTILE[preset.takes]}")
        assert rc in (0, 1), (preset.name, err)
        assert err == "" or (err.startswith("groovebin: ") and len(err.strip().splitlines()) == 1), (preset.name, err)
        assert "Traceback" not in err, (preset.name, err)


def test_listing_the_presets_refuses_a_transform_in_the_same_breath(tmp_path, capsys):
    src = build(tmp_path / "in.mid", NOTES)
    rc, _, err = run(capsys, "transform", src, "-o", tmp_path / "out.mid", "--op", "add:velocity=1", "--presets")
    assert rc == 1 and "--presets lists the presets" in err
    assert not (tmp_path / "out.mid").exists()


def test_a_refusal_the_command_line_prints_says_track_where_the_library_says_part(tmp_path, capsys):
    src, out = build(tmp_path / "in.mid", NOTES), tmp_path / "out.mid"
    rc, _text, err = run(capsys, "transform", src, "-o", out, "--select", "position=0-2",
                         "--op", "set:velocity=90")
    assert rc == 1
    assert "where a track starts" in err
    assert "part" not in err


def test_only_the_librarys_own_wording_is_rewritten_never_the_users_text(tmp_path, capsys):
    """Only a `PartWording` refusal is rewritten. A message that quotes the user's own --select or
    --op text back at them must come back exactly as they typed it."""
    src, out = build(tmp_path / "in.mid", NOTES), tmp_path / "out.mid"
    rc, _t, err = run(capsys, "transform", src, "-o", out, "--select", "the part's=3", "--op", "set:velocity=90")
    assert rc == 1 and "the part's=3" in err and "the track's" not in err
    rc, _t, err = run(capsys, "transform", src, "-o", out, "--op", "set:a part at=3")
    assert rc == 1 and "a part at" in err and "a track at" not in err


def test_a_path_holding_the_librarys_phrase_is_not_rewritten(tmp_path, capsys):
    """The same rule for a file name: data, not wording."""
    folder = tmp_path / "the part's mix"
    folder.mkdir()
    bad = folder / "a part at rest.mid"
    bad.write_bytes(b"not a Standard MIDI File")
    rc, _text, err = run(capsys, "notes", bad)
    assert rc == 1
    assert "a part at rest.mid" in err
    assert "a track at rest" not in err
