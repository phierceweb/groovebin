"""`groovebin search` by feel and by rhythm, and the feel line `show` prints."""

import json

import pytest
from smf_bytes import pattern_file

from groovebin.cli import main

KICK, SNARE, HAT = 36, 38, 42
BAR = 3840


def two_bars(kicks, snares, hats):
    one = [(t, KICK) for t in kicks] + [(t, SNARE) for t in snares] + [(t, HAT) for t in hats]
    return pattern_file(960, [(b + t, p, 100, 60) for b in (0, BAR) for t, p in one])


BACKBEAT = two_bars((0, 1920), (960, 2880), range(0, BAR, 480))
PUSH = two_bars((0, 1680), (960, 2880), range(0, BAR, 480))
SHUFFLE = two_bars((0, 1920), (960, 2880), (b + o for b in range(0, BAR, 960) for o in (0, 640)))


def run(capsys, *argv):
    rc = main([str(a) for a in argv])
    out, err = capsys.readouterr()
    return rc, out, err


@pytest.fixture
def db(tmp_path, capsys):
    lib = tmp_path / "lib"
    lib.mkdir()
    for name, data in (("backbeat.mid", BACKBEAT), ("push.mid", PUSH), ("shuffle.mid", SHUFFLE)):
        (lib / name).write_bytes(data)
    path = tmp_path / "library.sqlite"
    assert run(capsys, "index", lib, "--map", "gm", "--db", path)[0] == 0
    return path


def listed(out):
    return [line.split()[-1] for line in out.splitlines()[1:]]


def rows(capsys, db, *argv):
    rc, out, err = run(capsys, "search", *argv, "--json", "--db", db)
    assert (rc, err) == (0, "")
    return json.loads(out)


def test_search_by_feel(capsys, db):
    assert [r["file"] for r in rows(capsys, db, "--subdivision", "triplets")] == ["shuffle.mid"]
    assert [r["file"] for r in rows(capsys, db, "--swing8", "0.6-0.7")] == ["shuffle.mid"]
    assert [r["file"] for r in rows(capsys, db, "--syncopation", ">=2")] == ["push.mid"]
    assert rows(capsys, db, "--lag", "<-5") == []


def test_like_a_pattern_ranks_the_others_and_leaves_it_out(capsys, db):
    backbeat = rows(capsys, db, "--subdivision", "8ths", "--syncopation", "0")[0]
    found = rows(capsys, db, "--like", backbeat["id"])
    assert [(r["file"], r["distance"]) for r in found] == [("push.mid", 1.0), ("shuffle.mid", 2.0)]


def test_like_a_file_needs_its_map(capsys, db, tmp_path):
    query = tmp_path / "query.mid"
    query.write_bytes(PUSH)
    found = rows(capsys, db, "--like", query, "--like-map", "gm")
    assert [(r["file"], r["distance"]) for r in found][:2] == [("push.mid", 0.0), ("backbeat.mid", 1.0)]
    rc, _out, err = run(capsys, "search", "--like", query, "--db", db)
    assert rc == 1 and "--like-map" in err


def test_like_map_is_only_for_a_file(capsys, db):
    backbeat = rows(capsys, db, "--syncopation", "0", "--subdivision", "8ths")[0]
    rc, _out, err = run(capsys, "search", "--like", backbeat["id"], "--like-map", "gm", "--db", db)
    assert rc == 1 and "--like-map" in err
    rc, _out, err = run(capsys, "search", "--like-map", "gm", "--db", db)
    assert rc == 1 and "--like-map" in err


def test_a_pattern_indexed_without_a_map_cannot_be_like(capsys, tmp_path):
    lib = tmp_path / "keys"
    lib.mkdir()
    (lib / "a.mid").write_bytes(BACKBEAT)
    db = tmp_path / "keys.sqlite"
    run(capsys, "index", lib, "--db", db)
    (row,) = rows(capsys, db)
    rc, _out, err = run(capsys, "search", "--like", row["id"], "--db", db)
    assert rc == 1 and "no rhythm" in err and "--map" in err


def test_the_listing_leads_with_the_distance(capsys, db):
    backbeat = rows(capsys, db, "--syncopation", "0", "--subdivision", "8ths")[0]
    rc, out, _err = run(capsys, "search", "--like", backbeat["id"], "--db", db)
    first = out.splitlines()[1].split()
    assert rc == 0 and (first[0], first[1]) == ("1.0", rows(capsys, db, "--syncopation", ">=2")[0]["id"])


def test_show_prints_the_feel_in_search_terms(capsys, db):
    (shuffle,) = rows(capsys, db, "--subdivision", "triplets")
    rc, out, _err = run(capsys, "show", shuffle["id"], "--db", db)
    assert rc == 0
    assert out.splitlines()[1] == ("feel  density 12  syncopation 0  subdivision triplets  swing8 0.667  swing16 -  lag 0  "
                                   "accent 0")


def test_rhythm_ranks_by_the_lanes_typed(capsys, db):
    found = rows(capsys, db, "--rhythm", "kick=x.......x....... snare=....x.......x...")
    assert {r["file"]: r["distance"] for r in found} == {"backbeat.mid": 0, "shuffle.mid": 0, "push.mid": 1.0}
    assert found[-1]["file"] == "push.mid"


def test_rhythm_is_refused_with_like_or_like_map_or_when_it_does_not_read(capsys, db):
    backbeat = rows(capsys, db, "--syncopation", "0", "--subdivision", "8ths")[0]
    for argv, needle in ((("--rhythm", "kick=x...", "--like", backbeat["id"]), "--like or --rhythm"),
                         (("--rhythm", "kick=x...", "--like-map", "gm"), "--like-map"),
                         (("--rhythm", "kick=x..y"), "only x and .")):
        rc, _out, err = run(capsys, "search", *argv, "--db", db)
        assert rc == 1 and needle in err, argv


def test_show_rhythm_prints_lanes_that_search_reads_back(capsys, db):
    push = rows(capsys, db, "--syncopation", ">=2")[0]
    rc, out, _err = run(capsys, "show", push["id"], "--rhythm", "--db", db)
    assert rc == 0 and out.startswith("kick=x......x........|x......x........ snare=")
    found = rows(capsys, db, "--rhythm", out.strip())
    assert (found[0]["id"], found[0]["distance"]) == (push["id"], 0)


def test_the_accent_help_names_the_window_off_the_beat():
    from groovebin._parsers import build_parser
    search = next(a for a in build_parser()._subparsers._group_actions[0].choices.values() if a.prog.endswith("search"))
    (accent,) = [a for a in search._actions if "--accent" in a.option_strings]
    assert "0.4 to 0.72" in accent.help and "eighths" not in accent.help
