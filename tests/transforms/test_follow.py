"""`transforms.follow`: notes played over one chart moved onto another, each by its place in its chord."""

import time

import pytest

from groovebin.events import Event, Note
from groovebin.harmony import chart, chart_spans
from groovebin.song import Part
from groovebin.timing import MeterMap
from groovebin.transforms import chord_at, follow, laid

PPQ, BAR = 480, 1920
METERS = MeterMap(PPQ, ())


def spans(text, bars=2):
    return chart_spans(chart(text), METERS, bars)


def note(at, pitch, length=240, channel=1):
    return Note(at, length, channel, pitch, 90)


def part(*notes, events=()):
    return Part(PPQ, notes, events)


def pitches(followed):
    return [n.pitch for n in followed.part.notes]


def counts(followed):
    return followed.anticipated, followed.ringing, followed.doubled, followed.folded


def test_chord_at_is_the_span_holding_the_tick():
    two = spans("| C | G |")
    assert [str(chord_at(two, t)) for t in (0, BAR - 1, BAR, 2 * BAR - 1)] == ["C", "C", "G", "G"]
    assert chord_at(two, 2 * BAR) is None and chord_at(two, -1) is None


def test_onto_its_own_chart_nothing_moves():
    p = part(note(0, 48), note(480, 52), note(BAR, 55), note(BAR + 480, 59), events=(Event(10, b"\xb0\x07\x64"),))
    out = follow(p, None, spans("| C | G |"), spans("| C | G |"))
    assert out.part == p and counts(out) == (0, 0, 0, 0)


def test_each_note_keeps_its_place_in_the_chord_and_every_other_field():
    p = part(note(0, 60), note(480, 64), note(960, 67), note(1440, 62), events=(Event(10, b"\xb0\x07\x64"),))
    out = follow(p, None, spans("C", 1), spans("Am", 1))
    assert pitches(out) == [57, 60, 64, 59]                    # root to root, third, fifth, a ninth stays a ninth
    assert [(n.tick, n.length, n.channel, n.velocity) for n in out.part.notes] == \
        [(n.tick, n.length, n.channel, n.velocity) for n in p.notes]
    assert out.part.events == p.events


def test_a_note_outside_the_chord_keeps_its_distance_above_the_root():
    """A blue third over a major chord stays one; onto its own chart it does not move at all."""
    p = part(note(0, 63), note(480, 66))
    assert pitches(follow(p, None, spans("C", 1), spans("A", 1))) == [60, 63]
    assert pitches(follow(p, None, spans("C", 1), spans("C", 1))) == [63, 66]


def test_a_slash_chords_bass_note_goes_to_the_new_bass_note():
    out = follow(part(note(0, 52), note(480, 55)), None, spans("C/E", 1), spans("Am", 1))
    assert pitches(out) == [57, 52]


def test_a_note_a_32nd_or_less_before_a_change_takes_the_new_chord():
    window = PPQ // 8
    p = part(note(BAR - window, 60, length=30), note(BAR - window - 1, 60, length=1, channel=2))
    out = follow(p, None, spans("| C | G |"), spans("| C | F |"))
    assert sorted((n.channel, n.pitch) for n in out.part.notes) == [(1, 58), (2, 60)]
    assert counts(out) == (1, 0, 0, 0)


def test_a_change_on_the_target_chart_alone_is_one_a_note_can_lead_into():
    out = follow(part(note(940, 60, length=10)), None, spans("C", 1), spans("| C F |", 1))
    assert pitches(out) == [65] and out.anticipated == 1


def test_a_note_held_into_a_chord_it_is_not_in_is_counted_once():
    p = part(note(BAR - 480, 60, length=2 * BAR), note(BAR - 480, 64, length=2 * BAR, channel=2))
    out = follow(p, None, spans("| C | C | C |", 3), spans("| C | F | Am |", 3))
    assert pitches(out) == [60, 64] and out.ringing == 1          # C is in F and Am; E is not in F


def test_two_notes_of_one_start_landing_on_one_pitch_are_counted_and_both_kept():
    out = follow(part(note(0, 63), note(0, 64), note(0, 64, channel=2)), None, spans("C", 1), spans("Am", 1))
    assert pitches(out) == [60, 60, 60] and out.doubled == 1


