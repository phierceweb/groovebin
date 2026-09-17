import random
import time

import pytest

from groovebin.events import Event, Note
from groovebin.song import Part, Song, merged, meter_map, nested_overlaps, pair, rescale, tempo_map, unpair

EOT = b"\xff\x2f\x00"


def on(pitch, velocity=100, channel=1):
    return bytes([0x90 | channel - 1, pitch, velocity])


def off(pitch, velocity=64, channel=1):
    return bytes([0x80 | channel - 1, pitch, velocity])


def test_a_part_keeps_notes_and_events_in_canonical_order():
    late, early = Note(480, 10, 1, 36, 90), Note(0, 10, 1, 38, 90)
    bend, program = Event(0, b"\xe0\x00\x40"), Event(0, b"\xc0\x01")
    part = Part(960, [late, early], [bend, program])
    assert (part.notes, part.events) == ((early, late), (program, bend))


def test_a_part_is_named_by_its_first_track_name_event():
    assert Part(960, (), (Event(0, b"\xff\x03\x03Kit"),)).name == "Kit"
    assert Part(960).name is None


def test_a_song_refuses_a_track_at_another_ppq_and_formats_it_cannot_hold():
    with pytest.raises(ValueError, match="track 2 is at PPQ 480, not the song's 960"):
        Song(960, 1, (Part(960), Part(480)))
    with pytest.raises(ValueError, match="format 2 is not supported: only format 0 and format 1"):
        Song(960, 2, (Part(960),))
    with pytest.raises(ValueError, match="a format 0 song holds 2 tracks, not one"):
        Song(960, 0, (Part(960), Part(960)))


def test_pairing_closes_the_earliest_open_note_first():
    part = pair([(0, on(60, 64)), (10, on(60, 80)), (20, off(60, 1)), (30, on(60, 0)),
                 (35, on(62, 96)), (55, EOT)], ppq=96)
    assert part.notes == (Note(0, 20, 1, 60, 64, 1), Note(10, 20, 1, 60, 80, None),
                          Note(35, 20, 1, 62, 96, None))
    assert (part.end, part.orphan_offs) == (55, 0)


def test_pairing_is_per_channel():
    part = pair([(0, on(36, channel=10)), (0, on(36, channel=1)), (5, off(36, channel=1)),
                 (9, off(36, channel=10))], ppq=96)
    assert {(n.channel, n.length) for n in part.notes} == {(10, 9), (1, 5)}


def test_an_orphan_off_is_dropped_and_counted_and_an_open_note_closes_at_the_track_end():
    part = pair([(0, off(40)), (10, on(60)), (30, b"\xb0\x07\x64"), (50, EOT)], ppq=96)
    assert part.notes == (Note(10, 40, 1, 60, 100),)
    assert part.events == (Event(30, b"\xb0\x07\x64"),)
    assert (part.orphan_offs, part.end) == (1, 50)


def test_unpair_writes_offs_first_and_equal_starts_by_length_so_pairing_reads_them_back():
    notes = (Note(0, 0, 1, 60, 90), Note(0, 240, 1, 60, 80, 10), Note(0, 120, 1, 60, 70), Note(120, 120, 1, 60, 60))
    events = (Event(120, b"\xc0\x05"),)
    part = Part(960, notes, events, end=960)
    messages = unpair(part)
    assert messages[:4] == [(0, on(60, 90)), (0, on(60, 0)), (0, on(60, 70)), (0, on(60, 80))]
    assert messages[4:6] == [(120, on(60, 0)), (120, b"\xc0\x05")]
    assert pair(messages + [(960, EOT)], ppq=960) == part


def test_notes_ending_at_one_tick_keep_their_own_off_velocities():
    part = Part(960, (Note(0, 480, 1, 60, 90, 11), Note(240, 240, 1, 60, 90, 22)), end=480)
    assert pair(unpair(part) + [(480, EOT)], ppq=960) == part


def test_merged_puts_every_track_in_one_part():
    a = Part(96, (Note(10, 5, 10, 36, 90),), (Event(0, b"\xff\x03\x01A"),))
    b = Part(96, (Note(0, 5, 1, 60, 90),))
    part = merged(Song(96, 1, (a, b)))
    assert part.notes == (Note(0, 5, 1, 60, 90), Note(10, 5, 10, 36, 90))
    assert part.events == a.events


