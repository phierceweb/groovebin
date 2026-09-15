"""A drum part planned over a song's sections from one group of the library: the section's name gives its
role, the role picks the group's groove patterns (never a fill), and the pattern repeats to fill the
section. Nothing is written; a caller that owns a song format lays the notes in.

The nth section of a role takes the nth groove of that role in variant-number order, cycling; only
patterns whose every bar is in the section's meter count. With fills, the section's last bar becomes a
fill's bar: a fill named for the section's role first, else one with no role, cycling likewise.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field, replace
from pathlib import Path

from ..events import Note
from ..timing import MeterMap
from .names import role_of
from .pattern import Pattern, bar_ticks, meter_text, pattern, repeated
from .search import group_rows

ROLES = ("intro", "verse", "pre-chorus", "chorus", "bridge", "outro")


@dataclass(frozen=True, slots=True)
class Section:
    name: str
    start: int
    length: int


@dataclass
class SectionPlan:
    section: Section
    start_bar: float
    end_bar: float
    skipped: str | None = None
    beat: Pattern | None = None
    fill: Pattern | None = None
    fill_bar: float | None = None
    no_fill: str | None = None
    copies: int = 0
    notes: list[Note] = field(default_factory=list)
    dropped: int = 0
    replaced: int = 0


def _order(p: Pattern) -> tuple:
    m = re.search(r"(\d+)\s*$", p.variant)
    stem = p.variant[:m.start()] if m else p.variant
    return stem.strip().lower(), int(m.group(1)) if m else 0, p.id


def group_patterns(db_path: Path, library: str | None, group: str) -> list[Pattern]:
    return sorted((pattern(r) for r in group_rows(db_path, library, group)), key=_order)


def _section_meter(meters: MeterMap, s: Section) -> tuple[int, int] | None:
    first = meters.meter_at(s.start)
    inside = [(n, d) for t, n, d in meters.changes if s.start < t < s.start + s.length]
    return None if any(m != first for m in inside) else first


def _title(role: str) -> str:
    return "-".join(w.title() for w in role.split("-"))


def plan_sections(sections: list[Section], meters: MeterMap, patterns: list[Pattern], *,
                  fills: bool = False) -> list[SectionPlan]:
    """What each section gets, in section order; nothing is written."""
    out, seen = [], {}
    for s in sections:
        p = SectionPlan(s, meters.bar(s.start), meters.bar(s.start + s.length))
        out.append(p)
        role = role_of(s.name)
        if role is None:
            p.skipped = f"{s.name or 'an unnamed section'!r} is not an intro, verse, pre-chorus, chorus, bridge or outro"
            continue
        n, seen[role] = seen.get(role, 0), seen.get(role, 0) + 1
        sig = _section_meter(meters, s)
        if s.length <= 0:
            p.skipped = "the section has no length"
        elif sig is None:
            p.skipped = "the meter changes inside the section"
        elif not float(p.start_bar).is_integer():
            p.skipped = "the section does not start on a bar line"
        if p.skipped:
            continue
        named = [x for x in patterns if not x.is_fill and x.role == role]
        fit = [x for x in named if x.meter == sig]
        if not fit:
            have = sorted({meter_text(x.meter) for x in named})
            p.skipped = (f"no {_title(role)} pattern in {meter_text(sig)}; the group's are {', '.join(have)}" if named
                         else f"no {_title(role)} pattern in the group")
            continue
        p.beat = fit[n % len(fit)]
        p.copies = math.ceil(s.length / p.beat.ticks)
        p.notes, p.dropped = repeated(p.beat.notes, p.beat.ticks, p.copies, s.length)
        if fills:
            _with_fill(p, patterns, role, sig, seen)
    return out


def _with_fill(p: SectionPlan, patterns: list[Pattern], role: str, sig: tuple[int, int], seen: dict) -> None:
    all_fills = [x for x in patterns if x.is_fill]
    candidates = ([x for x in all_fills if x.role == role and x.bars[-1] == sig]
                  or [x for x in all_fills if x.role is None and x.bars[-1] == sig])
    if not candidates:
        p.no_fill = f"no fill pattern ending in {meter_text(sig)}" if all_fills else "no fill pattern in the group"
        return
    key = ("fill", candidates[0].role)
    n, seen[key] = seen.get(key, 0), seen.get(key, 0) + 1
    p.fill = candidates[n % len(candidates)]
    bar = p.fill.fill_bar()
    if bar is None:
        p.no_fill = f"fill {p.fill.name!r} is one bar that only lands on its downbeat"
        p.fill = None
        return
    span, length = bar_ticks(sig), p.section.length
    last = (math.ceil(length / span) - 1) * span
    kept = [x for x in p.notes if x.tick < last]
    laid = [replace(x, tick=x.tick + last) for x in bar if x.tick + last < length]
    p.replaced = len(p.notes) - len(kept)
    p.dropped += len(bar) - len(laid)
    p.notes = sorted(kept + laid, key=lambda x: x.tick)
    p.fill_bar = p.start_bar + last // span
