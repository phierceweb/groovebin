"""Tempo ramps read from a map's points."""

from groovebin.timing import Ramp, TempoMap


def line(start, end, lo, hi, step):
    """Points every ``step`` ticks on a ramp from ``lo`` to ``hi`` bpm, ending on ``hi`` at ``end``."""
    return tuple((t, round(60_000_000 / (lo + (hi - lo) * (t - start) / (end - start))))
                 for t in [*range(start, end, step), end])


def test_a_dense_run_on_a_straight_line_is_one_ramp():
    (ramp,) = TempoMap(line(0, 3840, 100, 120, 240)).ramps(960)
    assert ramp == Ramp(0, 3840, 600_000, 500_000, 17)
    assert (ramp.from_bpm, ramp.to_bpm) == (100.0, 120.0)


def test_steps_a_bar_apart_and_a_held_tempo_are_not_ramps():
    assert TempoMap(((0, 600_000), (3840, 545_455), (7680, 500_000))).ramps(960) == ()
    assert TempoMap(((0, 500_000), (240, 500_000), (480, 500_000))).ramps(960) == ()
    assert TempoMap(()).ramps(960) == ()


def test_a_ramp_stops_where_the_line_turns():
    up, down = line(0, 1920, 100, 120, 240), line(2160, 3840, 118, 100, 240)
    assert [(r.start, r.end, r.points) for r in TempoMap(up + down).ramps(960)] == [(0, 1920, 9), (2160, 3840, 8)]


def test_two_points_at_one_tick_end_a_run():
    points = line(0, 960, 100, 110, 240) + ((960, 545_455),)
    assert TempoMap(points).ramps(960) == (Ramp(0, 960, 600_000, 545_455, 5),)


def test_points_at_one_tick_count_once_as_the_later():
    once = line(0, 1920, 100, 120, 120)
    twice = tuple(sorted(once + once, key=lambda p: p[0]))
    assert TempoMap(twice).points == once and TempoMap(twice).ramps(960) == TempoMap(once).ramps(960)
    overridden = TempoMap(((1920, 1_000_000), (1920, 500_000)))
    assert (overridden.points, overridden.at(0), overridden.seconds(1920, 960)) == (((1920, 500_000),), 500_000, 1.0)


def test_two_ramps_meeting_on_one_point_both_read_back():
    m = TempoMap(()).with_ramp(0, 3840, 100, 120, 240).with_ramp(3840, 7680, 120, 100, 240)
    assert [(r.start, r.end, round(r.from_bpm, 3), round(r.to_bpm, 3)) for r in m.ramps(960)] == \
        [(0, 3840, 100.0, 120.0), (3840, 7680, 120.0, 100.0)]


def test_finding_ramps_takes_time_in_line_with_the_points():
    import time
    points = line(0, 20_000 * 24, 60, 300, 24)
    began = time.perf_counter()
    assert len(TempoMap(points).ramps(960)) == 1
    assert time.perf_counter() - began < 3
