"""A row's notes and channel events packed as records: every field comes back, and a tick past 32 bits is refused."""

import pytest

from groovebin.events import Event, Note
from groovebin.library.blobs import pack_events, pack_notes, unpack_events, unpack_notes

NOTES = (Note(0, 480, 10, 36, 100), Note(960, 120, 1, 127, 1), Note(0xFFFFFFFF - 5, 5, 16, 0, 127))
CHANNEL = (Event(50, b"\xb0\x43\x40"), Event(60, b"\xa0\x2d\x30"), Event(2000, b"\xe0\x00\x50"), Event(2100, b"\xc0\x05"))
TEMPO = Event(0, b"\xff\x51\x03\x07\xa1\x20")


def test_notes_pack_and_unpack():
    assert unpack_notes(pack_notes(NOTES)) == list(NOTES)
    assert unpack_notes(None) == []


def test_only_channel_messages_are_packed():
    assert unpack_events(pack_events((TEMPO, *CHANNEL))) == list(CHANNEL)
    assert unpack_events(None) == []


@pytest.mark.parametrize(("item", "pack"), [(Note(0xFFFFFFFF, 1, 1, 60, 90), pack_notes),
                                            (Event(1 << 32, b"\xb0\x01\x02"), pack_events)])
def test_a_tick_past_32_bits_is_refused(item, pack):
    with pytest.raises(OverflowError, match="32-bit tick range"):
        pack([item])
