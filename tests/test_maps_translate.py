"""Translation between maps, and remapping a Part."""

from collections import Counter

import pytest

from groovebin.events import Event, Note
from groovebin.maps import drum_map, remap, translate
from groovebin.song import Part

ADDICTIVE = "addictive-drums-2"
DKD = "drum-kit-designer"


def test_gm_to_addictive_drums_2():
    expect = {35: 36, 36: 36, 37: 42, 38: 38, 40: 38, 42: 49, 44: 48, 46: 55, 50: 71, 48: 69, 47: 69,
              45: 67, 43: 65, 41: 65, 49: 77, 57: 79, 55: 81, 52: 89, 51: 60, 53: 61, 59: 84}
    assert {n: translate(n, "gm", ADDICTIVE) for n in expect} == expect
    assert all(translate(n, "gm", ADDICTIVE) is None for n in [39, 54, 56, 58, *range(60, 82)])


def test_round_trips_that_lose_nothing():
    for n in [36, 37, 38, 41, 42, 44, 45, 46, 48, 49, 50, 51, 52, 53, 55, 57, 59]:
        assert translate(translate(n, "gm", ADDICTIVE), ADDICTIVE, "gm") == n
    for n in [36, 38, 42, 48, 49, 55, 60, 61, 65, 67, 69, 71, 77, 79, 81, 84, 89]:
        assert translate(translate(n, ADDICTIVE, "gm"), "gm", ADDICTIVE) == n


def test_an_exact_term_beats_one_that_extends_it():
    assert translate(37, "gm", ADDICTIVE) == 42
    assert translate(65, ADDICTIVE, "gm") == 41
    assert translate(36, ADDICTIVE, "gm") == 36


def test_a_term_falls_back_by_dropping_its_last_word():
    assert translate(41, ADDICTIVE, "gm") == 38
    assert translate(59, ADDICTIVE, "gm") == 44
    assert translate(52, ADDICTIVE, "gm") == 42
    assert translate(85, ADDICTIVE, "gm") == 59
    assert translate(91, ADDICTIVE, "gm") == 49
    assert translate(47, "gm", ADDICTIVE) == 69


def test_a_duplicate_translates_as_its_original():
    assert translate(39, ADDICTIVE, "gm") == translate(37, ADDICTIVE, "gm")
    assert translate(46, ADDICTIVE, "gm") == 49


def test_notes_without_a_term_or_a_counterpart_translate_to_nothing():
    for n in [5, 26, 64, 120]:
        assert drum_map(ADDICTIVE).term(n) is None and translate(n, ADDICTIVE, "gm") is None
    for n in [47, 96]:
        assert drum_map(ADDICTIVE).term(n) and translate(n, ADDICTIVE, "gm") is None


def test_a_choke_or_stick_click_never_falls_back_onto_a_strike():
    not_strikes = [(ADDICTIVE, n) for n, row in drum_map(ADDICTIVE).notes.items() if row["stroke"] in ("Choke", "Sticks")]
    not_strikes += [(DKD, n) for n, row in drum_map(DKD).notes.items() if row["name"].endswith(" Stop")]
    assert len(not_strikes) == 11
    assert [(m, n) for m, n in not_strikes if translate(n, m, "gm") is not None] == []


def test_a_choke_never_falls_back_to_the_bare_word_choke():
    assert translate(63, ADDICTIVE, DKD) is None
    assert translate(87, ADDICTIVE, DKD) is None
    assert (translate(78, ADDICTIVE, DKD), translate(77, ADDICTIVE, DKD)) == (28, 49)
    assert (translate(82, ADDICTIVE, DKD), translate(81, ADDICTIVE, DKD)) == (28, 49)


def test_a_strike_still_falls_back_to_its_first_word():
    assert {n: translate(n, ADDICTIVE, DKD) for n in (71, 91, 84)} == {71: 48, 91: 49, 84: 51}


