"""A bassline by rules: a note on every kick, the chord's bass note on every change, chord tones between,
approach notes into changes, voice-led octaves and legato lengths."""

import pytest

from groovebin.harmony import Chord, chart, chart_spans
from groovebin.library.bass_rules import APPROACH_RATE, APPROACHES, bass_line
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


def test_snare_hits_get_a_note_as_kicks_do():
    line = bass_line(kicks(0, 1920), [], spans("Am", 1), PPQ, seed=1, approach=0, snare_hits=[(960, 90), (2880, 70)])
    assert [(n.tick, n.velocity) for n in line.notes] == [(0, 100), (960, 90), (1920, 100), (2880, 70)]
    assert (line.on_kicks, line.on_snares) == (2, 2)


def test_without_snare_hits_the_count_is_none_and_the_line_as_before():
    line = bass_line(kicks(0, 1920), [960, 2880], spans("Am", 1), PPQ, seed=1, approach=0)
    assert [n.tick for n in line.notes] == [0, 1920] and line.on_snares is None and line.pushes is None


def test_a_snare_on_a_kick_is_one_note_on_the_kick():
    line = bass_line(kicks(0, 1920), [], spans("Am", 1), PPQ, seed=1, approach=0, snare_hits=[(1930, 60)])
    assert [(n.tick, n.velocity) for n in line.notes] == [(0, 100), (1920, 100)]
    assert (line.on_kicks, line.on_snares) == (2, 0)


def test_a_snare_at_a_change_is_the_changes_note():
    line = bass_line(kicks(0), [], spans("| Am | F |"), PPQ, seed=1, approach=0, snare_hits=[(BAR - 20, 77)])
    assert [(n.tick, n.pitch % 12, n.velocity) for n in line.notes][-1] == (BAR, 5, 77)
    assert (line.on_kicks, line.on_snares, len(line.notes)) == (1, 1, 2)


def test_root_only_plays_each_chords_bass_note():
    line = bass_line(kicks(*range(0, 2 * BAR, 480)), [], spans("| Am | C/G |"), PPQ, seed=2, approach=0, root_only=True)
    assert {n.pitch % 12 for n in line.notes if n.tick < BAR} == {9}
    assert {n.pitch % 12 for n in line.notes if n.tick >= BAR} == {7}


def test_mutes_and_snare_notes_do_not_go_together():
    with pytest.raises(ValueError, match="mute"):
        bass_line(kicks(0), [960], spans("Am", 1), PPQ, seed=1, snare_hits=[(960, 90)], mute=15)


def test_a_push_plays_the_new_chord_in_the_last_eighth():
    args = dict(seed=1, approach=0, root_only=True)
    plain = bass_line(kicks(0, BAR - 480, BAR), [], spans("| Am | F |"), PPQ, **args)
    pushed = bass_line(kicks(0, BAR - 480, BAR), [], spans("| Am | F |"), PPQ, push=True, **args)
    assert [n.pitch % 12 for n in plain.notes] == [9, 9, 5]
    assert [n.pitch % 12 for n in pushed.notes] == [9, 5, 5]
    assert [n.tick for n in pushed.notes] == [n.tick for n in plain.notes] and pushed.pushes == 1


def test_a_push_adds_no_note_and_leaves_earlier_notes_alone():
    line = bass_line(kicks(0, BAR - 960, BAR), [], spans("| Am | F |"), PPQ, seed=1, approach=0, root_only=True, push=True)
    assert [(n.tick, n.pitch % 12) for n in line.notes] == [(0, 9), (BAR - 960, 9), (BAR, 5)] and line.pushes == 0


def test_a_push_takes_a_stroke_played_just_ahead_of_the_eighth():
    line = bass_line(kicks(0, BAR - 480 - 30, BAR), [], spans("| Am | F |"), PPQ, seed=1, approach=0, root_only=True, push=True)
    assert [n.pitch % 12 for n in line.notes] == [9, 5, 5]


