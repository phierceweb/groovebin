import random
from collections import Counter

import pytest
from library_fixture import index as fixture_index
from smf_bytes import EOT, csv_row, pattern_file, smf, write_csv

from groovebin.events import Note
from groovebin.library.generate import families, generate, humanise, load_pool, onsets, parse_meter, phrase, phrase_song
from groovebin.library.index import build
from groovebin.maps import translate
from groovebin.midi import read, write
from groovebin.song import merged, meter_map, tempo_map

BAR = 3840
KICK, SNARE, HAT, TOM, STICKS, RIDE, SIDESTICK = 0x24, 0x26, 0x31, 0x47, 0x4B, 60, 42


def bars_file(*bars):
    return pattern_file(960, [(k * BAR + t, p, v, 120) for k, bar in enumerate(bars) for t, p, v in bar])


BACKBEAT = [(0, KICK, 100), (1920, SNARE, 96)]
PUSH = [(0, KICK, 110), (1920, SNARE, 90), (2400, KICK, 80)]
GROOVES = ((BACKBEAT + [(0, HAT, 70), (960, HAT, 60)], PUSH + [(0, HAT, 72), (2880, HAT, 50)]),
           (BACKBEAT + [(0, RIDE, 64), (1920, RIDE, 64)], [(0, KICK, 120), (960, SNARE, 80), (2880, SNARE, 127)]),
           (PUSH + [(0, RIDE, 1), (1440, SIDESTICK, 40), (3360, STICKS, 50)],))
A, B, C = (bars_file(*bars) for bars in GROOVES)
FILL_2 = bars_file(BACKBEAT + [(0, HAT, 70)], [(0, TOM, 90), (960, TOM, 100), (1920, SNARE, 120), (2880, SNARE, 127)])
FILL_1 = bars_file([(0, KICK, 100), (1920, SNARE, 60), (2160, SNARE, 70), (2400, SNARE, 80), (2640, SNARE, 90)])
WALTZ = pattern_file(960, [(0, KICK, 100, 120), (1920, SNARE, 90, 120)], (3, 4))
CHANGING = smf(0, 960, [(0, b"\xff\x58\x04\x04\x02\x18\x08"), (0, b"\x99\x24\x64"), (120, b"\x89\x24\x00"),
                        (3720, b"\xff\x58\x04\x03\x02\x18\x08"), (0, b"\x99\x26\x64"), (120, b"\x89\x26\x00"), (0, EOT)])


def index(folder, map_name="addictive-drums-2"):
    rows = [csv_row("g/a.mid", "Grooves", "Verse 01", "Rock", "4/4", "111", True, "0.5", "0.70", A),
            csv_row("g/b.mid", "Grooves", "Verse 02", "Rock", "4/4", "96", True, "0.5", "0.50", B),
            csv_row("g/c.mid", "Grooves", "Chorus", "Rock", "4/4", "120", True, "0.5", "0.72", C),
            csv_row("g/f2.mid", "Grooves", "Fills 01", "Rock", "4/4", "120", False, "0.5", "0.7", FILL_2),
            csv_row("g/f1.mid", "Grooves", "Fills 02", "Rock", "4/4", "120", False, "0.5", "0.7", FILL_1),
            csv_row("g/w.mid", "Grooves", "Waltz", "Rock", "3/4", "120", True, "0.5", "0.7", WALTZ),
            csv_row("g/x.mid", "Grooves", "Odd", "Rock", "4/4", "120", True, "0.5", "0.7", CHANGING),
            csv_row("j/j.mid", "Swing", "Verse", "Jazz", "4/4", "120", True, "0.5", "0.7", B)]
    db = folder / f"{map_name}.sqlite"
    build(db, csv_path=write_csv(folder / (map_name or "none") / "MidiDb.csv", rows), map_name=map_name)
    return db


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    return index(tmp_path_factory.mktemp("generate"))


@pytest.fixture(scope="module")
def pool(db):
    return load_pool(db, sig=(4, 4), category="rock", fills=True)


def notes_of(bar):
    return sorted((n.tick, n.pitch) for n in bar.notes)


