"""Tempo and meter maps over a part's ticks, with bar 1 starting at tick 0.

Tempo points hold microseconds per quarter note, the unit a file stores, so they survive a round
trip exactly; ``bpm`` is derived. A meter change takes effect at the first bar line at or after
its tick, which is where a DAW puts a change dropped inside a bar.
"""

from __future__ import annotations

import math
from bisect import bisect_right
from dataclasses import dataclass, field

from .timing_ramps import Ramp, ramps_of

DEFAULT_TEMPO = 500_000
MAX_TEMPO = 0xFFFFFF


def _in_tick_order(ticks: list[int], what: str) -> None:
    for before, after in zip(ticks, ticks[1:], strict=False):
        if after < before:
            raise ValueError(f"{what} are not in tick order: {after} after {before}")


def _ppq(ppq: int) -> None:
    if ppq < 1:
        raise ValueError(f"a PPQ of {ppq} is not 1 or more")


def _usec(bpm: float) -> int:
    if not (math.isfinite(bpm) and bpm > 0):
        raise ValueError(f"a tempo of {bpm:g} bpm is not a finite number above 0")
    usec = round(60_000_000 / bpm)
    if not 1 <= usec <= MAX_TEMPO:
        raise ValueError(f"{bpm:g} bpm is {usec} microseconds per quarter note, not 1-{MAX_TEMPO}")
    return usec


def ramp_points(start: int, end: int, from_bpm: float, to_bpm: float, step: int) -> tuple[tuple[int, int], ...]:
    """Tempo points for a ramp linear in bpm: one at ``start`` and every ``step`` ticks after, each at the line's
    bpm at its tick, and ``to_bpm`` at ``end``."""
    if end <= start:
        raise ValueError(f"a ramp from tick {start} to {end} does not move forward")
    if step < 1:
        raise ValueError(f"a ramp step of {step} tick(s) is not 1 or more")
    if end - start <= step:
        raise ValueError(f"a ramp from tick {start} to {end} in steps of {step} has no point between its ends: it is a "
                         "tempo step")
    return tuple((t, _usec(from_bpm + (to_bpm - from_bpm) * (t - start) / (end - start)))
                 for t in [*range(start, end, step), end])


