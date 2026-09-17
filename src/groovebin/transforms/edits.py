"""Pure edits of a Part: each returns a new Part in canonical order and leaves its input alone.

A retiming edit refuses to move an event from the part's start or later to before it; an event
already before the start may move anywhere.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import replace

from ..events import Event, Note
from ..song import Part
from ..timing import MeterMap

class PartWording(ValueError):
    """A refusal whose wording names the Part. A consumer that says "track" rewrites these alone:
    every other message may quote the user's own text back at them."""


POLYTOUCH = 0xA0
GRIDS = (1, 2, 4, 8, 16, 32, 64)
Mask = frozenset[int]


def rounded(value: float) -> int:
    """Half up: 0.5 rounds to 1, -0.5 to 0; a whole number is already one. A value that is not
    finite is refused, since no tick, length or velocity can be."""
    if isinstance(value, int):
        return value
    if not math.isfinite(value):
        raise ValueError(f"a result of {value:g} is not a finite number")
    return math.floor(value + 0.5)


def retimed(items: list[Note | Event], when: Callable[[int], int]) -> list[Note | Event]:
    """Each item at ``when(tick)``; one moved from the part's start or later to before it is refused."""
    ticks = [when(i.tick) for i in items]
    early = [new for i, new in zip(items, ticks, strict=True) if new < 0 <= i.tick]
    if early:
        raise PartWording(f"an event would land {-min(early)} tick(s) before the part's start")
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
    notes = retimed(list(part.notes), lambda t: t + ticks)
    events = retimed(list(part.events), lambda t: t + ticks)
    end = None if part.end is None else part.end + ticks
    return replace(part, notes=tuple(notes), events=tuple(events), end=end)


def delete(part: Part, pitch: int | None = None) -> tuple[Part, int]:
    """The Part without its notes, or only those of ``pitch``, and how many went; a deleted
    key's polyphonic aftertouch goes with its notes."""
    kept = tuple(n for n in part.notes if pitch is not None and n.pitch != pitch)
    events = tuple(e for e in part.events
                   if e.data[0] & 0xF0 != POLYTOUCH or (pitch is not None and e.pitch != pitch))
    return replace(part, notes=kept, events=events), len(part.notes) - len(kept)


def grid_ticks(denominator: int, ppq: int) -> int:
    """A note value's ticks at ``ppq``: 4 is a quarter note, 16 a sixteenth."""
    if denominator not in GRIDS:
        raise ValueError(f"1/{denominator} is not a grid of 1/1 to 1/64")
    if ppq * 4 % denominator:
        raise ValueError(f"1/{denominator} at PPQ {ppq} is not a whole number of ticks")
    return ppq * 4 // denominator


def snap(at: int, grid: int, meters: MeterMap) -> int:
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
        raise PartWording(f"the meter map is at PPQ {meters.ppq} but the part is at PPQ {part.ppq}")
    notes = retimed(list(part.notes), lambda t: snap(start + t, grid, meters) - start)
    return replace(part, notes=tuple(notes))


def merge(dst: Part, src: Part, offset: int) -> Part:
    """``src`` moved by ``offset`` among ``dst``; where the canonical order ties, ``dst`` comes first."""
    if src.ppq != dst.ppq:
        raise PartWording(f"a part at PPQ {src.ppq} cannot merge into one at PPQ {dst.ppq}")
    notes = list(dst.notes) + retimed(list(src.notes), lambda t: t + offset)
    events = list(dst.events) + retimed(list(src.events), lambda t: t + offset)
    ends = [e for e in (dst.end, None if src.end is None else src.end + offset) if e is not None]
    return replace(dst, notes=tuple(notes), events=tuple(events), end=max(ends) if ends else None)


def masked(part: Part, mask: Mask | None) -> set[int]:
    """The note indexes ``mask`` names, every note when it is None; an index the part lacks is refused."""
    if mask is None:
        return set(range(len(part.notes)))
    bad = [i for i in mask if not 0 <= i < len(part.notes)]
    if bad:
        raise PartWording(f"note index {min(bad)} is not in the part's {len(part.notes)} note(s)")
    return set(mask)


