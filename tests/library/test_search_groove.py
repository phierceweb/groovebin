import sqlite3
from contextlib import closing

import pytest
from smf_bytes import pattern_file

from groovebin.library.groove import Bar, file_rhythm
from groovebin.library.groove_text import parse_rhythm
from groovebin.library.index import build
from groovebin.library.search import MAX_QUERY_BARS, get, parse_range, pattern_rhythm, query_bars, search, similar

KICK, SNARE, HAT = 36, 38, 42
BAR = 3840


def bar(kicks, snares, hats):
    return [(t, KICK) for t in kicks] + [(t, SNARE) for t in snares] + [(t, HAT) for t in hats]


def two_bars(one):
    return pattern_file(960, [(b + t, p, 100, 60) for b in (0, BAR) for t, p in one])


EIGHTHS = range(0, BAR, 480)
FILES = {
    "backbeat.mid": two_bars(bar((0, 1920), (960, 2880), EIGHTHS)),
    "push.mid": two_bars(bar((0, 1680), (960, 2880), EIGHTHS)),
    "busy.mid": two_bars(bar((0, 720, 1920, 2400), (960, 2880), range(0, BAR, 240))),
    "shuffle.mid": two_bars(bar((0, 1920), (960, 2880), (b + o for b in range(0, BAR, 960) for o in (0, 640)))),
    "laid-back.mid": two_bars(bar((0, 1920), (990, 2910), EIGHTHS)),
    "waltz.mid": pattern_file(960, [(0, KICK, 100, 60), (960, SNARE, 100, 60), (1920, SNARE, 100, 60)], (3, 4)),
}


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    root = tmp_path_factory.mktemp("feel")
    (root / "lib").mkdir()
    for name, data in FILES.items():
        (root / "lib" / name).write_bytes(data)
    path = root / "library.sqlite"
    build(path, folder=root / "lib", map_name="gm")
    return path


def names(rows):
    return [r["file"] for r in rows]


def test_signed_numbers_in_ranges():
    cases = {"<-10": ("ROUND({col}, 3) < ?", [-10.0]), "-20--5": ("{col} >= ? AND {col} < ?", [-20.5, -4.5]),
             "-20-5": ("{col} >= ? AND {col} < ?", [-20.5, 5.5]), "-3": ("{col} >= ? AND {col} < ?", [-3.5, -2.5])}
    for text, want in cases.items():
        assert parse_range(text) == want, text
    with pytest.raises(ValueError, match="-5 is above -20"):
        parse_range("-5--20")


def test_feel_filters(db):
    assert names(search(db, subdivision="triplets")) == ["shuffle.mid"]
    assert names(search(db, subdivision="16ths")) == ["busy.mid"]
    assert names(search(db, density=">13")) == ["busy.mid"]
    assert names(search(db, swing8="0.6-0.7")) == ["shuffle.mid"]
    assert names(search(db, lag=">10")) == ["laid-back.mid"]
    assert names(search(db, lag="<-10")) == []
    assert names(search(db, syncopation=">=2")) == ["push.mid"]


def test_an_unknown_subdivision_is_refused(db):
    with pytest.raises(ValueError, match="quarters, 8ths, 16ths or triplets"):
        search(db, subdivision="32nds")


def test_the_listing_carries_the_feel(db):
    (row,) = search(db, subdivision="triplets")
    assert (row["density"], row["swing8"], row["subdivision"]) == (12.0, 0.667, "triplets")


def test_similar_ranks_by_distance_and_leaves_out_other_meters(db):
    query = file_rhythm(FILES["backbeat.mid"], "gm")
    found = similar(db, query)
    # lateness is not rhythm: 30 ticks behind still rounds onto the same sixteenth
    assert {r["file"]: r["distance"] for r in found[:2]} == {"backbeat.mid": 0, "laid-back.mid": 0}
    assert "waltz.mid" not in names(found)
    assert [r["distance"] for r in found] == sorted(r["distance"] for r in found)


def test_similar_leaves_out_the_query_pattern_and_takes_filters_and_a_limit(db):
    backbeat = next(r for r in search(db) if r["file"] == "backbeat.mid")
    key, query = get(db, backbeat["id"])["key"], file_rhythm(FILES["backbeat.mid"], "gm")
    found = similar(db, query, exclude=key, subdivision="8ths", limit=2)
    assert names(found) == ["laid-back.mid", "push.mid"]


def test_a_near_miss_is_nearer_than_a_far_one(db):
    query = file_rhythm(FILES["backbeat.mid"], "gm")
    distances = {r["file"]: r["distance"] for r in similar(db, query)}
    assert distances["push.mid"] == 1.0
    assert distances["push.mid"] < distances["busy.mid"]


def test_the_query_is_its_distinct_bars_with_onsets_up_to_a_limit():
    a, b, silent = Bar(16, 1, 0, 0), Bar(16, 2, 0, 0), Bar(16, 0, 0, 0)
    assert query_bars([a, a, silent, b, a]) == ((a, b), 2)
    many = [Bar(16, 1 << (k % 16), k // 16 + 1, 0) for k in range(MAX_QUERY_BARS + 3)]
    used, distinct = query_bars(many)
    assert (len(used), distinct) == (MAX_QUERY_BARS, MAX_QUERY_BARS + 3)


def test_a_query_with_no_onsets_is_refused(db):
    with pytest.raises(ValueError, match="no kick, snare or hands"):
        similar(db, [Bar(16, 0, 0, 0)])


def test_a_file_query_counts_bars_in_its_own_meter():
    assert [b.steps for b in file_rhythm(FILES["waltz.mid"], "gm")] == [12]


def test_a_typed_rhythm_counts_only_the_voices_it_gives(db):
    bars, voices = parse_rhythm("kick=x.......x.......")
    assert {r["file"]: r["distance"] for r in similar(db, bars, voices=voices)} == {
        "backbeat.mid": 0, "laid-back.mid": 0, "shuffle.mid": 0, "push.mid": 1.0, "busy.mid": 2.0}
    assert similar(db, bars)[0]["distance"] > 0


def test_a_pattern_with_no_rhythm_says_why(tmp_path):
    drums, bass = tmp_path / "drums", tmp_path / "bass"
    drums.mkdir()
    bass.mkdir()
    (drums / "broken.mid").write_bytes(b"not a midi file")
    (drums / "empty.mid").write_bytes(pattern_file(960, []))
    (bass / "line.mid").write_bytes(pattern_file(960, [(0, 45, 100, 480)]))
    build(tmp_path / "d.sqlite", folder=drums, map_name="gm")
    build(tmp_path / "b.sqlite", folder=bass, map_name="ezbass")

    def reason(db, name):
        with closing(sqlite3.connect(db)) as con:
            (pattern_id,) = con.execute("SELECT id FROM beats WHERE file LIKE ?", (f"%{name}",)).fetchone()
        with pytest.raises(ValueError, match="has no rhythm to compare") as caught:
            pattern_rhythm(db, pattern_id)
        return str(caught.value).partition(": ")[2]

    assert reason(tmp_path / "d.sqlite", "broken.mid") == "it was not parsed"
    assert reason(tmp_path / "d.sqlite", "empty.mid") == "it holds no notes"
    assert reason(tmp_path / "b.sqlite", "line.mid") == "its map, ezbass, is not a drum map"
