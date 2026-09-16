import random

import pytest

from groovebin.events import Event, Note
from groovebin.song import Part
from groovebin.timing import MeterMap
from groovebin.transforms import (Operation, Range, apply, apply_all, humanize, parse_operation, position_ticks,
                                  select)


def note(at, pitch=60, velocity=80, length=240, channel=1):
    return Note(at, length, channel, pitch, velocity)


def part(*notes, events=(), ppq=960):
    return Part(ppq, notes, events)


FOUR_FOUR = MeterMap(960, ())
EIGHT = part(*(note(k * 240, 36 + k, 10 + k * 10, 100 + k) for k in range(8)), events=(Event(100, b"\xb0\x01\x40"),))


def test_a_range_holds_its_bounds_as_written():
    assert [Range(2, 4).holds(v) for v in (1, 2, 3, 4, 5)] == [False, True, True, True, False]
    assert [Range(2, 4, lo_open=True, hi_open=True).holds(v) for v in (2, 3, 4)] == [False, True, False]
    assert [Range(2, 4, outside=True).holds(v) for v in (1, 3, 5)] == [True, False, True]
    assert Range(None, None).holds(-5) and Range(3, None).holds(1000) and not Range(None, 3, hi_open=True).holds(3)


def test_position_ticks_treats_a_whole_bar_number_as_the_whole_bar():
    bar = 3840
    assert position_ticks(Range(9, 12), FOUR_FOUR) == Range(8 * bar, 12 * bar, False, True)
    assert position_ticks(Range(9, 9), FOUR_FOUR) == Range(8 * bar, 9 * bar, False, True)
    assert position_ticks(Range(None, 12, hi_open=True), FOUR_FOUR) == Range(None, 11 * bar, False, True)
    assert position_ticks(Range(None, 12), FOUR_FOUR) == Range(None, 12 * bar, False, True)
    assert position_ticks(Range(12, None, lo_open=True), FOUR_FOUR) == Range(12 * bar, None, False, False)
    assert position_ticks(Range(9.5, 10.25), FOUR_FOUR) == Range(8 * bar + 1920, 9 * bar + 960, False, False)
    assert position_ticks(Range(9.5, 10.25, hi_open=True), FOUR_FOUR, start=bar) == Range(7 * bar + 1920, 8 * bar + 960, False, True)
    assert position_ticks(Range(9, 9, outside=True), FOUR_FOUR).outside


def test_position_ticks_follows_the_meter_map_through_its_changes():
    meters = MeterMap(960, ((0, 3, 4), (2880, 4, 4), (2880 + 3840, 7, 8)))    # bar 1 in 3/4, bar 2 in 4/4, bar 3 on in 7/8
    assert position_ticks(Range(2, 2), meters) == Range(2880, 6720, False, True)
    assert position_ticks(Range(3, 4), meters) == Range(6720, 13440, False, True)
    assert position_ticks(Range(3.5, 3.5), meters) == Range(8400, 8400)
    assert position_ticks(Range(None, 3, hi_open=True), meters, start=2880) == Range(None, 3840, False, True)


def test_a_position_before_bar_1_is_refused():
    for rng in (Range(0, 1), Range(1, 0), Range(None, 0), Range(-2, None)):
        with pytest.raises(ValueError, match="before bar 1"):
            position_ticks(rng, FOUR_FOUR)
    assert position_ticks(Range(1, 1), FOUR_FOUR) == Range(0, 3840, False, True)


def test_select_by_each_field_and_by_a_value():
    assert select(EIGHT, pitch=Range(38, 40)) == frozenset({2, 3, 4})
    assert select(EIGHT, velocity=Range(None, 30, hi_open=True), tick=Range(240, None)) == frozenset({1})
    assert select(EIGHT, length=105) == frozenset({5})
    assert select(EIGHT, channel=2) == frozenset()
    assert select(EIGHT) == frozenset(range(8))


