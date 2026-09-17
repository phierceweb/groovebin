from dataclasses import replace

import pytest

from groovebin.events import Event, Note, ordered


def test_a_note_holds_its_fields_and_end():
    n = Note(tick=-240, length=480, channel=10, pitch=36, velocity=100, off_velocity=64)
    assert (n.tick, n.length, n.channel, n.pitch, n.velocity, n.off_velocity) == (-240, 480, 10, 36, 100, 64)
    assert n.end == 240


@pytest.mark.parametrize(("fields", "message"), [
    ({"pitch": 128}, "pitch 128 is not 0-127"),
    ({"pitch": -1}, "pitch -1 is not 0-127"),
    ({"channel": 0}, "channel 0 is not 1-16"),
    ({"channel": 17}, "channel 17 is not 1-16"),
    ({"velocity": 0}, "velocity 0 is not 1-127"),
    ({"velocity": 128}, "velocity 128 is not 1-127"),
    ({"length": -1}, "a note's length of -1 ticks is negative"),
    ({"off_velocity": 128}, "note-off velocity 128 is not 0-127"),
])
def test_a_note_refuses_values_a_file_cannot_hold(fields, message):
    base = {"tick": 0, "length": 0, "channel": 1, "pitch": 60, "velocity": 1}
    with pytest.raises(ValueError, match=message):
        Note(**(base | fields))


def test_equality_ignores_the_tag_and_replace_keeps_it():
    a = Note(0, 10, 1, 60, 100, tag="line 7")
    assert a == Note(0, 10, 1, 60, 100)
    assert replace(a, pitch=62).tag == "line 7"


@pytest.mark.parametrize(("data", "kind", "channel", "reads"), [
    (b"\xb9\x07\x64", "control", 10, {"number": 7, "value": 100}),
    (b"\xc0\x05", "program", 1, {"program": 5}),
    (b"\xe0\x00\x40", "bend", 1, {"bend": 8192}),
    (b"\xef\x7f\x7f", "bend", 16, {"bend": 16383}),
    (b"\xa1\x24\x10", "polytouch", 2, {"pitch": 36, "value": 16}),
    (b"\xd0\x20", "pressure", 1, {"value": 32}),
    (b"\xf0\x7e\x7f\xf7", "sysex", None, {}),
    (b"\xff\x51\x03\x07\xa1\x20", "meta", None, {"meta_type": 0x51, "payload": b"\x07\xa1\x20"}),
])
def test_an_event_reads_as_its_kind(data, kind, channel, reads):
    e = Event(tick=0, data=data)
    assert (e.kind, e.channel) == (kind, channel)
    assert {name: getattr(e, name) for name in reads} == reads


def test_a_meta_payload_past_127_bytes_reads_through_its_length_prefix():
    e = Event(0, b"\xff\x01\x81\x48" + b"x" * 200)
    assert (e.meta_type, e.payload) == (0x01, b"x" * 200)


@pytest.mark.parametrize(("data", "message"), [
    (b"", "an event holds no bytes"),
    (b"\x90\x3c\x40", "a note-on is a Note, not an Event"),
    (b"\x80\x3c\x40", "a note-off is a Note, not an Event"),
    (b"\xb0\x07", "0xB0 carries 2 data bytes, not 1"),
    (b"\xc0\x05\x06", "0xC0 carries 1 data byte, not 2"),
    (b"\xb0\x07\x80", "data byte 0x80 is not below 0x80"),
    (b"\x07\x64", "0x07 is not a status byte"),
    (b"\xf0\x7e\x80\xf7", "SysEx data byte 0x80 is not below 0x80"),
    (b"\xff\x51\x05\x07\xa1\x20", "meta event 0x51 claims 5 bytes but holds 3"),
    (b"\xff\x80\x00", "meta type 0x80 is not below 0x80"),
    (b"\xf1\x00", "0xF1 is not an event a file holds"),
])
def test_an_event_refuses_bytes_a_file_cannot_hold(data, message):
    with pytest.raises(ValueError, match=message):
        Event(0, data)


def test_the_canonical_order_ranks_kinds_at_one_tick():
    tempo = Event(0, b"\xff\x51\x03\x07\xa1\x20")
    sysex = Event(0, b"\xf0\x01\xf7")
    program = Event(0, b"\xc0\x01")
    control = Event(0, b"\xb0\x07\x64")
    low, high, short = Note(0, 480, 1, 36, 90), Note(0, 240, 2, 42, 90), Note(0, 120, 1, 42, 90)
    poly = Event(0, b"\xa0\x24\x10")
    pressure = Event(0, b"\xd0\x20")
    bend = Event(0, b"\xe0\x00\x40")
    later = Event(1, b"\xc0\x02")
    shuffled = [later, bend, pressure, poly, high, short, low, control, program, sysex, tempo]
    assert ordered(shuffled) == [tempo, sysex, program, control, low, short, high, poly, pressure, bend, later]


def test_the_canonical_order_is_stable_for_ties_and_ignores_channel():
    first, second = Event(0, b"\xb9\x40\x7f"), Event(0, b"\xb0\x07\x64")
    a, b = Note(0, 10, 10, 60, 100), Note(0, 10, 1, 60, 50)
    assert ordered([first, second, a, b]) == [first, second, a, b]
    assert ordered([second, first, b, a]) == [second, first, b, a]


def test_a_sysex_packet_without_its_terminator_and_an_escape_are_events():
    assert Event(0, b"\xf0\x7e\x7f").kind == "sysex"
    assert Event(0, b"\xf7\xf8").kind == "escape"
    assert Event(0, b"\xf7").kind == "escape"
