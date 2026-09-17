"""Standard MIDI Files to Songs and back, both written here. Every event keeps its delta time and its
bytes, a meta type this module does not know included."""

from __future__ import annotations

import struct

from .events import MAX_VLQ
from .song import END_OF_TRACK, Song, pair, unpair

MAX_PPQ = 0x7FFF
DATA_BYTES = {0x80: 2, 0x90: 2, 0xA0: 2, 0xB0: 2, 0xC0: 1, 0xD0: 1, 0xE0: 2}


class MidiFileError(ValueError):
    """A file that is not a Standard MIDI File groovebin can read."""


def _vlq_bytes(value: int) -> bytes:
    out = [value & 0x7F]
    while value := value >> 7:
        out.append(value & 0x7F | 0x80)
    return bytes(reversed(out))


def _chunks(data: bytes) -> tuple[int, int, list[bytes]]:
    if data[:4] != b"MThd":
        raise MidiFileError("no MThd header: not a Standard MIDI File")
    if len(data) < 14:
        raise MidiFileError(f"the MThd header ends {14 - len(data)} bytes short")
    size, fmt, _, division = struct.unpack_from(">IHHH", data, 4)
    if division & 0x8000:
        raise MidiFileError("SMPTE time division (frames per second, not ticks per quarter note) is not supported")
    if division == 0:
        raise MidiFileError("a PPQ of 0 is not 1 or more")
    if fmt not in (0, 1):
        raise MidiFileError(f"format {fmt} is not supported: only format 0 and format 1")
    tracks, pos = [], 8 + size
    while pos + 8 <= len(data):
        tag, length = data[pos:pos + 4], struct.unpack_from(">I", data, pos + 4)[0]
        body = data[pos + 8:pos + 8 + length]
        if len(body) < length:
            raise MidiFileError(f"chunk {tag!r} claims {length} bytes but the file ends {length - len(body)} short")
        if tag == b"MTrk":
            tracks.append(body)
        pos += 8 + length
    if not tracks:
        raise MidiFileError("the file holds no MTrk chunk")
    if fmt == 0 and len(tracks) != 1:
        raise MidiFileError(f"a format 0 file holds {len(tracks)} tracks, not one")
    return fmt, division, tracks


class _Track:
    def __init__(self, body: bytes, number: int):
        self.body, self.number, self.pos = body, number, 0

    def fail(self, what: str) -> MidiFileError:
        return MidiFileError(f"track {self.number}: {what}")

    def take(self, n: int) -> bytes:
        if self.pos + n > len(self.body):
            raise MidiFileError(f"track {self.number} ends inside an event")
        out = self.body[self.pos:self.pos + n]
        self.pos += n
        return out

    def vlq(self) -> int:
        value = 0
        for _ in range(4):
            byte = self.take(1)[0]
            value = value << 7 | byte & 0x7F
            if not byte & 0x80:
                return value
        raise self.fail("a variable-length quantity runs past four bytes")

    def events(self) -> list[tuple[int, bytes]]:
        """Every event with its absolute tick. Running status survives meta and SysEx events;
        a SysEx packet and an F7 escape each read as the bytes the file holds."""
        out: list[tuple[int, bytes]] = []
        tick, status = 0, None
        while self.pos < len(self.body):
            tick += self.vlq()
            first = self.take(1)[0]
            if first == 0xFF:
                meta_type = self.take(1)[0]
                length = self.vlq()
                out.append((tick, bytes([0xFF, meta_type]) + _vlq_bytes(length) + self.take(length)))
            elif first in (0xF0, 0xF7):
                payload = self.take(self.vlq())
                if first == 0xF0:                     # a packet without its F7 continues in an escape
                    body = payload[:-1] if payload.endswith(b"\xf7") else payload
                    if bad := next((b for b in body if b & 0x80), None):
                        raise self.fail(f"SysEx data byte 0x{bad:02X} at tick {tick} is not below 0x80")
                out.append((tick, bytes([first]) + payload))
            else:
                if first & 0x80:
                    if first >= 0xF0:
                        raise self.fail(f"status 0x{first:02X} at tick {tick} is not an event a file holds")
                    status = first
                    data = b""
                elif status is None:
                    raise self.fail(f"data byte 0x{first:02X} at tick {tick} has no running status")
                else:
                    data = bytes([first])
                data += self.take(DATA_BYTES[status & 0xF0] - len(data))
                if bad := next((b for b in data if b & 0x80), None):
                    raise self.fail(f"data byte 0x{bad:02X} at tick {tick} is not below 0x80")
                out.append((tick, bytes([status]) + data))
        return out


def read(data: bytes) -> Song:
    fmt, division, bodies = _chunks(data)
    tracks = [pair(_Track(body, i).events(), ppq=division) for i, body in enumerate(bodies, 1)]
    return Song(division, fmt, tuple(tracks))


def _controls_before_programs(messages: list[tuple[int, bytes]]) -> list[tuple[int, bytes]]:
    """A tick's program changes moved after its controllers, so a bank select applies to the program."""
    last_control = {tick: i for i, (tick, data) in enumerate(messages) if data[0] & 0xF0 == 0xB0}

    def position(item: tuple[int, tuple[int, bytes]]) -> tuple[float, int]:
        i, (tick, data) = item
        moved = data[0] & 0xF0 == 0xC0 and last_control.get(tick, -1) > i
        return (last_control[tick] + 0.5 if moved else i), i

    return [message for _, message in sorted(enumerate(messages), key=position)]


def _event_bytes(data: bytes) -> bytes:
    """An event's bytes on the wire: a SysEx packet or escape takes its length after its status;
    channel messages and meta events carry their own."""
    if data[0] in (0xF0, 0xF7):
        return bytes([data[0]]) + _vlq_bytes(len(data) - 1) + data[1:]
    return data


def write(song: Song) -> bytes:
    if not 1 <= song.ppq <= MAX_PPQ:
        raise ValueError(f"a PPQ of {song.ppq} is not 1 to {MAX_PPQ}, a file's 15-bit division")
    if not song.tracks:
        raise ValueError("a song holds at least one track")
    chunks = []
    for number, part in enumerate(song.tracks, 1):
        messages = _controls_before_programs(unpair(part))
        if messages and messages[0][0] < 0:
            raise ValueError(f"track {number}: an event at tick {messages[0][0]} is before the start of the file")
        body, now = bytearray(), 0
        for tick, data in messages:
            if tick - now > MAX_VLQ:
                raise ValueError(f"track {number}: a gap of {tick - now} ticks is past the {MAX_VLQ} a file can hold")
            body += _vlq_bytes(tick - now) + _event_bytes(data)
            now = tick
        end = max(part.last_tick, now) - now
        if end > MAX_VLQ:
            raise ValueError(f"track {number}: a gap of {end} ticks is past the {MAX_VLQ} a file can hold")
        body += _vlq_bytes(end) + END_OF_TRACK
        chunks.append(b"MTrk" + struct.pack(">I", len(body)) + bytes(body))
    return b"MThd" + struct.pack(">IHHH", 6, song.format, len(chunks), song.ppq) + b"".join(chunks)
