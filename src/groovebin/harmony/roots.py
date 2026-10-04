"""The chords a bassline implies, and charts laid over bars."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from ..events import Note
from ..timing import MeterMap
from .chords import CHORD_NAMES, Chord

SPLIT_SHARE = 0.8
START_WEIGHT = 3
THIRD_SHARE = 0.05


@dataclass(frozen=True, slots=True)
class Span:
    start: int
    end: int
    chord: Chord


def _held(notes: list[Note], lo: int, hi: int, ppq: int, start_weight: int = 1) -> Counter[int]:
    """Each pitch class's held length from ``lo`` to ``hi``; a note starting within an eighth of a beat of ``lo``
    counts ``start_weight`` times."""
    held: Counter[int] = Counter()
    for n in notes:
        if n.tick < hi and n.end > lo:
            weight = start_weight if 8 * abs(n.tick - lo) <= ppq else 1
            held[n.pitch % 12] += (min(n.end, hi) - max(n.tick, lo)) * weight
    return held


def _root(notes: list[Note], lo: int, hi: int, ppq: int) -> tuple[int | None, float]:
    held = _held(notes, lo, hi, ppq, START_WEIGHT)
    if not sum(held.values()):
        return None, 0.0
    pitch, weight = held.most_common(1)[0]
    return pitch, weight / sum(held.values())


def _quality(notes: list[Note], span: tuple[int, int], root: int, ppq: int) -> Chord:
    held = _held(notes, *span, ppq)
    total = sum(held.values())
    minor, major = held[(root + 3) % 12] / total, held[(root + 4) % 12] / total
    if max(minor, major) >= THIRD_SHARE and minor != major:
        return Chord(root, "min" if minor > major else "maj")
    return Chord(root, "5")


def roots(notes: Iterable[Note], meters: MeterMap, bars: int) -> list[Span]:
    """The chords a bassline implies over its first ``bars`` bars. A window's root is the pitch class held longest
    in it, a note starting on the window counting three times; a bar splits into halves only when each half's
    root holds 80% of it and they differ. A silent bar keeps the chord before it (the first bars take the first
    chord), equal neighbours merge, and a span is major or minor when the bass holds that third for 5% of it,
    else a power chord (``5``)."""
    notes, ppq, windows = list(notes), meters.ppq, []
    for bar in range(1, bars + 1):
        lo = meters.bar_line(bar)
        hi = lo + meters.bar_ticks(lo)
        mid = (lo + hi) // 2
        if (hi - lo) % 2 == 0:
            (first, s1), (second, s2) = _root(notes, lo, mid, ppq), _root(notes, mid, hi, ppq)
            if None not in (first, second) and first != second and min(s1, s2) >= SPLIT_SHARE:
                windows += [(lo, mid, first), (mid, hi, second)]
                continue
        windows.append((lo, hi, _root(notes, lo, hi, ppq)[0]))
    current = next((root for _lo, _hi, root in windows if root is not None), None)
    if current is None:
        return []
    merged: list[list[int]] = []
    for lo, hi, root in windows:
        current = current if root is None else root
        if merged and merged[-1][2] == current:
            merged[-1][1] = hi
        else:
            merged.append([lo, hi, current])
    return [Span(lo, hi, _quality(notes, (lo, hi), root, ppq)) for lo, hi, root in merged]


def chart_text(spans: list[Span], meters: MeterMap, bars: int) -> str:
    """``spans`` as a chart a bar at a time, two chords where a bar splits: ``| A5 | F5 G5 |``."""
    cells = []
    for bar in range(1, bars + 1):
        lo = meters.bar_line(bar)
        points = (lo, lo + meters.bar_ticks(lo) // 2)
        found = [next((s.chord for s in spans if s.start <= t < s.end), None) for t in points]
        cells.append(" ".join(str(c) for c in dict.fromkeys(found) if c is not None) or "N.C.")
    return "| " + " | ".join(cells) + " |"


def chart_spans(bars_of_chords: list[tuple[Chord, ...]], meters: MeterMap, bars: int) -> list[Span]:
    """A chart laid over ``bars`` bars from bar 1, looping when it is shorter; a bar's chords share it evenly, the
    last taking what an uneven split leaves."""
    spans = []
    for bar in range(1, bars + 1):
        chords = bars_of_chords[(bar - 1) % len(bars_of_chords)]
        lo = meters.bar_line(bar)
        size = meters.bar_ticks(lo)
        edges = [lo + size * k // len(chords) for k in range(len(chords))] + [lo + size]
        spans += [Span(a, b, c) for a, b, c in zip(edges[:-1], edges[1:], chords, strict=True)]
    return spans


def root_notes(spans: Sequence[Span], octave: int = 2) -> tuple[Note, ...]:
    """A note per span at its lowest pitch class — the slash bass, else the root — in ``octave`` (C4 is 60), velocity
    100 on channel 1, as long as the span."""
    notes = []
    for s in spans:
        pitch = 12 * (octave + 1) + s.chord.lowest
        if not 0 <= pitch <= 127:
            raise ValueError(f"octave {octave} puts {CHORD_NAMES[s.chord.lowest]} at {pitch}, outside 0-127")
        notes.append(Note(s.start, s.end - s.start, 1, pitch, 100))
    return tuple(notes)
