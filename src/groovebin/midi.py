"""Standard MIDI Files to Songs and back. Tracks are read here, not through mido, which drops the delta
time of a meta event type it does not know; writing goes through mido, every meta passed as raw bytes."""

from __future__ import annotations

import io
import struct

import mido

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
        while True:
            byte = self.take(1)[0]
            value = value << 7 | byte & 0x7F
            if not byte & 0x80:
                return value

    def events(self) -> list[tuple[int, bytes]]:
        """Every event with its absolute tick. Running status survives meta and SysEx events,
        and an F7 escape reads as a SysEx event."""
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
                if first == 0xF0 and not payload.endswith(b"\xf7"):
                    raise self.fail(f"a SysEx event at tick {tick} does not end with 0xF7")
                payload = payload.removesuffix(b"\xf7")
                if bad := next((b for b in payload if b & 0x80), None):
                    raise self.fail(f"SysEx data byte 0x{bad:02X} at tick {tick} is not below 0x80")
                out.append((tick, b"\xf0" + payload + b"\xf7"))
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


def _message(data: bytes, delta: int) -> mido.Message | mido.MetaMessage:
    if data[0] == 0xFF:
        payload_at = next(i for i in range(2, len(data)) if not data[i] & 0x80) + 1
        return mido.UnknownMetaMessage(data[1], data[payload_at:], time=delta)
    return mido.Message.from_bytes(list(data), time=delta)


def _controls_before_programs(messages: list[tuple[int, bytes]]) -> list[tuple[int, bytes]]:
    """A tick's program changes moved after its controllers, so a bank select applies to the program."""
    last_control = {tick: i for i, (tick, data) in enumerate(messages) if data[0] & 0xF0 == 0xB0}

    def position(item: tuple[int, tuple[int, bytes]]) -> tuple[float, int]:
        i, (tick, data) = item
        moved = data[0] & 0xF0 == 0xC0 and last_control.get(tick, -1) > i
        return (last_control[tick] + 0.5 if moved else i), i

    return [message for _, message in sorted(enumerate(messages), key=position)]


def write(song: Song) -> bytes:
    if song.ppq > MAX_PPQ:
        raise ValueError(f"a PPQ of {song.ppq} does not fit a file's 15-bit division")
    out = mido.MidiFile(type=song.format, ticks_per_beat=song.ppq)
    for number, part in enumerate(song.tracks, 1):
        messages = _controls_before_programs(unpair(part))
        if messages and messages[0][0] < 0:
            raise ValueError(f"track {number}: an event at tick {messages[0][0]} is before the start of the file")
        track, now = mido.MidiTrack(), 0
        for tick, data in messages:
            track.append(_message(data, tick - now))
            now = tick
        end = max(part.last_tick, now) - now
        track.append(mido.MetaMessage.from_bytes(list(END_OF_TRACK)).copy(time=end))
        out.tracks.append(track)
    buffer = io.BytesIO()
    out.save(file=buffer)
    return buffer.getvalue()
