"""Following a chord chart: a part's notes moved from the chords they were played over onto another chart's, each
by its place in its chord (`harmony.revoice`)."""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, replace

from ..events import Event, Note
from ..harmony import Chord, Span, chart_spans, revoice
from ..song import Part
from ..timing import MeterMap
from .edits import POLYTOUCH, Mask, masked
from .theory import Hold


def _never(pitch: int) -> bool:
    return False


def chord_at(spans: Sequence[Span], tick: int) -> Chord | None:
    """The chord of the span holding ``tick``; None where no span does."""
    i = bisect_right([s.start for s in spans], tick) - 1
    return spans[i].chord if i >= 0 and tick < spans[i].end else None


def laid(bars_of_chords: list[tuple[Chord, ...]], meters: MeterMap, end: int) -> list[Span]:
    """A chart laid from bar 1 through the bar a part ending at tick ``end`` ends in, looping when it is shorter."""
    if not bars_of_chords:
        raise ValueError("a chart with no bars to lay")
    return chart_spans(bars_of_chords, meters, meters.bar_of(max(end - 1, 0)))


@dataclass(frozen=True)
class Followed:
    """A followed part, and what the move did that its notes do not show: notes read at a change they lead into, where
    the chords differ from their own place's (``anticipated``), notes held into a chord they are not in
    (``ringing``), notes that landed on a pitch another note of their start and channel reached from another pitch
    (``doubled``), and notes moved an octave back into the register (``folded``)."""
    part: Part
    anticipated: int
    ringing: int
    doubled: int
    folded: int = 0


def follow(part: Part, mask: Mask | None, source: Sequence[Span], target: Sequence[Span], *,
           hold: Hold = _never, register: tuple[int, int] | None = None, bass: bool = True) -> Followed:
    """Each selected note moved from the chord ``source`` has at its start to the one ``target`` has there. A note a
    32nd note or less before a change on either chart counts as on it. With no mask, a polyphonic aftertouch key
    moves with the note it touches. A held pitch, and a note either chart leaves uncovered, stay; nothing is added,
    dropped or shortened. A note the move takes out of ``register`` goes an octave the other way, back inside it.
    Without ``bass`` the part is not the bass: a slash chord reads as its chord, its bass note left to the bass."""
    if register is not None and register[1] - register[0] < 11:
        raise ValueError(f"a register of {register[0]}-{register[1]} is narrower than an octave")
    changes = sorted({s.start for s in (*source, *target)})
    starts = [s.start for s in target]

    def read_at(tick: int) -> int:
        i = bisect_right(changes, tick)
        return changes[i] if i < len(changes) and 8 * (changes[i] - tick) <= part.ppq else tick

    def chords(tick: int) -> tuple[Chord | None, Chord | None]:
        return tuple(c if bass or c is None or c.bass is None else replace(c, bass=None)
                     for c in (chord_at(source, tick), chord_at(target, tick)))

    def revoiced(pitch: int, tick: int) -> int:
        old, new = chords(read_at(tick))
        return pitch if old is None or new is None else revoice(pitch, old, new, own_tones=True)

    def placed(pitch: int, was: int, what: str) -> int:
        inside = register is not None and register[0] <= was <= register[1]
        while inside and pitch < register[0]:
            pitch += 12
        while inside and pitch > register[1]:
            pitch -= 12
        if not 0 <= pitch <= 127:
            raise ValueError(f"{what} {was} would move to {pitch}, outside 0-127")
        return pitch

    chosen = {i for i in masked(part, mask) if not hold(part.notes[i].pitch)}
    notes, folded = list(part.notes), 0
    for i in chosen:
        n = part.notes[i]
        raw = revoiced(n.pitch, n.tick)
        notes[i] = replace(n, pitch=placed(raw, n.pitch, "note"))
        folded += notes[i].pitch != raw
    anticipated = sum(1 for i in chosen if chords(read_at(part.notes[i].tick)) != chords(part.notes[i].tick))
    ringing = sum(1 for i in chosen if _rings(notes[i], read_at(notes[i].tick), target, starts, bass))
    landed: dict[tuple[int, int, int], set[int]] = defaultdict(set)
    for before, after in zip(part.notes, notes, strict=True):
        landed[before.tick, before.channel, after.pitch].add(before.pitch)
    doubled = sum(len(pitches) - 1 for pitches in landed.values())
    events = part.events
    if mask is None:
        keys = _keys(part.notes)

        def touched(e: Event) -> Event:
            if hold(e.pitch):
                return e
            i = _sounding(keys.get((e.channel, e.pitch)), e.tick)
            key = notes[i].pitch if i is not None else placed(revoiced(e.pitch, e.tick), e.pitch, "aftertouch key")
            return replace(e, data=bytes([e.data[0], key, e.data[2]]))

        events = tuple(touched(e) if e.data[0] & 0xF0 == POLYTOUCH else e for e in part.events)
    return Followed(replace(part, notes=tuple(notes), events=events), anticipated, ringing, doubled, folded)


def _rings(n: Note, at: int, target: Sequence[Span], starts: list[int], bass: bool) -> bool:
    later = target[bisect_right(starts, at):bisect_left(starts, n.end)]
    return any(n.pitch % 12 not in (*s.chord.tones, *([s.chord.lowest] if bass else [])) for s in later)


Keyed = tuple[list[int], list[int], list[int], list[int]]


def _keys(notes: Sequence[Note]) -> dict[tuple[int, int], Keyed]:
    """Each channel and key's notes in start order: their starts, indexes and ends, and the latest end so far."""
    found: dict[tuple[int, int], Keyed] = {}
    for i, n in enumerate(notes):
        starts, indexes, ends, latest = found.setdefault((n.channel, n.pitch), ([], [], [], []))
        starts.append(n.tick)
        indexes.append(i)
        ends.append(n.end)
        latest.append(max(n.end, latest[-1]) if latest else n.end)
    return found


def _sounding(keyed: Keyed | None, tick: int) -> int | None:
    """The index of the latest-started note of a key still sounding at ``tick``."""
    if keyed is None:
        return None
    starts, indexes, ends, latest = keyed
    j = bisect_right(starts, tick) - 1
    while j >= 0 and latest[j] > tick:
        if ends[j] > tick:
            return indexes[j]
        j -= 1
    return None
