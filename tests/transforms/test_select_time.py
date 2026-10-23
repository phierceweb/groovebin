"""`time_ticks`: a position Range in milliseconds as ticks, each note's time read to the millisecond."""

import pytest

from groovebin.timing import TempoMap
from groovebin.transforms import Range, time_ticks


def test_time_ticks_follows_the_tempo_changes():
    tempos = TempoMap(((0, 500_000), (960, 1_000_000)))           # 120 bpm for a beat, then 60
    assert time_ticks(Range(250, 1500), tempos, ppq=960) == Range(480, 1921, hi_open=True)
    assert time_ticks(Range(250, 1500), tempos, ppq=960, start=480) == Range(0, 1441, hi_open=True)
    assert time_ticks(Range(250, 1500, lo_open=True, hi_open=True), tempos, ppq=960) == Range(481, 1920, hi_open=True)


@pytest.mark.parametrize(("usec", "ppq"), [(500_000, 960), (652_174, 960), (468_750, 480), (500_000, 480)])
def test_a_time_holds_every_tick_that_reads_as_it_to_the_millisecond(usec, ppq):
    """A tick shorter than a millisecond reads as its neighbour's time; both answer to that time."""
    tempos = TempoMap(((0, usec),))
    for tick in range(0, 4000, 3):
        ms = tempos.milliseconds(tick, ppq)
        held = [time_ticks(r, tempos, ppq=ppq).holds(tick) for r in (
            Range(ms, ms), Range(ms, None), Range(None, ms), Range(ms, ms, outside=True),
            Range(None, ms, hi_open=True), Range(ms, None, lo_open=True))]
        assert held == [True, True, True, False, False, False], (tick, ms)


def test_a_bound_is_whole_milliseconds():
    with pytest.raises(ValueError, match="1.5 is not a whole number of milliseconds"):
        time_ticks(Range(1.5, None), TempoMap(()), ppq=960)
