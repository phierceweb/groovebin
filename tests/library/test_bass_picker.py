"""A bassline picked from a bass library's own bars by how their onsets meet the kicks, re-voiced onto a chart."""

from pathlib import PurePath

import pytest
from smf_bytes import pattern_file

from groovebin.events import Event, Note
from groovebin.harmony import Chord, chart, chart_spans
from groovebin.library.bass_picker import BassBar, BassPick, lay, load_bass_bars, pick_bass
from groovebin.library.groove import Bar
from groovebin.library.index import build
from groovebin.library.search import search
from groovebin.midi import write
from groovebin.song import Part, Song
from groovebin.timing import MeterMap

PPQ, BAR = 960, 3840
METER = Event(0, bytes([0xFF, 0x58, 4, 4, 2, 24, 8]))
FOUR = MeterMap(PPQ, ((0, 4, 4),))


def chord_file(*chords):
    blocks = "".join(f"Chord {{\nNote {r} {r} {q}\nTime {s} {e}\nChordParts \n}}\n" for r, q, s, e in chords)
    return "ChordList {\n" + blocks + "}\n"


def bits(*steps):
    return sum(1 << s for s in steps)


@pytest.fixture(scope="module")
def pool(db):
    return load_bass_bars(db, sig=(4, 4))


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    root = tmp_path_factory.mktemp("basslib")
    lib = root / "lib"
    lib.mkdir()
    # two bars over Am: on beats 1 and 3, then on every beat, a ghost keyswitch in the first
    two = [(0, 45, 100, 900), (1920, 40, 90, 900), (1000, 16, 100, 5),
           (BAR, 45, 80, 400), (BAR + 960, 48, 80, 400), (BAR + 1920, 40, 80, 400), (BAR + 2880, 45, 80, 400)]
    notes = tuple(Note(t, n, 1, p, v) for t, p, v, n in two)
    damping_and_touch = (Event(0, bytes([0xB0, 67, 90])), Event(100, bytes([0xA0, 45, 40])), METER)
    (lib / "beats.mid").write_bytes(write(Song(960, 0, (Part(960, notes, damping_and_touch),))))
    (lib / "beats.midchordinfo").write_text(chord_file((9, 1, 0, 8)))
    (lib / "busy.mid").write_bytes(pattern_file(960, [(t, 45, 90, 200) for t in range(0, BAR, 240)]))
    (lib / "busy.midchordinfo").write_text(chord_file((9, 1, 0, 4)))
    (lib / "unlabelled.mid").write_bytes(pattern_file(960, [(0, 45, 90, 900)]))
    path = root / "bass.sqlite"
    build(path, folder=lib, map_name="ezbass")
    return path


def test_the_pool_is_bars_with_chords_and_played_onsets(pool):
    assert sorted((b.index, b.onsets) for b in pool if b.count == 2) == [(0, bits(0, 8)), (1, bits(0, 4, 8, 12))]
    assert len(pool) == 3


def test_each_drum_bar_takes_the_bar_nearest_its_kicks(pool):
    picks = pick_bass(pool, (Bar(16, bits(0, 8), 0, 0), Bar(16, bits(*range(16)), 0, 0)), seed=1)
    assert [(p.bar.onsets, p.distance) for p in picks] == [(bits(0, 8), 0), (bits(*range(16)), 0)]


def test_the_bar_after_the_last_pick_wins_when_it_is_nearly_as_near(pool):
    picks = pick_bass(pool, (Bar(16, bits(0, 8), 0, 0), Bar(16, bits(0, 4, 8), 0, 0)), seed=1)
    assert [p.bar.index for p in picks if p.bar.count == 2] == [0, 1]


def test_laid_out_and_re_voiced_onto_the_chart_keyswitches_as_they_are(pool):
    picks = pick_bass(pool, (Bar(16, bits(0, 8), 0, 0),), seed=1)
    notes, events = lay(picks, chart_spans(chart("F"), FOUR, 1), FOUR, 960, (28, 50), "ezbass")
    assert [(n.tick, n.pitch) for n in notes] == [(0, 41), (1000, 16), (1920, 36)]
    assert events == (Event(0, bytes([0xB0, 67, 90])), Event(100, bytes([0xA0, 41, 40])))


def test_a_meter_the_library_lacks_is_refused(db):
    with pytest.raises(ValueError, match="no bass bars with chords in the index for 3/4"):
        load_bass_bars(db, sig=(3, 4))



def cc(tick, number, value):
    return Event(tick, bytes([0xB0, number, value]))


def bass_bar(key, index, events=(), chase=()):
    return BassBar(key, key[:10], index, 4, 16, 1, (Note(0, 480, 1, 45, 90),), ((0, BAR, Chord(9, "min")),), "ezbass",
                   tuple(events), tuple(chase))


def test_each_bar_starts_under_the_controllers_its_source_played_it_with():
    first = bass_bar("a" * 40, 0, events=[cc(960, 64, 127)])
    second = bass_bar("b" * 40, 2, chase=[cc(0, 67, 90)])
    picks = [BassPick(first, 0), BassPick(second, 0)]
    _notes, events = lay(picks, chart_spans(chart("Am"), FOUR, 2), FOUR, 960, (28, 50), "ezbass")
    assert [(e.tick, e.data[1], e.data[2]) for e in events] == [(960, 64, 127), (BAR, 64, 0), (BAR, 67, 90)]


