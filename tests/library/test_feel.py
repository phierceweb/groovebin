import pytest

from groovebin.events import Note
from groovebin.library.feel import apply_feel, grid_of, template
from groovebin.timing import MeterMap

PPQ = 960
KICK, SNARE, HAT = 36, 38, 42
FOUR = MeterMap(PPQ, ((0, 4, 4),))


def note(tick, pitch, velocity=80, ppq=PPQ):
    return Note(tick, ppq // 8, 10, pitch, velocity)


def swung_reference(bars=2):
    """Hats on the beat at 110 and on a triplet off-beat at 60; the snare 20 ticks late on 2 and 4."""
    notes = []
    for bar in range(bars):
        start = bar * 4 * PPQ
        notes += [note(start, KICK, 100), note(start + 1920, KICK, 100),
                  note(start + 980, SNARE, 100), note(start + 2900, SNARE, 100)]
        notes += [note(start + beat * PPQ + o, HAT, v) for beat in range(4) for o, v in ((0, 110), (640, 60))]
    return notes


def straight_target():
    return ([note(0, KICK), note(1920, KICK), note(960, SNARE), note(2880, SNARE)]
            + [note(t, HAT, 80) for t in range(0, 4 * PPQ, 480)])


def by_pitch(notes, pitch):
    return sorted((n.tick, n.velocity) for n in notes if n.pitch == pitch)


def test_the_grid_follows_the_references_subdivision():
    assert grid_of(swung_reference(), FOUR, "gm") == 8
    sixteenths = [note(t, HAT) for t in range(0, 4 * PPQ, 240)]
    assert grid_of(sixteenths, FOUR, "gm") == 16
    assert grid_of(sixteenths, FOUR, None) == 16


def test_a_swung_template_swings_straight_eighths():
    tpl = template(swung_reference(), FOUR, 2, "gm", grid=8)
    felt = apply_feel(straight_target(), FOUR, tpl, "gm")
    assert [t for t, _v in by_pitch(felt.notes, HAT)] == [0, 640, 960, 1600, 1920, 2560, 2880, 3520]
    assert by_pitch(felt.notes, SNARE) == [(980, 80), (2900, 80)]
    assert [t for t, _v in by_pitch(felt.notes, KICK)] == [0, 1920]
    assert felt.moved == 6 and felt.unmatched == 0


def test_accents_follow_the_reference_around_the_targets_own_level():
    tpl = template(swung_reference(), FOUR, 2, "gm", grid=8)
    felt = apply_feel(straight_target(), FOUR, tpl, "gm")
    hats = [v for _t, v in by_pitch(felt.notes, HAT)]
    # the reference's hats average 85: on the beat 110/85 of the target's 80, off it 60/85
    assert hats == [104, 56] * 4


def test_timing_and_velocity_take_a_share():
    tpl = template(swung_reference(), FOUR, 2, "gm", grid=8)
    felt = apply_feel(straight_target(), FOUR, tpl, "gm", timing=0.5, velocity=0)
    assert by_pitch(felt.notes, HAT)[:2] == [(0, 80), (560, 80)]


def test_a_note_off_the_templates_grid_is_left_alone():
    tpl = template(swung_reference(), FOUR, 2, "gm", grid=8)
    sixteenth = note(240, HAT, 80)
    felt = apply_feel([sixteenth], FOUR, tpl, "gm")
    assert felt.notes == (sixteenth,) and felt.unmatched == 1


def test_a_position_the_reference_never_plays_takes_any_voices_feel_there():
    tpl = template(swung_reference(), FOUR, 2, "gm", grid=8)
    snare_on_the_and = note(480, SNARE, 80)
    (moved,) = apply_feel([snare_on_the_and], FOUR, tpl, "gm").notes
    assert moved.tick == 640


def test_without_a_map_one_template_covers_every_note():
    tpl = template(swung_reference(), FOUR, 2, None, grid=8)
    felt = apply_feel(straight_target(), FOUR, tpl, None)
    assert [t for t, _v in by_pitch(felt.notes, HAT)][:2] == [0, 640]


def test_the_template_scales_between_resolutions():
    half = [Note(n.tick // 2, n.length // 2, n.channel, n.pitch, n.velocity) for n in swung_reference()]
    tpl = template(half, MeterMap(480, ((0, 4, 4),)), 2, "gm", grid=8)
    felt = apply_feel(straight_target(), FOUR, tpl, "gm")
    assert by_pitch(felt.notes, SNARE)[0][0] == 980


def test_a_note_that_would_move_before_the_start_is_held_there():
    tpl = template([note(0, KICK), note(PPQ * 4 - 30, KICK)], FOUR, 2, "gm", grid=8)
    assert tpl.places[("kick", 8, 0)][0] == pytest.approx(-15)
    felt = apply_feel([note(0, KICK)], FOUR, tpl, "gm")
    assert felt.notes[0].tick == 0 and felt.held == 1


def test_bars_of_a_length_the_template_lacks_are_left_alone():
    tpl = template(swung_reference(), FOUR, 2, "gm", grid=8)
    waltz = MeterMap(PPQ, ((0, 3, 4),))
    target = [note(480, HAT)]
    felt = apply_feel(target, waltz, tpl, "gm")
    assert felt.notes == tuple(target) and felt.unmatched == 1


def test_a_grid_is_8_or_16():
    with pytest.raises(ValueError, match="grid of 8 or 16"):
        template(swung_reference(), FOUR, 2, "gm", grid=4)
    with pytest.raises(ValueError, match="0 to 1"):
        apply_feel([], FOUR, template(swung_reference(), FOUR, 2, "gm", grid=8), "gm", timing=1.5)


def test_the_offset_is_the_one_most_notes_there_take():
    shuffle = [note(beat * PPQ + o, HAT) for beat in range(8) for o in (0, 640)]
    triplets = [note(beat * PPQ + o, HAT) for beat in range(8, 11) for o in (0, 320, 640)]
    tpl = template(shuffle + triplets, FOUR, 3, "gm", grid=8)
    assert tpl.places[("hands", 8, 1)][0] == 160


def test_a_ghost_near_a_line_its_voice_strikes_that_bar_does_not_pull_the_line():
    """Sixteenth ghosts under eighth hats, played a few ticks late, sit just inside half a step of beats 2 and 4."""
    ref = []
    for start in (0, 4 * PPQ):
        ref += [note(start + t, HAT, 90) for t in range(0, 4 * PPQ, 480)]
        ref += [note(start, KICK, 100), note(start + 1920, KICK, 100)]
        ref += [note(start + 970, SNARE, 110), note(start + 2890, SNARE, 110)]
        ref += [note(start + 725, SNARE, 35), note(start + 2645, SNARE, 35)]
    tpl = template(ref, FOUR, 2, "gm", grid=8)
    assert tpl.places[("snare", 8, 2)] == (10, 1.0)
    felt = apply_feel(straight_target(), FOUR, tpl, "gm")
    assert [t for t, _v in by_pitch(felt.notes, SNARE)] == [970, 2890]


def test_of_two_strokes_as_near_a_line_the_later_one_counts():
    triplet = [note(beat * PPQ + o, HAT) for beat in range(4) for o in (0, 320, 640)]
    assert template(triplet, FOUR, 1, "gm", grid=8).places[("hands", 8, 1)][0] == 160


def test_a_note_on_every_voices_feel_keeps_its_own_voices_level():
    tpl = template(swung_reference(), FOUR, 2, "gm", grid=8)
    target = [note(0, KICK, 110), note(480, KICK, 110), note(1920, KICK, 110)]
    target += [note(t, HAT, 50) for t in range(0, 4 * PPQ, 480)]
    felt = apply_feel(target, FOUR, tpl, "gm")
    # the reference plays only a 60 hat on the "and" of 1, two thirds of its 90 average: two thirds of the kicks' 110
    assert by_pitch(felt.notes, KICK) == [(0, 110), (640, 73), (1920, 110)]
