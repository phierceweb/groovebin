"""Ticks to seconds and back over a tempo map."""

import math

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


@pytest.mark.parametrize(("call", "message"), [
    (lambda: TWO.tick_at(math.inf, 960), "inf seconds is not a finite number"),
    (lambda: TWO.seconds(0, 0), "a PPQ of 0 is not 1 or more"),
    (lambda: TWO.tick_at(1.0, 0), "a PPQ of 0 is not 1 or more"),
])
def test_what_has_no_answer_is_refused(call, message):
    with pytest.raises(ValueError, match=message):
        call()