def test_a_bar_under_the_same_controllers_sends_nothing_new():
    picks = [BassPick(bass_bar("a" * 40, 0, chase=[cc(0, 67, 90)]), 0), BassPick(bass_bar("a" * 40, 1, chase=[cc(0, 67, 90)]), 0)]
    _notes, events = lay(picks, chart_spans(chart("Am"), FOUR, 2), FOUR, 960, (28, 50), "ezbass")
    assert [(e.tick, e.data[1], e.data[2]) for e in events] == [(0, 67, 90)]


def test_the_pool_records_the_controllers_a_bar_starts_under(pool):
    later = next(b for b in pool if b.count == 2 and b.index == 1)
    assert [(e.data[1], e.data[2]) for e in later.chase] == [(67, 90)]


def test_no_reset_where_the_bar_sets_the_controller_on_its_line():
    picks = [BassPick(bass_bar("a" * 40, 0, events=[cc(0, 67, 90)]), 0), BassPick(bass_bar("b" * 40, 0, events=[cc(0, 67, 90)]), 0)]
    _notes, events = lay(picks, chart_spans(chart("Am"), FOUR, 2), FOUR, 960, (28, 50), "ezbass")
    assert [(e.tick, e.data[1], e.data[2]) for e in events] == [(0, 67, 90), (BAR, 67, 90)]


@pytest.fixture(scope="module")
def pushed(tmp_path_factory):
    """Three 2-bar grooves over Am: one plays bar 2's downbeat 8 ticks early and holds a note over the line, one
    plays on the lines, one pushes its loop's downbeat 6 ticks before the end."""
    root = tmp_path_factory.mktemp("pushed")
    lib = root / "lib"
    lib.mkdir()
    grooves = {"push": [(0, 45, 100, 1800), (1920, 40, 90, 2400), (BAR - 8, 45, 100, 1800), (BAR + 1920, 40, 90, 1800)],
               "ontime": [(t, 45, 80, 900) for t in (0, 1920, BAR, BAR + 1920)],
               "loop": [(0, 45, 70, 900), (BAR, 40, 70, 900), (2 * BAR - 6, 45, 70, 200)]}
    for name, notes in grooves.items():
        (lib / f"{name}.mid").write_bytes(pattern_file(960, notes))
        (lib / f"{name}.midchordinfo").write_text(chord_file((9, 1, 0, 8)))
    build(root / "bass.sqlite", folder=lib, map_name="ezbass")
    names = {r["id"]: PurePath(r["file"]).stem for r in search(root / "bass.sqlite")}
    return {(names[b.id], b.index): b for b in load_bass_bars(root / "bass.sqlite", sig=(4, 4))}


def laid(bars, register=(28, 50), chords="Am"):
    notes, _events = lay([BassPick(b, 0) for b in bars], chart_spans(chart(chords), FOUR, len(bars)), FOUR, PPQ,
                         register, "ezbass")
    return [(n.tick, n.pitch, n.length) for n in notes]


def test_a_downbeat_played_early_belongs_to_the_bar_it_anticipates(pushed):
    assert [n.tick for n in pushed[("push", 0)].notes] == [0, 1920]
    assert [n.tick for n in pushed[("push", 1)].notes] == [-8, 1920]
    assert pushed[("push", 1)].onsets == bits(0, 8)
    assert [n.tick for n in pushed[("loop", 0)].notes] == [-6, 0] and [n.tick for n in pushed[("loop", 1)].notes] == [0]
    assert pick_bass([pushed[("push", 1)]], (Bar(16, bits(0, 8), 0, 0),), seed=0)[0].distance == 0


def test_where_two_grooves_meet_the_downbeat_is_struck_once_and_nothing_rings_over(pushed):
    assert laid([pushed[("push", 0)], pushed[("ontime", 1)]]) == [(0, 45, 1800), (1920, 40, 1920), (BAR, 45, 900),
                                                                 (BAR + 1920, 45, 900)]
    assert laid([pushed[("ontime", 0)], pushed[("push", 1)]]) == [(0, 45, 900), (1920, 45, 900), (BAR - 8, 45, 1800),
                                                                 (BAR + 1920, 40, 1800)]


def test_a_groove_followed_into_its_own_next_bar_plays_as_written(pushed):
    assert laid([pushed[("push", 0)], pushed[("push", 1)]]) == [(0, 45, 1800), (1920, 40, 2400), (BAR - 8, 45, 1800),
                                                               (BAR + 1920, 40, 1800)]


def test_a_first_bar_played_early_starts_at_the_top(pushed):
    assert laid([pushed[("push", 1)]])[0][:2] == (0, 45)


@pytest.mark.parametrize("register", [(40, 44), (50, 28)])
def test_a_register_under_an_octave_is_refused(pushed, register):
    with pytest.raises(ValueError, match="at least an octave"):
        laid([pushed[("ontime", 0)]], register)


def test_a_note_played_early_takes_the_chord_of_the_bar_it_anticipates(pushed):
    assert laid([pushed[("ontime", 0)], pushed[("push", 1)]], chords="| Am | F |")[2][:2] == (BAR - 8, 41)


def test_a_picking_seed_is_0_or_more(pool):
    with pytest.raises(ValueError, match="a seed is 0 or more"):
        pick_bass(pool, (Bar(16, bits(0, 8), 0, 0),), seed=-1)