def test_approach_notes_are_refused_with_a_push_or_a_rest_and_left_out_by_default():
    with pytest.raises(ValueError, match="approach notes are not written"):
        bass_line(kicks(0, BAR), [], spans("| Am | F |"), PPQ, seed=3, approach=0.5, push=True)
    with pytest.raises(ValueError, match="approach notes are not written"):
        bass_line(kicks(0, BAR), [], rested("| Am - | F |"), PPQ, seed=3, approach=1)
    for seed in range(12):
        assert bass_line(kicks(0, BAR), [], spans("| Am | F |"), PPQ, seed=seed, push=True).approaches == 0
        assert bass_line(kicks(0, BAR), [], rested("| Am - | F |"), PPQ, seed=seed).approaches == 0


def test_without_a_push_or_a_rest_the_default_rate_is_the_measured_one():
    args = (kicks(0, BAR, 2 * BAR, 3 * BAR), [], spans("| Am | F | C | G |", 4), PPQ)
    assert any(bass_line(*args, seed=seed).approaches for seed in range(12))
    assert all(bass_line(*args, seed=seed).notes == bass_line(*args, seed=seed, approach=APPROACH_RATE).notes
               for seed in range(12))


def test_a_pushed_change_with_no_stroke_on_it_gets_no_note_of_its_own():
    args = dict(seed=1, approach=0, root_only=True)
    plain = bass_line(kicks(0, BAR - 480), [], spans("| Am | F |"), PPQ, **args)
    pushed = bass_line(kicks(0, BAR - 480), [], spans("| Am | F |"), PPQ, push=True, **args)
    assert [(n.tick, n.pitch % 12) for n in plain.notes] == [(0, 9), (BAR - 480, 9), (BAR, 5)]
    assert [(n.tick, n.pitch % 12) for n in pushed.notes] == [(0, 9), (BAR - 480, 5)]
    assert (pushed.pushes, pushed.on_changes) == (1, 1)


def test_a_pushed_change_keeps_the_stroke_that_is_on_it():
    line = bass_line(kicks(0, BAR - 480, BAR), [], spans("| Am | F |"), PPQ, seed=1, approach=0, root_only=True, push=True)
    assert [n.tick for n in line.notes] == [0, BAR - 480, BAR]


def rested(text, bars=2):
    return chart_spans(chart(text, rests=True), FOUR, bars)


def test_no_note_starts_or_rings_in_a_rest():
    line = bass_line(kicks(0, 960, 1920, 2880), [], rested("| Am - |", 1), PPQ, seed=1, approach=0, root_only=True)
    assert [(n.tick, n.length) for n in line.notes] == [(0, 960), (960, 960)]


def test_a_chord_back_after_a_rest_is_no_change_and_a_new_one_is():
    same = bass_line(kicks(0), [], rested("| Am - | Am - |"), PPQ, seed=1, approach=0)
    new = bass_line(kicks(0), [], rested("| Am - | F - |"), PPQ, seed=1, approach=0)
    assert [n.tick for n in same.notes] == [0] and same.on_changes == 0
    assert [n.tick for n in new.notes] == [0] and new.on_changes == 1


def test_a_chord_after_a_rest_comes_in_on_its_first_stroke_with_its_bass_note():
    line = bass_line(kicks(0, BAR + 3360), [], rested("| Am - | - C/G |"), PPQ, seed=1, approach=0)
    assert [(n.tick, n.pitch % 12) for n in line.notes] == [(0, 9), (BAR + 3360, 7)]
    start = bass_line(kicks(2880), [], rested("| - Am |", 1), PPQ, seed=1, approach=0, push=True)
    assert [(n.tick, n.pitch % 12) for n in start.notes] == [(2880, 9)]


def test_a_stroke_just_ahead_of_a_chord_after_a_rest_plays_on_the_chord_not_in_the_rest():
    line = bass_line(kicks(0, BAR - 20), [], rested("| Am - | Am - |"), PPQ, seed=1, approach=0, root_only=True)
    assert [(n.tick, n.pitch % 12) for n in line.notes] == [(0, 9), (BAR, 9)]


def test_the_same_chord_back_after_a_rest_comes_in_on_its_bass_note():
    for seed in range(12):
        line = bass_line(kicks(0, BAR - 60, BAR + 960, BAR + 1920), [], rested("| A - | A |"), PPQ, seed=seed, approach=0)
        assert [n.tick for n in line.notes] == [0, BAR, BAR + 960, BAR + 1920]
        assert line.notes[1].pitch % 12 == 9 and line.on_changes == 0


