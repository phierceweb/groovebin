"""`groovebin generate` on a library the test builds."""

import pytest
from library_fixture import index

from groovebin.cli import main
from groovebin.library.generate import load_pool, phrase
from groovebin.midi import read
from groovebin.song import merged


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    return index(tmp_path_factory.mktemp("cli-generate"))


def run(capsys, *argv):
    rc = main([str(a) for a in argv])
    out, err = capsys.readouterr()
    return rc, out, err


def test_a_seed_writes_the_same_file_and_the_listing_names_every_pick(db, tmp_path, capsys):
    out = tmp_path / "phrase.mid"
    base = ("generate", "--meter", "4/4", "--bars", 8, "--fills", "--category", "Rock", "--db", db)
    rc, text, _ = run(capsys, *base, "--seed", 11, "-o", out)
    lines = text.splitlines()
    assert rc == 0, text
    assert lines[0].startswith("pool: ") and "fill bar(s)" in lines[0]
    assert lines[1].startswith("seed 11: 8 bar(s) of 4/4, ") and lines[1].endswith(" note(s) in addictive-drums-2")
    assert sum(1 for line in lines if line.lstrip().startswith("bar ")) == 8
    assert [line.split()[2] for line in lines if line.lstrip().startswith("bar ")] == ["beat"] * 3 + ["fill"] + ["beat"] * 3 + ["fill"]
    assert all("replaces" in line for line in lines if line.lstrip().startswith("bar ") and " fill " in line)
    assert lines[-1] == f"out : {out}"
    first = out.read_bytes()
    assert len(merged(read(first)).notes) > 0
    assert run(capsys, *base, "--seed", 11, "-o", out, "--force")[0] == 0
    assert out.read_bytes() == first


def test_without_a_seed_one_is_chosen_and_printed(db, tmp_path, capsys):
    rc, text, _ = run(capsys, "generate", "--meter", "4/4", "--bars", 2, "--db", db, "-o", tmp_path / "a.mid")
    seed = text.splitlines()[1].split("seed ", 1)[1].split(":", 1)[0]
    rc2, _, _ = run(capsys, "generate", "--meter", "4/4", "--bars", 2, "--db", db, "--seed", seed, "-o", tmp_path / "b.mid")
    assert (rc, rc2) == (0, 0)
    assert (tmp_path / "a.mid").read_bytes() == (tmp_path / "b.mid").read_bytes()


def test_a_phrase_in_another_map_reports_what_it_kept(db, tmp_path, capsys):
    rc, text, _ = run(capsys, "generate", "--meter", "4/4", "--bars", 4, "--map", "gm", "--seed", 3, "--db", db,
                      "-o", tmp_path / "gm.mid")
    assert rc == 0 and text.splitlines()[1].endswith(" note(s) in gm")


def test_unmapped_drop_is_reported(db, tmp_path, capsys):
    pool = load_pool(db, sig=(4, 4))
    seed = next(s for s in range(50) if phrase(pool, bars=8, seed=s, map_name="drum-kit-designer").unmapped)
    rc, text, _ = run(capsys, "generate", "--meter", "4/4", "--bars", 8, "--map", "drum-kit-designer", "--unmapped", "drop",
                      "--seed", seed, "--db", db, "-o", tmp_path / "dkd.mid")
    assert rc == 0 and "no drum-kit-designer counterpart, dropped: " in text


def test_refusals_before_anything_is_written(db, tmp_path, capsys):
    out = tmp_path / "p.mid"
    out.write_bytes(b"keep")
    cases = [(("--meter", "4/5", "--bars", 4, "-o", tmp_path / "x.mid"), "bad meter '4/5'"),
             (("--meter", "4/4", "--bars", 4, "--category", "Polka", "-o", tmp_path / "x.mid"),
              "no beat bars in the index for category 'Polka', meter 4/4"),
             (("--meter", "4/4", "--bars", 4, "--seed", -1, "-o", tmp_path / "x.mid"), "seed -1: a seed is 0 or more"),
             (("--meter", "4/4", "--bars", 4, "-o", out), "already exists; pass --force to overwrite it")]
    for argv, message in cases:
        rc, _, err = run(capsys, "generate", *argv, "--db", db)
        assert rc == 1 and message in err, err
    assert out.read_bytes() == b"keep" and not (tmp_path / "x.mid").exists()
