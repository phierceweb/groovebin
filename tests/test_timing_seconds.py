"""Ticks to seconds and back over a tempo map."""

import math
from bisect import bisect_left

import pytest

from groovebin.timing import TempoMap

TWO = TempoMap(((0, 500_000), (3840, 600_000)))


def test_seconds_add_each_stretch_at_its_own_tempo():
    assert TWO.seconds(0, 960) == 0.0
    assert TWO.seconds(3840, 960) == 2.0
    assert math.isclose(TWO.seconds(4800, 960), 2.6)


def test_a_map_with_no_points_runs_at_120_bpm():
    assert TempoMap(()).seconds(960, 960) == 0.5


def test_the_first_point_applies_before_it_and_before_tick_0():
    early = TempoMap(((960, 400_000),))
    assert (early.seconds(0, 960), early.seconds(960, 960), early.seconds(1920, 960)) == (0.0, 0.4, 0.8)
    assert TWO.seconds(-960, 960) == -0.5


def test_the_later_of_two_points_at_one_tick_is_the_one_counted():
    both = TempoMap(((0, 500_000), (0, 400_000)))
    assert both.seconds(960, 960) == 0.4
    assert both.tick_at(0.4, 960) == 960


def test_tick_at_inverts_seconds_to_the_nearest_tick():
    for tick in (-480, 0, 1, 959, 3840, 4321, 100_000):
        assert TWO.tick_at(TWO.seconds(tick, 960), 960) == tick
    per_tick = TWO.seconds(1, 960)
    assert (TWO.tick_at(per_tick * 0.6, 960), TWO.tick_at(per_tick * 0.4, 960)) == (1, 0)
    assert TempoMap(()).tick_at(0.5, 960) == 960


def test_milliseconds_round_each_ticks_time_half_up():
    assert [TWO.milliseconds(t, 960) for t in (0, 1, 3840, 4800, -960)] == [0, 1, 2000, 2600, -500]
    assert [TempoMap(((0, 1000),)).milliseconds(t, 2) for t in (1, 3, 5)] == [1, 2, 3]     # 0.5, 1.5, 2.5 ms


@pytest.mark.parametrize(("tempos", "ppq"), [
    (TWO, 960), (TempoMap(()), 960), (TempoMap(((960, 400_000), (2000, 1_000_000))), 960),
    (TempoMap(((0, 1),)), 1), (TempoMap(((0, 3),)), 7), (TempoMap(((700, 652_177),)), 480),
])
def test_first_tick_at_is_the_first_tick_that_reaches_a_millisecond(tempos, ppq):
    """A tempo sharing no factor with the PPQ puts a tick's time on every fraction of a millisecond, the half too."""
    ticks = range(-2000, 6000)
    ms = [tempos.milliseconds(t, ppq) for t in ticks]
    for m in range(ms[0] + 1, ms[-1] + 1):
        assert tempos.first_tick_at(m, ppq) == ticks[bisect_left(ms, m)], m


def test_first_tick_at_takes_any_whole_millisecond():
    assert TWO.first_tick_at(10**30, 960) > 0
    with pytest.raises(ValueError, match="0.5 is not a whole number of milliseconds"):
        TWO.first_tick_at(0.5, 960)


@pytest.mark.parametrize(("call", "message"), [
    (lambda: TWO.tick_at(math.inf, 960), "inf seconds is not a finite number"),
    (lambda: TWO.seconds(0, 0), "a PPQ of 0 is not 1 or more"),
    (lambda: TWO.tick_at(1.0, 0), "a PPQ of 0 is not 1 or more"),
])
def test_what_has_no_answer_is_refused(call, message):
    with pytest.raises(ValueError, match=message):
        call()