def test_tempo_and_meter_maps_come_from_every_track_and_skip_what_they_cannot_use():
    conductor = Part(960, (), (Event(0, b"\xff\x51\x03\x07\xa1\x20"), Event(0, b"\xff\x58\x04\x03\x02\x18\x08"),
                               Event(3840, b"\xff\x51\x03\x00\x00\x00"), Event(3840, b"\xff\x58\x04\x00\x02\x18\x08")))
    other = Part(960, (), (Event(2880, b"\xff\x51\x03\x06\x1a\x80"),))
    song = Song(960, 1, (conductor, other))
    assert tempo_map(song).points == ((0, 500_000), (2880, 400_000))
    assert meter_map(song).changes == ((0, 3, 4),)
    assert meter_map(Song(960, 1, (Part(960),))).defaulted


def test_rescale_rounds_each_note_start_and_end_half_up():
    part = Part(7, (Note(3, 3, 1, 60, 90),), (Event(1, b"\xc0\x01"),), end=14)
    scaled = rescale(part, 960)
    assert scaled.notes == (Note(411, 412, 1, 60, 90),)
    assert (scaled.events[0].tick, scaled.end, scaled.ppq) == (137, 1920, 960)


def test_nested_overlaps_names_the_pairs_pairing_cannot_read_back():
    outer, inner, after = Note(0, 960, 10, 36, 90), Note(240, 240, 10, 36, 90), Note(480, 960, 10, 36, 90)
    other_channel = Note(240, 240, 1, 36, 90)
    assert nested_overlaps(Part(960, (outer, inner, after, other_channel))) == [(outer, inner)]


def test_nested_overlaps_gives_every_nested_pair_outer_first_in_part_order():
    for seed in range(200):
        rng = random.Random(seed)
        notes = [Note(rng.randrange(0, 48, 4), rng.choice([0, 4, 8, 12, 24, 40]), rng.choice([1, 10]), rng.choice([36, 38]), 90)
                 for _ in range(rng.randint(0, 30))]
        part = Part(96, notes)
        by_key = {}
        for n in part.notes:
            by_key.setdefault((n.channel, n.pitch), []).append(n)
        expected = [(outer, inner) for ns in by_key.values() for i, outer in enumerate(ns)
                    for inner in ns[i + 1:] if inner.tick > outer.tick and inner.end < outer.end]
        assert nested_overlaps(part) == expected, seed


def test_nested_overlaps_on_many_notes_of_one_pitch_takes_no_quadratic_time():
    part = Part(96, [Note(0, 1, 10, 36, 90)] * 20_000 + [Note(t, 1, 10, 36, 90) for t in range(1, 20_001)])
    start = time.perf_counter()
    assert nested_overlaps(part) == []
    assert time.perf_counter() - start < 3


def test_a_time_signature_with_a_denominator_past_64_is_skipped():
    part = Part(96, (), (Event(0, b"\xff\x58\x04\x04\xff\x18\x08"), Event(96, b"\xff\x58\x04\x03\x07\x18\x08")))
    assert meter_map(Song(96, 0, (part,))).changes == ((0, 4, 4),)


def test_pairing_counts_a_note_off_that_found_two_of_its_key_open():
    from groovebin.song import pair
    part = pair([(0, b"\x90\x24\x64"), (10, b"\x90\x24\x5a"), (20, b"\x80\x24\x00"), (100, b"\x80\x24\x00")], ppq=96)
    assert part.nested_ons == 1
    assert [(n.tick, n.length) for n in part.notes] == [(0, 20), (10, 90)]
    assert pair([(0, b"\x90\x24\x64"), (20, b"\x80\x24\x00")], ppq=96).nested_ons == 0


def test_a_signature_the_ppq_cannot_hold_in_whole_ticks_is_skipped():
    from groovebin.events import Event
    from groovebin.song import Part, Song, meter_map
    sixty_fourth = Event(0, b"\xff\x58\x04\x01\x06\x18\x08")
    assert meter_map(Song(120, 1, (Part(120, (), (sixty_fourth,)),))).changes == ((0, 4, 4),)
    assert meter_map(Song(960, 1, (Part(960, (), (sixty_fourth,)),))).changes == ((0, 1, 64),)


def test_the_skipped_signatures_are_counted_for_a_caller_to_report():
    from groovebin.events import Event
    from groovebin.song import Part, Song, meter_map, skipped_meters
    sixty_fourth = Event(0, b"\xff\x58\x04\x01\x06\x18\x08")
    zero = Event(10, b"\xff\x58\x04\x00\x02\x18\x08")
    past_64 = Event(20, b"\xff\x58\x04\x04\x07\x18\x08")
    song = Song(120, 1, (Part(120, (), (sixty_fourth, zero, past_64)),))
    assert meter_map(song).defaulted and meter_map(song).changes == ((0, 4, 4),)
    assert skipped_meters(song) == 3
    assert skipped_meters(Song(960, 1, (Part(960, (), (sixty_fourth,)),))) == 0
    assert skipped_meters(Song(960, 1, (Part(960),))) == 0
