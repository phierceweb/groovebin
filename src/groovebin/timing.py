"""Tempo and meter maps over a part's ticks, with bar 1 starting at tick 0.

Tempo points hold microseconds per quarter note, the unit a file stores, so they survive a round
trip exactly; ``bpm`` is derived. A meter change takes effect at the first bar line at or after
its tick, which is where a DAW puts a change dropped inside a bar.
"""

from __future__ import annotations

import math
from bisect import bisect_right
from dataclasses import dataclass, field

DEFAULT_TEMPO = 500_000
MAX_TEMPO = 0xFFFFFF


def _in_tick_order(ticks: list[int], what: str) -> None:
    for before, after in zip(ticks, ticks[1:], strict=False):
        if after < before:
            raise ValueError(f"{what} are not in tick order: {after} after {before}")


@dataclass(frozen=True, slots=True)
class TempoMap:
    points: tuple[tuple[int, int], ...]
    _ticks: tuple[int, ...] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        for _, usec in self.points:
            if not 1 <= usec <= MAX_TEMPO:
                raise ValueError(f"a tempo of {usec} microseconds per quarter note is not 1-{MAX_TEMPO}")
        _in_tick_order([t for t, _ in self.points], "tempo points")
        object.__setattr__(self, "_ticks", tuple(t for t, _ in self.points))

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
