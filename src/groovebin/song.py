"""Parts and songs: notes and events per track, note on/off pairing, and the maps a song carries.

``pair`` turns a track's messages, as ``(absolute tick, bytes)``, into a Part; ``unpair`` turns a
Part back into messages in an order ``pair`` reads back to the same Part.
"""

from __future__ import annotations

from bisect import bisect_right, insort
from collections import defaultdict, deque
from collections.abc import Iterable
from dataclasses import dataclass, field, replace

from .events import RANK, Event, Note, order_key
from .timing import MeterMap, TempoMap

END_OF_TRACK = b"\xff\x2f\x00"
TEMPO, TIME_SIGNATURE, TRACK_NAME = 0x51, 0x58, 0x03
MAX_DENOMINATOR_POWER = 6


@dataclass(frozen=True, slots=True)
class Part:
    ppq: int
    notes: tuple[Note, ...] = ()
    events: tuple[Event, ...] = ()
    end: int | None = None
    orphan_offs: int = field(default=0, compare=False)

    def __post_init__(self) -> None:
        if self.ppq < 1:
            raise ValueError(f"a PPQ of {self.ppq} is not 1 or more")
        object.__setattr__(self, "notes", tuple(sorted(self.notes, key=order_key)))
        object.__setattr__(self, "events", tuple(sorted(self.events, key=order_key)))

    @property
    def name(self) -> str | None:
        found = next((e for e in self.events if e.meta_type == TRACK_NAME), None)
        return found.payload.decode("latin-1") if found else None

    @property
    def last_tick(self) -> int:
        ticks = [n.end for n in self.notes] + [e.tick for e in self.events]
        if self.end is not None:
            ticks.append(self.end)
        return max(ticks, default=0)


@dataclass(frozen=True, slots=True)
class Song:
    ppq: int
    format: int
    tracks: tuple[Part, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "tracks", tuple(self.tracks))
        if self.format not in (0, 1):
            raise ValueError(f"format {self.format} is not supported: only format 0 and format 1")
        if self.format == 0 and len(self.tracks) != 1:
            raise ValueError(f"a format 0 song holds {len(self.tracks)} tracks, not one")
        for i, track in enumerate(self.tracks, 1):
            if track.ppq != self.ppq:
                raise ValueError(f"track {i} is at PPQ {track.ppq}, not the song's {self.ppq}")


def pair(messages: Iterable[tuple[int, bytes]], *, ppq: int) -> Part:
    """A track's messages, in file order, as a Part. Each note-off closes the earliest open note of
    its channel and pitch; a note still open at the track's end closes there."""
    open_notes: dict[tuple[int, int], deque[tuple[int, int]]] = defaultdict(deque)
    closed: list[tuple[int, int, int, int, int | None]] = []
    events: list[Event] = []
    end, orphans = 0, 0
    for tick, data in messages:
        end = max(end, tick)
        high = data[0] & 0xF0
        if data == END_OF_TRACK:
            continue
        if high not in (0x80, 0x90):
            events.append(Event(tick, data))
            continue
        key = (data[0] & 0x0F, data[1])
        if high == 0x90 and data[2]:
            open_notes[key].append((tick, data[2]))
        elif open_notes[key]:
            start, velocity = open_notes[key].popleft()
            closed.append((start, tick, *key, velocity, data[2] if high == 0x80 else None))
        else:
            orphans += 1
    for key, starts in open_notes.items():
        closed += [(start, end, *key, velocity, None) for start, velocity in starts]
    notes = [Note(start, stop - start, channel + 1, pitch, velocity, off_velocity)
             for start, stop, channel, pitch, velocity, off_velocity in closed]
    return Part(ppq, notes, events, end=end, orphan_offs=orphans)


def unpair(part: Part) -> list[tuple[int, bytes]]:
    """The Part's messages in write order, without the end-of-track event."""
    keyed: list[tuple[tuple[int, ...], bytes, int]] = []
    for e in part.events:
        keyed.append(((*order_key(e), 0), e.data, e.tick))
    for n in part.notes:
        keyed.append(((*order_key(n), 0), bytes([0x90 | n.channel - 1, n.pitch, n.velocity]), n.tick))
        off = (bytes([0x90 | n.channel - 1, n.pitch, 0]) if n.off_velocity is None
               else bytes([0x80 | n.channel - 1, n.pitch, n.off_velocity]))
        key = (n.tick, RANK["note"], n.pitch, 0, 1) if n.length == 0 else (n.end, -1, n.pitch, n.tick, 0)
        keyed.append((key, off, n.end))
    return [(tick, data) for _, data, tick in sorted(keyed, key=lambda k: k[0])]


def merged(song: Song) -> Part:
    ends = [t.end for t in song.tracks if t.end is not None]
    return Part(song.ppq, [n for t in song.tracks for n in t.notes],
                [e for t in song.tracks for e in t.events], end=max(ends) if ends else None)


def _metas(song: Song, meta_type: int) -> list[Event]:
    return sorted((e for t in song.tracks for e in t.events if e.meta_type == meta_type),
                  key=lambda e: e.tick)


def tempo_map(song: Song) -> TempoMap:
    """Tempo events from every track; a zero tempo or a malformed one is skipped."""
    points = [(e.tick, int.from_bytes(e.payload)) for e in _metas(song, TEMPO) if len(e.payload) == 3]
    return TempoMap(tuple((t, usec) for t, usec in points if usec))


def meter_map(song: Song) -> MeterMap:
    """Time signatures from every track; one with a zero numerator or a denominator past 64 is skipped."""
    changes = [(e.tick, e.payload[0], 1 << e.payload[1]) for e in _metas(song, TIME_SIGNATURE)
               if len(e.payload) >= 2 and e.payload[0] and e.payload[1] <= MAX_DENOMINATOR_POWER]
    return MeterMap(song.ppq, tuple(changes))


def rescale(part: Part, ppq: int) -> Part:
    """The Part at another PPQ; note starts, note ends and event ticks each round half up."""
    def scale(tick: int) -> int:
        return (tick * ppq + part.ppq // 2) // part.ppq

    notes = [replace(n, tick=scale(n.tick), length=scale(n.end) - scale(n.tick)) for n in part.notes]
    events = [replace(e, tick=scale(e.tick)) for e in part.events]
    end = None if part.end is None else scale(part.end)
    return Part(ppq, notes, events, end=end, orphan_offs=part.orphan_offs)


def nested_overlaps(part: Part) -> list[tuple[Note, Note]]:
    """(outer, inner) pairs of one channel and pitch where inner starts later and ends earlier,
    which pairing on read gives back with their lengths swapped."""
    by_key: dict[tuple[int, int], list[Note]] = defaultdict(list)
    for n in part.notes:
        by_key[n.channel, n.pitch].append(n)
    return [(notes[i], notes[j]) for notes in by_key.values() for i, j in sorted(_nested(notes))]


def _nested(notes: list[Note]) -> list[tuple[int, int]]:
    """(outer, inner) indices into ``notes``, which are in tick order."""
    started: list[tuple[int, int]] = []
    found, ready = [], 0
    for j, inner in enumerate(notes):
        while notes[ready].tick < inner.tick:
            insort(started, (notes[ready].end, ready))
            ready += 1
        found += [(i, j) for _, i in started[bisect_right(started, (inner.end, len(notes))):]]
    return found

