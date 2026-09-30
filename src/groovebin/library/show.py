"""A library row drawn as text, a cell per sixteenth and ``|`` at each bar: a lane per note number for a
drum row, a piano roll with note names and held notes for any other.

A note sits in its nearest cell; one rounding past the last bar wraps to the first, as a loop plays it.
"""

from __future__ import annotations

import json
from collections.abc import Callable

from ..maps import NAMES
from ..timing import MeterMap
from .groove import FEATURES
from .pattern import SIXTEENTH, signatures
from .blobs import unpack_notes
from .index import PPQ

NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")


def note_name(pitch: int) -> str:
    return f"{NOTE_NAMES[pitch % 12]}{pitch // 12 - 1}"


def _mark(velocity: int) -> str:
    return "X" if velocity >= 100 else "x" if velocity >= 64 else "o"


def _layout(row: dict) -> tuple[list[int], int]:
    starts, steps = [], 0
    for num, den in signatures(row["meters"], row["bars"] or 0):
        starts.append(steps)
        steps += max(1, 16 * num // den)
    return starts, steps


def _with_bars(cells: list[str], starts: list[int]) -> str:
    cells = list(cells)
    for s in reversed(starts):
        cells.insert(s, "|")
    return "".join(cells) + "|"


def lanes(row: dict, label: Callable[[int], str | None] | None = None) -> list[str]:
    """A line per note number used, highest first, named by ``label`` when given."""
    starts, steps = _layout(row)
    if not steps:
        return []
    loudest: dict[int, list[int]] = {}
    for n in unpack_notes(row["notes"]):
        step = (n.tick + SIXTEENTH // 2) // SIXTEENTH % steps
        line = loudest.setdefault(n.pitch, [0] * steps)
        line[step] = max(line[step], n.velocity)
    names = {pitch: (label(pitch) or "-") + " " for pitch in loudest} if label else dict.fromkeys(loudest, "")
    width = max(map(len, names.values()), default=0)
    return [f"{pitch:3d} {names[pitch]:{width}s}" + _with_bars([_mark(v) if v else "." for v in loudest[pitch]], starts)
            for pitch in sorted(loudest, reverse=True)]


def piano_roll(row: dict) -> list[str]:
    """A line per pitch from the highest used to the lowest, held notes drawn to their end."""
    starts, steps = _layout(row)
    notes = unpack_notes(row["notes"])
    if not steps or not notes:
        return []
    grid = {p: ["."] * steps for p in range(min(n.pitch for n in notes), max(n.pitch for n in notes) + 1)}
    for n in notes:
        first = (n.tick + SIXTEENTH // 2) // SIXTEENTH
        line = grid[n.pitch]
        for cell in range(first + 1, steps):
            if cell * SIXTEENTH >= n.end:
                break
            if line[cell] == ".":
                line[cell] = "="
    for n in notes:
        grid[n.pitch][(n.tick + SIXTEENTH // 2) // SIXTEENTH % steps] = _mark(n.velocity)
    return [f"{note_name(p):>4s} " + _with_bars(grid[p], starts) for p in sorted(grid, reverse=True)]


def show(row: dict, label: Callable[[int], str | None] | None = None) -> str:
    if row["error"]:
        return f"{row['id']}  {row['file']}: not parsed ({row['error']})"
    title = " / ".join(str(row[c]) for c in ("library", "category", "group_name", "variant") if row[c])
    tempo = f"{row['tempo']:g} bpm" if row["tempo"] is not None else "no tempo"
    head = f"{row['id']}  {title or row['file']}  {row['meter'] or '?'}  {tempo}  {row['bars']} bar(s)"
    body = lanes(row, label) if row.get("map") in NAMES or label else piano_roll(row)
    return "\n".join([head, *feel(row), *harmony(row), *body])


def harmony(row: dict) -> list[str]:
    """The chords the row was played over, each with the bar it starts in; none for a row without them."""
    if not row.get("chords"):
        return []
    meters = MeterMap(PPQ, tuple(tuple(c) for c in json.loads(row["meters"])))
    placed = (f"{symbol} (bar {meters.bar(start):g})" for start, _end, symbol in json.loads(row["chords"]))
    return ["chords  " + ", ".join(placed)]


def feel(row: dict) -> list[str]:
    """The row's feel columns as one line, named as `search` filters them; none for a row without them."""
    if row.get("density") is None:
        return []
    cells = ("-" if row[c] is None else f"{row[c]:g}" if isinstance(row[c], float) else str(row[c]) for c in FEATURES)
    return ["feel  " + "  ".join(f"{c} {v}" for c, v in zip(FEATURES, cells, strict=True))]
