import math

import pytest

from groovebin.events import Event, Note
from groovebin.song import Part
from groovebin.timing import MeterMap
from groovebin.transforms import delete, grid_ticks, merge, quantize, scale_velocity, shift, transpose


def note(at, pitch=60, velocity=80, length=240, channel=1):
    return Note(at, length, channel, pitch, velocity)


def control(at, number=1, value=64):
    return Event(at, bytes([0xB0, number, value]))


def part(*items, ppq=960, end=None):
    return Part(ppq, [i for i in items if isinstance(i, Note)], [i for i in items if isinstance(i, Event)], end=end)


def test_transpose_moves_notes_and_aftertouch_keys_and_nothing_else():
    out = transpose(part(control(0, 7, 100), note(0, 60), Event(0, b"\xa0\x3c\x10")), 5)
    assert out.notes == (note(0, 65),)
    assert out.events == (control(0, 7, 100), Event(0, b"\xa0\x41\x10"))


def test_transpose_reaches_the_edges_and_nothing_goes_past_them():
    assert transpose(part(note(0, 120)), 7).notes[0].pitch == 127
    assert transpose(part(note(0, 5)), -5).notes[0].pitch == 0
    with pytest.raises(ValueError, match=r"note 121 moved \+7 is 128, outside 0-127"):
        transpose(part(note(0, 121)), 7)
    with pytest.raises(ValueError, match=r"aftertouch key 125 moved \+7 is 132, outside 0-127"):
        transpose(part(Event(0, b"\xa0\x7d\x10")), 7)


def test_scale_and_offset_clamp_velocity_to_1_127():
    p = part(note(0, velocity=100), note(1, velocity=10), control(2, value=100))
    assert [n.velocity for n in scale_velocity(p, 2.0).notes] == [127, 20]
    assert [n.velocity for n in scale_velocity(p, offset=-50).notes] == [50, 1]
    assert [n.velocity for n in scale_velocity(p, 0.0).notes] == [1, 1]
    assert scale_velocity(p, 2.0).events == p.events
    assert scale_velocity(part(note(0, velocity=5)), 0.5).notes[0].velocity == 2


@pytest.mark.parametrize("factor", [-1.0, math.nan, math.inf])
def test_a_velocity_scale_that_is_negative_or_not_finite_is_refused(factor):
    with pytest.raises(ValueError, match="is not a finite number of 0 or more"):
        scale_velocity(part(note(0)), factor)


def test_shift_moves_every_event_and_the_end():
    out = shift(part(control(480), note(480), end=960), -480)
    assert (out.notes[0].tick, out.events[0].tick, out.end) == (0, 0, 480)


def test_shift_refuses_moving_an_event_before_the_start_and_names_the_farthest():
    with pytest.raises(ValueError, match=r"an event would land 1 tick\(s\) before the part's start"):
        shift(part(note(480), control(960)), -481)


def test_an_event_already_before_the_start_may_move():
    assert [n.tick for n in shift(part(note(-100), note(480)), -10).notes] == [-110, 470]


def test_delete_by_pitch_or_every_note_leaves_other_events():
    p = part(note(0, 36), control(0), note(240, 38), note(480, 36), Event(0, b"\xa0\x24\x10"))
    kept, gone = delete(p, 36)
    assert (gone, [n.pitch for n in kept.notes], kept.events) == (2, [38], p.events)
    kept, gone = delete(p)
    assert (gone, kept.notes, kept.events) == (3, (), p.events)


def test_grid_ticks_are_note_values_at_the_parts_ppq():
    assert (grid_ticks(1, 960), grid_ticks(16, 960), grid_ticks(64, 960), grid_ticks(8, 96)) == (3840, 240, 60, 48)
    for bad in (3, 128, 0):
        with pytest.raises(ValueError, match=f"1/{bad} is not a grid of 1/1 to 1/64"):
            grid_ticks(bad, 960)
    with pytest.raises(ValueError, match="1/64 at PPQ 120 is not a whole number of ticks"):
        grid_ticks(64, 120)


FOUR_FOUR = MeterMap(960, ())


def test_quantize_snaps_starts_keeps_lengths_and_order():
    p = part(note(100, 61, length=100), note(110, 60, length=90), control(130), note(130, 62, length=700),
             note(350, 64, length=5))
    out = quantize(p, grid_ticks(16, 960), FOUR_FOUR)
    assert [(n.tick, n.pitch, n.length) for n in out.notes] == [(0, 60, 90), (0, 61, 100), (240, 62, 700), (240, 64, 5)]
    assert out.events == (control(130),)


def test_a_tie_goes_to_the_later_line():
    assert quantize(part(note(120)), 240, FOUR_FOUR).notes[0].tick == 240


def test_the_grid_counts_from_each_bar_line_after_a_meter_change():
    meters = MeterMap(960, ((0, 3, 4), (2880, 4, 4)))
    assert quantize(part(note(3000)), grid_ticks(1, 960), meters).notes[0].tick == 2880
    assert quantize(part(note(1500)), grid_ticks(2, 960), meters, start=2880).notes[0].tick == 1920


