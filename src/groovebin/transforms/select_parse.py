"""The command line's vocabulary for a transform, read into the `select` types: a condition
(``pitch=36-47,velocity<40``) into a Range per field, and an operation (``add:velocity=10``) into an
Operation. A value a Standard MIDI File cannot hold is refused here, where it is read."""

from __future__ import annotations

import math
import re

from .edits import grid_ticks
from .select import ALIASES, FIELDS, OPS, Operation, Range

CONDITION = re.compile(r"^(\w+)(!=|<=|>=|=|<|>)(.+)$")
NUMBER = re.compile(r"^-?\d+(\.\d+)?$")
MAX_VALUE = 0x0FFFFFFF                            # a Standard MIDI File's delta time is four VLQ bytes at most


def _inside(value: int, text: str) -> int:
    if abs(value) > MAX_VALUE:
        raise ValueError(f"{text!r} is past {MAX_VALUE}, the largest value a file can hold")
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
    """``240``, ``240t`` or a note value ``1/16`` as ticks at ``ppq``."""
    t = text.strip()
    if t.startswith("1/"):
        return grid_ticks(whole_number(t[2:]), ppq)
    try:
        return int(t.removesuffix("t"))
    except ValueError:
        raise ValueError(f"{t!r} is not a tick count or a note value like 1/16") from None


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


def parse_select(text: str, *, ppq: int) -> dict[str, Range]:
    """``pitch=36-47,velocity<40,position=9-12`` -> a Range per field. A position is in bars (the caller
    converts with `position_ticks`); a length is ticks or a note value."""
    out: dict[str, Range] = {}
    for item in text.split(","):
        m = CONDITION.match(item.strip())
        if not m:
            raise ValueError(f"bad condition {item.strip()!r}: FIELD=VALUE, FIELD=LO-HI, or FIELD with <, <=, >, >=, != a value")
        field, op, value = _field(m.group(1)), m.group(2), m.group(3)
        reading = (lambda v: ticks_of(v, ppq)) if field == "length" else number
        if op == "=" and "-" in value.strip().lstrip("-"):
            lo, _, hi = value.strip().partition("-")
            r = Range(reading(lo), reading(hi))
            if r.hi < r.lo:
                raise ValueError(f"a range of {value.strip()!r} runs backwards")
        else:
            r = _compared(op, reading(value))
        if field in out:
            raise ValueError(f"{m.group(1)} is given twice")
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
        lo, dots, hi = value.partition("..")
        if not dots:
            raise ValueError("crescendo takes LO..HI")
        return Operation(field, op, (unit(lo), unit(hi)))
    v = unit(value)
    if op == "random" and v < 0:
        raise ValueError("random takes a spread of 0 or more")
    if op == "quantize" and v < 1:
        raise ValueError("quantize takes a grid of 1 tick or more")
    return Operation(field, op, v)
