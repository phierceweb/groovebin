import io
import struct

import mido
import pytest

from groovebin.events import MAX_VLQ, Event, Note
from groovebin.midi import MidiFileError, read, write
from groovebin.song import Part, Song

EOT = b"\xff\x2f\x00"


def vlq(n):
    out = [n & 0x7F]
    while n := n >> 7:
        out.append(n & 0x7F | 0x80)
    return bytes(reversed(out))


def track(*events, tag=b"MTrk"):
    body = b"".join(vlq(delta) + data for delta, data in events)
    return tag + struct.pack(">I", len(body)) + body


def smf(fmt, division, *chunks, ntrks=None):
    return b"MThd" + struct.pack(">IHHH", 6, fmt, len(chunks) if ntrks is None else ntrks, division) + b"".join(chunks)


def test_read_pairs_notes_and_keeps_every_other_event_per_track():
    data = smf(1, 480,
               track((0, b"\xff\x51\x03\x07\xa1\x20"), (0, b"\xff\x58\x04\x03\x02\x18\x08"), (0, EOT)),
               track((0, b"\xff\x03\x03Kit"), (0, b"\x99\x24\x64"), (120, b"\x24\x00"), (0, b"\xb9\x04\x7f"),
                     (360, b"\x89\x26\x40"), (0, EOT)))
    song = read(data)
    assert (song.ppq, song.format, len(song.tracks)) == (480, 1, 2)
    drums = song.tracks[1]
    assert drums.name == "Kit"
    assert drums.notes == (Note(0, 120, 10, 36, 100),)
    assert drums.events == (Event(0, b"\xff\x03\x03Kit"), Event(120, b"\xb9\x04\x7f"))
    assert (drums.orphan_offs, drums.end) == (1, 480)


def test_a_song_survives_write_and_read():
    conductor = Part(960, (), (Event(0, b"\xff\x51\x03\x07\xa1\x20"), Event(0, b"\xff\x58\x04\x07\x03\x0c\x08"),
                               Event(0, b"\xff\x59\x02\x01\x00")), end=0)
    notes = (Note(0, 0, 10, 36, 110), Note(0, 240, 10, 42, 80, 64), Note(0, 120, 10, 42, 70),
             Note(240, 480, 10, 38, 127, 0), Note(480, 960, 1, 60, 50))
    events = (Event(0, b"\xff\x03\x04Kit\xe9"), Event(0, b"\xf0\x7e\x7f\x09\x01\xf7"), Event(0, b"\xc9\x19"),
              Event(0, b"\xb9\x04\x7f"), Event(0, b"\xb9\x07\x64"), Event(240, b"\xa9\x2a\x30"),
              Event(240, b"\xd9\x10"), Event(240, b"\xe0\x00\x40"), Event(300, b"\xff\x60\x02\x01\x02"),
              Event(300, b"\xff\x7f\x03\x00\x00\x41"), Event(310, b"\xff\x01\x81\x48" + b"x" * 200))
    song = Song(960, 1, (conductor, Part(960, notes, events, end=3840)))
    assert read(write(song)) == song


def test_controllers_are_written_before_a_program_change_at_their_tick():
    events = (Event(0, b"\xff\x03\x03Kit"), Event(0, b"\xc9\x19"), Event(0, b"\xb9\x00\x7f"), Event(0, b"\xb9\x20\x00"),
              Event(0, b"\xc0\x05"), Event(96, b"\xc9\x1a"), Event(96, b"\xb0\x07\x64"))
    song = Song(96, 0, (Part(96, (Note(0, 48, 10, 36, 100), Note(96, 0, 10, 38, 90)), events, end=96),))
    data = write(song)
    written = [m.bytes() for m in mido.MidiFile(file=io.BytesIO(data)).tracks[0]]
    assert written[:10] == [[0xFF, 0x03, 3, *b"Kit"], [0xB9, 0, 127], [0xB9, 32, 0], [0xC9, 25], [0xC0, 5],
                            [0x99, 36, 100], [0x99, 36, 0], [0xB0, 7, 100], [0xC9, 26], [0x99, 38, 90]]
    assert read(data) == song


def test_a_file_read_written_and_read_again_is_the_same_song():
    data = smf(0, 96, track((0, b"\x90\x3c\x40"), (10, b"\x3c\x50"), (10, b"\x3c\x00"), (10, b"\x80\x3c\x05"),
                            (0, b"\x80\x40\x00"), (5, b"\xf7\x02\x01\x02"), (5, b"\x90\x3e\x60"), (20, EOT)))
    first = read(data)
    assert read(write(first)) == first


def test_a_meta_event_of_any_type_keeps_its_tick_and_bytes():
    data = smf(0, 96, track((60, b"\xff\x08\x05Brush"), (10, b"\x90\x3c\x40"), (0, b"\xff\x00\x00"),
                            (5, b"\x80\x3c\x00"), (0, b"\xff\x59\x02\x09\x00"), (0, EOT)))
    part = read(data).tracks[0]
    assert part.events == (Event(60, b"\xff\x08\x05Brush"), Event(70, b"\xff\x00\x00"), Event(75, b"\xff\x59\x02\x09\x00"))
    assert part.notes == (Note(70, 5, 1, 60, 64, 0),)
    assert read(write(read(data))) == read(data)


