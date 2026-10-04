"""Scale quantize, diatonic transpose and a change of key, on pitches and on parts."""

import pytest

from groovebin.events import Event, Note
from groovebin.harmony import Scale
from groovebin.song import Part
from groovebin.transforms import change_key, diatonic, key_at, moved_key, quantized, scale_quantize, stepped

C, A_MINOR = Scale(0), Scale(9, "minor")


def part(*pitches, events=()):
    return Part(960, tuple(Note(k * 240, 200, 1, p, 90, tag=k) for k, p in enumerate(pitches)), events)


def poly(tick, key):
    return Event(tick, bytes([0xA0, key, 40]))


def signature(tick, sharps, minor):
    return Event(tick, bytes([0xFF, 0x59, 2, sharps & 0xFF, minor]))


def test_quantize_takes_an_outside_note_to_the_nearer_scale_note_down_on_a_tie():
    assert [quantized(p, C) for p in (60, 61, 63, 66, 70)] == [60, 60, 62, 65, 69]
    assert [quantized(p, Scale(0, "major-pentatonic")) for p in (65, 66, 70, 71)] == [64, 67, 69, 72]


def test_diatonic_steps_along_the_scale_and_an_outside_note_keeps_its_offset():
    assert [stepped(p, C, 2) for p in (60, 62, 64, 71)] == [64, 65, 67, 74]
    assert (stepped(61, C, 1), stepped(60, C, -1), stepped(60, C, 7)) == (63, 59, 72)


def test_a_change_of_key_keeps_each_degree_and_moves_the_shorter_way():
    assert [moved_key(p, C, A_MINOR) for p in (60, 64, 67)] == [57, 60, 64]
    assert [moved_key(p, C, Scale(0, "minor")) for p in (64, 69, 71)] == [63, 68, 70]
    assert (moved_key(60, C, Scale(6)), moved_key(60, C, Scale(5)), moved_key(61, C, Scale(2))) == (54, 65, 63)
    with pytest.raises(ValueError, match="C major has 7 notes and C blues 6"):
        moved_key(60, C, Scale(0, "blues"))


def test_key_points_give_each_tick_its_key_the_first_applying_before_it():
    points = [(960, C), (3840, A_MINOR)]
    assert (key_at(points, 0), key_at(points, 3839), key_at(points, 3840), key_at(C, 5)) == (C, C, A_MINOR, C)


def test_with_no_selection_aftertouch_moves_with_its_notes_and_with_one_it_stays():
    control = Event(0, b"\xb0\x01\x40")
    p = part(61, 62, 63, events=(poly(0, 61), control))
    whole = scale_quantize(p, None, C)
    assert [n.pitch for n in whole.notes] == [60, 62, 62] and [n.tag for n in whole.notes] == [0, 1, 2]
    assert poly(0, 60) in whole.events and control in whole.events
    some = scale_quantize(p, frozenset({2}), C)
    assert [n.pitch for n in some.notes] == [61, 62, 62] and poly(0, 61) in some.events


def test_a_held_pitch_never_moves_and_a_result_past_127_is_refused():
    assert [n.pitch for n in scale_quantize(part(15, 61), None, C, hold=lambda pitch: pitch < 23).notes] == [15, 60]
    with pytest.raises(ValueError, match="note 127 would move to 129, outside 0-127"):
        diatonic(part(127), None, 1, C)


def test_change_key_moves_the_notes_and_the_parts_key_signatures():
    out = change_key(part(60, 64, events=(signature(0, 0, 0), signature(3840, 1, 0))), C, Scale(2, "major", "D"))
    assert [n.pitch for n in out.notes] == [62, 66]
    assert [e.data for e in out.events if e.meta_type == 0x59] == [bytes([0xFF, 0x59, 2, 2, 0]),
                                                                    bytes([0xFF, 0x59, 2, 3, 0])]


def test_a_change_of_mode_takes_the_target_mode_and_a_mode_target_leaves_signatures_alone():
    to_minor = change_key(part(64, events=(signature(0, 0, 0),)), C, Scale(0, "minor"))
    assert signature(0, -3, 1) in to_minor.events and to_minor.notes[0].pitch == 63
    dorian = change_key(part(64, events=(signature(0, 0, 0),)), C, Scale(2, "dorian"))
    assert signature(0, 0, 0) in dorian.events and dorian.notes[0].pitch == 65


def test_change_key_reads_its_source_at_the_parts_first_note():
    p = Part(960, (Note(3840, 200, 1, 57, 90),))
    assert change_key(p, [(0, C), (3840, A_MINOR)], Scale(0, "minor")).notes[0].pitch == 60


def test_key_points_out_of_order_are_refused():
    with pytest.raises(ValueError, match="key points are not in tick order"):
        key_at([(3840, C), (0, A_MINOR)], 0)


def test_the_signature_in_force_becomes_the_targets_whatever_key_the_notes_were_read_in():
    out = change_key(part(57, events=(signature(0, 0, 0),)), A_MINOR, Scale(9, "major"))
    assert [e.data for e in out.events if e.meta_type == 0x59] == [bytes([0xFF, 0x59, 2, 3, 0])]


def test_on_a_change_of_mode_signatures_in_other_keys_are_left_as_they_were():
    out = change_key(part(57, events=(signature(0, 0, 1), signature(3840, 1, 1))), A_MINOR, Scale(9, "major"))
    assert [e.data for e in out.events if e.meta_type == 0x59] == [bytes([0xFF, 0x59, 2, 3, 0]),
                                                                    bytes([0xFF, 0x59, 2, 1, 1])]


def test_change_key_reads_the_signature_in_force_at_the_tick_given():
    conductor = Part(960, (), (signature(0, 0, 0), signature(3840, 1, 0)))
    out = change_key(conductor, Scale(7), Scale(9), at=3840)
    assert [e.data for e in out.events if e.meta_type == 0x59] == [bytes([0xFF, 0x59, 2, 2, 0]),
                                                                    bytes([0xFF, 0x59, 2, 3, 0])]


def test_quantize_never_picks_a_note_outside_0_to_127():
    assert quantized(0, Scale(2)) == 1
    assert quantized(127, Scale(9, "harmonic-minor")) == 125
