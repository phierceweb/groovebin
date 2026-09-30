"""A library row's notes and channel events as packed records, at the index's PPQ."""

from __future__ import annotations

import struct
from collections.abc import Iterable

from ..events import Event, Note

NOTE = struct.Struct("<IIBBB")          # tick, length, channel, pitch, velocity
EVENT = struct.Struct("<IB3s")          # tick, byte count, a channel message's bytes


def pack_notes(notes: list[Note] | tuple[Note, ...]) -> bytes:
    out = []
    for n in notes:
        if n.tick < 0 or n.end > 0xFFFFFFFF:
            raise OverflowError(f"a note at tick {n.tick} is past the index's 32-bit tick range")
        out.append(NOTE.pack(n.tick, n.length, n.channel, n.pitch, n.velocity))
    return b"".join(out)


def unpack_notes(blob: bytes | None) -> list[Note]:
    return [Note(t, length, ch, p, v) for t, length, ch, p, v in NOTE.iter_unpack(blob or b"")]


def pack_events(events: Iterable[Event]) -> bytes:
    """Channel messages as records; any other event is left out."""
    out = []
    for e in events:
        if e.channel is not None:
            if e.tick < 0 or e.tick > 0xFFFFFFFF:
                raise OverflowError(f"an event at tick {e.tick} is past the index's 32-bit tick range")
            out.append(EVENT.pack(e.tick, len(e.data), e.data))
    return b"".join(out)


def unpack_events(blob: bytes | None) -> list[Event]:
    return [Event(tick, data[:size]) for tick, size, data in EVENT.iter_unpack(blob or b"")]