ALL = frozenset(range(8))


def velocities(p):
    return [n.velocity for n in p.notes]


def test_each_operation_has_a_known_answer():
    assert velocities(apply(EIGHT, ALL, field="velocity", op="set", value=64)) == [64] * 8
    assert velocities(apply(EIGHT, ALL, field="velocity", op="add", value=-15)) == [1, 5, 15, 25, 35, 45, 55, 65]
    assert velocities(apply(EIGHT, ALL, field="velocity", op="mul", value=2)) == [20, 40, 60, 80, 100, 120, 127, 127]
    assert velocities(apply(EIGHT, ALL, field="velocity", op="min", value=35)) == [35, 35, 35, 40, 50, 60, 70, 80]
    assert velocities(apply(EIGHT, ALL, field="velocity", op="max", value=35)) == [10, 20, 30, 35, 35, 35, 35, 35]
    assert [n.pitch for n in apply(EIGHT, ALL, field="pitch", op="flip", value=40).notes] == [44, 43, 42, 41, 40, 39, 38, 37]
    assert [n.pitch for n in apply(EIGHT, ALL, field="pitch", op="reverse").notes] == [43, 42, 41, 40, 39, 38, 37, 36]
    assert [(n.tick, n.pitch) for n in apply(EIGHT, ALL, field="tick", op="reverse").notes] == \
        [(k * 240, 43 - k) for k in range(8)]
    assert velocities(apply(EIGHT, ALL, field="velocity", op="crescendo", value=(40, 120))) == \
        [40, 51, 63, 74, 86, 97, 109, 120]
    assert velocities(apply(EIGHT, ALL, field="velocity", op="exp", value=2.0)) == [2, 4, 8, 13, 20, 29, 39, 51]
    assert [n.tick for n in apply(part(note(100), note(119), note(120), note(360)), frozenset(range(4)),
                                  field="tick", op="quantize", value=240).notes] == [0, 0, 240, 480]
    assert [n.length for n in apply(EIGHT, ALL, field="length", op="quantize", value=100).notes] == [100] * 5 + [100, 100, 100]


def test_a_position_quantize_snaps_to_the_grid_lines_of_its_bar():
    seven_eight = MeterMap(960, ((0, 7, 8),))            # a 3360-tick bar: 1/4 lines at 0, 960, 1920, 2880, 3360
    p, both = part(note(3200), note(3400)), frozenset({0, 1})
    assert [n.tick for n in apply(p, both, field="tick", op="quantize", value=960, meters=seven_eight).notes] == [3360, 3360]
    assert [n.tick for n in apply(p, both, field="tick", op="quantize", value=960).notes] == [2880, 3840]
    assert [n.length for n in apply(EIGHT, ALL, field="length", op="quantize", value=100, meters=FOUR_FOUR).notes] == [100] * 8


def test_random_is_seeded_and_bounded():
    a = apply(EIGHT, ALL, field="velocity", op="random", value=12, seed=7)
    b = apply(EIGHT, ALL, field="velocity", op="random", value=12, seed=7)
    c = apply(EIGHT, ALL, field="velocity", op="random", value=12, seed=8)
    assert a == b and a != c
    assert all(abs(x - y) <= 12 for x, y in zip(velocities(a), velocities(EIGHT), strict=True))
    assert all(1 <= v <= 127 for v in velocities(a))


def test_only_selected_notes_change_and_events_ride_through():
    out = apply(EIGHT, frozenset({2, 5}), field="velocity", op="set", value=1)
    assert velocities(out) == [10, 20, 1, 40, 50, 1, 70, 80]
    assert out.events == EIGHT.events
    assert apply(EIGHT, frozenset(), field="velocity", op="set", value=1) == EIGHT


