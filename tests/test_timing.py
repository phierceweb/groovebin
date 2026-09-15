import math
import time

import pytest

from groovebin.timing import MeterMap, TempoMap


def test_a_tempo_map_reads_the_tempo_in_force():
    tempos = TempoMap(((0, 500_000), (3840, 600_000)))
    assert tempos.at(0) == 500_000
    assert tempos.at(3839) == 500_000
    assert tempos.at(3840) == 600_000
    assert tempos.bpm(3840) == 60_000_000 / 600_000
    assert not tempos.defaulted


def test_two_tempos_at_one_tick_leave_the_later_in_force():
    assert TempoMap(((0, 500_000), (0, 400_000))).at(0) == 400_000


def test_a_tempo_map_with_no_points_is_120_bpm_and_says_so():
    tempos = TempoMap(())
    assert (tempos.at(0), tempos.bpm(99), tempos.defaulted) == (500_000, 120.0, True)


def test_points_before_the_first_apply_the_first():
    assert TempoMap(((960, 400_000),)).at(0) == 400_000


@pytest.mark.parametrize(("points", "message"), [
    (((0, 0),), "a tempo of 0 microseconds per quarter note is not 1-16777215"),
    (((0, 0x1000000),), "a tempo of 16777216 microseconds per quarter note is not 1-16777215"),
    (((960, 500_000), (0, 500_000)), "tempo points are not in tick order: 0 after 960"),
])
def test_a_tempo_map_refuses_what_a_file_cannot_hold(points, message):
    with pytest.raises(ValueError, match=message):
        TempoMap(points)


def test_a_meter_map_counts_bars_from_tick_0_as_bar_1():
    m = MeterMap(960, ((0, 4, 4),))
    assert (m.bar(0), m.bar(1920), m.bar(3840), m.bar(-3840)) == (1.0, 1.5, 2.0, 0.0)
    assert (m.tick(1.0), m.tick(1.5), m.tick(0.0)) == (0, 1920, -3840)
    assert (m.bar_line(3), m.bar_of(3839), m.bar_of(3840), m.bar_of(-1)) == (7680, 1, 2, 0)
    assert m.meter_at(-99) == (4, 4)


def test_a_meter_change_on_a_bar_line_takes_effect_there():
    m = MeterMap(960, ((0, 4, 4), (7680, 3, 4)))
    assert m.changes == ((0, 4, 4), (7680, 3, 4))
    assert (m.bar(7680), m.bar(7680 + 2880), m.bar_line(5)) == (3.0, 4.0, 7680 + 2 * 2880)
    assert (m.tick(4.5), m.bar_of(10559), m.bar_of(10560)) == (7680 + 2880 + 1440, 3, 4)
    assert (m.meter_at(7679), m.meter_at(7680)) == ((4, 4), (3, 4))


def test_a_meter_change_off_a_bar_line_snaps_to_the_next_one():
    m = MeterMap(960, ((0, 4, 4), (5000, 3, 4)))
    assert m.changes == ((0, 4, 4), (7680, 3, 4))
    assert m.meter_at(6000) == (4, 4)


def test_changes_that_snap_to_one_bar_line_leave_the_later_in_force():
    m = MeterMap(960, ((0, 4, 4), (5000, 3, 4), (7000, 6, 8)))
    assert m.changes == ((0, 4, 4), (7680, 6, 8))


def test_a_map_without_a_change_at_tick_0_starts_in_4_4():
    m = MeterMap(960, ((3840, 3, 4),))
    assert m.changes == ((0, 4, 4), (3840, 3, 4))
    assert not m.defaulted


def test_an_empty_meter_map_is_4_4_and_says_so():
    m = MeterMap(480, ())
    assert (m.changes, m.defaulted, m.bar_line(2)) == (((0, 4, 4),), True, 1920)


@pytest.mark.parametrize(("ppq", "changes", "message"), [
    (0, (), "a PPQ of 0 is not 1 or more"),
    (960, ((0, 0, 4),), "a meter of 0/4 needs a numerator of 1 or more"),
    (960, ((0, 3, 6),), "a meter of 3/6 needs a power-of-two denominator"),
    (120, ((0, 7, 64),), "a bar of 7/64 at PPQ 120 is not a whole number of ticks"),
    (960, ((-3840, 3, 4),), "a meter change at tick -3840 is before bar 1"),
    (960, ((3840, 3, 4), (0, 4, 4)), "meter changes are not in tick order: 0 after 3840"),
])
def test_a_meter_map_refuses_what_it_cannot_count(ppq, changes, message):
    with pytest.raises(ValueError, match=message):
        MeterMap(ppq, changes)


@pytest.mark.parametrize("bar", [math.nan, math.inf, -math.inf])
def test_tick_refuses_a_bar_that_is_not_a_finite_number(bar):
    with pytest.raises(ValueError, match="is not a finite number"):
        MeterMap(960, ()).tick(bar)


def test_lookups_on_maps_of_many_changes_take_no_quadratic_time():
    meters = MeterMap(16, tuple(change for k in range(20_000) for change in ((48 * k, 1, 4), (48 * k + 16, 2, 4))))
    tempos = TempoMap(tuple((tick, 500_000 + tick % 7) for tick in range(40_000)))
    start = time.perf_counter()
    assert sum(meters.bar_of(tick) for tick in range(0, 960_000, 24)) == 800_020_000
    assert tempos.at(39_999) == 500_000 + 39_999 % 7 and len({tempos.at(tick) for tick in range(40_000)}) == 7
    assert time.perf_counter() - start < 3
