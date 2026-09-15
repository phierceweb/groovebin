import pytest
from library_fixture import BAR, GROUP, SNARE, TOM, index

from groovebin.library.compose import Section, group_patterns, plan_sections
from groovebin.library.search import find_group
from groovebin.timing import MeterMap

FOUR_FOUR = MeterMap(960, ())


@pytest.fixture(scope="module")
def patterns(tmp_path_factory):
    db = index(tmp_path_factory.mktemp("compose"))
    return group_patterns(db, *find_group(db, GROUP))


def sections(*spec):
    return [Section(name, bar * BAR, bars * BAR) for name, bar, bars in spec]


def test_group_patterns_come_in_variant_then_number_order(patterns):
    assert [p.variant for p in patterns] == ["Chorus", "Fills 01", "Fills 02", "Intro", "Verse 01", "Verse 02", "Verse Fill 01"]


def test_names_pick_grooves_by_role_and_verses_cycle_in_number_order(patterns):
    got = plan_sections(sections(("Intro", 0, 4), ("verse A", 4, 2), ("VERSE", 6, 3), ("Verse", 9, 1), ("Pre-Chorus", 10, 1),
                                 ("Chorus", 11, 2), ("Outro", 13, 1), ("", 14, 1)), FOUR_FOUR, patterns)
    assert [(p.beat.name if p.beat else None, p.copies) for p in got] == \
           [("Intro", 2), ("Verse 01", 2), ("Verse 02", 3), ("Verse 01", 1), (None, 0), (None, 0), (None, 0), (None, 0)]
    assert [p.skipped for p in got[4:]] == [
        "no Pre-Chorus pattern in the group", "no Chorus pattern in 4/4; the group's are 3/4", "no Outro pattern in the group",
        "'an unnamed section' is not an intro, verse, pre-chorus, chorus, bridge or outro"]
    assert [n.tick for n in got[2].notes] == [0, 1920, 2880, BAR, BAR + 1920, BAR + 2880, 2 * BAR, 2 * BAR + 1920, 2 * BAR + 2880]


def test_a_section_word_joined_by_an_underscore_or_a_digit_still_names_the_role(patterns):
    got = plan_sections(sections(("Verse2", 0, 1), ("Intro_1", 1, 2)), FOUR_FOUR, patterns)
    assert [(p.skipped, p.beat.name if p.beat else None) for p in got] == [(None, "Verse 01"), (None, "Intro")]


def test_a_fill_named_for_a_section_is_never_its_groove(patterns):
    for p in plan_sections(sections(*[("Verse", k, 1) for k in range(6)]), FOUR_FOUR, patterns):
        assert not p.beat.is_fill and p.beat.name != "Verse Fill 01"


def test_a_section_not_whole_patterns_long_drops_what_falls_past_it(patterns):
    (p,) = plan_sections(sections(("Intro", 0, 3)), FOUR_FOUR, patterns)
    assert (p.copies, [n.tick for n in p.notes], p.dropped) == (2, [0, 1920, 3840, 5760, 7680, 9600], 2)


def test_a_fill_replaces_the_last_bar_preferring_one_named_for_the_section(patterns):
    intro, verse = plan_sections(sections(("Intro", 0, 4), ("Verse", 4, 1)), FOUR_FOUR, patterns, fills=True)
    assert (intro.fill.name, intro.fill_bar, intro.replaced) == ("Fills 01", 4, 2)
    assert [(n.tick, n.pitch) for n in intro.notes[-4:]] == [(3 * BAR - 1920, SNARE), (3 * BAR, TOM), (3 * BAR + 960, TOM), (3 * BAR + 1920, SNARE)]
    assert verse.fill.name == "Verse Fill 01"
    assert [(n.tick, n.pitch) for n in verse.notes] == [(0, TOM), (960, TOM), (1920, SNARE)]


def test_a_fill_that_ends_on_a_landing_gives_the_bar_before(patterns):
    _first, second = plan_sections(sections(("Intro", 0, 2), ("Intro", 2, 2)), FOUR_FOUR, patterns, fills=True)
    assert second.fill.name == "Fills 02"
    assert [(n.tick, n.pitch) for n in second.notes if n.tick >= BAR] == [(BAR, TOM), (BAR + 1920, SNARE)]


def test_a_meter_change_inside_a_section_and_a_start_off_a_bar_line_are_skipped(patterns):
    waltz = MeterMap(960, ((0, 4, 4), (2 * BAR, 3, 4)))
    found = [*sections(("Intro", 0, 2), ("Verse", 1, 2)), Section("Chorus", 2 * BAR, 2 * 2880),
             Section("Bridge", 2 * BAR + 960, 2880), Section("Outro", 0, 0)]
    got = plan_sections(found, waltz, patterns, fills=True)
    assert [p.skipped for p in got] == [None, "the meter changes inside the section", None,
                                        "the section does not start on a bar line", "the section has no length"]
    assert (got[0].no_fill, got[2].beat.name, got[2].no_fill) == (None, "Chorus", "no fill pattern ending in 3/4")
    assert (got[2].start_bar, got[2].end_bar) == (3.0, 5.0)