def test_every_operation_reads_the_note_as_it_was_and_a_second_on_one_field_reads_the_first():
    ops = [Operation("velocity", "min", 20), Operation("velocity", "max", 110), Operation("tick", "add", 100)]
    out = apply_all(EIGHT, ALL, ops)
    assert velocities(out) == [20, 20, 30, 40, 50, 60, 70, 80] and [n.tick for n in out.notes] == [k * 240 + 100 for k in range(8)]
    crescendo = apply_all(EIGHT, ALL, [Operation("tick", "reverse"), Operation("velocity", "crescendo", (1, 8))])
    assert velocities(crescendo) == [8, 7, 6, 5, 4, 3, 2, 1]


def test_an_exp_curve_needs_a_positive_exponent_and_reads_a_velocity_in_range():
    for bad in (0.0, -1.0):
        with pytest.raises(ValueError, match="not a number above 0"):
            apply(EIGHT, ALL, field="velocity", op="exp", value=bad)
    lowered = apply_all(part(note(0, velocity=50)), frozenset({0}),
                        [Operation("velocity", "add", -100), Operation("velocity", "exp", 0.5)])
    assert velocities(lowered) == [1]


def test_results_are_held_to_each_fields_range():
    assert [n.pitch for n in apply(EIGHT, ALL, field="pitch", op="add", value=100).notes] == [127] * 8
    assert [n.length for n in apply(EIGHT, ALL, field="length", op="add", value=-500).notes] == [1] * 8
    assert [n.channel for n in apply(EIGHT, ALL, field="channel", op="set", value=40).notes] == [16] * 8


def test_refusals():
    with pytest.raises(ValueError, match=r"a note would land 300 tick\(s\) before the part's start"):
        apply(EIGHT, ALL, field="tick", op="add", value=-300)
    with pytest.raises(ValueError, match="exp is a velocity curve"):
        apply(EIGHT, ALL, field="length", op="exp", value=2.0)
    with pytest.raises(ValueError, match="note index 9 is not in the part's 8 note"):
        apply(EIGHT, frozenset({9}), field="velocity", op="set", value=1)
    with pytest.raises(ValueError, match="no operation grow"):
        apply_all(EIGHT, ALL, [Operation("velocity", "grow", 1)])
    with pytest.raises(ValueError, match="quantize takes a grid of 1 tick or more"):
        apply(EIGHT, ALL, field="tick", op="quantize", value=0)


def test_a_note_already_before_the_start_may_move_earlier():
    out = apply(part(note(-100), note(500)), frozenset({0}), field="tick", op="add", value=-50)
    assert [n.tick for n in out.notes] == [-150, 500]


def test_humanize_moves_each_field_within_its_amount_and_repeats_with_a_seed():
    out = humanize(EIGHT, position=10, velocity=8, length=5, seed=3)
    for old, new in zip(EIGHT.notes, out.notes, strict=True):
        assert abs(new.tick - old.tick) <= 10 and abs(new.velocity - old.velocity) <= 8 and abs(new.length - old.length) <= 5
    assert out != EIGHT and out == humanize(EIGHT, position=10, velocity=8, length=5, seed=3)
    assert humanize(EIGHT, position=10, velocity=8, length=5, seed=random.Random(3)) == out
    assert humanize(EIGHT) == EIGHT
    with pytest.raises(ValueError, match="humanize velocity of -1"):
        humanize(EIGHT, velocity=-1)


def test_a_random_move_of_position_stops_at_the_parts_start_and_a_deliberate_one_is_refused():
    downbeat = part(note(0), note(3))
    for seed in range(20):
        out = humanize(downbeat, position=10, seed=seed)
        assert all(n.tick >= 0 for n in out.notes)
    assert any(humanize(downbeat, position=10, seed=s).notes[0].tick == 0 for s in range(20))
    with pytest.raises(ValueError, match="before the part's start"):
        apply(downbeat, frozenset({0, 1}), field="tick", op="add", value=-5)


def test_a_random_move_does_not_excuse_another_operations_move_before_the_start():
    with pytest.raises(ValueError, match="before the part's start"):
        apply_all(EIGHT, ALL, [Operation("tick", "add", -300), Operation("tick", "random", 5)])