def test_drum_kit_designer_keys_translate_like_the_gm_keys_they_sit_on():
    for n in [36, 37, 38, 39, 41, 42, 44, 45, 46, 48, 49, 51, 53, 54, 56, 57]:
        assert translate(n, DKD, "gm") == n, n
    assert {n: translate(n, DKD, ADDICTIVE) for n in [36, 38, 40, 42, 46, 28, 34, 43]} == {
        36: 36, 38: 38, 40: 37, 42: 49, 46: 55, 28: 78, 34: 38, 43: 65}


def part(*pitches, channel=10):
    return Part(960, [Note(i * 960, 240, channel, p, 100, 64) for i, p in enumerate(pitches)])


def test_remap_changes_only_pitches_and_counts_what_it_left():
    controller = Event(0, b"\xb9\x24\x40")
    source = Part(960, part(36, 38, 47, 55, 47, 26).notes, [controller], end=9600)
    out, unmapped = remap(source, ADDICTIVE, "gm")
    assert [n.pitch for n in out.notes] == [36, 38, 47, 46, 47, 26]
    assert unmapped == Counter({47: 2, 26: 1})
    assert out.events == (controller,) and out.end == 9600
    assert [(n.tick, n.length, n.channel, n.velocity, n.off_velocity) for n in out.notes] == \
           [(n.tick, n.length, n.channel, n.velocity, n.off_velocity) for n in source.notes]


def test_remap_can_drop_what_has_no_counterpart_and_its_aftertouch():
    source = Part(960, part(42, 56, 56).notes, [Event(0, b"\xa9\x38\x30"), Event(0, b"\xa9\x2a\x30"), Event(5, b"\xb9\x07\x64")])
    out, unmapped = remap(source, "gm", ADDICTIVE, unmapped="drop")
    assert [n.pitch for n in out.notes] == [49]
    assert out.events == (Event(0, b"\xa9\x31\x30"), Event(5, b"\xb9\x07\x64"))
    assert unmapped == Counter({56: 2})


def test_remap_refuses_an_unmapped_rule_it_does_not_know():
    with pytest.raises(ValueError, match="unmapped notes are kept or dropped, not 'mute'"):
        remap(Part(960), "gm", ADDICTIVE, unmapped="mute")


def test_remap_translates_a_polyphonic_aftertouch_key_with_its_notes():
    source = Part(960, part(42).notes, [Event(10, b"\xa9\x2a\x30"), Event(20, b"\xa9\x3a\x30")])
    out, _ = remap(source, "gm", ADDICTIVE)
    assert out.events == (Event(10, b"\xa9\x31\x30"), Event(20, b"\xa9\x3a\x30"))


def test_remap_keeps_to_the_channels_it_is_given():
    source = Part(960, part(42, channel=10).notes + part(42, channel=1).notes)
    out, unmapped = remap(source, "gm", ADDICTIVE, channels={10})
    assert sorted((n.channel, n.pitch) for n in out.notes) == [(1, 42), (10, 49)]
    assert not unmapped


def test_remap_output_is_in_canonical_order():
    source = Part(960, [Note(0, 240, 10, 43, 90), Note(0, 240, 10, 44, 90)])
    assert [n.pitch for n in remap(source, "gm", ADDICTIVE)[0].notes] == [48, 65]


def test_there_and_back_restores_the_core_kit():
    source = part(36, 38, 42, 44, 46, 50, 49, 51)
    back, unmapped = remap(remap(source, "gm", ADDICTIVE)[0], ADDICTIVE, "gm")
    assert back == source and not unmapped


def test_remap_refuses_an_unknown_map_a_map_to_itself_and_a_bad_channel():
    with pytest.raises(ValueError, match="no note map 'bfd'"):
        remap(Part(960), "gm", "bfd")
    with pytest.raises(ValueError, match="a remap from gm to gm would still move notes"):
        remap(Part(960), "gm", "gm")
    with pytest.raises(ValueError, match="channel 17 is not 1-16"):
        remap(Part(960), "gm", ADDICTIVE, channels={17})


def test_tom_order_survives_a_map_with_fewer_toms():
    assert [translate(n, "gm", DKD) for n in (50, 48, 47, 45, 43, 41)] == [48, 48, 48, 45, 41, 41]
    assert [translate(n, ADDICTIVE, DKD) for n in (71, 72, 69, 67, 65)] == [48, 48, 48, 45, 41]
