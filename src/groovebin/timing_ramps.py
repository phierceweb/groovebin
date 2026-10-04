"""Tempo ramps read out of a tempo map's points."""

from __future__ import annotations

import math
from typing import NamedTuple

RAMP_TOLERANCE = 0.01


class Ramp(NamedTuple):
    start: int
    end: int
    from_usec: int
    to_usec: int
    points: int

    @property
    def from_bpm(self) -> float:
        return 60_000_000 / self.from_usec

    @property
    def to_bpm(self) -> float:
        return 60_000_000 / self.to_usec


def ramps_of(points: tuple[tuple[int, int], ...], ppq: int) -> tuple[Ramp, ...]:
    """Runs of three or more (tick, usec) points, each at most a quarter note after the last, whose bpm never turns
    back and ends where it did not start, each point on the straight line from the run's first point to its last
    within `RAMP_TOLERANCE` and a microsecond's rounding. Runs are taken longest first from the earliest point; two
    ramps can share the point where they meet."""
    found, i, last = [], 0, len(points) - 1
    while i + 2 <= last:
        j = _run(points, i, ppq)
        if j < i + 2:
            i += 1
            continue
        (start, from_usec), (end, to_usec) = points[i], points[j]
        if from_usec != to_usec:
            found.append(Ramp(start, end, from_usec, to_usec, j - i + 1))
        i = j
    return tuple(found)


def _run(points: tuple[tuple[int, int], ...], i: int, ppq: int) -> int:
    """The last point of the longest run from point ``i`` that `ramps_of` would read, flat or not."""
    t0, b0 = points[i][0], 60_000_000 / points[i][1]
    low, high, way, j = -math.inf, math.inf, 0, i
    while j + 1 < len(points):
        (tick, usec), (after, next_usec) = points[j], points[j + 1]
        if not 0 < after - tick <= ppq or way * (usec - next_usec) < 0:
            break
        if j > i:
            bpm = 60_000_000 / usec
            tolerance = RAMP_TOLERANCE + bpm * bpm / 60_000_000
            low = max(low, (bpm - tolerance - b0) / (tick - t0))
            high = min(high, (bpm + tolerance - b0) / (tick - t0))
        if not low <= (60_000_000 / next_usec - b0) / (after - t0) <= high:
            break
        way, j = way or (usec > next_usec) - (usec < next_usec), j + 1
    return j
