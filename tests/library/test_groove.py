import pytest

from groovebin.events import Note
from groovebin.library.groove import (Bar, bar_distance, distance, features, rhythm, subdivision, swing, syncopation,
                                      voices)
from groovebin.timing import MeterMap

PPQ = 960
KICK, SNARE, SIDESTICK, HAT, OPEN_HAT, PEDAL, RIDE, CRASH, TOM = 36, 38, 37, 42, 46, 44, 51, 49, 45
FOUR = MeterMap(PPQ, ((0, 4, 4),))


def hits(*pairs, ppq=PPQ, velocity=100):
    return [Note(tick, ppq // 8, 10, pitch, velocity) for tick, pitch in pairs]


def backbeat(bar=0, hat_step=480):
    start = bar * 4 * PPQ
    return hits((start, KICK), (start + 1920, KICK), (start + 960, SNARE), (start + 2880, SNARE),
                *((start + t, HAT) for t in range(0, 4 * PPQ, hat_step)))


def bits(*steps):
    return sum(1 << s for s in steps)


def per_beat(*offsets, beats=8, pitch=HAT):
    return hits(*((beat * PPQ + o, pitch) for beat in range(beats) for o in offsets))


def test_voices_read_the_map_not_note_numbers():
    gm = voices("gm")
    assert gm[35] == gm[36] == 0
    assert gm[SNARE] == gm[40] == gm[SIDESTICK] == 1
    assert gm[HAT] == gm[OPEN_HAT] == gm[RIDE] == gm[53] == 2
    assert PEDAL not in gm and CRASH not in gm and TOM not in gm
    ad2 = voices("addictive-drums-2")
    assert ad2[36] == 0 and ad2[37] == ad2[38] == 1
    assert ad2[49] == ad2[54] == 2 and 48 not in ad2 and 59 not in ad2


def test_a_bar_is_three_sixteenth_grids():
    (bar,) = rhythm(backbeat(), FOUR, 1, "gm")
    assert bar == Bar(16, bits(0, 8), bits(4, 12), bits(*range(0, 16, 2)))


def test_a_note_rounding_onto_the_bar_line_starts_the_next_bar():
    notes = hits((3 * PPQ + 900, KICK), (7 * PPQ + 900, SNARE))
    first, second = rhythm(notes, FOUR, 2, "gm")
    assert first.kick == 0
    assert second.kick == bits(0)
    assert second.snare == 0


def test_bars_follow_the_meter():
    notes = hits((0, KICK), (3 * PPQ, KICK), (3 * PPQ + 1440, SNARE))
    changing = MeterMap(PPQ, ((0, 3, 4), (3 * PPQ, 6, 8)))
    waltz, jig = rhythm(notes, changing, 2, "gm")
    assert (waltz.steps, waltz.kick) == (12, bits(0))
    assert (jig.steps, jig.kick, jig.snare) == (12, bits(0), bits(6))


def test_a_bar_with_no_whole_sixteenths_stays_empty_and_keeps_its_notes():
    odd_then_four = MeterMap(PPQ, ((0, 3, 32), (360, 4, 4)))
    odd, four = rhythm(hits((0, KICK), (360, SNARE)), odd_then_four, 2, "gm")
    assert odd == Bar(0, 0, 0, 0)
    assert four == Bar(16, 0, bits(0), 0)


def test_syncopation_is_zero_on_the_beat():
    assert syncopation(bits(0, 4, 8, 12), (4, 4)) == 0


def test_syncopation_counts_a_rest_on_a_stronger_position():
    # the kick on the and of 2 is followed by a rest on beat 3: weight 3 against 1
    assert syncopation(bits(0, 4, 6, 12), (4, 4)) == 2


def test_syncopation_wraps_round_the_bar():
    # the last sixteenth ties over the next downbeat: weight 4 against 0
    assert syncopation(bits(4, 8, 12, 15), (4, 4)) == 4


def test_compound_meters_group_eighths_in_threes():
    # in 6/8 the second beat is step 6; a note on step 4 resting over it syncopates
    assert syncopation(bits(0, 4), (6, 8)) == 1
    assert syncopation(bits(0, 6), (6, 8)) == 0


@pytest.mark.parametrize(("offsets", "expected"), [
    ((0,), "quarters"),
    ((0, 480), "8ths"),
    ((0, 240, 480, 720), "16ths"),
    ((0, 640), "triplets"),
])
def test_subdivision_of_the_hands(offsets, expected):
    assert subdivision(per_beat(*offsets), FOUR, "gm") == expected


def test_no_hands_no_subdivision():
    assert subdivision(hits((0, KICK), (960, SNARE)), FOUR, "gm") is None


@pytest.mark.parametrize(("offbeat", "expected"), [(480, 0.5), (640, 0.667), (560, 0.583)])
def test_swing8_is_where_the_offbeat_eighth_sits(offbeat, expected):
    assert swing(per_beat(0, offbeat), FOUR, "gm") == expected


def test_swing16_is_where_the_offbeat_sixteenth_sits_in_its_eighth():
    swung = per_beat(0, 320, 480, 800)
    assert swing(swung, FOUR, "gm", sixteenths=True) == 0.667
    assert swing(swung, FOUR, "gm") == 0.5


def test_straight_sixteenths_are_straight_both_ways():
    straight = per_beat(0, 240, 480, 720)
    assert swing(straight, FOUR, "gm") == swing(straight, FOUR, "gm", sixteenths=True) == 0.5


def test_eighths_have_no_sixteenth_swing():
    assert swing(per_beat(0, 480), FOUR, "gm", sixteenths=True) is None
    assert swing(per_beat(0, 640), FOUR, "gm", sixteenths=True) is None


def test_swing_reads_humanised_downbeats():
    notes = hits(*((beat * PPQ + o, HAT) for beat in range(8) for o in ((-12 if beat % 2 else 9), 640)))
    assert swing(notes, FOUR, "gm") == 0.667


def test_swing_needs_four_samples():
    assert swing(per_beat(0, 640, beats=3), FOUR, "gm") is None


def test_swing_is_for_quarter_note_beats():
    notes = hits(*((beat * 1440 + o, HAT) for beat in range(8) for o in (0, 480)))
    assert swing(notes, MeterMap(PPQ, ((0, 6, 8),)), "gm") is None


def test_features_of_a_backbeat():
    notes = backbeat() + backbeat(1)
    found = features(notes, FOUR, 2, "gm")
    assert found == {"density": 12.0, "syncopation": 0.0, "subdivision": "8ths", "swing8": 0.5, "swing16": None,
                     "lag": 0.0}


def test_lag_is_the_backbeat_behind_the_beat_in_ticks_at_960():
    late = [n if n.pitch != SNARE else Note(n.tick + 20, n.length, n.channel, n.pitch, n.velocity)
            for n in backbeat() + backbeat(1)]
    assert features(late, FOUR, 2, "gm")["lag"] == 20.0
    half = [Note(n.tick // 2, n.length // 2, n.channel, n.pitch, n.velocity) for n in late]
    assert features(half, MeterMap(480, ((0, 4, 4),)), 2, "gm")["lag"] == 20.0


def test_a_flam_between_beats_is_not_lag():
    notes = backbeat() + hits((1440, SNARE))
    assert features(notes, FOUR, 1, "gm")["lag"] == 0.0


def test_no_snare_near_a_beat_no_lag():
    assert features(hits((0, KICK), (480, SNARE)), FOUR, 1, "gm")["lag"] is None


def test_an_empty_part_has_no_features():
    assert features([], FOUR, 0, "gm") == {"density": None, "syncopation": None, "subdivision": None,
                                          "swing8": None, "swing16": None, "lag": None}


def test_identical_bars_are_zero_apart():
    bar = Bar(16, bits(0, 8), bits(4, 12), bits(*range(0, 16, 2)))
    assert bar_distance(bar, bar) == 0


def test_an_onset_one_sixteenth_off_counts_half():
    a = Bar(16, bits(0, 8), bits(4, 12), 0)
    near = Bar(16, bits(0, 9), bits(4, 12), 0)
    far = Bar(16, bits(0, 11), bits(4, 12), 0)
    assert bar_distance(a, near) == 1
    assert bar_distance(a, far) == 2


def test_hands_weigh_half():
    a = Bar(16, 0, 0, bits(0, 2, 4))
    assert bar_distance(a, Bar(16, 0, 0, bits(0, 2))) == 0.5


def test_bars_of_different_lengths_do_not_compare():
    assert bar_distance(Bar(16, 1, 0, 0), Bar(12, 1, 0, 0)) is None


def test_a_pattern_is_as_near_as_its_best_bar_for_each_query_bar():
    groove, other = Bar(16, bits(0, 8), bits(4, 12), 0), Bar(16, bits(0, 6), bits(4, 12), 0)
    assert distance([groove], [other, groove]) == 0
    assert distance([groove, other], [groove]) == 1
    assert distance([groove], [Bar(12, bits(0), 0, 0)]) is None


def test_only_the_voices_given_count():
    groove = Bar(16, bits(0, 8), bits(4, 12), bits(*range(16)))
    assert distance([Bar(16, bits(0, 8), 0, 0)], [groove], voices=(0,)) == 0
    assert distance([Bar(16, bits(0, 8), 0, 0)], [groove]) > 0


def test_each_unmatched_onset_pairs_with_a_near_one_once():
    """Kicks {0, 2} against {1}, and {9} against {8, 10}: in each group one pair and one onset left alone."""
    assert bar_distance(Bar(16, bits(0, 2), 0, 0), Bar(16, bits(1), 0, 0)) == 2
    both, other = Bar(16, bits(0, 2, 9), 0, 0), Bar(16, bits(1, 8, 10), 0, 0)
    assert bar_distance(both, other) == bar_distance(other, both) == 4
