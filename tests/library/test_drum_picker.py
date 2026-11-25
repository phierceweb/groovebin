"""Drum bars picked to a typed kick and snare: the nearest real bars, one pattern kept in its own order."""

import random
from itertools import product

import pytest
from smf_bytes import csv_row, pattern_file, write_csv

from groovebin.library.drum_picker import pick_drums
from groovebin.library.generate import Bar, Pool, load_pool
from groovebin.library.groove import Bar as Lanes
from groovebin.library.groove_text import parse_rhythm
from groovebin.library.index import build

BAR, STEP = 3840, 240
KICK, SNARE, HAT, RIDE, TOM = 0x24, 0x26, 0x31, 60, 0x47


def bar(kicks, snares, hand=HAT):
    return [(s * STEP, KICK, 100) for s in kicks] + [(s * STEP, SNARE, 96) for s in snares] + [(0, hand, 70)]


def bars_file(*bars):
    return pattern_file(960, [(k * BAR + t, p, v, 120) for k, b in enumerate(bars) for t, p, v in b])


PLAIN = bars_file(bar([0], [8]), bar([0, 10], [8]))
VERSE = bars_file(bar([2, 8], [4, 12]), bar([0, 8, 10, 14], [4, 12]))
ONE = bars_file(bar([2, 8], [4, 12], RIDE))
TWO = bars_file(bar([0, 8, 10, 14], [4, 12], RIDE))
FILL = bars_file([(0, TOM, 90), (960, TOM, 100), (1920, SNARE, 120), (2880, SNARE, 127)])
TYPED = "kick=..x.....x.......|x.......x.x...x. snare=....x.......x..."


def library(folder):
    rows = [csv_row(f"g/{name}.mid", "Grooves", variant, "Rock", "4/4", "120", beat, "0.5", "0.7", data)
            for name, variant, beat, data in (("plain", "Verse 01", True, PLAIN), ("verse", "Verse 02", True, VERSE),
                                              ("one", "Verse 03", True, ONE), ("two", "Verse 04", True, TWO),
                                              ("fill", "Fills 01", False, FILL))]
    db = folder / "lib.sqlite"
    build(db, csv_path=write_csv(folder / "lib" / "MidiDb.csv", rows), map_name="addictive-drums-2")
    return db


@pytest.fixture(scope="module")
def pool(tmp_path_factory):
    return load_pool(library(tmp_path_factory.mktemp("drum-picker")), sig=(4, 4), fills=True)


def picks(pool, text, bars, seed=1, fills=False):
    rhythm, voices = parse_rhythm(text)
    return pick_drums(pool, bars, random.Random(seed), fills=fills, rhythm=rhythm, voices=voices)


def lanes(pick):
    return pick.bar.onsets & 0xFFFF, pick.bar.onsets >> 16


def mask(*steps):
    return sum(1 << s for s in steps)


def test_a_typed_rhythm_takes_the_pattern_that_plays_it_in_its_own_order(pool):
    for seed in range(10):
        got = picks(pool, TYPED, 4, seed)
        assert [p.bar.index for p in got] == [0, 1, 0, 1] and len({p.bar.key for p in got}) == 1
        assert [p.distance for p in got] == [0, 0, 0, 0] and not any(p.fill for p in got)
        assert lanes(got[1]) == (mask(0, 8, 10, 14), mask(4, 12))


def test_a_change_of_pattern_is_taken_when_it_saves_more_than_it_costs(pool):
    got = picks(pool, "kick=..x.....x.......|x.........x..... snare=....x.......x...|........x.......", 2)
    assert lanes(got[0]) == (mask(2, 8), mask(4, 12)) and lanes(got[1]) == (mask(0, 10), mask(8))
    assert got[0].bar.key != got[1].bar.key and [p.distance for p in got] == [0, 0]


def test_only_the_lanes_typed_count(pool):
    got = picks(pool, "kick=x...............", 2)
    assert got[0].distance == 0 and lanes(got[0]) == (mask(0), mask(8))


def test_equal_bars_go_to_the_seed_and_a_seed_repeats(pool):
    text = "kick=..x.....x....... snare=....x.......x..."
    keys = {picks(pool, text, 1, seed)[0].bar.key for seed in range(20)}
    assert len(keys) == 2
    assert picks(pool, TYPED, 8, 7) == picks(pool, TYPED, 8, 7)


def test_every_fourth_bar_is_a_fill_and_the_groove_carries_on(pool):
    got = picks(pool, TYPED, 8, fills=True)
    assert [p.fill for p in got] == [False, False, False, True] * 2
    assert got[3].replaces.index == 1 and got[4].bar.index == 0 and got[4].bar.key == got[2].bar.key


def test_refusals(pool):
    with pytest.raises(ValueError, match="12 step"):
        picks(pool, "kick=x...x...x...", 2)
    with pytest.raises(ValueError, match="1 to"):
        picks(pool, TYPED, 0)


def score(pool, seq, targets, care):
    """Steps off plus changes of pattern, then the patterns entered past their first bar."""
    off = sum(((b.onsets ^ targets[k % len(targets)]) & care).bit_count() for k, b in enumerate(seq))
    changed = [b for a, b in zip(seq, seq[1:], strict=False) if pool.following(a) is not b]
    return off + len(changed), sum(b.index != 0 for b in (seq[0], *changed))


def test_the_picks_cost_no_more_than_any_other_sequence():
    """Against every sequence of a small generated pool. Which of several equal sequences is picked is the seed's."""
    for case in range(150):
        rng = random.Random(case)
        patterns = {}
        for p in range(rng.randint(1, 3)):
            count = rng.randint(1, 3)
            patterns[f"p{p}"] = tuple(Bar(f"p{p}", f"p{p}", i, count, (), rng.getrandbits(8) | rng.getrandbits(8) << 16,
                                          120.0, "gm") for i in range(count))
        small = Pool((4, 4), patterns, (), 0)
        rhythm = [Lanes(16, rng.getrandbits(8), rng.getrandbits(8), 0) for _ in range(rng.randint(1, 3))]
        voices = rng.choice([(0,), (1,), (0, 1)])
        bars = rng.randint(1, 4)
        care = (0xFFFF if 0 in voices else 0) | (0xFFFF0000 if 1 in voices else 0)
        targets = [(r.kick | r.snare << 16) & care for r in rhythm]
        best = min(score(small, seq, targets, care) for seq in product(small.bars, repeat=bars))
        got = pick_drums(small, bars, random.Random(case), rhythm=rhythm, voices=voices)
        assert score(small, [p.bar for p in got], targets, care) == best, case
        assert [p.distance for p in got] == [((p.bar.onsets ^ targets[k % len(targets)]) & care).bit_count()
                                             for k, p in enumerate(got)]
