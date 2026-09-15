import pytest
from library_fixture import BAR, FILL, HAT, KICK, SNARE, TOM, index, row

from groovebin.events import Note
from groovebin.library.pattern import Pattern, fit, pattern, repeated
from groovebin.timing import MeterMap


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    return index(tmp_path_factory.mktemp("library"))


def test_bars_ticks_name_and_labels_come_from_the_row(db):
    intro, waltz, tail = pattern(row(db, "Intro")), pattern(row(db, "Chorus")), pattern(row(db, "tails/tail.mid", "Tails"))
    assert (intro.name, intro.bars, intro.ticks, intro.meter, intro.map, intro.role, intro.is_fill, intro.tempo) == \
           ("Intro", ((4, 4), (4, 4)), 2 * BAR, (4, 4), "addictive-drums-2", "intro", False, 120.0)
    assert intro.notes == (Note(0, 480, 10, KICK, 100), Note(1920, 240, 10, SNARE, 90), Note(3840, 480, 10, KICK, 100),
                           Note(5760, 240, 10, SNARE, 110))
    assert (waltz.bars, waltz.ticks, waltz.role) == (((3, 4),), 2880, "chorus")
    assert (tail.name, tail.ticks, tail.notes[-1].tick) == ("tail", BAR, BAR)


def test_a_row_that_did_not_parse_or_holds_no_notes_is_refused():
    with pytest.raises(ValueError, match="pattern ab was not parsed \\(not a file\\): nothing to use"):
        pattern({"id": "ab", "error": "not a file"})
    with pytest.raises(ValueError, match="pattern ab holds no notes: nothing to use"):
        pattern({"id": "ab", "error": None, "bars": 0})


def test_the_last_bar_alone_from_its_own_bar_line(db):
    assert [n.tick for n in pattern(row(db, "Fills 01")).last_bar()] == [0, 960, 1920]


def test_a_fill_bar_is_the_last_bar_unless_that_bar_is_only_a_landing(db):
    plain, landing, verse_fill = (pattern(row(db, v)) for v in ("Fills 01", "Fills 02", "Verse Fill 01"))
    assert [n.pitch for n in plain.fill_bar()] == [TOM, TOM, SNARE]
    assert [(n.tick, n.pitch) for n in landing.fill_bar()] == [(0, TOM), (1920, SNARE)]
    assert [n.pitch for n in verse_fill.fill_bar()] == [TOM, TOM, SNARE]
    one_bar_landing = Pattern(id="x", name="x", variant="x", bars=((4, 4),), notes=(Note(10, 120, 10, HAT, 127),),
                              map=None, role=None, is_fill=True, tempo=None)
    assert one_bar_landing.fill_bar() is None


def test_copies_back_to_back_and_notes_at_a_copys_end_dropped():
    notes = [Note(0, 240, 10, KICK, 100), Note(1920, 240, 10, SNARE, 90), Note(BAR, 10, 10, KICK, 90)]
    copies, dropped = repeated(notes, BAR, 2)
    assert (copies, dropped) == ([notes[0], notes[1], Note(BAR, 240, 10, KICK, 100), Note(BAR + 1920, 240, 10, SNARE, 90)], 2)
    assert repeated(notes, BAR, 2, end=BAR + 1920) == ([notes[0], notes[1], Note(BAR, 240, 10, KICK, 100)], 3)


def test_bars_fit_a_meter_map_and_are_refused_where_it_differs():
    meters = MeterMap(960, ((0, 4, 4), (4 * BAR, 3, 4)))
    assert fit(meters, 1, ((4, 4), (4, 4))) == (0, 2 * BAR)
    assert fit(meters, 5, ((3, 4),), times=3) == (4 * BAR, 3 * 2880)
    with pytest.raises(ValueError, match=r"^the pattern's bar 2 is 4/4 but the song is 3/4 at bar 5$"):
        fit(meters, 4, ((4, 4), (4, 4)))
    with pytest.raises(ValueError, match=r"^the phrase's bar 1 is 4/4 but the song is 3/4 at bar 6$"):
        fit(meters, 6, ((4, 4),), noun="phrase")
    with pytest.raises(ValueError, match="1 bar\\(s\\) x 4097 is past 4096 bars"):
        fit(meters, 1, ((4, 4),), times=4097)
    with pytest.raises(ValueError, match="bar 0: bars start at 1"):
        fit(meters, 0, ((4, 4),))


def test_the_fixture_fill_is_two_bars(db):
    assert FILL and pattern(row(db, "Fills 01")).bars == ((4, 4), (4, 4))


def test_a_fill_bar_index_names_the_bar_the_fill_bar_is(db):
    plain, landing, verse_fill = (pattern(row(db, v)) for v in ("Fills 01", "Fills 02", "Verse Fill 01"))
    assert (plain.fill_bar_index(), landing.fill_bar_index(), verse_fill.fill_bar_index()) == (1, 0, 0)
    assert landing.fill_bar() == landing.bar_notes(0)
