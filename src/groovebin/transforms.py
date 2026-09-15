"""Pure edits of a Part: each returns a new Part in canonical order and leaves its input alone.

A retiming edit refuses to move an event from the part's start or later to before it; an event
already before the start may move anywhere.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import replace

from .events import Event, Note
from .song import Part
from .timing import MeterMap

POLYTOUCH = 0xA0
GRIDS = (1, 2, 4, 8, 16, 32, 64)


def _retimed(items: list[Note | Event], when: Callable[[int], int]) -> list[Note | Event]:
    ticks = [when(i.tick) for i in items]
    early = [new for i, new in zip(items, ticks, strict=True) if new < 0 <= i.tick]
    if early:
        raise ValueError(f"an event would land {-min(early)} tick(s) before the part's start")
    return [replace(i, tick=new) for i, new in zip(items, ticks, strict=True)]


def transpose(part: Part, semitones: int) -> Part:
    """Every note, and every polyphonic aftertouch key, ``semitones`` higher."""
    notes = []
    for n in part.notes:
        if not 0 <= n.pitch + semitones <= 127:
            raise ValueError(f"note {n.pitch} moved {semitones:+d} is {n.pitch + semitones}, outside 0-127")
        notes.append(replace(n, pitch=n.pitch + semitones))
    events = []
    for e in part.events:
        if e.data[0] & 0xF0 == POLYTOUCH:
            key = e.pitch + semitones
            if not 0 <= key <= 127:
                raise ValueError(f"aftertouch key {e.pitch} moved {semitones:+d} is {key}, outside 0-127")
            e = replace(e, data=bytes([e.data[0], key, e.data[2]]))
        events.append(e)
    return replace(part, notes=tuple(notes), events=tuple(events))


def scale_velocity(part: Part, factor: float = 1.0, offset: int = 0) -> Part:
    """Each note's velocity times ``factor`` plus ``offset``, rounded half to even, held to 1-127."""
    if not math.isfinite(factor) or factor < 0:
        raise ValueError(f"a velocity scale of {factor:g} is not a finite number of 0 or more")
    notes = [replace(n, velocity=max(1, min(127, round(n.velocity * factor + offset)))) for n in part.notes]
    return replace(part, notes=tuple(notes))


def shift(part: Part, ticks: int) -> Part:
    """Every note and event ``ticks`` later (earlier when negative), the end with them."""
    notes = _retimed(list(part.notes), lambda t: t + ticks)
    events = _retimed(list(part.events), lambda t: t + ticks)
    end = None if part.end is None else part.end + ticks
    return replace(part, notes=tuple(notes), events=tuple(events), end=end)


def delete(part: Part, pitch: int | None = None) -> tuple[Part, int]:
    """The Part without its notes, or only those of ``pitch``, and how many went."""
    kept = tuple(n for n in part.notes if pitch is not None and n.pitch != pitch)
    return replace(part, notes=kept), len(part.notes) - len(kept)


def grid_ticks(denominator: int, ppq: int) -> int:
    """A note value's ticks at ``ppq``: 4 is a quarter note, 16 a sixteenth."""
    if denominator not in GRIDS:
        raise ValueError(f"1/{denominator} is not a grid of 1/1 to 1/64")
    if ppq * 4 % denominator:
        raise ValueError(f"1/{denominator} at PPQ {ppq} is not a whole number of ticks")
    return ppq * 4 // denominator


def _snap(at: int, grid: int, meters: MeterMap) -> int:
    """The grid line nearest ``at``, the later on a tie, counted from the bar line at or before it;
    the next bar line is always one of the choices."""
    bar = meters.bar_of(at)
    first, following = meters.bar_line(bar), meters.bar_line(bar + 1)
    lo = first + (at - first) // grid * grid
    hi = min(lo + grid, following)
    return hi if at - lo >= hi - at else lo


def quantize(part: Part, grid: int, meters: MeterMap, *, start: int = 0) -> Part:
    """Each note's start to the nearest ``grid`` line of its bar, lengths kept. ``start`` is where
    the part begins on the meter map's timeline."""
    if grid <= 0:
        raise ValueError("a quantize grid is at least one tick")
    if meters.ppq != part.ppq:
        raise ValueError(f"the meter map is at PPQ {meters.ppq} but the part is at PPQ {part.ppq}")
    notes = _retimed(list(part.notes), lambda t: _snap(start + t, grid, meters) - start)
    return replace(part, notes=tuple(notes))


def merge(dst: Part, src: Part, offset: int) -> Part:
    """``src`` moved by ``offset`` among ``dst``; where the canonical order ties, ``dst`` comes first."""
    if src.ppq != dst.ppq:
        raise ValueError(f"a part at PPQ {src.ppq} cannot merge into one at PPQ {dst.ppq}")
    notes = list(dst.notes) + _retimed(list(src.notes), lambda t: t + offset)
    events = list(dst.events) + _retimed(list(src.events), lambda t: t + offset)
    ends = [e for e in (dst.end, None if src.end is None else src.end + offset) if e is not None]
    return replace(dst, notes=tuple(notes), events=tuple(events), end=max(ends) if ends else None)
