import sqlite3

import pytest
from smf_bytes import FORMAT_1, TWO_BARS, csv_row, write_csv

from groovebin.library.index import build
from groovebin.library.search import find_group, get, parse_range, search


@pytest.fixture
def db(tmp_path):
    lines = [csv_row("a.mid", "Alpha 50% Mix", "Verse 01", "Rock", "4/4", "97.999985", True, "0.5", "0.72", TWO_BARS),
             csv_row("b.mid", "Beta", "Fills 02", "jazz", "3/4", "125.0", False, "0.66", "0.4", FORMAT_1),
             csv_row("c.mid", "Gamma", "Chorus", "Rock", "4/4", "140.0", True, "0.5", "0.9", "4D546864"),
             csv_row("d.mid", "Beta Two", "Chorus 1", "jazz", "3/4", "125.0", True, "0.66", "0.4", FORMAT_1)]
    path = tmp_path / "library.sqlite"
    build(path, csv_path=write_csv(tmp_path / "csv" / "MidiDb.csv", lines), map_name="gm")
    return path


def ids(db, **filters):
    return sorted(r["variant"] for r in search(db, **filters))


def test_every_filter(db):
    cases = {"category": ("rock", ["Verse 01"]), "meter": ("3/4", ["Chorus 1", "Fills 02"]),
             "tempo": ("100-130", ["Chorus 1", "Fills 02"]), "swing": ("<0.55", ["Verse 01"]),
             "intensity": (">0.7", ["Verse 01"]), "variant": ("fill", ["Fills 02"]), "group": ("%", ["Verse 01"]),
             "library": ("LIB ONE", ["Chorus 1", "Fills 02", "Verse 01"]), "role": ("chorus", ["Chorus 1"])}
    for name, (value, want) in cases.items():
        assert ids(db, **{name: value}) == want, name
    assert (ids(db, fill=True), ids(db, beat=True)) == (["Fills 02"], ["Chorus 1", "Verse 01"])
    assert (ids(db, tempo="98"), ids(db, tempo="97"), ids(db, tempo=">=125")) == (["Verse 01"], [], ["Chorus 1", "Fills 02"])
    assert len(search(db, limit=1)) == 1
    with pytest.raises(ValueError, match="a limit of -1 rows is below 0"):
        search(db, limit=-1)
    assert {"role", "map"} <= set(search(db)[0])


def test_a_row_that_did_not_parse_is_left_out(db):
    assert "Chorus" not in ids(db)


def test_range_syntax():
    cases = {"100-130": ("{col} >= ? AND {col} < ?", [99.5, 130.5]), "<0.55": ("ROUND({col}, 3) < ?", [0.55]),
             "0.7": ("{col} >= ? AND {col} < ?", [0.65, 0.75]), ">2": ("ROUND({col}, 3) > ?", [2.0]),
             "<=2.5": ("ROUND({col}, 3) <= ?", [2.5]), ">=.5": ("ROUND({col}, 3) >= ?", [0.5])}
    for text, (want, bounds) in cases.items():
        condition, got = parse_range(text)
        assert (condition, [round(b, 9) for b in got]) == (want, bounds), text
    with pytest.raises(ValueError, match=r"bad range '130-100': 130 is above 100"):
        parse_range("130-100")
    for bad in ("fast", "<", "1-2-3", "=5"):
        with pytest.raises(ValueError, match="bad number filter"):
            parse_range(bad)


def test_every_bound_compares_the_value_rounded_to_the_digits_written(tmp_path):
    db = tmp_path / "edge.sqlite"
    lines = [csv_row(f"{t}.mid", "G", t, "Rock", "4/4", t, True, "0.5", "0.5", TWO_BARS) for t in ("55.99998", "97.999985", "140.000137")]
    build(db, csv_path=write_csv(tmp_path / "edge" / "MidiDb.csv", lines), map_name="gm")
    cases = {"98-120": [98], "120-140": [140], "<=97": [56], ">=98": [98, 140], "<56": [], "<=56": [56],
             ">140": [], "56": [56], ">97.99": [98, 140], "97.99": [], "98.0": [98]}
    for text, want in cases.items():
        assert sorted(round(r["tempo"]) for r in search(db, tempo=text)) == want, text


def test_get_by_id_or_prefix_and_its_refusals(db, tmp_path):
    a = search(db, variant="Verse")[0]["id"]
    assert get(db, a[:6])["variant"] == "Verse 01"
    with pytest.raises(ValueError, match="no pattern ffffffff in the index"):
        get(db, "ffffffff")
    with pytest.raises(ValueError, match="bad pattern id 'zz': the hex id `groovebin search` prints"):
        get(db, "zz")
    with pytest.raises(FileNotFoundError, match="no pattern library index at .*: build it with `groovebin index`"):
        search(tmp_path / "none.sqlite")
    sqlite3.connect(tmp_path / "other.sqlite").close()
    with pytest.raises(ValueError, match="rebuild it with `groovebin index`"):
        search(tmp_path / "other.sqlite")


def test_find_group_takes_a_whole_name_or_one_substring(db):
    assert find_group(db, "alpha 50% mix") == ("Lib One", "Alpha 50% Mix")
    assert find_group(db, "beta") == ("Lib One", "Beta")
    assert find_group(db, "Two") == ("Lib One", "Beta Two")
    with pytest.raises(ValueError, match="no group in the index matches 'delta'"):
        find_group(db, "delta")
    with pytest.raises(ValueError, match=r"2 groups match 'et' \('Beta', 'Beta Two'\): give more of the name"):
        find_group(db, "et")
