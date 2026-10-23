"""The command line's vocabulary for a transform, read into the `select` types: a condition
(``pitch=36-47,velocity<40``) into a Range per field, and an operation (``add:velocity=10``) into an
Operation. A value a Standard MIDI File cannot hold is refused here, where it is read."""

from __future__ import annotations

import math
import re

from ..events import MAX_VLQ
from .edits import grid_ticks, note_value
from .select import ALIASES, FIELDS, OPS, Operation, Range

CONDITION = re.compile(r"^(\w+)(!=|<=|>=|=|<|>)(.+)$")
NUMBER = re.compile(r"^-?\d+(\.\d+)?$")
TIME = re.compile(r"^(?:(\d{1,15}):([0-5]\d)(?:\.(\d+))?|(\d{1,15})(?:\.(\d+))?s)$", re.ASCII)


def _inside(value: int, text: str) -> int:
    if abs(value) > MAX_VLQ:
        raise ValueError(f"{text!r} is past {MAX_VLQ}, the largest value a file can hold")
    return value


def number(text: str) -> float:
    if not NUMBER.match(text.strip()):
        raise ValueError(f"{text.strip()!r} is not a number")
    value = float(text)
    if not math.isfinite(value):
        raise ValueError(f"{text.strip()!r} is not a finite number")
    return value


def whole_number(text: str) -> int:
    try:
        return int(text.strip())
    except ValueError:
        raise ValueError(f"{text.strip()!r} is not a whole number") from None


def ticks_of(text: str, ppq: int) -> int:
    """``240``, ``240t`` or a note value ``1/16``, ``1/16t`` or ``1/16.`` as ticks at ``ppq``."""
    t = text.strip()
    if t.startswith("1/"):
        denominator, triplet, dotted = note_value(t)
        return grid_ticks(denominator, ppq, triplet=triplet, dotted=dotted)
    try:
        return int(t.removesuffix("t"))
    except ValueError:
        raise ValueError(f"{t!r} is not a tick count or a note value like 1/16, 1/8t or 1/8.") from None


def tick_value(text: str, ppq: int) -> int:
    """`ticks_of` for a value that ends up in a file, so one past what a file can hold is refused
    here rather than when it is written. A `parse_select` bound is not one: it is only compared."""
    return _inside(ticks_of(text, ppq), text.strip())


def _field(name: str) -> str:
    field = ALIASES.get(name.strip(), name.strip())
    if field not in FIELDS:
        raise ValueError(f"no note field {name.strip()!r}: position, pitch, velocity, length or channel")
    return field


def _compared(op: str, value: float) -> Range:
    if op == "!=":
        return Range(value, value, outside=True)
    if op == "<":
        return Range(None, value, hi_open=True)
    if op == "<=":
        return Range(None, value)
    if op == ">":
        return Range(value, None, lo_open=True)
    if op == ">=":
        return Range(value, None)
    return Range(value, value)


def _milliseconds_of(text: str) -> int | None:
    """``1:05.5`` or ``65.5s`` as 65500 milliseconds; None for text not written as a time. A time finer than a
    millisecond is refused: note times are read to the millisecond (`TempoMap.milliseconds`)."""
    t = text.strip()
    m = TIME.match(t)
    if not m:
        return None
    minutes, secs, frac, whole, plain = m.groups()
    frac = ((frac if minutes is not None else plain) or "").rstrip("0")
    if len(frac) > 3:
        raise ValueError(f"{t!r} is finer than a millisecond, the most a time is read to")
    seconds = int(minutes) * 60 + int(secs) if minutes is not None else int(whole)
    return seconds * 1000 + int(frac.ljust(3, "0"))


def _bar(text: str, times: bool) -> float:
    try:
        return number(text)
    except ValueError:
        kinds = "a bar like 9.5 or a time like 1:05.5 or 65.5s" if times else "a bar like 9.5"
        raise ValueError(f"{text.strip()!r} is not {kinds}") from None


def _times(texts: tuple[str, ...], value: str, allowed: bool) -> list[int]:
    if not allowed:
        written = next(t for t in texts if TIME.match(t.strip()))
        raise ValueError(f"{written.strip()!r} is a time: give the position in bars")
    found = [_milliseconds_of(t) for t in texts]
    if None in found:
        raise ValueError(f"a position range is bars or times at both ends, not {value!r}")
    return found


def parse_select(text: str, *, ppq: int, times: bool = False) -> dict[str, Range]:
    """``pitch=36-47,velocity<40,position=9-12`` -> a Range per field. A position is in bars (the caller
    converts with `position_ticks`); a length is ticks or a note value. A position written as a time, ``1:05.5``
    or ``65.5s``, comes back under ``time`` in milliseconds when ``times`` is set (the caller converts with
    `time_ticks`), and is refused otherwise."""
    out: dict[str, Range] = {}
    named: set[str] = set()
    for item in text.split(","):
        m = CONDITION.match(item.strip())
        if not m:
            raise ValueError(f"bad condition {item.strip()!r}: FIELD=VALUE, FIELD=LO-HI, or FIELD with <, <=, >, >=, != a value")
        field, op, value = _field(m.group(1)), m.group(2), m.group(3).strip()
        if field in named:
            raise ValueError(f"{m.group(1)} is given twice")
        named.add(field)
        ranged = op == "=" and "-" in value.lstrip("-")
        if ranged and value.startswith("-"):
            raise ValueError(f"a range of {value!r} starts below 0")
        lo, _, hi = value.partition("-")
        texts = (lo, hi) if ranged else (value,)
        if ranged and not hi.strip():
            raise ValueError(f"a range of {value!r} needs both ends")
        if field == "tick" and any(TIME.match(t.strip()) for t in texts):
            field, bounds = "time", _times(texts, value, times)
        elif field == "tick":
            bounds = [_bar(t, times) for t in texts]
        else:
            reading = (lambda v: ticks_of(v, ppq)) if field == "length" else number
            bounds = [reading(t) for t in texts]
        if ranged:
            r = Range(*bounds)
            if r.hi < r.lo:
                raise ValueError(f"a range of {value!r} runs backwards")
        else:
            r = _compared(op, bounds[0])
        out[field] = r
    return out


def parse_operation(op: str, spec: str, *, ppq: int) -> Operation:
    """``op`` one of `OPS`, ``spec`` ``FIELD=VALUE`` (``FIELD`` alone for reverse): a value in the field's
    unit — ticks or a note value for position and length — ``LO..HI`` for crescendo, a factor for mul
    and exp, a spread of 0 or more for random."""
    if op not in OPS:
        raise ValueError(f"no operation {op!r}: {', '.join(OPS)}")
    name, sep, value = spec.partition("=")
    field, value = _field(name), value.strip()
    if op == "reverse":
        if sep:
            raise ValueError("reverse takes a field and no value")
        return Operation(field, op)
    if not sep or not value:
        raise ValueError(f"{op} takes FIELD=VALUE")
    if op in ("mul", "exp"):
        return Operation(field, op, number(value))
    unit = (lambda t: tick_value(t, ppq)) if field in ("tick", "length") else whole_number
    if op == "crescendo":
        lo, dots, hi = value.rpartition("..")
        if not dots:
            raise ValueError("crescendo takes LO..HI")
        return Operation(field, op, (unit(lo), unit(hi)))
    v = unit(value)
    if op == "random" and v < 0:
        raise ValueError("random takes a spread of 0 or more")
    if op == "quantize" and v < 1:
        raise ValueError("quantize takes a grid of 1 tick or more")
    return Operation(field, op, v)