def test_running_status_survives_a_meta_event_and_an_escape_reads_as_sysex():
    data = smf(0, 96, track((0, b"\x90\x3c\x40"), (0, b"\xff\x06\x01A"), (10, b"\x3c\x00"),
                            (0, b"\xf7\x02\x01\x02"), (0, EOT)))
    part = read(data).tracks[0]
    assert part.notes == (Note(0, 10, 1, 60, 64),)
    assert part.events == (Event(0, b"\xff\x06\x01A"), Event(10, b"\xf0\x01\x02\xf7"))


def test_chunks_that_are_not_tracks_are_skipped():
    data = smf(1, 96, track((0, EOT)), track((0, b"\x01\x02"), tag=b"XFIH"), track((0, b"\x90\x3c\x40"), (5, EOT)))
    assert len(read(data).tracks) == 2


@pytest.mark.parametrize(("data", "message"), [
    (b"", "no MThd header: not a Standard MIDI File"),
    (b"RIFF" + bytes(10), "no MThd header: not a Standard MIDI File"),
    (smf(0, 0xE728, track((0, EOT))), "SMPTE time division .* is not supported"),
    (smf(0, 0, track((0, EOT))), "a PPQ of 0 is not 1 or more"),
    (smf(2, 96, track((0, EOT))), "format 2 is not supported: only format 0 and format 1"),
    (smf(0, 96, track((0, EOT)))[:-1], "chunk b'MTrk' claims 4 bytes but the file ends 1 short"),
    (smf(0, 96), "the file holds no MTrk chunk"),
    (smf(0, 96, track((0, EOT)), track((0, EOT))), "a format 0 file holds 2 tracks, not one"),
    (smf(0, 96, track((0, b"\x99\x24\x90"), (0, EOT))), "track 1: data byte 0x90 at tick 0 is not below 0x80"),
    (smf(0, 96, track((7, b"\x24\x40"), (0, EOT))), "track 1: data byte 0x24 at tick 7 has no running status"),
    (smf(1, 96, track((0, EOT)), track((0, b"\xf0\x10\x01\x02"))), "track 2 ends inside an event"),
    (smf(0, 96, track((0, b"\xf0\x02\x01\x02"), (0, EOT))), "track 1: a SysEx event at tick 0 does not end with 0xF7"),
    (smf(0, 96, track((4, b"\xf0\x03\x01\x90\xf7"), (0, EOT))), "track 1: SysEx data byte 0x90 at tick 4 is not below 0x80"),
    (smf(0, 96, track((0, b"\xf7\x01\xfa"), (0, EOT))), "track 1: SysEx data byte 0xFA at tick 0 is not below 0x80"),
    (smf(0, 96, track((3, b"\xf1\x00"), (0, EOT))), "track 1: status 0xF1 at tick 3 is not an event a file holds"),
    (smf(0, 96, track((0, b"\x90\x3c"))), "track 1 ends inside an event"),
])
def test_read_refuses_what_it_cannot_read_with_a_message(data, message):
    with pytest.raises(MidiFileError, match=message):
        read(data)


def test_a_read_error_is_a_value_error():
    assert issubclass(MidiFileError, ValueError)


def test_write_refuses_a_tick_before_the_start_of_the_file():
    song = Song(96, 0, (Part(96, (Note(-5, 10, 1, 60, 90),)),))
    with pytest.raises(ValueError, match="track 1: an event at tick -5 is before the start of the file"):
        write(song)


def test_write_refuses_a_ppq_a_file_cannot_hold():
    with pytest.raises(ValueError, match="a PPQ of 32768 does not fit a file's 15-bit division"):
        write(Song(32768, 0, (Part(32768),)))


def test_a_meta_length_written_with_spare_bytes_reads_as_its_shortest_form():
    data = smf(0, 96, track((0, b"\xff\x58\x80\x04\x04\x02\x18\x08"), (0, b"\x90\x3c\x40"), (5, b"\x80\x3c\x00"), (0, EOT)))
    song = read(data)
    assert song.tracks[0].events == (Event(0, b"\xff\x58\x04\x04\x02\x18\x08"),)
    assert read(write(song)) == song


def test_a_gap_past_what_a_file_can_hold_is_refused():
    far = Part(480, (Note(MAX_VLQ + 1, 10, 1, 36, 100),))
    with pytest.raises(ValueError, match=f"a gap of {MAX_VLQ + 1} ticks is past the {MAX_VLQ}"):
        write(Song(480, 0, (far,)))
    ok = Part(480, (Note(MAX_VLQ, 10, 1, 36, 100),))
    assert read(write(Song(480, 0, (ok,)))).tracks[0].notes[-1].tick == MAX_VLQ


def test_a_delta_time_of_more_than_four_bytes_is_refused():
    body = b"\xff\xff\xff\xff\x00" + b"\x90\x24\x64" + b"\x00" + EOT
    data = b"MThd" + struct.pack(">IHHH", 6, 0, 1, 480) + b"MTrk" + struct.pack(">I", len(body)) + body
    with pytest.raises(MidiFileError, match="runs past four bytes"):
        read(data)