def test_rows_split_into_bars_fills_apart_and_a_row_off_the_meter_left_out(pool):
    assert (len(pool.patterns), len(pool.bars), len(pool.fills), pool.left_out) == (3, 5, 2, 1)
    assert sorted([notes_of(b) for b in bars] for bars in pool.patterns.values()) == \
           sorted([sorted((t, p) for t, p, _v in bar) for bar in bars] for bars in GROOVES)
    assert sorted(notes_of(b)[0][1] for b in pool.fills) == [KICK, TOM]
    assert all(b.index == b.count - 1 and b.map == "addictive-drums-2" for b in pool.fills)


def test_filters_narrow_the_pool_and_category_is_optional(db):
    assert len(load_pool(db, sig=(4, 4), category="Rock", intensity="0.7").patterns) == 2
    assert len(load_pool(db, sig=(4, 4), category="Rock", tempo="90-100").bars) == 2
    assert len(load_pool(db, sig=(3, 4)).bars) == 1
    assert len(load_pool(db, sig=(4, 4), role="verse").patterns) == 3
    assert len(load_pool(db, sig=(4, 4), role="verse", fills=True).fills) == 2
    assert len(load_pool(db, sig=(4, 4), role="chorus", fills=True).patterns) == 1
    assert len(load_pool(db, sig=(4, 4)).patterns) == 4


def test_an_empty_pool_is_refused_with_the_filters(db):
    with pytest.raises(ValueError, match=r"^no beat bars in the index for category 'Polka', meter 4/4, tempo '100-130'$"):
        load_pool(db, sig=(4, 4), category="Polka", tempo="100-130")
    with pytest.raises(ValueError, match=r"^no fill bars in the index for category 'Jazz', meter 4/4$"):
        load_pool(db, sig=(4, 4), category="Jazz", fills=True)


def test_a_pool_needs_a_drum_map_to_find_kick_and_snare(tmp_path):
    with pytest.raises(ValueError, match="has no drum map: generating needs one to find its kick and snare"):
        load_pool(index(tmp_path, None), sig=(4, 4))


def test_meters():
    assert (parse_meter(" 6/8 "), parse_meter("4/4")) == ((6, 8), (4, 4))
    for bad in ("4", "4/5", "0/4", "x/4", "4/0", "1/32"):
        with pytest.raises(ValueError, match="bad meter"):
            parse_meter(bad)


def test_kick_and_snare_onsets_come_from_the_rows_map():
    ad2, gm = families("addictive-drums-2"), families("gm")
    notes = [Note(0, 1, 10, KICK, 1), Note(1920, 1, 10, SNARE, 1), Note(2500, 1, 10, 37, 1), Note(0, 1, 10, HAT, 1)]
    assert onsets(notes, 16, ad2) == 1 | 1 << 16 + 8 | 1 << 16 + 10
    assert onsets(notes, 16, gm) == 1 | 1 << 16 + 8
    assert onsets([Note(BAR - 100, 1, 10, KICK, 1)], 16, ad2) == 0


def test_every_bar_is_a_pool_bar_and_follows_the_last_picks_successor(pool):
    jumps = set()
    for seed in range(40):
        picks = generate(pool, 8, random.Random(seed))
        assert (picks[0].bar.index, picks[0].distance) == (0, None)
        for prev, pick in zip(picks, picks[1:], strict=False):
            assert pick.bar in pool.bars and not pick.fill
            assert (pick.bar.onsets, pick.distance) == (pool.following(prev.bar).onsets, 0)
            jumps.add(pick.bar.key != prev.bar.key and pick.bar != pool.following(prev.bar))
    assert jumps == {True, False}


def test_each_fill_is_the_one_nearest_the_groove_bar_it_replaces(pool):
    for seed in range(30):
        picks = generate(pool, 12, random.Random(seed), fills=True)
        assert [p.fill for p in picks] == [False, False, False, True] * 3
        assert generate(pool, 12, random.Random(seed), fills=True) == picks
        for p in picks:
            if p.fill:
                assert p.bar in pool.fills and p.replaces in pool.bars
                nearest = min((f.onsets ^ p.replaces.onsets).bit_count() for f in pool.fills)
                assert p.distance == nearest == (p.bar.onsets ^ p.replaces.onsets).bit_count()
            else:
                assert p.replaces is None