def stretch(part: Part, factor: float) -> Part:
    """Every tick and length times ``factor`` (2 halves the speed, 0.5 doubles it), events and the end with them."""
    if not math.isfinite(factor) or factor <= 0:
        raise ValueError(f"a stretch factor of {factor:g} is not a finite number above 0")

    def at(tick: int) -> int:
        return rounded(tick * factor)
    notes = [replace(n, tick=at(n.tick), length=max(1, at(n.end) - at(n.tick))) for n in part.notes]
    events = [replace(e, tick=at(e.tick)) for e in part.events]
    end = None if part.end is None else at(part.end)
    return replace(part, notes=tuple(notes), events=tuple(events), end=end)


def note_lengths(part: Part, mask: Mask | None = None, *, percent: float | None = None, fixed: int | None = None,
                 legato: float | None = None) -> Part:
    """Selected notes' lengths: ``percent`` of their own (staccato), ``fixed`` ticks, or ``legato`` times the
    distance to the next note's start (1 touches it, more overlaps; the last note keeps its length); at
    least one tick."""
    given = [k for k, v in (("percent", percent), ("fixed", fixed), ("legato", legato)) if v is not None]
    if len(given) != 1:
        raise ValueError("note_lengths takes exactly one of percent, fixed and legato")
    if percent is not None and (not math.isfinite(percent) or percent < 0):
        raise ValueError(f"a length of {percent:g}% is not a finite number of 0 or more")
    if fixed is not None and fixed < 1:
        raise ValueError(f"a fixed length of {fixed} tick(s) is not 1 or more")
    if legato is not None and (not math.isfinite(legato) or legato <= 0):
        raise ValueError(f"a legato of {legato:g} is not a finite number above 0")
    chosen = masked(part, mask)
    notes = list(part.notes)
    for i in sorted(chosen):
        n = notes[i]
        if fixed is not None:
            length = fixed
        elif percent is not None:
            length = rounded(n.length * percent / 100)
        else:
            following = next((m.tick for m in part.notes[i + 1:] if m.tick > n.tick), None)
            if following is None:
                continue
            length = rounded((following - n.tick) * legato)
        notes[i] = replace(n, length=max(1, length))
    return replace(part, notes=tuple(notes))


def velocity_curve(part: Part, mask: Mask | None = None, *, floor: int = 1, ceiling: int = 127,
                   gamma: float = 1.0) -> Part:
    """Velocities 1-127 mapped onto ``floor``..``ceiling`` through a power curve: gamma 1 is linear,
    above 1 pushes the middle down, below 1 lifts it."""
    if not 1 <= floor <= ceiling <= 127:
        raise ValueError(f"a velocity band of {floor}..{ceiling} is not inside 1..127 with the floor first")
    if not math.isfinite(gamma) or gamma <= 0:
        raise ValueError(f"a gamma of {gamma:g} is not a finite number above 0")
    chosen = masked(part, mask)
    notes = [replace(n, velocity=floor + rounded((ceiling - floor) * ((n.velocity - 1) / 126) ** gamma)) if i in chosen else n
             for i, n in enumerate(part.notes)]
    return replace(part, notes=tuple(notes))


def swing(part: Part, grid: int, amount: float, meters: MeterMap, *, start: int = 0) -> Part:
    """`quantize` to ``grid``, then every second grid line of each bar delayed by grid x (2·amount - 1):
    0.5 is straight, 0.6 puts the off-beat a fifth of a grid late (Logic's Q-Swing 60%), 2/3 is a
    triplet feel."""
    if not math.isfinite(amount) or not 0 <= amount <= 1:
        raise ValueError(f"a swing of {amount:g} is not 0 to 1 (0.5 is straight)")
    snapped = quantize(part, grid, meters, start=start)
    delay = rounded(grid * (2 * amount - 1))

    def late(tick: int) -> int:
        line = (start + tick - meters.bar_line(meters.bar_of(start + tick))) // grid
        return tick + delay if line % 2 else tick
    return replace(snapped, notes=tuple(retimed(list(snapped.notes), late)))
