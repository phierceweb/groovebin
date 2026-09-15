"""A library row as a pattern: its notes at 960 PPQ from its own start, a meter per bar, and the labels
section planning and generation choose by.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import PurePosixPath

from ..events import Note
from ..timing import MeterMap
from .index import MAX_BARS, PPQ, unpack_notes

SIXTEENTH = PPQ // 4


def bar_ticks(sig: tuple[int, int]) -> int:
    return PPQ * 4 * sig[0] // sig[1]


def meter_text(sig: tuple[int, int] | None) -> str:
    return f"{sig[0]}/{sig[1]}" if sig else "a changing meter"


@dataclass(frozen=True, slots=True)
class Pattern:
    id: str
    name: str
    variant: str
    bars: tuple[tuple[int, int], ...]
    notes: tuple[Note, ...]
    map: str | None
    role: str | None
    is_fill: bool
    tempo: float | None

    @property
    def ticks(self) -> int:
        return sum(bar_ticks(sig) for sig in self.bars)

    @property
    def meter(self) -> tuple[int, int] | None:
        """The one meter of every bar; None when the pattern changes meter."""
        return self.bars[0] if len(set(self.bars)) == 1 else None

    def bar_notes(self, index: int) -> list[Note]:
        """Bar ``index``'s notes (0-based), ticks from that bar's line."""
        start = sum(bar_ticks(sig) for sig in self.bars[:index])
        end = start + bar_ticks(self.bars[index])
        return [replace(n, tick=n.tick - start) for n in self.notes if start <= n.tick < end]

    def last_bar(self) -> list[Note]:
        start = self.ticks - bar_ticks(self.bars[-1])
        return [replace(n, tick=n.tick - start) for n in self.notes if n.tick >= start]

    def fill_bar_index(self) -> int | None:
        """The bar (0-based) a fill contributes: its last, unless the last holds only a landing (every
        note nearest the bar's first sixteenth), then the bar before; None when there is none before."""
        last = len(self.bars) - 1
        if not all(n.tick < SIXTEENTH // 2 for n in self.last_bar()):
            return last
        return last - 1 if last else None

    def fill_bar(self) -> list[Note] | None:
        """The notes of `fill_bar_index`'s bar, ticks from its bar line."""
        index = self.fill_bar_index()
        if index is None:
            return None
        return self.last_bar() if index == len(self.bars) - 1 else self.bar_notes(index)


def signatures(meters_json: str | None, bars: int) -> tuple[tuple[int, int], ...]:
    meters = MeterMap(PPQ, tuple(tuple(c) for c in json.loads(meters_json or "[]")))
    return tuple(meters.meter_at(meters.bar_line(b)) for b in range(1, bars + 1))


def pattern(row: dict) -> Pattern:
    """The library row ``row`` (`search.get`) as a pattern; one that did not parse, or holds no notes,
    is refused."""
    if row.get("error"):
        raise ValueError(f"pattern {row['id']} was not parsed ({row['error']}): nothing to use")
    if not row.get("bars"):
        raise ValueError(f"pattern {row['id']} holds no notes: nothing to use")
    variant = (row.get("variant") or "").strip()
    name = variant or PurePosixPath(row.get("file") or "").stem or row["id"]
    return Pattern(row["id"], name, variant, signatures(row["meters"], row["bars"]), tuple(unpack_notes(row["notes"])),
                   row.get("map"), row.get("role"), bool(row.get("is_fill")), row.get("tempo"))


def repeated(notes, span: int, times: int, end: int | None = None) -> tuple[list[Note], int]:
    """``notes`` laid ``times`` back to back every ``span`` ticks -> (notes, dropped). A note at or past
    its copy's ``span``, or past ``end``, is dropped: it would sound over the next copy's start."""
    notes = list(notes)
    out = [replace(n, tick=n.tick + k * span) for k in range(times) for n in notes
           if n.tick < span and (end is None or n.tick + k * span < end)]
    return out, len(notes) * times - len(out)


def fit(meters: MeterMap, bar: int, bars: tuple[tuple[int, int], ...], *, times: int = 1,
        noun: str = "pattern") -> tuple[int, int]:
    """(start tick, length) of ``bars`` laid ``times`` over ``meters`` from bar ``bar``; refused at the
    first bar whose meter is not the song's there."""
    if bar < 1:
        raise ValueError(f"bar {bar}: bars start at 1")
    if len(bars) * times > MAX_BARS:
        raise ValueError(f"{len(bars)} bar(s) x {times} is past {MAX_BARS} bars")
    start = at = meters.bar_line(bar)
    for i in range(len(bars) * times):
        want, have = bars[i % len(bars)], meters.meter_at(at)
        if want != have:
            raise ValueError(f"the {noun}'s bar {i % len(bars) + 1} is {meter_text(want)} but the song is "
                             f"{meter_text(have)} at bar {bar + i}")
        at += bar_ticks(want)
    return start, at - start