def test_bar_counts_and_seeds_are_refused_outside_their_range(pool):
    for bad in (0, 4097):
        with pytest.raises(ValueError, match=f"a phrase of {bad} bar\\(s\\): 1 to 4096"):
            generate(pool, bad, random.Random(0))
    with pytest.raises(ValueError, match="seed -5: a seed is 0 or more"):
        phrase(pool, bars=4, seed=-5)


def test_humanise_stays_within_five_ticks_and_six_velocity_held_to_the_phrase_and_1_127():
    notes = [Note(0, 10, 10, KICK, 127), Note(BAR - 1, 10, 10, SNARE, 1), Note(1920, 10, 10, HAT, 64)] * 20
    moved = set()
    for seed in range(30):
        for n, h in zip(notes, humanise(notes, random.Random(seed), BAR), strict=True):
            assert (n.length, n.channel, n.pitch) == (h.length, h.channel, h.pitch)
            assert abs(h.tick - n.tick) <= 5 and abs(h.velocity - n.velocity) <= 6 and 0 <= h.tick < BAR
            moved.add((h.tick != n.tick, h.velocity != n.velocity))
    assert (True, True) in moved


def test_a_seed_gives_the_same_phrase_and_another_seed_another(pool):
    one, again, other = (phrase(pool, bars=8, seed=s, fills=True) for s in (7, 7, 8))
    assert one == again and one.notes != other.notes
    assert (one.seed, one.sig, len(one.picks), one.ticks, one.map) == (7, (4, 4), 8, 8 * BAR, "addictive-drums-2")


def test_the_phrase_takes_the_first_picks_tempo(pool):
    for seed in range(12):
        ph = phrase(pool, bars=2, seed=seed)
        assert ph.tempo == ph.picks[0].bar.tempo


def test_a_phrase_can_be_written_in_another_map_and_counts_what_has_no_counterpart(pool):
    source, ph = phrase(pool, bars=8, seed=4), phrase(pool, bars=8, seed=4, map_name="gm")
    expected = [translate(n.pitch, "addictive-drums-2", "gm") for n in source.notes]
    assert ph.map == "gm"
    assert [n.pitch for n in ph.notes] == [new if new is not None else n.pitch for n, new in zip(source.notes, expected, strict=True)]
    assert ph.unmapped == {p: c for p, c in sorted(Counter(n.pitch for n, new in zip(source.notes, expected, strict=True) if new is None).items())}


def test_a_phrase_in_another_map_can_drop_what_has_no_counterpart(pool):
    kept, dropped = (phrase(pool, bars=8, seed=4, map_name="drum-kit-designer", unmapped=u) for u in ("keep", "drop"))
    assert kept.unmapped and kept.unmapped == dropped.unmapped
    assert len(dropped.notes) == len(kept.notes) - sum(kept.unmapped.values())
    assert not {n.pitch for n in dropped.notes} & set(kept.unmapped)


def test_the_song_holds_the_phrase_its_meter_and_the_first_bars_tempo(pool):
    ph = phrase(pool, bars=4, seed=2)
    song = read(write(phrase_song(ph)))
    assert (song.ppq, meter_map(song).changes, tempo_map(song).bpm(0)) == (960, ((0, 4, 4),), pytest.approx(ph.tempo, abs=1e-3))
    assert sorted((n.tick, n.pitch, n.velocity, n.length) for n in merged(song).notes) == \
           sorted((n.tick, n.pitch, n.velocity, n.length) for n in ph.notes)
    assert song.tracks[1].name == "Generated 2"
    assert write(phrase_song(ph)) == write(phrase_song(phrase(pool, bars=4, seed=2)))


def test_a_fill_bar_keeps_the_number_of_the_bar_it_came_from(tmp_path):
    fills = load_pool(fixture_index(tmp_path), sig=(4, 4), category="Rock", fills=True).fills
    assert sorted((b.index, b.count) for b in fills) == [(0, 1), (0, 2), (1, 2)]
