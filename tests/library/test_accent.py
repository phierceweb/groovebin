"""How hard a drum part strikes where."""

from groovebin.events import Note
from groovebin.library.accent import accent, placed, profile
from groovebin.timing import MeterMap

FOUR = MeterMap(960, ())


def hat(step, velocity):
    return Note(step * 240, 60, 10, 42, velocity)


def test_accent_is_the_hands_on_the_beat_less_on_the_off_beat_eighths():
    beats = [hat(s, 110 if s % 4 == 0 else 70) for s in range(0, 16, 2)]
    upbeats = [hat(s, 60 if s % 4 == 0 else 100) for s in range(0, 16, 2)]
    assert (accent(placed(beats, FOUR, 1, "gm")), accent(placed(upbeats, FOUR, 1, "gm"))) == (40.0, -40.0)


def test_a_compound_meter_counts_the_dotted_quarter():
    notes = [hat(s, 100 if s % 6 == 0 else 80) for s in range(0, 12, 2)]
    assert accent(placed(notes, MeterMap(960, ((0, 6, 8),)), 1, "gm")) == 20.0


def test_no_accent_without_both_sides_and_a_profile_per_voice_and_bar_length():
    assert accent(placed([hat(0, 100), hat(4, 90)], FOUR, 1, "gm")) is None
    kicks = placed([Note(0, 60, 10, 36, 120), Note(1920, 60, 10, 36, 60)], FOUR, 1, "gm")
    assert profile(kicks) == {"kick": {"16": [1.33, *[None] * 7, 0.67, *[None] * 7]}}


def test_a_shuffles_swung_eighth_is_its_off_beat():
    notes = [Note(beat * 960 + at, 60, 10, 42, 110 if at == 0 else 70) for beat in range(4) for at in (0, 640)]
    assert accent(placed(notes, FOUR, 1, "gm")) == 40.0


def test_a_meter_whose_beat_is_an_eighth_reads_the_sixteenths_between():
    seven = MeterMap(960, ((0, 7, 8),))
    notes = [hat(s, 100 if s % 2 == 0 else 60) for s in range(14)]
    assert accent(placed(notes, seven, 1, "gm")) == 40.0
