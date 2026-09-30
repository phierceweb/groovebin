"""`phrase` options for the joins between picked bars: a crash after each fill, velocities levelled."""

import statistics
from itertools import pairwise
from types import SimpleNamespace

import pytest
from smf_bytes import csv_row, pattern_file, write_csv

from groovebin.events import Note
from groovebin.library.generate import crashed, load_pool, phrase, phrase_song
from groovebin.library.index import build
from groovebin.library.pattern import SIXTEENTH, bar_ticks
from groovebin.midi import read, write

KICK, SNARE, HAT, RIDE, CRASH, TOM = 36, 38, 49, 60, 77, 71
SPAN = bar_ticks((4, 4))


def groove(velocity, extra=()):
    notes = [(0, KICK, velocity), (1920, KICK, velocity), (960, SNARE, velocity), (2880, SNARE, velocity),
             *((t, HAT, velocity) for t in range(0, SPAN, 480)), *extra]
    return pattern_file(960, [(t, p, v, 120) for t, p, v in notes])


LOUD, SOFT = groove(120), groove(40)
CRASHED = groove(90, [(0, CRASH, 110)])
FILL = pattern_file(960, [(t, TOM, 100, 120) for t in range(0, 1920, 240)] + [(t, SNARE, 110, 120) for t in range(1920, SPAN, 240)])


@pytest.fixture(scope="module")
def pool(tmp_path_factory):
    root = tmp_path_factory.mktemp("joins")
    lines = [csv_row(f"{name}.mid", "Kit", name, "Rock", "4/4", "100", beat, "0.5", "0.5", data)
             for name, data, beat in (("loud", LOUD, True), ("soft", SOFT, True), ("crashed", CRASHED, True),
                                      ("fill", FILL, False))]
    db = root / "library.sqlite"
    build(db, csv_path=write_csv(root / "csv" / "MidiDb.csv", lines), map_name="addictive-drums-2")
    return load_pool(db, sig=(4, 4), fills=True)


def bars_of(ph):
    return [[n for n in ph.notes if k * SPAN <= n.tick < (k + 1) * SPAN] for k in range(len(ph.picks))]


def level(bar):
    return statistics.median(n.velocity for n in bar if n.pitch in (KICK, SNARE))


def test_without_levelling_the_bars_keep_their_own_velocities(pool):
    jumps = [abs(level(b) - level(bars_of(ph)[0])) for seed in range(20)
             for ph in [phrase(pool, bars=8, seed=seed)] for b in bars_of(ph)]
    assert max(jumps) > 60


def test_levelling_brings_every_bar_to_the_first_bars_kick_and_snare_median(pool):
    for seed in range(20):
        ph = phrase(pool, bars=8, seed=seed, fills=True, level=True)
        assert ph.level == level(ph.picks[0].bar.notes)
        # humanising moves a velocity by up to 6 after the levelling, and rounding by half
        assert all(abs(level(b) - ph.level) <= 6.5 for b in bars_of(ph)), seed


def test_levelling_keeps_the_picks_and_the_timing(pool):
    plain, levelled = phrase(pool, bars=8, seed=3, fills=True), phrase(pool, bars=8, seed=3, fills=True, level=True)
    assert plain.picks == levelled.picks
    assert [n.tick for n in plain.notes] == [n.tick for n in levelled.notes]
    assert levelled.level == level([n for n in plain.picks[0].bar.notes])


def downbeat(ph, k):
    return [n.pitch for n in ph.notes if abs(n.tick - k * SPAN) < SIXTEENTH // 2]


def test_a_crash_lands_on_the_downbeat_after_each_fill_in_place_of_the_hat(pool):
    for seed in range(20):
        ph = phrase(pool, bars=9, seed=seed, fills=True, crash=True)
        added = tuple(k for k in (4, 8) if ph.picks[k].bar.id != _crashed_id(pool))
        assert ph.crashes == added, seed
        for k in (4, 8):
            assert downbeat(ph, k).count(CRASH) == 1, (seed, k)
            assert (HAT in downbeat(ph, k)) == (k not in added), (seed, k)


def _crashed_id(pool):
    return next(b.id for b in pool.bars if any(n.pitch == CRASH for n in b.notes))


def test_no_crash_after_a_fill_that_ends_the_phrase(pool):
    ph = phrase(pool, bars=8, seed=1, fills=True, crash=True)
    assert ph.picks[-1].fill and 7 not in ph.crashes and all(k < 8 for k in ph.crashes)


def test_the_crash_is_written_in_the_phrases_map(pool):
    ph = phrase(pool, bars=5, seed=2, fills=True, crash=True, map_name="gm")
    assert 49 in downbeat(ph, 4)


def test_without_the_options_nothing_is_added(pool):
    ph = phrase(pool, bars=8, seed=5, fills=True)
    assert (ph.crashes, ph.level) == ((), None)


def test_a_crash_is_on_the_channel_of_the_bar_it_lands_in_when_its_downbeat_is_empty():
    fill = [Note(t, 120, 1, 45, 100) for t in range(0, SPAN, 480)]
    after = [Note(t, 120, 1, 42, 80) for t in range(480, SPAN, 480)]
    bars, added = crashed([SimpleNamespace(fill=True), SimpleNamespace(fill=False)], [fill, after], ["gm", "gm"])
    assert added == (1,) and {n.channel for n in bars[1]} == {1}


def test_a_note_ends_where_the_next_of_its_pitch_starts(tmp_path):
    """Hats held over the next hat: the phrase keeps every stroke where it falls, and a reader pairs each."""
    held_hats = pattern_file(960, [(t, HAT, 90, 300) for t in range(0, SPAN, 240)] + [(0, KICK, 100, 120)])
    lines = [csv_row("held.mid", "Kit", "held", "Rock", "4/4", "100", True, "0.5", "0.5", held_hats)]
    db = tmp_path / "library.sqlite"
    build(db, csv_path=write_csv(tmp_path / "csv" / "MidiDb.csv", lines), map_name="addictive-drums-2")
    ph = phrase(load_pool(db, sig=(4, 4)), bars=4, seed=3)
    hats = sorted((n.tick, n.end) for n in ph.notes if n.pitch == HAT)
    assert len(hats) == 4 * 16 and all(end <= after for (_t, end), (after, _e) in pairwise(hats))
    assert [t.nested_ons for t in read(write(phrase_song(ph))).tracks] == [0, 0]