@dataclass(frozen=True, slots=True)
class TempoMap:
    points: tuple[tuple[int, int], ...]
    _ticks: tuple[int, ...] = field(init=False, repr=False, compare=False)
    _elapsed: tuple[int, ...] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        for _, usec in self.points:
            if not 1 <= usec <= MAX_TEMPO:
                raise ValueError(f"a tempo of {usec} microseconds per quarter note is not 1-{MAX_TEMPO}")
        _in_tick_order([t for t, _ in self.points], "tempo points")
        latest: dict[int, int] = {}
        for tick, usec in self.points:
            latest[tick] = usec
        object.__setattr__(self, "points", tuple(latest.items()))
        object.__setattr__(self, "_ticks", tuple(t for t, _ in self.points))
        elapsed: list[int] = []
        for i, (tick, usec) in enumerate(self.points):
            before = self.points[i - 1] if i else None
            elapsed.append(tick * usec if before is None else elapsed[-1] + (tick - before[0]) * before[1])
        object.__setattr__(self, "_elapsed", tuple(elapsed))

    @property
    def defaulted(self) -> bool:
        """True when no point was given, so the map is the file format's default 120 bpm."""
        return not self.points

    def at(self, tick: int) -> int:
        """Microseconds per quarter note in force at ``tick``; the first point applies before it."""
        if not self.points:
            return DEFAULT_TEMPO
        i = bisect_right(self._ticks, tick)
        return self.points[max(i - 1, 0)][1]

    def bpm(self, tick: int) -> float:
        return 60_000_000 / self.at(tick)

    def _units(self, tick: int) -> int:
        """Ticks times microseconds per quarter note from tick 0 to ``tick``."""
        if not self.points:
            return tick * DEFAULT_TEMPO
        i = max(bisect_right(self._ticks, tick) - 1, 0)
        return self._elapsed[i] + (tick - self._ticks[i]) * self.points[i][1]

    def seconds(self, tick: int, ppq: int) -> float:
        """Where ``tick`` falls in seconds from tick 0, each stretch at its own tempo."""
        _ppq(ppq)
        return self._units(tick) / (ppq * 1_000_000)

    def tick_at(self, seconds: float, ppq: int) -> int:
        """The tick nearest ``seconds``, half up: the inverse of `seconds`."""
        _ppq(ppq)
        if not math.isfinite(seconds):
            raise ValueError(f"{seconds:g} seconds is not a finite number")
        units = seconds * ppq * 1_000_000
        if not self.points:
            return math.floor(units / DEFAULT_TEMPO + 0.5)
        i = max(bisect_right(self._elapsed, units) - 1, 0)
        return math.floor(self._ticks[i] + (units - self._elapsed[i]) / self.points[i][1] + 0.5)

    def ramps(self, ppq: int) -> tuple[Ramp, ...]:
        """The tempo ramps the points hold (`timing_ramps.ramps_of`)."""
        _ppq(ppq)
        return ramps_of(self.points, ppq)

    def _pinned(self, tick: int) -> list[tuple[int, int]]:
        """The points, with the tempo in force at tick 0 written there, for an edit at ``tick``."""
        if tick < 0:
            raise ValueError(f"a tempo point at tick {tick} is before bar 1")
        points = list(self.points)
        if not points or points[0][0] > 0:
            points.insert(0, (0, self.at(0)))
        return points

    def with_point(self, tick: int, bpm: float) -> TempoMap:
        """The map with ``bpm`` from ``tick`` until the next point; a point already on ``tick`` is replaced."""
        points = [p for p in self._pinned(tick) if p[0] != tick] + [(tick, _usec(bpm))]
        return TempoMap(tuple(sorted(points, key=lambda p: p[0])))

    def with_ramp(self, start: int, end: int, from_bpm: float, to_bpm: float, step: int) -> TempoMap:
        """The map with the points from ``start`` through ``end`` replaced by a ramp (`ramp_points`)."""
        ramp = ramp_points(start, end, from_bpm, to_bpm, step)
        points = [p for p in self._pinned(start) if not start <= p[0] <= end] + list(ramp)
        return TempoMap(tuple(sorted(points, key=lambda p: p[0])))


