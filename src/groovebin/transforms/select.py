"""Selecting notes by their fields and applying operations to the selection — Logic's Transform
window without the DAW. A Range per field picks notes into a Mask (indexes into ``part.notes``);
every operation reads the note as it was and writes its own field, each written field held to its range
(pitch 0-127, velocity 1-127, channel 1-16, length from 1); a field no operation names is left alone and
a note moved before the part's start is refused. Positions are ticks here; `position_ticks` turns a Range in bars into one."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, replace

from ..song import Part
from ..timing import MeterMap
from .edits import Mask, PartWording, masked, rounded, snap

FIELDS = ("tick", "pitch", "velocity", "length", "channel")
ALIASES = {"position": "tick"}
OPS = ("set", "add", "mul", "min", "max", "random", "flip", "quantize", "crescendo", "exp", "reverse")
BOUNDS = {"tick": (None, None), "pitch": (0, 127), "velocity": (1, 127), "length": (1, None), "channel": (1, 16)}
SPOKEN = {"tick": "position"}


@dataclass(frozen=True)
class Range:
    """``lo``..``hi``, each side inclusive unless open; ``outside`` selects what the range does not."""
    lo: float | None = None
    hi: float | None = None
    lo_open: bool = False
    hi_open: bool = False
    outside: bool = False

    def holds(self, value: float) -> bool:
        above = self.lo is None or value > self.lo or (value == self.lo and not self.lo_open)
        below = self.hi is None or value < self.hi or (value == self.hi and not self.hi_open)
        return (above and below) != self.outside


@dataclass(frozen=True)
class Operation:
    field: str
    op: str
    value: object = None


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def velocity_band(value: tuple[int, int]) -> tuple[int, int]:
    """A ``LO..HI`` velocity pair, each inside 1-127; HI below LO is a ramp downwards, not an error."""
    if not (isinstance(value, (tuple, list)) and len(value) == 2 and all(_is_number(v) for v in value)):
        raise ValueError(f"a velocity band is a LO..HI pair, not {value!r}")
    if not all(1 <= v <= 127 for v in value):
        raise ValueError(f"a velocity band of {value[0]}..{value[1]} is not inside 1..127")
    return value


def position_ticks(rng: Range, meters: MeterMap, *, start: int = 0) -> Range:
    """A position Range in bars as ticks from ``start``: a whole-number bound means the whole bar
    (9-12 runs from bar 9's line up to bar 13's), a fractional one the exact position."""
    def whole(bar: float) -> bool:
        return float(bar).is_integer()

    for bound in (rng.lo, rng.hi):
        if bound is not None and bound < 1:
            raise PartWording(f"bar {bound:g} is before bar 1, where a part starts")
    lo, lo_open = rng.lo, rng.lo_open
    if lo is not None:
        lo = (meters.bar_line(int(lo) + 1) if lo_open else meters.bar_line(int(lo))) - start if whole(lo) else meters.tick(lo) - start
        lo_open = False if whole(rng.lo) else lo_open
    hi, hi_open = rng.hi, rng.hi_open
    if hi is not None:
        hi = (meters.bar_line(int(hi)) if hi_open else meters.bar_line(int(hi) + 1)) - start if whole(hi) else meters.tick(hi) - start
        hi_open = True if whole(rng.hi) else hi_open
    return Range(lo, hi, lo_open, hi_open, rng.outside)


def select(part: Part, *, tick: Range | float | None = None, pitch: Range | float | None = None,
           velocity: Range | float | None = None, length: Range | float | None = None,
           channel: Range | float | None = None) -> Mask:
    """Indexes of the notes every given condition holds for; a condition is a Range or one value."""
    given = {"tick": tick, "pitch": pitch, "velocity": velocity, "length": length, "channel": channel}
    conditions = {f: (v if isinstance(v, Range) else Range(v, v)) for f, v in given.items() if v is not None}
    return frozenset(i for i, n in enumerate(part.notes) if all(r.holds(getattr(n, f)) for f, r in conditions.items()))


def _held(field: str, value: float) -> int:
    lo, hi = BOUNDS[field]
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"an operation took {SPOKEN.get(field, field)} to {value:g}, which is not a finite number")
    x = rounded(value)
    if lo is not None:
        x = max(lo, x)
    if hi is not None:
        x = min(hi, x)
    return x


def _checked(o: Operation) -> None:
    """The refusals no note is needed for: which field an operation takes, and its value's shape and range."""
    if o.op not in OPS or o.field not in FIELDS:
        raise ValueError(f"no operation {o.op} on {o.field}")
    if o.op == "reverse":
        if o.value is not None:
            raise ValueError("reverse takes no value")
    elif o.op == "crescendo":
        if not (isinstance(o.value, (tuple, list)) and len(o.value) == 2 and all(_is_number(v) for v in o.value)):
            raise ValueError(f"crescendo takes a LO..HI pair, not {o.value!r}")
    elif not _is_number(o.value):
        raise ValueError(f"{o.op} {o.field} takes a number, not {o.value!r}")
    if o.op in ("crescendo", "reverse") and o.field == "channel":
        raise ValueError(f"{o.op} {'ramps' if o.op == 'crescendo' else 'mirrors'} "
                         "position, pitch, velocity or length, not channel")
    if o.op == "exp":
        if o.field != "velocity":
            raise ValueError("exp is a velocity curve; use mul on another field")
        if o.value <= 0:
            raise ValueError(f"an exp curve of {o.value:g} is not a number above 0")
    if o.op == "quantize" and o.value < 1:
        raise ValueError("quantize takes a grid of 1 tick or more")
    if o.op == "crescendo" and o.field == "velocity":
        velocity_band(o.value)


