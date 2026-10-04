"""Tempo points and ramps written into a map."""

import re

import pytest

from groovebin.timing import TempoMap, ramp_points


def test_ramp_points_hold_the_lines_bpm_at_each_step_and_end_on_the_target():
    assert ramp_points(0, 960, 100, 120, 480) == ((0, 600_000), (480, 545_455), (960, 500_000))
    assert ramp_points(0, 1000, 100, 120, 480)[-2:] == ((960, 503_356), (1000, 500_000))


def test_a_written_ramp_reads_back_as_that_ramp():
    (ramp,) = TempoMap(ramp_points(3840, 7680, 120, 140, 240)).ramps(960)
    assert (ramp.start, ramp.end, ramp.points, ramp.from_bpm, round(ramp.to_bpm, 3)) == (3840, 7680, 17, 120.0, 140.0)


@pytest.mark.parametrize(("args", "message"), [
    ((960, 960, 100, 120, 240), "a ramp from tick 960 to 960 does not move forward"),
    ((0, 960, 100, 120, 0), "a ramp step of 0 tick(s) is not 1 or more"),
    ((0, 960, 0, 120, 240), "a tempo of 0 bpm is not a finite number above 0"),
    ((0, 960, 3, 120, 240), "3 bpm is 20000000 microseconds per quarter note, not 1-16777215"),
])
def test_a_ramp_that_cannot_be_written_is_refused(args, message):
    with pytest.raises(ValueError, match=re.escape(message)):
        ramp_points(*args)


def test_with_point_pins_the_tempo_before_it_and_replaces_a_point_on_its_tick():
    assert TempoMap(()).with_point(3840, 100).points == ((0, 500_000), (3840, 600_000))
    m = TempoMap(((0, 500_000), (3840, 600_000), (7680, 400_000)))
    assert m.with_point(3840, 120).points == ((0, 500_000), (3840, 500_000), (7680, 400_000))
    assert TempoMap(((1920, 400_000),)).with_point(3840, 100).points == \
        ((0, 400_000), (1920, 400_000), (3840, 600_000))


def test_with_ramp_replaces_the_points_from_its_start_through_its_end():
    m = TempoMap(((0, 500_000), (1920, 450_000), (3840, 600_000), (7680, 400_000)))
    out = m.with_ramp(960, 3840, 120, 100, 960)
    assert out.points == ((0, 500_000), (960, 500_000), (1920, 529_412), (2880, 562_500), (3840, 600_000),
                          (7680, 400_000))
    assert out.seconds(960, 960) == m.seconds(960, 960)


def test_an_edit_before_bar_1_is_refused():
    with pytest.raises(ValueError, match="a tempo point at tick -1 is before bar 1"):
        TempoMap(()).with_point(-1, 100)


def test_a_ramp_of_two_points_is_refused_as_a_tempo_step():
    with pytest.raises(ValueError, match=re.escape("a ramp from tick 0 to 960 in steps of 960 has no point between "
                                                   "its ends")):
        ramp_points(0, 960, 100, 120, 960)
    assert len(ramp_points(0, 961, 100, 120, 960)) == 3


@pytest.mark.parametrize(("ppq", "start", "end", "lo", "hi", "step"), [
    (480, 0, 1920, 400, 800, 7),
    (480, 0, 1920, 900, 1000, 3),
    (15360, 0, 61445, 100, 100.5, 1),
    (960, 0, 3840, 100, 100.5, 1),
])
def test_a_written_ramp_reads_back_as_one_ramp_at_any_tempo_and_step(ppq, start, end, lo, hi, step):
    points = ramp_points(start, end, lo, hi, step)
    assert [(r.start, r.end, r.points) for r in TempoMap(points).ramps(ppq)] == [(start, end, len(points))]