def test_the_last_grid_line_of_a_short_bar_is_the_next_bar_line():
    meters = MeterMap(960, ((0, 3, 4),))
    assert quantize(part(note(2600)), grid_ticks(2, 960), meters).notes[0].tick == 2880
    assert quantize(part(note(2300)), grid_ticks(2, 960), meters).notes[0].tick == 1920


def test_quantize_refusals():
    with pytest.raises(ValueError, match=r"an event would land 100 tick\(s\) before the part's start"):
        quantize(part(note(10)), grid_ticks(4, 960), FOUR_FOUR, start=100)
    with pytest.raises(ValueError, match="a quantize grid is at least one tick"):
        quantize(part(note(10)), 0, FOUR_FOUR)
    with pytest.raises(ValueError, match="the meter map is at PPQ 960 but the part is at PPQ 480"):
        quantize(part(note(10), ppq=480), 120, FOUR_FOUR)


def test_merge_puts_the_destination_first_at_one_tick_kind_and_pitch():
    bend = Event(1920, b"\xe0\x00\x40")
    dst = part(note(960, 50), Note(960, 240, 2, 70, 11), bend, end=3840)
    src = part(Event(0, b"\xc0\x00"), note(0, 70), Event(0, b"\xe0\x00\x40"), control(0))
    out = merge(dst, src, 960)
    assert [(n.tick, n.pitch, n.velocity) for n in out.notes] == [(960, 50, 80), (960, 70, 11), (960, 70, 80)]
    assert [(e.tick, e.kind) for e in out.events] == [(960, "program"), (960, "control"), (960, "bend"), (1920, "bend")]
    assert out.end == 3840


def test_merge_refusals():
    with pytest.raises(ValueError, match="before the part's start"):
        merge(part(note(0)), part(note(0)), -1)
    with pytest.raises(ValueError, match="a part at PPQ 480 cannot merge into one at PPQ 960"):
        merge(part(note(0)), part(note(0), ppq=480), 0)


from groovebin.transforms import note_lengths, stretch, swing, velocity_curve  # noqa: E402


def test_stretch_scales_ticks_lengths_events_and_the_end():
    p = part(note(0, length=241), note(961, length=3), control(1000), end=2000)
    out = stretch(p, 0.5)
    assert [(n.tick, n.length) for n in out.notes] == [(0, 121), (481, 1)]
    assert (out.events[0].tick, out.end) == (500, 1000)
    assert stretch(p, 2.0).notes[1].tick == 1922
    assert [n.length for n in stretch(part(note(1, length=1), note(3, length=1)), 0.5).notes] == [1, 1]
    for bad in (0.0, -1.0, math.inf):
        with pytest.raises(ValueError, match="not a finite number above 0"):
            stretch(p, bad)


def test_note_lengths_takes_one_rule_and_holds_a_tick():
    p = part(note(0, length=200), note(100, 62, length=200), note(100, 64, length=10), note(1000, length=50))
    assert [n.length for n in note_lengths(p, percent=50).notes] == [100, 100, 5, 25]
    assert [n.length for n in note_lengths(p, fixed=7).notes] == [7] * 4
    assert [n.length for n in note_lengths(p, legato=1.0).notes] == [100, 900, 900, 50]
    assert [n.length for n in note_lengths(p, frozenset({0}), legato=0.5).notes] == [50, 200, 10, 50]
    assert [n.length for n in note_lengths(p, percent=0).notes] == [1] * 4
    for kw, message in ((dict(), "exactly one"), (dict(percent=50, fixed=3), "exactly one"), (dict(fixed=0), "1 or more"),
                        (dict(legato=0), "above 0"), (dict(percent=-1), "0 or more")):
        with pytest.raises(ValueError, match=message):
            note_lengths(p, **kw)


def test_velocity_curve_maps_the_band_through_gamma():
    p = part(*(note(k, velocity=v) for k, v in enumerate((1, 64, 127))))
    assert [n.velocity for n in velocity_curve(p, floor=40, ceiling=100).notes] == [40, 70, 100]
    assert [n.velocity for n in velocity_curve(p, gamma=2.0).notes] == [1, 33, 127]
    assert [n.velocity for n in velocity_curve(p, frozenset({1}), floor=100, ceiling=100).notes] == [1, 100, 127]
    for kw in (dict(floor=0), dict(floor=100, ceiling=90), dict(ceiling=128), dict(gamma=0)):
        with pytest.raises(ValueError):
            velocity_curve(p, **kw)


def test_swing_is_a_quantize_with_the_odd_lines_late():
    out = swing(part(note(250, 60), note(470, 62), note(250, 64, length=5)), 240, 0.6, FOUR_FOUR)
    assert [(n.tick, n.pitch) for n in out.notes] == [(288, 60), (288, 64), (480, 62)]
    assert swing(part(note(3840 + 250)), 240, 0.75, MeterMap(960, ((0, 3, 4),))).notes[0].tick == 2880 + 960 + 240 + 120
