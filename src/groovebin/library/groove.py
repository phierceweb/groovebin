"""What a drum part plays, read through its map: which sixteenths the kick, the snare and the hands strike in
each bar, and the numbers a library search filters on. The snare voice holds the sidestick; the hands are the
hi-hat, less its pedal, and the ride."""

from __future__ import annotations

import json
import math
import statistics
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from functools import cache
from types import MappingProxyType
from typing import NamedTuple

from ..events import Note
from ..maps import drum_map
from ..midi import read
from ..song import merged, meter_map
from ..timing import MeterMap

VOICES = ("kick", "snare", "hands")
WEIGHTS = (1.0, 1.0, 0.5)
FEATURES = ("density", "syncopation", "subdivision", "swing8", "swing16", "lag")
SUBDIVISIONS = ("quarters", "8ths", "16ths", "triplets")
HANDS = VOICES.index("hands")
ON_BEAT = 0.1
OFFBEAT = (0.4, 0.72)
SWING_SAMPLES = 4
LAG_WINDOW = 0.125
LAG_PPQ = 960
THIRDS = (0, 1 / 3, 2 / 3, 1)
QUARTERS = (0, 0.25, 0.5, 0.75, 1)


class Bar(NamedTuple):
    steps: int
    kick: int
    snare: int
    hands: int


@cache
def voices(map_name: str) -> Mapping[int, int]:
    """Each note ``map_name`` gives a voice, as its index in `VOICES`."""
    m = drum_map(map_name)
    table = dict.fromkeys(m.family("kick"), 0)
    table |= dict.fromkeys((*m.family("snare"), *m.family("sidestick")), 1)
    table |= dict.fromkeys((n for n in (*m.family("hihat"), *m.family("ride"))
                            if not (m.term(n) or "").startswith("hihat pedal")), 2)
    return MappingProxyType(table)


def _steps(sig: tuple[int, int]) -> int:
    num, den = sig
    return 16 * num // den if 16 * num % den == 0 else 0


def _compound(sig: tuple[int, int]) -> bool:
    return sig[1] == 8 and sig[0] % 3 == 0 and sig[0] > 3


def rhythm(notes: Iterable[Note], meters: MeterMap, bars: int, map_name: str) -> tuple[Bar, ...]:
    """The first ``bars`` bars as a sixteenth grid per voice. A note rounding onto a bar line starts the next
    bar; one past the last bar is left out, and a bar whose meter holds no whole number of sixteenths is empty."""
    table, ppq = voices(map_name), meters.ppq
    steps = [_steps(meters.meter_at(meters.bar_line(b))) for b in range(1, bars + 1)]
    grids = [[0, 0, 0] for _ in range(bars)]
    for n in notes:
        voice = table.get(n.pitch)
        if voice is None or n.tick < 0:
            continue
        bar = meters.bar_of(n.tick)
        if bar > bars or not steps[bar - 1]:
            continue
        step = (8 * (n.tick - meters.bar_line(bar)) + ppq) // (2 * ppq)
        if step >= steps[bar - 1]:
            bar, step = bar + 1, 0
        if bar <= bars and steps[bar - 1]:
            grids[bar - 1][voice] |= 1 << step
    return tuple(Bar(s, *g) for s, g in zip(steps, grids, strict=True))


def file_rhythm(data: bytes, map_name: str) -> tuple[Bar, ...]:
    """The rhythm of a whole file, its tracks merged, in bars of its own meters (4/4 when it has none)."""
    song = read(data)
    part, meters = merged(song), meter_map(song)
    bars = meters.bar_of(max(n.tick for n in part.notes)) if part.notes else 0
    return rhythm(part.notes, meters, bars, map_name)


def to_json(bars: Sequence[Bar]) -> str:
    return json.dumps([list(b) for b in bars])


def from_json(text: str | None) -> tuple[Bar, ...]:
    return tuple(Bar(*b) for b in json.loads(text or "[]"))


