"""Notes and every other event on a signed tick timeline, and the order events take at one tick.

A Note is a note-on paired with its note-off. An Event is any other event a Standard MIDI File
holds, kept as its file bytes: a channel message, a SysEx (``F0 … F7``), or a meta event
(``FF type length payload``). Ticks may be negative: a part's events can sit before its start.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

CHANNEL_KINDS = {0xA0: "polytouch", 0xB0: "control", 0xC0: "program", 0xD0: "pressure", 0xE0: "bend"}
DATA_BYTES = {0xA0: 2, 0xB0: 2, 0xC0: 1, 0xD0: 1, 0xE0: 2}
RANK = {"meta": 0, "sysex": 1, "program": 2, "control": 3, "note": 4, "polytouch": 5,
        "pressure": 6, "bend": 7}
MAX_VLQ = 0x0FFFFFFF                     # a variable-length quantity is four bytes at most


def _in_range(name: str, value: int, low: int, high: int) -> None:
    if not low <= value <= high:
        raise ValueError(f"{name} {value} is not {low}-{high}")


@dataclass(frozen=True, slots=True)
class Note:
    tick: int
    length: int
    channel: int
    pitch: int
    velocity: int
    off_velocity: int | None = None
    tag: object = field(default=None, compare=False)

    def __post_init__(self) -> None:
        _in_range("pitch", self.pitch, 0, 127)
        _in_range("channel", self.channel, 1, 16)
        _in_range("velocity", self.velocity, 1, 127)
        if self.length < 0:
            raise ValueError(f"a note's length of {self.length} ticks is negative")
        if self.off_velocity is not None:
            _in_range("note-off velocity", self.off_velocity, 0, 127)

    @property
    def end(self) -> int:
        return self.tick + self.length


def read_vlq(data: bytes, pos: int) -> tuple[int, int]:
    """(value, position after it) for the variable-length quantity at ``pos``."""
    value = 0
    for i in range(pos, min(pos + 4, len(data))):
        value = value << 7 | data[i] & 0x7F
        if not data[i] & 0x80:
            return value, i + 1
    raise ValueError("a variable-length quantity runs past its event")


@dataclass(frozen=True, slots=True)
class Event:
    tick: int
    data: bytes
    tag: object = field(default=None, compare=False)

    def __post_init__(self) -> None:
        data = self.data
        if not data:
            raise ValueError("an event holds no bytes")
        status = data[0]
        if status < 0x80:
            raise ValueError(f"0x{status:02X} is not a status byte")
        high = status & 0xF0
        if high in (0x80, 0x90):
            raise ValueError(f"a note-{'on' if high == 0x90 else 'off'} is a Note, not an Event")
        if high in DATA_BYTES:
            n = DATA_BYTES[high]
            if len(data) - 1 != n:
                raise ValueError(f"0x{high:02X} carries {n} data byte{'s' * (n > 1)}, not {len(data) - 1}")
            if bad := next((b for b in data[1:] if b & 0x80), None):
                raise ValueError(f"data byte 0x{bad:02X} is not below 0x80")
        elif status == 0xF0:
            if data[-1] != 0xF7 or len(data) < 2:
                raise ValueError("a SysEx event ends with 0xF7")
            if bad := next((b for b in data[1:-1] if b & 0x80), None):
                raise ValueError(f"SysEx data byte 0x{bad:02X} is not below 0x80")
        elif status == 0xFF:
            if len(data) < 3 or data[1] & 0x80:
                raise ValueError(f"meta type 0x{data[1] if len(data) > 1 else 0:02X} is not below 0x80")
            size, start = read_vlq(data, 2)
            if len(data) - start != size:
                raise ValueError(f"meta event 0x{data[1]:02X} claims {size} bytes but holds {len(data) - start}")
        else:
            raise ValueError(f"0x{status:02X} is not an event a file holds")

    @property
    def kind(self) -> str:
        status = self.data[0]
        if status == 0xFF:
            return "meta"
        if status == 0xF0:
            return "sysex"
        return CHANNEL_KINDS[status & 0xF0]

    @property
    def channel(self) -> int | None:
        return (self.data[0] & 0x0F) + 1 if self.data[0] < 0xF0 else None

    @property
    def number(self) -> int:
        return self.data[1]

    @property
    def pitch(self) -> int:
        return self.data[1]

    @property
    def program(self) -> int:
        return self.data[1]

    @property
    def value(self) -> int:
        return self.data[-1]

    @property
    def bend(self) -> int:
        """0-16383, centre 8192: the second data byte is the high seven bits."""
        return self.data[2] << 7 | self.data[1]

    @property
    def meta_type(self) -> int | None:
        return self.data[1] if self.data[0] == 0xFF else None

    @property
    def payload(self) -> bytes:
        return self.data[read_vlq(self.data, 2)[1]:]


def order_key(item: Note | Event) -> tuple[int, int, int, int]:
    if isinstance(item, Note):
        return item.tick, RANK["note"], item.pitch, item.length
    return item.tick, RANK[item.kind], 0, 0


def ordered(items: Iterable[Note | Event]) -> list[Note | Event]:
    """Stably sorted by tick, then meta < SysEx < program < controller < note < polytouch <
    pressure < bend, notes by pitch then length. Channel is not in the key."""
    return sorted(items, key=order_key)
