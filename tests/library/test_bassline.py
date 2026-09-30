"""What a bassline does: its rhythm on its own, against a drum part, and against a chord chart."""

import pytest

from groovebin.events import Note
from groovebin.harmony import chart, chart_spans
from groovebin.library.bassline import analyze
from groovebin.timing import MeterMap

PPQ, BAR = 960, 3840
FOUR = MeterMap(PPQ, ((0, 4, 4),))
KICK, SNARE = 36, 38


def notes(*pairs, length=480):
    return [Note(t, length, 1, p, 90) for t, p in pairs]


BASS = notes((0, 45), (1920, 45), (2400, 40), (3360, 48),
             (BAR, 41), (BAR + 1920, 41), (BAR + 2400, 48), (BAR + 3360, 45))
DRUMS = [Note(b + t, 120, 10, p, 100) for b in (0, BAR) for t, p in ((0, KICK), (1920, KICK), (960, SNARE),
                                                                      (2880, SNARE))]


def test_the_rhythm_on_its_own():
    report = analyze(BASS, FOUR, 2)
    assert (report.notes, report.onsets_per_bar, report.on_beat, report.register) == (8, 4.0, 0.5, (40, 48))
    assert report.scale == "C major / A minor"
    assert (report.with_kick, report.kicks_followed, report.on_snare, report.on_change, report.tones) == \
           (None, None, None, None, None)


def test_against_the_drums():
    report = analyze(BASS, FOUR, 2, drums=DRUMS, drum_map="gm")
    assert (report.with_kick, report.kicks_followed, report.on_snare) == (0.5, 1.0, 0.0)


def test_a_bass_note_a_32nd_off_the_kick_is_with_it():
    late = notes((30, 45), (1920 + 150, 45))
    assert analyze(late, FOUR, 1, drums=DRUMS, drum_map="gm").with_kick == 0.5


def test_against_a_chart():
    report = analyze(BASS, FOUR, 2, spans=chart_spans(chart("| Am | F |"), FOUR, 2))
    assert report.on_change == 1.0
    assert report.tones == {"root": 0.5, "third": 0.25, "fifth": 0.25, "seventh": 0.0, "other": 0.0}


def test_a_chart_with_no_change_has_no_change_to_score():
    assert analyze(BASS, FOUR, 2, spans=chart_spans(chart("Am"), FOUR, 2)).on_change is None


def test_keyswitches_are_counted_not_played():
    line = BASS + [Note(3360, 5, 1, 16, 100)]
    report = analyze(line, FOUR, 2, bass_map="ezbass")
    assert report.notes == 8 and report.keyswitches == {"keyswitch repeat ghost": 1}


def test_a_drum_map_is_needed_for_drums_and_a_bass_map_for_keyswitches():
    with pytest.raises(ValueError, match="needs a drum map"):
        analyze(BASS, FOUR, 2, drums=DRUMS)
    with pytest.raises(ValueError, match="ezbass is a bass map, not a drum map"):
        analyze(BASS, FOUR, 2, drums=DRUMS, drum_map="ezbass")
    with pytest.raises(ValueError, match="gm is a drums map, not a bass map"):
        analyze(BASS, FOUR, 2, bass_map="gm")


def test_the_beat_is_the_meters_own():
    jig = MeterMap(PPQ, ((0, 6, 8),))
    line = notes((0, 45), (1440, 45), (1920, 45), (4320, 45))
    assert analyze(line, jig, 2).on_beat == 0.75


def test_only_the_bars_read_count():
    two_bars = notes(*((t, 45) for t in range(0, BAR, 960)), *((BAR + t, 52) for t in range(0, BAR, 480)))
    four_bars_of_kicks = [Note(b + t, 120, 10, KICK, 100) for b in range(0, 4 * BAR, BAR) for t in (0, 1920)]
    report = analyze(two_bars, FOUR, 1, drums=four_bars_of_kicks, drum_map="gm")
    assert (report.notes, report.onsets_per_bar, report.on_beat, report.register) == (4, 4.0, 1.0, (45, 45))
    assert (report.with_kick, report.kicks_followed) == (0.5, 1.0)


@pytest.mark.parametrize(("pitch", "symbol"), [(47, "C7"), (50, "Gdim"), (43, "Csus4"), (40, "C/E")])
def test_a_degree_is_the_charts_own(pitch, symbol):
    """B is not C7's seventh (B flat), D not G diminished's fifth (D flat), G is Csus4's fifth, E is C/E's third."""
    report = analyze(notes((0, pitch), length=BAR), FOUR, 1, spans=chart_spans(chart(symbol), FOUR, 1))
    held = {degree for degree, share in report.tones.items() if share}
    assert held == {{"C7": "other", "Gdim": "other", "Csus4": "fifth", "C/E": "third"}[symbol]}