def test_only_the_selected_notes_move():
    out = follow(part(note(0, 60), note(480, 64)), frozenset({1}), spans("C", 1), spans("Am", 1))
    assert pitches(out) == [60, 60]


def test_a_held_pitch_never_moves():
    out = follow(part(note(0, 16), note(480, 60)), None, spans("C", 1), spans("Am", 1), hold=lambda pitch: pitch < 21)
    assert pitches(out) == [16, 57]


def test_aftertouch_follows_its_own_note_and_stays_under_a_selection():
    held = note(BAR - 480, 64, length=960)
    during, alone = Event(BAR + 240, bytes([0xA0, 64, 50])), Event(BAR + 1000, bytes([0xA0, 67, 40]))
    p = part(held, events=(during, alone))
    whole = follow(p, None, spans("| C | C |"), spans("| Am | F |"))
    assert pitches(whole) == [60] and [e.pitch for e in whole.part.events] == [60, 72]
    some = follow(p, frozenset({0}), spans("| C | C |"), spans("| Am | F |"))
    assert pitches(some) == [60] and some.part.events == p.events


def test_a_note_no_chart_covers_stays():
    out = follow(part(note(BAR, 60)), None, spans("C", 1), spans("Am", 1))
    assert pitches(out) == [60] and counts(out) == (0, 0, 0, 0)


def test_a_move_past_127_is_refused():
    with pytest.raises(ValueError, match="note 127 would move to 130, outside 0-127"):
        follow(part(note(0, 127)), None, spans("Am", 1), spans("C", 1))


def test_a_note_the_move_takes_out_of_the_register_goes_an_octave_the_other_way():
    low = follow(part(note(0, 23)), None, spans("Bb", 1), spans("Gm", 1), register=(21, 64))
    assert pitches(low) == [32] and low.folded == 1
    high = follow(part(note(0, 64)), None, spans("C", 1), spans("F", 1), register=(21, 64))
    assert pitches(high) == [57] and high.folded == 1
    assert pitches(follow(part(note(0, 23)), None, spans("Bb", 1), spans("Gm", 1))) == [20]


def test_a_note_already_outside_the_register_is_not_folded():
    p = part(note(0, 67))
    assert pitches(follow(p, None, spans("C", 1), spans("C", 1), register=(21, 64))) == [67]
    out = follow(p, None, spans("C", 1), spans("F", 1), register=(21, 64))
    assert pitches(out) == [72] and out.folded == 0


def test_a_register_narrower_than_an_octave_is_refused():
    with pytest.raises(ValueError, match="a register of 40-50 is narrower than an octave"):
        follow(part(note(0, 40)), None, spans("C", 1), spans("F", 1), register=(40, 50))


def test_a_note_read_at_a_change_is_anticipated_only_when_the_chords_there_differ():
    p = part(note(BAR - 20, 60, length=10), note(BAR + 480, 60))
    assert follow(p, None, spans("| C | C |"), spans("| C | C |")).anticipated == 0
    assert follow(p, None, spans("| C | G |"), spans("| C | G |")).anticipated == 1


def test_doubled_counts_only_notes_of_one_start_and_channel_that_met_from_different_pitches():
    same = part(note(0, 60), note(0, 60))
    assert follow(same, frozenset({0}), spans("C", 1), spans("Am", 1)).doubled == 0
    assert follow(part(note(0, 63), note(0, 64, channel=2)), None, spans("C", 1), spans("Am", 1)).doubled == 0


@pytest.mark.parametrize(("held", "target"), [
    (note(BAR - 480, 64, length=480), "| C | F |"),            # ends on the change
    (note(0, 62), "| C | C |"),                                # a passing tone at its own chord's start
    (note(BAR - 480, 64, length=960), "| Am | F |"),           # E moves to C, which F holds
    (note(BAR - 480, 55, length=960), "| C | F/G |"),          # G is F/G's bass
])
def test_a_note_that_does_not_ring_into_a_chord_without_it_is_not_counted(held, target):
    assert follow(part(held), None, spans("| C | C |"), spans(target)).ringing == 0


