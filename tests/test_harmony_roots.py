"""The chords a bassline implies: held length decides the root, the note on a change counts three times, a bar
splits in half only when each half has a root of its own, and a third the bass holds names the quality."""

from groovebin.events import Note
from groovebin.harmony import Chord, Span, chart, chart_spans, chart_text, roots
from groovebin.timing import MeterMap

PPQ, BAR = 960, 3840
FOUR = MeterMap(PPQ, ((0, 4, 4),))
A, C, CS, E, F, G = 45, 48, 49, 40, 41, 43


def held(*spans):
    return [Note(start, length, 1, pitch, 90) for start, length, pitch in spans]


def test_a_held_root_with_no_third_is_a_power_chord():
    assert roots(held((0, BAR, A)), FOUR, 1) == [Span(0, BAR, Chord(9, "5"))]


def test_a_bar_splits_when_each_half_has_its_own_root():
    assert roots(held((0, 1920, A), (1920, 1920, F)), FOUR, 1) == [Span(0, 1920, Chord(9, "5")),
                                                                  Span(1920, BAR, Chord(5, "5"))]


def test_a_passing_note_does_not_split_the_bar():
    line = held((0, 960, A), (960, 960, A), (1920, 960, A), (2880, 960, G))
    assert roots(line, FOUR, 1) == [Span(0, BAR, Chord(9, "5"))]


def test_a_third_the_bass_holds_names_the_quality():
    assert roots(held((0, 2880, A), (2880, 960, C)), FOUR, 1)[0].chord == Chord(9, "min")
    assert roots(held((0, 2880, A), (2880, 960, CS)), FOUR, 1)[0].chord == Chord(9, "maj")


def test_the_note_on_the_change_counts_three_times():
    line = held((0, 960, E), (1200, 2640, A))
    assert roots(line, FOUR, 1)[0].chord.root == 4


def test_equal_neighbours_merge_and_a_silent_bar_carries_the_chord():
    line = held((0, BAR, A), (2 * BAR, BAR, A), (3 * BAR, BAR, F))
    assert roots(line, FOUR, 4) == [Span(0, 3 * BAR, Chord(9, "5")), Span(3 * BAR, 4 * BAR, Chord(5, "5"))]


def test_a_leading_rest_takes_the_first_chord():
    assert roots(held((BAR, BAR, A)), FOUR, 2) == [Span(0, 2 * BAR, Chord(9, "5"))]


def test_no_notes_no_chords():
    assert roots([], FOUR, 2) == []


def test_the_chart_is_a_bar_at_a_time():
    spans = roots(held((0, BAR, A), (BAR, 1920, F), (BAR + 1920, 1920, G), (2 * BAR, BAR, F), (3 * BAR, BAR, G)),
                  FOUR, 4)
    assert chart_text(spans, FOUR, 4) == "| A5 | F5 G5 | F5 | G5 |"


def test_a_chart_laid_over_bars_loops_and_shares_each_bar():
    spans = chart_spans(chart("| Am | F G |"), FOUR, 3)
    assert spans == [Span(0, BAR, Chord(9, "min")), Span(BAR, BAR + 1920, Chord(5)), Span(BAR + 1920, 2 * BAR, Chord(7)),
                     Span(2 * BAR, 3 * BAR, Chord(9, "min"))]
    waltz = MeterMap(PPQ, ((0, 3, 4),))
    assert [s.end - s.start for s in chart_spans(chart("| C F G |"), waltz, 1)] == [960, 960, 960]
