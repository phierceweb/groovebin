"""`groovebin index`, `search` and `show` on a library the test builds."""

import json

from library_fixture import INTRO, VERSE_1

from groovebin._parsers import default_db
from groovebin.cli import main


def run(capsys, *argv):
    rc = main([str(a) for a in argv])
    out, err = capsys.readouterr()
    return rc, out, err


def folder(tmp_path):
    root = tmp_path / "pack"
    (root / "Rock" / "Verse").mkdir(parents=True)
    (root / "Rock" / "Verse" / "Kit_V_Verse 01_C_Rock.mid").write_bytes(VERSE_1)
    (root / "Rock" / "Intro 02.mid").write_bytes(INTRO)
    return root


def test_index_then_search_then_show(tmp_path, capsys):
    db = tmp_path / "library.sqlite"
    rc, out, _ = run(capsys, "index", folder(tmp_path), "--map", "addictive-drums-2", "--db", db)
    assert rc == 0
    assert out.splitlines() == [f"indexing the .mid files under {tmp_path / 'pack'}",
                                "  2 pattern(s) indexed, 0 not parsed, 0 duplicate(s) skipped", "", f"out : {db}"]
    rc, out, _ = run(capsys, "search", "--role", "verse", "--db", db)
    lines = out.splitlines()
    assert (rc, lines[0], len(lines)) == (0, "1 pattern(s)", 2)
    pattern_id = lines[1].split()[0]
    assert "verse" in lines[1] and "Verse 01" in lines[1]
    rc, out, _ = run(capsys, "search", "--json", "--db", db)
    assert sorted(r["variant"] for r in json.loads(out)) == ["Intro 02", "Verse 01"]
    rc, out, _ = run(capsys, "show", pattern_id, "--db", db)
    assert rc == 0 and out.splitlines()[1] == " 49 HiHat Closed 1 Tip |x...........o...|"
    rc, out, _ = run(capsys, "show", pattern_id, "--map", "gm", "--db", db)
    assert out.splitlines()[1].startswith(" 49 Crash Cymbal 1 ")


def test_index_takes_a_csv_instead_of_a_folder(tmp_path, capsys):
    from smf_bytes import csv_row, write_csv
    source = write_csv(tmp_path / "csv" / "MidiDb.csv", [csv_row("a.mid", "G", "V", "Rock", "4/4", "120", True, "0.5", "0.5", INTRO)])
    rc, out, _ = run(capsys, "index", "--csv", source, "--map", "gm", "--db", tmp_path / "x.sqlite")
    assert rc == 0 and out.splitlines()[0] == "indexing the MIDI index MidiDb.csv"


def test_library_refusals_are_one_line(tmp_path, capsys):
    db = tmp_path / "library.sqlite"
    run(capsys, "index", folder(tmp_path), "--db", db)
    assert run(capsys, "search", "--swing", "lots", "--db", db) == \
           (1, "", "groovebin: bad number filter 'lots': use 100-130, <0.55, >0.7, <=, >= or a bare number\n")
    assert run(capsys, "show", "abcdef", "--db", db) == (1, "", "groovebin: no pattern abcdef in the index\n")
    rc, _, err = run(capsys, "index", "--db", db)
    assert rc == 1 and err == "groovebin: index one source: a folder or --csv\n"
    rc, _, err = run(capsys, "search", "--db", tmp_path / "none.sqlite")
    assert rc == 1 and "build it with `groovebin index`" in err


def test_the_default_index_is_in_the_user_cache(monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", "/cache-root")
    assert str(default_db()) == "/cache-root/groovebin/library.sqlite"
    monkeypatch.delenv("XDG_CACHE_HOME")
    assert str(default_db()).endswith("/.cache/groovebin/library.sqlite")
