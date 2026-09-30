"""Drum rhythms typed as text — a lane of `x` and `.` per voice, `|` between bars — read into `groove.Bar`s and
written back."""

from __future__ import annotations

from collections.abc import Sequence

from .groove import VOICES, Bar


def _lane(voice: str, text: str) -> list[str]:
    bars = []
    for cells in text.split("|"):
        if not cells:
            raise ValueError(f"{voice}={text}: a bar needs at least one step")
        if set(cells) - {"x", "."}:
            raise ValueError(f"{voice}={text}: a lane holds only x and . steps, with | between bars")
        bars.append(cells)
    return bars


def parse_rhythm(text: str) -> tuple[tuple[Bar, ...], tuple[int, ...]]:
    """Bars from lanes typed as ``kick=x...x...|x.x.x... snare=....x.......x...``: a step per character, ``x``
    struck, ``|`` between bars. A lane of one bar plays in every bar. Returns the bars and the voices given, as
    indices in `VOICES`; a voice left out is empty."""
    lanes: dict[int, list[str]] = {}
    for word in text.split():
        voice, sep, cells = word.partition("=")
        if not sep:
            raise ValueError(f"{word}: write each lane as voice=lane, e.g. kick=x...x...")
        if voice not in VOICES:
            raise ValueError(f"{voice}: a lane is kick, snare or hands")
        if VOICES.index(voice) in lanes:
            raise ValueError(f"{voice}: a lane given twice")
        lanes[VOICES.index(voice)] = _lane(voice, cells)
    if not lanes:
        raise ValueError("no lanes: type them as kick=x.......x....... snare=....x.......x...")
    count = max(map(len, lanes.values()))
    if any(len(cells) not in (1, count) for cells in lanes.values()):
        raise ValueError(f"every lane gives one bar or the same number of bars ({count})")
    bars = []
    for b in range(count):
        cells = {v: lane[b if len(lane) > 1 else 0] for v, lane in lanes.items()}
        if len(set(map(len, cells.values()))) > 1:
            raise ValueError(f"bar {b + 1}: every lane needs the same number of steps")
        grid = [sum(1 << s for s, c in enumerate(cells.get(v, "")) if c == "x") for v in range(len(VOICES))]
        bars.append(Bar(len(next(iter(cells.values()))), *grid))
    return tuple(bars), tuple(sorted(lanes))


def rhythm_text(bars: Sequence[Bar]) -> str:
    """``bars`` as the lanes `parse_rhythm` reads, every voice given."""
    return " ".join(f"{voice}=" + "|".join("".join("x" if b[v + 1] >> s & 1 else "." for s in range(b.steps))
                                           for b in bars)
                    for v, voice in enumerate(VOICES))