def test_no_mute_lands_in_a_rest():
    line = bass_line(kicks(0, BAR), [960, 2880], rested("| Am - | F - |"), PPQ, seed=3, mute=15)
    assert all(n.tick < 1920 or n.tick >= BAR for n in line.notes)
    assert sorted(n.tick for n in line.notes if n.pitch == 15) == [960]


def test_a_note_is_pushed_once_onto_the_first_change_after_it():
    line = bass_line(kicks(0, 2850), [], spans("| C C C C C C C D E |", 1), PPQ, seed=1, approach=0, push=True)
    assert [(n.tick, n.pitch % 12) for n in line.notes] == [(0, 0), (2850, 2), (3413, 4)]
    assert (line.pushes, line.on_changes) == (1, 2)


def test_a_chord_after_a_rest_takes_its_bass_note_on_a_first_stroke_in_a_later_bar():
    for seed in range(12):
        line = bass_line(kicks(BAR + 960), [], rested("| - A | A |"), PPQ, seed=seed, approach=0)
        assert [(n.tick, n.pitch % 12) for n in line.notes] == [(BAR + 960, 9)]


def test_two_notes_in_one_changes_eighth_are_two_pushes():
    line = bass_line(kicks(0, BAR - 480, BAR - 240, BAR), [], spans("| Am | F |"), PPQ, seed=1, approach=0,
                     root_only=True, push=True)
    assert [n.pitch % 12 for n in line.notes] == [9, 5, 5, 5] and line.pushes == 2


def test_a_stroke_just_after_a_chord_starts_plays_on_its_start():
    after_rest = bass_line(kicks(0, BAR + 20), [], rested("| Am - | Am - |"), PPQ, seed=1, approach=0, root_only=True)
    at_change = bass_line(kicks(0, BAR + 20), [], spans("| Am | F |"), PPQ, seed=1, approach=0)
    assert [(n.tick, n.pitch % 12) for n in after_rest.notes] == [(0, 9), (BAR, 9)]
    assert [(n.tick, n.pitch % 12) for n in at_change.notes] == [(0, 9), (BAR, 5)]


def test_the_first_note_after_a_rest_keeps_its_chord_and_is_not_pushed():
    line = bass_line(kicks(BAR + 1720), [], rested("| - A | A D |"), PPQ, seed=1, approach=0, push=True)
    assert [(n.tick, n.pitch % 12) for n in line.notes] == [(BAR + 1720, 9), (BAR + 1920, 2)] and line.pushes == 0


def test_only_the_returning_chord_takes_the_first_strokes_bass_note():
    lines = [bass_line(kicks(2880), [], rested("| - A D |", 1), PPQ, seed=seed, approach=0).notes for seed in range(24)]
    assert all([(n.tick, n.pitch % 12) for n in line[:-1]] == [(2560, 2)] and line[-1].tick == 2880 for line in lines)
    heard = {line[-1].pitch % 12 for line in lines}
    assert len(heard) > 1 and heard <= {2, 6, 9}


def test_roots_only_writes_no_approach_notes():
    with pytest.raises(ValueError, match="approach notes are not written"):
        bass_line(kicks(0), [], spans("| A5 | C |"), PPQ, seed=1, approach=0.5, root_only=True)
    for seed in range(40):
        line = bass_line(kicks(0), [], spans("| A5 | C |"), PPQ, seed=seed, root_only=True)
        assert line.approaches == 0 and [n.pitch % 12 for n in line.notes] == [9, 0]


def test_a_snare_adds_no_note_only_next_to_a_stroke_that_has_one():
    drag = bass_line([], [], spans("Am", 1), PPQ, seed=1, snare_hits=[(960, 90), (1060, 90), (1160, 90)], root_only=True)
    assert [n.tick for n in drag.notes] == [0, 960, 1160] and drag.on_snares == 2
    by_a_kick = bass_line(kicks(960), [], spans("Am", 1), PPQ, seed=1, snare_hits=[(1060, 90), (1160, 90)], root_only=True)
    assert [n.tick for n in by_a_kick.notes] == [0, 960, 1160] and (by_a_kick.on_kicks, by_a_kick.on_snares) == (1, 1)
    resting = bass_line(kicks(1925), [], rested("| Am - |", 1), PPQ, seed=1, snare_hits=[(1850, 90)])
    assert [n.tick for n in resting.notes] == [0, 1850] and (resting.on_kicks, resting.on_snares) == (0, 1)