def test_aftertouch_follows_only_a_note_of_its_channel_sounding_at_its_tick():
    charts = spans("| C | C |"), spans("| Am | F |")
    other_channel = part(note(BAR - 480, 64, length=960), events=(Event(BAR + 240, bytes([0xA1, 64, 50])),))
    assert [e.pitch for e in follow(other_channel, None, *charts).part.events] == [69]
    nested = part(note(0, 64, length=3000), note(BAR, 64), events=(Event(BAR + 100, bytes([0xA0, 64, 50])),))
    assert [e.pitch for e in follow(nested, None, *charts).part.events] == [69]
    on_its_end = part(note(BAR - 480, 64, length=480), events=(Event(BAR, bytes([0xA0, 64, 50])),))
    assert [e.pitch for e in follow(on_its_end, None, *charts).part.events] == [69]
    switch = part(events=(Event(240, bytes([0xA0, 16, 50])),))
    assert [e.pitch for e in follow(switch, None, *charts, hold=lambda pitch: pitch < 21).part.events] == [16]


def test_an_upper_part_reads_a_slash_chord_as_its_chord():
    triad = part(note(0, 60), note(0, 64), note(0, 67))
    assert pitches(follow(triad, None, spans("C", 1), spans("G/B", 1))) == [59, 59, 62]
    assert pitches(follow(triad, None, spans("C", 1), spans("G/B", 1), bass=False)) == [55, 59, 62]


def test_a_change_on_the_source_chart_alone_is_one_a_note_can_lead_into():
    out = follow(part(note(940, 67, length=10)), None, spans("| C G |", 1), spans("Am", 1))
    assert pitches(out) == [69] and out.anticipated == 1


def test_ringing_is_read_from_where_the_note_was_read():
    assert follow(part(note(BAR - 20, 62, length=100)), None, spans("| C | C |"), spans("| C | F |")).ringing == 0


def test_a_register_of_exactly_an_octave_is_enough_and_laid_charts_end_with_the_part():
    assert pitches(follow(part(note(0, 40)), None, spans("C", 1), spans("F", 1), register=(40, 51))) == [45]
    assert (len(laid(chart("C"), METERS, BAR)), len(laid(chart("C"), METERS, BAR + 1))) == (1, 2)


def test_dense_aftertouch_takes_no_quadratic_time():
    notes = tuple(note(k * 10, 40 + k % 20, length=5) for k in range(2000))
    events = tuple(Event(k, bytes([0xA0, 40 + k % 20, 30])) for k in range(20000))
    started = time.perf_counter()
    follow(part(*notes, events=events), None, spans("C", 20), spans("Am", 20))
    assert time.perf_counter() - started < 1.0


def test_aftertouch_after_a_short_note_ends_follows_the_long_one_still_sounding():
    p = part(note(0, 64, length=3000), note(BAR, 64, length=100), events=(Event(BAR + 500, bytes([0xA0, 64, 50])),))
    out = follow(p, None, spans("| C | C |"), spans("| Am | F |"))
    assert pitches(out) == [60, 69] and [e.pitch for e in out.part.events] == [60]


def test_an_upper_part_reads_and_rings_against_the_plain_chord():
    lead = part(note(BAR - 20, 60, length=10), note(BAR + 480, 60))
    assert follow(lead, None, spans("| C | C |"), spans("| C | C/E |")).anticipated == 1
    assert follow(lead, None, spans("| C | C |"), spans("| C | C/E |"), bass=False).anticipated == 0
    held = part(note(BAR - 480, 62, length=960))
    assert follow(held, None, spans("| C | C |"), spans("| C | C/D |")).ringing == 0
    assert follow(held, None, spans("| C | C |"), spans("| C | C/D |"), bass=False).ringing == 1


def test_notes_meeting_on_one_pitch_at_different_starts_are_not_doubled():
    assert follow(part(note(0, 63), note(480, 64)), None, spans("C", 1), spans("Am", 1)).doubled == 0


def test_an_orphan_aftertouch_key_is_held_to_0_127_and_folded_into_the_register():
    stray = part(events=(Event(240, bytes([0xA0, 127, 50])),))
    with pytest.raises(ValueError, match="aftertouch key 127 would move to 130, outside 0-127"):
        follow(stray, None, spans("Am", 1), spans("C", 1))
    lone = part(events=(Event(240, bytes([0xA0, 64, 50])),))
    assert [e.pitch for e in follow(lone, None, spans("C", 1), spans("F", 1), register=(21, 64)).part.events] == [57]


def test_an_empty_chart_is_refused_by_name():
    with pytest.raises(ValueError, match="a chart with no bars to lay"):
        laid([], METERS, BAR)