def _levels(sig: tuple[int, int]) -> list[int]:
    """Each sixteenth's metrical level in a bar of ``sig``: 0 the downbeat, higher weaker."""
    steps = _steps(sig)
    beat = 6 if _compound(sig) else max(16 // sig[1], 1)
    periods = [steps]
    if steps // beat > 2 and steps // beat % 2 == 0:
        periods.append(steps // 2)
    periods.append(beat)
    unit = 2 if beat == 6 else beat
    if beat == 6:
        periods.append(unit)
    while unit > 1:
        unit //= 2
        periods.append(unit)
    return [next(level for level, p in enumerate(periods) if s % p == 0) for s in range(steps)]


def syncopation(onsets: int, sig: tuple[int, int]) -> int:
    """Longuet-Higgins and Lee's syncopation of one bar's onsets, the bar heard as a loop: each onset followed
    by silence over a stronger position adds how much stronger that position is."""
    levels = _levels(sig)
    steps = len(levels)
    struck = [s for s in range(steps) if onsets >> s & 1]
    total = 0
    for i, s in enumerate(struck):
        after = struck[i + 1] if i + 1 < len(struck) else struck[0] + steps
        strongest = min((levels[t % steps] for t in range(s + 1, after)), default=levels[s])
        total += max(levels[s] - strongest, 0)
    return total


def _hands(notes: Iterable[Note], map_name: str) -> list[Note]:
    table = voices(map_name)
    return [n for n in notes if table.get(n.pitch) == HANDS]


def _gap(p: float, grid: tuple[float, ...]) -> float:
    return min(abs(p - g) for g in grid)


def subdivision(notes: Iterable[Note], meters: MeterMap, map_name: str) -> str | None:
    """The grid the hands play against the quarter note — ``quarters``, ``8ths``, ``16ths`` or ``triplets`` —
    or None with no hand strokes."""
    ppq = meters.ppq
    places = [(n.tick - meters.bar_line(meters.bar_of(n.tick))) % ppq / ppq for n in _hands(notes, map_name)]
    if not places:
        return None
    off = [p for p in places if ON_BEAT <= p <= 1 - ON_BEAT]
    if len(off) < ON_BEAT * len(places):
        return "quarters"
    straight = [p for p in off if _gap(p, QUARTERS) <= _gap(p, THIRDS)]
    if 2 * len(straight) <= len(off):
        return "triplets"
    sixteenths = [p for p in straight if abs(p - 0.5) > 0.125]
    return "16ths" if 4 * len(sixteenths) >= len(off) else "8ths"


def swing(notes: Iterable[Note], meters: MeterMap, map_name: str, *, sixteenths: bool = False) -> float | None:
    """Where the hands' off-beat eighth sits in its beat — or with ``sixteenths``, the off-beat sixteenth in its
    eighth — as a share of it: 0.5 straight, 0.667 a triplet feel. Read over each beat (or eighth) holding a stroke
    on its line and exactly one between 0.4 and 0.72 of it; None with fewer than four, or in a meter whose beat
    is not a quarter note."""
    if any(den != 4 for _tick, _num, den in meters.changes):
        return None
    unit = meters.ppq / (2 if sixteenths else 1)
    spans: dict[int, set[float]] = defaultdict(set)
    for n in _hands(notes, map_name):
        span = math.floor((n.tick + ON_BEAT * unit) / unit)
        spans[span].add((n.tick - span * unit) / unit)
    samples = []
    for places in spans.values():
        inside = [p for p in places if OFFBEAT[0] <= p <= OFFBEAT[1]]
        if len(inside) == 1 and any(abs(p) < ON_BEAT for p in places):
            samples.append(inside[0])
    return round(statistics.fmean(samples), 3) if len(samples) >= SWING_SAMPLES else None


def beat_ticks(sig: tuple[int, int], ppq: int) -> float:
    """A beat's length: a dotted quarter in 6/8, 9/8 and 12/8, else the meter's denominator."""
    return ppq * 4 / sig[1] * (3 if _compound(sig) else 1)


def lag(notes: Iterable[Note], meters: MeterMap, map_name: str) -> float | None:
    """How far behind its beat line the snare strikes on average, in ticks at 960 PPQ, over strokes within an
    eighth of a beat of one; None with no such stroke."""
    table, offsets = voices(map_name), []
    for n in notes:
        if table.get(n.pitch) != VOICES.index("snare"):
            continue
        beat = beat_ticks(meters.meter_at(n.tick), meters.ppq)
        into = n.tick - meters.bar_line(meters.bar_of(n.tick))
        off = into - round(into / beat) * beat
        if abs(off) <= LAG_WINDOW * beat:
            offsets.append(off * LAG_PPQ / meters.ppq)
    return round(statistics.fmean(offsets), 1) if offsets else None


def features(notes: Iterable[Note], meters: MeterMap, bars: int, map_name: str) -> dict[str, float | str | None]:
    """`FEATURES` of a part: onsets per bar over the three voices, syncopation per bar of kick and snare
    together, and the subdivision, eighth and sixteenth swing and lag above. All None for a part with no bars."""
    notes = list(notes)
    return _features(notes, meters, rhythm(notes, meters, bars, map_name), map_name)


def columns(notes: Iterable[Note], meters: MeterMap, bars: int, map_name: str) -> dict[str, float | str | None]:
    """A library row's `rhythm` as JSON, None with no bars, and its `FEATURES`."""
    notes = list(notes)
    grid = rhythm(notes, meters, bars, map_name)
    return {"rhythm": to_json(grid) if grid else None} | _features(notes, meters, grid, map_name)


def _features(notes: list[Note], meters: MeterMap, grid: tuple[Bar, ...], map_name: str) -> dict[str, float | str | None]:
    if not grid:
        return dict.fromkeys(FEATURES)
    signatures = [meters.meter_at(meters.bar_line(b)) for b in range(1, len(grid) + 1)]
    return {"density": round(statistics.fmean(b.kick.bit_count() + b.snare.bit_count() + b.hands.bit_count()
                                              for b in grid), 2),
            "syncopation": round(statistics.fmean(syncopation(b.kick | b.snare, sig)
                                                  for b, sig in zip(grid, signatures, strict=True)), 2),
            "subdivision": subdivision(notes, meters, map_name),
            "swing8": swing(notes, meters, map_name),
            "swing16": swing(notes, meters, map_name, sixteenths=True),
            "lag": lag(notes, meters, map_name)}


def _near_pairs(only_x: int, only_y: int) -> int:
    """How many pairs a sixteenth apart the two sides' unmatched onsets make, each onset in one pair at most."""
    pairs, free = 0, 0
    for step in range((only_x | only_y).bit_length()):
        side = (only_x >> step & 1) | (only_y >> step & 1) << 1
        if side and free and side != free:
            pairs, free = pairs + 1, 0
        else:
            free = side
    return pairs


def bar_distance(a: Bar, b: Bar, voices: Iterable[int] | None = None) -> float | None:
    """A fuzzy Hamming distance over ``voices`` (all by default): each onset one bar has and the other lacks
    costs its voice's weight, half of it when it pairs with an unmatched onset of the other a sixteenth away,
    each onset pairing once. None for bars of different lengths."""
    if a.steps != b.steps:
        return None
    total = 0.0
    for v in range(len(VOICES)) if voices is None else voices:
        weight, x, y = WEIGHTS[v], a[v + 1], b[v + 1]
        only_x, only_y = x & ~y, y & ~x
        total += weight * (only_x.bit_count() + only_y.bit_count() - _near_pairs(only_x, only_y))
    return total


def distance(query: Sequence[Bar], candidate: Sequence[Bar], voices: Iterable[int] | None = None) -> float | None:
    """How far ``candidate`` is from ``query`` over ``voices``: each query bar's nearest candidate bar of its
    length, averaged over the query bars that have one; None when none has."""
    voices = None if voices is None else tuple(voices)
    found = []
    for q in query:
        near = [d for c in candidate if (d := bar_distance(q, c, voices)) is not None]
        if near:
            found.append(min(near))
    return statistics.fmean(found) if found else None
