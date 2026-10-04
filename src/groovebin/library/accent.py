"""How hard a drum part strikes where: each voice's velocity at each sixteenth of its bar over the voice's own mean,
and how much harder the hands play on the beat than off it."""

from __future__ import annotations

import json
import statistics
from collections import defaultdict
from collections.abc import Iterable

from ..events import Note
from ..timing import MeterMap
from .groove import HANDS, OFFBEAT, VOICES, bar_steps, compound, voices

Placed = tuple[int, tuple[int, int], int, int, float]


def _beat(sig: tuple[int, int]) -> int:
    """A beat in sixteenths: the dotted quarter of a compound meter, else the meter's own note value."""
    return 6 if compound(sig) else max(16 // sig[1], 1)


def placed(notes: Iterable[Note], meters: MeterMap, bars: int, map_name: str) -> list[Placed]:
    """(voice, meter, step, velocity, phase) for each voiced note in the first ``bars`` bars: the sixteenth
    `groove.rhythm` puts it on, and how far through its beat it falls, 0 to 1."""
    table, ppq, out = voices(map_name), meters.ppq, []
    for n in notes:
        voice = table.get(n.pitch)
        if voice is None or n.tick < 0:
            continue
        bar = meters.bar_of(n.tick)
        sig = meters.meter_at(meters.bar_line(bar))
        if bar > bars or not bar_steps(sig):
            continue
        into = n.tick - meters.bar_line(bar)
        step = (8 * into + ppq) // (2 * ppq)
        beat = _beat(sig) * ppq / 4
        phase = into % beat / beat
        if step >= bar_steps(sig):
            bar, step = bar + 1, 0
            sig = meters.meter_at(meters.bar_line(bar))
        if bar <= bars and bar_steps(sig):
            out.append((voice, sig, step, n.velocity, phase))
    return out


def profile(found: list[Placed]) -> dict[str, dict[str, list[float | None]]]:
    """Per voice and bar length in sixteenths, each step's mean velocity over the voice's mean, to two decimals;
    None where the voice never strikes."""
    level: dict[int, list[int]] = defaultdict(list)
    cells: dict[tuple[int, int, int], list[int]] = defaultdict(list)
    for voice, sig, step, velocity, _phase in found:
        level[voice].append(velocity)
        cells[(voice, bar_steps(sig), step)].append(velocity)
    out: dict[str, dict[str, list[float | None]]] = {}
    for (voice, steps, step), heard in sorted(cells.items()):
        row = out.setdefault(VOICES[voice], {}).setdefault(str(steps), [None] * steps)
        row[step] = round(statistics.fmean(heard) / statistics.fmean(level[voice]), 2)
    return out


def accent(found: list[Placed]) -> float | None:
    """The hands' mean velocity on the beats less their mean off them, to one decimal: off a beat is from 0.4 to 0.72
    of the way through it, where `groove.swing` reads the off-beat, so a shuffle's swung eighth counts; in a compound
    meter, the eighths between the dotted quarters. None when the hands strike only one of the two."""
    on, off = [], []
    for voice, sig, step, velocity, phase in found:
        if voice != HANDS:
            continue
        if step % _beat(sig) == 0:
            on.append(velocity)
        elif step % 2 == 0 if compound(sig) else OFFBEAT[0] <= phase <= OFFBEAT[1]:
            off.append(velocity)
    return round(statistics.fmean(on) - statistics.fmean(off), 1) if on and off else None


def columns(notes: Iterable[Note], meters: MeterMap, bars: int, map_name: str) -> dict[str, float | str | None]:
    """A library row's `accent` and its `accents` profile as JSON."""
    found = placed(notes, meters, bars, map_name)
    return {"accent": accent(found), "accents": json.dumps(profile(found)) if found else None}
