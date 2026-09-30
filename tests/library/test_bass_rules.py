"""A bassline by rules: a note on every kick, the chord's bass note on every change, chord tones between,
approach notes into changes, voice-led octaves and legato lengths."""

import pytest

from groovebin.harmony import Chord, chart, chart_spans
from groovebin.library.bass_rules import APPROACHES, bass_line
from groovebin.timing import MeterMap

PPQ, BAR = 960, 3840
FOUR = MeterMap(PPQ, ((0, 4, 4),))


def kicks(*ticks, velocity=100):
    return [(t, velocity) for t in ticks]


def spans(text, bars=2):
    return chart_spans(chart(text), FOUR, bars)


def test_a_note_on_every_kick_and_the_root_on_the_first():
    line = bass_line(kicks(0, 1920, BAR, BAR + 1920), [], spans("Am"), PPQ, seed=1, approach=0)
    assert [n.tick for n in line.notes] == [0, 1920, BAR, BAR + 1920]
    assert line.notes[0].pitch % 12 == 9
    assert all(n.pitch % 12 in Chord(9, "min").tones for n in line.notes)
    assert line.on_kicks == 4


def test_every_change_gets_the_chords_bass_note_kick_or_not():
    line = bass_line(kicks(0), [], spans("| Am F | C/G |"), PPQ, seed=1, approach=0)
    at = {n.tick: n.pitch % 12 for n in line.notes}
    assert (at[0], at[1920], at[BAR]) == (9, 5, 7)
    assert line.on_changes == 2


def test_a_repeated_chord_is_not_a_change():
    line = bass_line(kicks(0), [], spans("| Am | Am |"), PPQ, seed=1, approach=0)
    assert [n.tick for n in line.notes] == [0]


def test_approach_notes_lead_into_a_change():
    line = bass_line(kicks(0, BAR), [], spans("| Am | F |"), PPQ, seed=3, approach=1)
    before = [n for n in line.notes if BAR - 2 * 240 <= n.tick < BAR]
    assert len(before) == 1 and line.approaches == 1
    assert (before[0].pitch - 5) % 12 in {step % 12 for step in APPROACHES}
    assert bass_line(kicks(0, BAR), [], spans("| Am | F |"), PPQ, seed=3, approach=0).approaches == 0


def test_no_approach_where_the_line_is_already_playing():
    line = bass_line(kicks(0, BAR - 240, BAR), [], spans("| Am | F |"), PPQ, seed=3, approach=1)
    assert line.approaches == 0


def test_octaves_follow_the_line_inside_the_register():
    line = bass_line(kicks(*range(0, 2 * BAR, 480)), [], spans("| C | G |"), PPQ, seed=5, approach=0, register=(28, 50))
    pitches = [n.pitch for n in line.notes]
    assert all(28 <= p <= 50 for p in pitches)
    assert all(abs(a - b) <= 7 for a, b in zip(pitches, pitches[1:], strict=False))


def test_legato_to_the_next_note_and_no_further_than_two_beats():
    line = bass_line(kicks(0, 480, BAR), [], spans("Am", bars=2), PPQ, seed=1, approach=0)
    assert [n.length for n in line.notes] == [480, 2 * PPQ, 2 * PPQ]


def test_a_snare_the_bass_leaves_open_gets_the_mute_keyswitch():
    line = bass_line(kicks(0, 1920), [960, 1920 + 30, 2880], spans("Am", bars=1), PPQ, seed=1, approach=0, mute=15)
    mutes = sorted(n.tick for n in line.notes if n.pitch == 15)
    assert mutes == [960, 2880] and line.mutes == 2


def test_the_same_seed_gives_the_same_line():
    args = (kicks(*range(0, 2 * BAR, 480)), [], spans("| Am F | G C |"), PPQ)
    assert bass_line(*args, seed=9).notes == bass_line(*args, seed=9).notes


def test_refusals():
    with pytest.raises(ValueError, match="no chords"):
        bass_line(kicks(0), [], [], PPQ, seed=1)
    with pytest.raises(ValueError, match="a register"):
        bass_line(kicks(0), [], spans("Am"), PPQ, seed=1, register=(40, 45))
    with pytest.raises(ValueError, match="0 to 1"):
        bass_line(kicks(0), [], spans("Am"), PPQ, seed=1, approach=2)


def test_a_change_on_a_kick_takes_the_kicks_velocity():
    line = bass_line(kicks(0, velocity=111), [], spans("Am", bars=1), PPQ, seed=1, approach=0)
    assert line.notes[0].velocity == 111


def test_an_approach_note_follows_the_note_before_it():
    line = bass_line([(0, 120), (1920, 50)], [], spans("| Am | F |"), PPQ, seed=3, approach=1)
    (lead,) = [n for n in line.notes if BAR - 480 <= n.tick < BAR]
    assert lead.velocity == round(50 * 0.8)


def test_a_seed_is_0_or_more():
    with pytest.raises(ValueError, match="a seed is 0 or more"):
        bass_line(kicks(0), [], spans("Am"), PPQ, seed=-1)
