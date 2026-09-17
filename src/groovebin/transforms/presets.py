"""Logic's Transform window presets, and a few of ours, by name: what a preset's value means, the
operations it expands to (`operations`) and `run` to apply one. Half and double speed, and swing,
take the whole part; the rest take a selection."""

from __future__ import annotations

import random
from dataclasses import dataclass

from ..song import Part
from ..timing import MeterMap
from .edits import Mask, PartWording, grid_ticks, masked, note_lengths, stretch, swing
from .select import Operation, apply_all, humanize, velocity_band
from .select_parse import number, tick_value, whole_number


@dataclass(frozen=True)
class Preset:
    name: str
    takes: str                   # none | int | int? | float | ticks | lo..hi | percent | swing | humanize
    default: int | float | tuple[int | float, ...] | None   # the value when none is given; None with a value kind means required
    about: str


PRESETS = (
    Preset("humanize", "humanize", (10, 8, 5), "each note's position, velocity and length moved at random"),
    Preset("fixed-velocity", "int", None, "every selected note at one velocity"),
    Preset("velocity-limit", "lo..hi", (20, 110), "velocities held inside LO..HI"),
    Preset("random-velocity", "int", 20, "each velocity moved by up to ±N"),
    Preset("crescendo", "lo..hi", (40, 120), "velocities ramped from LO at the first selected note to HI at the last"),
    Preset("reverse-position", "none", None, "the selected notes' positions mirrored, first for last"),
    Preset("reverse-pitch", "int?", None, "pitches mirrored around a pivot note; without one, around the selection's lowest and highest"),
    Preset("exp-velocity", "float", 1.5, "velocities through a power curve; above 1 softens the middle, below 1 lifts it"),
    Preset("fixed-length", "ticks", None, "every selected note one length, in ticks or a note value"),
    Preset("max-length", "ticks", None, "notes longer than the length cut to it"),
    Preset("min-length", "ticks", None, "notes shorter than the length stretched to it"),
    Preset("half-speed", "none", None, "every position and length doubled — the whole track, events too"),
    Preset("double-speed", "none", None, "every position and length halved — the whole track, events too"),
    Preset("legato", "percent", 100.0, "each note lasts PERCENT of the way to the next note's start (100 touches it)"),
    Preset("staccato", "percent", 50.0, "each note's length times PERCENT"),
    Preset("swing", "swing", (0.58, 16), "notes on the grid, every second line late: PERCENT[:1/N] (50% is straight, 1/16 the default grid)"),
)
BY_NAME = {p.name: p for p in PRESETS}
WHOLE_PART = ("half-speed", "double-speed", "swing")
HUMANIZE_KEYS = ("pos", "vel", "len")


def _percent(text: str) -> float:
    value = number(text.strip().removesuffix("%"))
    if value < 0:
        raise ValueError(f"{text.strip()!r} is not a percentage of 0 or more")
    return value


def _humanize(text: str, ppq: int, default: tuple[int, int, int]) -> tuple[int, int, int]:
    got = dict(zip(HUMANIZE_KEYS, default, strict=True))
    for item in text.split(","):
        key, sep, value = item.partition("=")
        key = key.strip()
        if not sep or key not in HUMANIZE_KEYS:
            raise ValueError(f"humanize takes pos=TICKS,vel=N,len=TICKS, not {item.strip()!r}")
        got[key] = whole_number(value) if key == "vel" else tick_value(value, ppq)
    return got["pos"], got["vel"], got["len"]