@dataclass(frozen=True, slots=True)
class MeterMap:
    ppq: int
    given: tuple[tuple[int, int, int], ...] = field(compare=False)
    changes: tuple[tuple[int, int, int], ...] = field(init=False)
    defaulted: bool = field(init=False, compare=False)
    _bars: tuple[int, ...] = field(init=False, repr=False, compare=False)
    _ticks: tuple[int, ...] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.ppq < 1:
            raise ValueError(f"a PPQ of {self.ppq} is not 1 or more")
        _in_tick_order([t for t, _, _ in self.given], "meter changes")
        effective = [(0, 4, 4)]
        for tick, num, den in self.given:
            self._check(tick, num, den)
            last_tick, *last_meter = effective[-1]
            line = last_tick
            if tick > last_tick:
                span = self._span(*last_meter)
                line += -(-(tick - last_tick) // span) * span
            if line == last_tick:
                effective[-1] = (line, num, den)
            else:
                effective.append((line, num, den))
        bars = [1]
        for (t0, n0, d0), (t1, _, _) in zip(effective, effective[1:], strict=False):
            bars.append(bars[-1] + (t1 - t0) // self._span(n0, d0))
        object.__setattr__(self, "changes", tuple(effective))
        object.__setattr__(self, "defaulted", not self.given)
        object.__setattr__(self, "_bars", tuple(bars))
        object.__setattr__(self, "_ticks", tuple(t for t, _, _ in effective))

    def _check(self, tick: int, num: int, den: int) -> None:
        if tick < 0:
            raise ValueError(f"a meter change at tick {tick} is before bar 1")
        if num < 1:
            raise ValueError(f"a meter of {num}/{den} needs a numerator of 1 or more")
        if den < 1 or den & (den - 1):
            raise ValueError(f"a meter of {num}/{den} needs a power-of-two denominator")
        if self.ppq * 4 * num % den:
            raise ValueError(f"a bar of {num}/{den} at PPQ {self.ppq} is not a whole number of ticks")

    def _span(self, num: int, den: int) -> int:
        return self.ppq * 4 * num // den

    def _segment_of_tick(self, tick: int) -> int:
        return max(bisect_right(self._ticks, tick) - 1, 0)

    def meter_at(self, tick: int) -> tuple[int, int]:
        _, num, den = self.changes[self._segment_of_tick(tick)]
        return num, den

    def bar_ticks(self, tick: int) -> int:
        return self._span(*self.meter_at(tick))

    def bar(self, tick: int) -> float:
        """The 1-based bar number at ``tick``, fractional inside a bar, whole on a bar line."""
        i = self._segment_of_tick(tick)
        start, num, den = self.changes[i]
        return self._bars[i] + (tick - start) / self._span(num, den)

    def bar_of(self, tick: int) -> int:
        """The number of the bar holding ``tick``."""
        i = self._segment_of_tick(tick)
        start, num, den = self.changes[i]
        return self._bars[i] + (tick - start) // self._span(num, den)

    def _segment_of_bar(self, bar: float) -> int:
        return max(bisect_right(self._bars, bar) - 1, 0)

    def bar_line(self, bar: int) -> int:
        """The tick where bar ``bar`` starts."""
        i = self._segment_of_bar(bar)
        start, num, den = self.changes[i]
        return start + (bar - self._bars[i]) * self._span(num, den)

    def tick(self, bar: float) -> int:
        """Where ``bar`` falls, rounded to a tick: the inverse of ``bar``."""
        if not math.isfinite(bar):
            raise ValueError(f"bar {bar} is not a finite number")
        i = self._segment_of_bar(bar)
        start, num, den = self.changes[i]
        return round(start + (bar - self._bars[i]) * self._span(num, den))


@dataclass(frozen=True, slots=True)
class KeyMap:
    """Key signatures as points of (tick, sharps, minor): sharps -7 to 7, flats below 0."""
    points: tuple[tuple[int, int, bool], ...]
    _ticks: tuple[int, ...] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        for _, sharps, _minor in self.points:
            if not -7 <= sharps <= 7:
                raise ValueError(f"a key signature of {sharps} sharps is not -7 to 7")
        _in_tick_order([t for t, _, _ in self.points], "key signatures")
        object.__setattr__(self, "_ticks", tuple(t for t, _, _ in self.points))

    @property
    def defaulted(self) -> bool:
        return not self.points

    def at(self, tick: int) -> tuple[int, bool] | None:
        """(sharps, minor) in force at ``tick``; None before the first signature."""
        i = bisect_right(self._ticks, tick)
        return None if i == 0 else (self.points[i - 1][1], self.points[i - 1][2])

    def tonic(self, tick: int) -> int | None:
        """The pitch class of the tonic in force at ``tick``."""
        found = self.at(tick)
        return None if found is None else (found[0] * 7 + 9 * found[1]) % 12

    def with_point(self, tick: int, sharps: int, minor: bool) -> KeyMap:
        """The map with this signature from ``tick``; one already on ``tick`` is replaced."""
        if tick < 0:
            raise ValueError(f"a key signature at tick {tick} is before bar 1")
        points = [p for p in self.points if p[0] != tick] + [(tick, sharps, minor)]
        return KeyMap(tuple(sorted(points, key=lambda p: p[0])))