def _operated(o: Operation, x: float, tick: int, span: dict[str, tuple[int, int]], rng: random.Random,
              meters: MeterMap | None = None, start: int = 0) -> float:
    v = o.value
    if o.op == "set":
        return v
    if o.op == "add":
        return x + v
    if o.op == "mul":
        return x * v
    if o.op == "min":
        return max(x, v)
    if o.op == "max":
        return min(x, v)
    if o.op == "random":
        return x + rng.randint(-int(v), int(v))
    if o.op == "flip":
        return 2 * v - x
    if o.op == "quantize":
        if o.field == "tick" and meters is not None:
            return snap(start + rounded(x), int(v), meters) - start
        return rounded(x / v) * v
    if o.op == "crescendo":
        lo, hi = v
        first, last = span["tick"]
        return lo if last == first else lo + (hi - lo) * (tick - first) / (last - first)
    if o.op == "exp":
        return 1 + 126 * ((_held("velocity", x) - 1) / 126) ** v
    lo, hi = span[o.field]
    return lo + hi - x


def apply_all(part: Part, mask: Mask | None, operations: list[Operation], *, seed: int | random.Random = 0,
              meters: MeterMap | None = None, start: int = 0) -> Part:
    """Every operation on every selected note in one pass, each reading the note as it was (a second
    operation on one field reads the first's result); with no note selected the part comes back as
    it is. Only the fields the operations name are written. ``seed`` fixes the random draws; a random
    move of position stops at the part's start, any other move before it is refused. With ``meters``,
    which must be at the part's PPQ, a position quantize snaps to the grid lines of each bar rather
    than to multiples counted from tick 0."""
    for o in operations:
        _checked(o)
    if meters is not None and meters.ppq != part.ppq:
        raise PartWording(f"the meter map is at PPQ {meters.ppq} but the part is at PPQ {part.ppq}")
    chosen = sorted(masked(part, mask))
    if not chosen or not operations:
        return part
    rng = seed if isinstance(seed, random.Random) else random.Random(seed)
    picked = [part.notes[i] for i in chosen]
    span = {f: (min(getattr(n, f) for n in picked), max(getattr(n, f) for n in picked)) for f in FIELDS}
    written = {o.field for o in operations}
    notes, early = list(part.notes), []
    for i in chosen:
        n = notes[i]
        values: dict[str, float] = {f: getattr(n, f) for f in FIELDS}
        steady = float(n.tick)                       # the tick the operations reach without the random draws
        for o in operations:
            if o.field == "tick" and o.op != "random":
                steady = _operated(o, steady, n.tick, span, rng, meters, start)
            values[o.field] = _operated(o, values[o.field], n.tick, span, rng, meters, start)
        settled = _held("tick", steady)              # where the operations land without the random draws
        if settled >= 0 > values["tick"]:
            values["tick"] = 0                       # a random move stops at the part's start
        notes[i] = replace(n, **{f: _held(f, values[f]) for f in written})
        if settled < 0 <= n.tick:
            early.append(settled)
    if early:
        raise PartWording(f"a note would land {-min(early)} tick(s) before the part's start")
    return replace(part, notes=tuple(notes))


def apply(part: Part, mask: Mask | None, *, field: str, op: str, value: object = None, seed: int | random.Random = 0,
          meters: MeterMap | None = None, start: int = 0) -> Part:
    """One operation on the selected notes; see `apply_all`."""
    return apply_all(part, mask, [Operation(field, op, value)], seed=seed, meters=meters, start=start)


def humanize(part: Part, mask: Mask | None = None, *, position: int = 0, velocity: int = 0, length: int = 0,
             seed: int | random.Random = 0) -> Part:
    """Each selected note moved by up to ±``position`` ticks, ±``velocity`` and ±``length`` ticks, uniformly."""
    for name, amount in (("position", position), ("velocity", velocity), ("length", length)):
        if amount < 0:
            raise ValueError(f"a humanize {name} of {amount} is not 0 or more")
    ops = [Operation(f, "random", v) for f, v in (("tick", position), ("velocity", velocity), ("length", length)) if v]
    return apply_all(part, frozenset(masked(part, mask)), ops, seed=seed)