def parse_value(preset: Preset, text: str | None, *, ppq: int) -> object:
    """The preset's value from the command line, or its default; one that needs a value and gets none is refused."""
    if preset.takes == "none":
        if text is not None:
            raise ValueError(f"{preset.name} takes no value")
        return None
    if text is None:
        if preset.default is None and preset.takes != "int?":
            raise ValueError(f"{preset.name} needs a value: {preset.name}=VALUE")
        return preset.default
    if preset.takes in ("int", "int?"):
        return whole_number(text)
    if preset.takes == "float":
        return number(text)
    if preset.takes == "ticks":
        return tick_value(text, ppq)
    if preset.takes == "lo..hi":
        lo, dots, hi = text.partition("..")
        if not dots:
            raise ValueError(f"{preset.name} takes LO..HI")
        return velocity_band((whole_number(lo), whole_number(hi)))
    if preset.takes == "percent":
        return _percent(text)
    if preset.takes == "swing":
        amount, _, grid = text.partition(":")
        value = _percent(amount) / 100
        den = whole_number(grid.strip().removeprefix("1/")) if grid else preset.default[1]
        grid_ticks(den, ppq)
        return value, den
    return _humanize(text, ppq, preset.default)


def operations(name: str, value: object = None) -> list[Operation]:
    """The operations a preset expands to; one that is not built from operations (`WHOLE_PART`, legato,
    staccato) is refused."""
    if name == "humanize":
        if not (isinstance(value, (tuple, list)) and len(value) == 3):
            raise ValueError(f"humanize takes (position, velocity, length) ticks, not {value!r}")
        pos, vel, length = value
        return [Operation(f, "random", v) for f, v in (("tick", pos), ("velocity", vel), ("length", length)) if v]
    if name == "fixed-velocity":
        return [Operation("velocity", "set", value)]
    if name == "velocity-limit":
        velocity_band(value)
        if value[1] < value[0]:
            raise ValueError(f"a velocity band of {value[0]}..{value[1]} runs backwards")
        return [Operation("velocity", "min", value[0]), Operation("velocity", "max", value[1])]
    if name == "random-velocity":
        return [Operation("velocity", "random", value)]
    if name == "crescendo":
        return [Operation("velocity", "crescendo", velocity_band(value))]
    if name == "reverse-position":
        return [Operation("tick", "reverse")]
    if name == "reverse-pitch":
        if value is not None and not 0 <= value <= 127:
            raise ValueError(f"a reverse-pitch pivot of {value} is not a note number 0-127")
        return [Operation("pitch", "reverse")] if value is None else [Operation("pitch", "flip", value)]
    if name == "exp-velocity":
        return [Operation("velocity", "exp", value)]
    if name in ("fixed-length", "max-length", "min-length"):
        return [Operation("length", {"fixed-length": "set", "max-length": "max", "min-length": "min"}[name], value)]
    if name in BY_NAME:
        raise ValueError(f"{name} is not built from operations")
    raise ValueError(f"no preset {name!r}: {', '.join(BY_NAME)}")


def run(part: Part, mask: Mask | None, name: str, value: object = None, *, seed: int | random.Random = 0,
        meters: MeterMap | None = None, start: int = 0) -> Part:
    """Preset ``name`` on the selected notes (every note when ``mask`` is None); a `WHOLE_PART` preset
    takes the whole part and refuses a mask; swing needs ``meters`` and the part's ``start`` on them."""
    if name not in BY_NAME:
        raise ValueError(f"no preset {name!r}: {', '.join(BY_NAME)}")
    if name in WHOLE_PART and mask is not None:
        raise PartWording(f"{name} takes the whole part; it has no selection")
    if name == "half-speed":
        return stretch(part, 2.0)
    if name == "double-speed":
        return stretch(part, 0.5)
    if name == "swing":
        if meters is None:
            raise ValueError("swing needs a meter map")
        amount, den = value if value is not None else BY_NAME[name].default
        return swing(part, grid_ticks(den, part.ppq), amount, meters, start=start)
    if name == "legato":
        return note_lengths(part, mask, legato=(100.0 if value is None else value) / 100)
    if name == "staccato":
        return note_lengths(part, mask, percent=50.0 if value is None else value)
    if name == "humanize":
        pos, vel, length = value if value is not None else BY_NAME[name].default
        return humanize(part, mask, position=pos, velocity=vel, length=length, seed=seed)
    chosen = frozenset(masked(part, mask))
    return apply_all(part, chosen, operations(name, BY_NAME[name].default if value is None else value), seed=seed,
                     meters=meters, start=start)
