"""Terminal output for `groovebin tempo` and `groovebin key`."""

from __future__ import annotations

from ._views import clock
from .harmony import scale_name, signature_name
from .timing import KeyMap, MeterMap, TempoMap


def _bpm(usec: int) -> str:
    return f"{round(60_000_000 / usec, 3):g} bpm"


def tempo_listing(name: str, tempos: TempoMap, meters: MeterMap, ppq: int) -> list[str]:
    """Each tempo point with its bar and time, a ramp's points as one line."""
    if tempos.defaulted:
        return [f"{name}: no tempo events: 120 bpm throughout"]
    ramps = list(tempos.ramps(ppq))
    lines = [f"{name}: PPQ {ppq}, {len(tempos.points)} tempo point(s), {len(ramps)} ramp(s)"]
    i, ended = 0, False
    while i < len(tempos.points):
        tick, usec = tempos.points[i]
        at = f"  bar {meters.bar(tick):8.3f}  {clock(tempos.seconds(tick, ppq)):>9}"
        if ramps and tick == ramps[0].start:
            r = ramps.pop(0)
            lines.append(f"{at}  ramp {_bpm(r.from_usec)} -> {_bpm(r.to_usec)} to bar {meters.bar(r.end):.3f}, "
                         f"{r.points} point(s)")
            i, ended = i + r.points - 1, True
            continue
        if not ended:
            lines.append(f"{at}  {_bpm(usec)}")
        i, ended = i + 1, False
    return lines


def key_listing(name: str, keys: KeyMap, meters: MeterMap, major: int | None) -> list[str]:
    """Each key signature with its bar, then the scale the notes hold."""
    lines = [f"{name}: {len(keys.points)} key signature(s)" if keys.points else f"{name}: no key signatures"]
    lines += [f"  bar {meters.bar(t):8.3f}  {signature_name(s, m)}" for t, s, m in keys.points]
    lines.append(f"scale  {scale_name(major)}" if major is not None else "scale  - (too few pitch classes to estimate one)")
    return lines
