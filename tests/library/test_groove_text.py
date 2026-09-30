"""Rhythms typed as lanes of x and . per voice, read into bars and written back."""

import pytest

from groovebin.library.groove import Bar
from groovebin.library.groove_text import parse_rhythm, rhythm_text


def bits(*steps):
    return sum(1 << s for s in steps)


def test_a_typed_rhythm_is_lanes_of_bars():
    bars, voices = parse_rhythm("kick=x.......x.......|x.....x.x....... snare=....x.......x...|....x.......x...")
    assert voices == (0, 1)
    assert bars == (Bar(16, bits(0, 8), bits(4, 12), 0), Bar(16, bits(0, 6, 8), bits(4, 12), 0))


def test_a_lane_given_once_serves_every_bar_and_hands_is_a_voice():
    bars, voices = parse_rhythm("kick=x...x...x...x...|x.x.x.x.x.x.x.x. hands=x.x.x.x.x.x.x.x.")
    assert voices == (0, 2) and bars[1].hands == bits(*range(0, 16, 2))


def test_a_typed_rhythm_that_does_not_read_is_refused():
    for bad, message in (("", "no lanes"), ("kick", "voice=lane"), ("bass=x...", "kick, snare or hands"),
                         ("kick=x..y", "only x and ."), ("kick=x...|x.. snare=x...", "the same number of"),
                         ("kick=x... kick=x...", "given twice"), ("kick=x...||x...", "at least one step"),
                         ("kick=x...|x...|x... snare=x...|x...", "the same number of bars")):
        with pytest.raises(ValueError, match=message):
            parse_rhythm(bad)


def test_a_rhythm_prints_as_the_lanes_it_reads_from():
    bars = (Bar(16, bits(0, 8), bits(4, 12), 0), Bar(16, bits(0, 6, 8), bits(4, 12), 0))
    text = rhythm_text(bars)
    assert text == "kick=x.......x.......|x.....x.x....... snare=....x.......x...|....x.......x... hands=................|................"
    assert parse_rhythm(text)[0] == bars