def test_a_quantize_operation_refuses_a_meter_map_at_another_ppq():
    at_480 = part(note(500), ppq=480)
    with pytest.raises(ValueError, match="the meter map is at PPQ 96 but the part is at PPQ 480"):
        apply(at_480, None, field="tick", op="quantize", value=480, meters=MeterMap(96, ()))
    assert apply(at_480, None, field="tick", op="quantize", value=480, meters=MeterMap(480, ())).notes[0].tick == 480


def test_the_before_the_start_refusal_is_the_deliberate_move_and_not_the_random_draw():
    """The draw decides neither the number nor whether the run is refused."""
    moved = [Operation("tick", "add", -102), Operation("tick", "random", 5)]
    said = set()
    for seed in range(12):
        with pytest.raises(ValueError) as caught:
            apply_all(part(note(100)), None, moved, seed=seed)
        said.add(str(caught.value))
    assert said == {"a note would land 2 tick(s) before the part's start"}


def test_a_random_draw_alone_still_stops_at_the_start_rather_than_refusing():
    at_zero = part(note(0))
    assert all(apply_all(at_zero, None, [Operation("tick", "random", 5)], seed=s).notes[0].tick >= 0 for s in range(12))


def test_an_operation_writes_only_the_fields_it_names():
    zero = Part(960, (Note(0, 0, 1, 36, 100),))
    assert apply_all(zero, None, [Operation("velocity", "add", 5)]).notes[0].length == 0
    assert apply_all(zero, None, [Operation("length", "add", 0)]).notes[0].length == 1


@pytest.mark.parametrize("op", ["crescendo", "reverse"])
def test_a_ramp_or_mirror_of_channel_is_refused(op):
    value = (1, 16) if op == "crescendo" else None
    with pytest.raises(ValueError, match="not channel"):
        apply_all(EIGHT, None, [Operation("channel", op, value)])


def test_a_factor_that_carries_a_field_past_a_finite_number_is_refused():
    for spec in ("position=1" + "0" * 308, "length=1" + "0" * 308):
        with pytest.raises(ValueError, match="is not a finite number"):
            apply_all(part(note(100)), None, [parse_operation("mul", spec, ppq=960)])


def test_a_quantize_after_a_factor_refuses_rather_than_overflowing():
    ops = [parse_operation("mul", "length=1" + "0" * 308, ppq=960), parse_operation("quantize", "length=240", ppq=960)]
    with pytest.raises(ValueError, match="is not a finite number"):
        apply_all(part(note(100)), None, ops)


def test_an_operation_crescendo_takes_the_same_velocity_band_a_preset_does():
    with pytest.raises(ValueError, match=r"not inside 1\.\.127"):
        apply_all(EIGHT, None, [Operation("velocity", "crescendo", (-5, 500))])
    assert apply_all(EIGHT, None, [Operation("velocity", "crescendo", (110, 30))]).notes[0].velocity == 110


def test_an_operation_is_refused_on_its_own_terms_even_when_nothing_is_selected():
    empty = frozenset()
    for bad in (Operation("channel", "reverse"), Operation("channel", "crescendo", (1, 8)),
                Operation("pitch", "exp", 2.0), Operation("tick", "quantize", 0),
                Operation("velocity", "crescendo", (-5, 500))):
        with pytest.raises(ValueError):
            apply_all(EIGHT, empty, [bad])
    with pytest.raises(ValueError, match="PPQ"):
        apply_all(EIGHT, empty, [Operation("velocity", "add", 1)], meters=MeterMap(96, ()))


def test_a_field_is_named_the_way_the_command_line_names_it():
    huge = parse_operation("mul", "position=1" + "0" * 308, ppq=960)
    with pytest.raises(ValueError, match="took position to inf"):
        apply_all(part(note(100)), None, [huge])
