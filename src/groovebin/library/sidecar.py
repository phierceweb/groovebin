"""The chord files EZbass keeps beside its grooves: the chords each groove was played over. Read only from
a folder the user indexes.

Each ``Chord`` block holds ``Note root bass flag`` — pitch classes, the flag 0 for major and 1 for minor — and
``Time start end`` in quarter notes from the groove's start, or ``TTime`` with ticks at 96,000 a quarter after each.
The older layout gives each chord an ``OrgChord`` line — root, bass, flag, start, six fields, end — read the same
way, a last chord ending at 0 running to the groove's end; its ``Chord`` lines and ``ChordParts`` codes are not
read."""

from __future__ import annotations

import json
import math
import re
from itertools import pairwise
from pathlib import Path

from ..harmony import Chord

SIDECAR = ".midchordinfo"
CHORD_COLUMNS = ("chords", "changes", "quality")
QUALITIES = ("major", "minor")
TTIME_PER_QUARTER = 96_000
QUALITY = {0: "maj", 1: "min"}


def _floats(text: str, name: str) -> list[float]:
    try:
        values = [float(v) for v in text.split()]
    except ValueError as e:
        raise ValueError(f"a chord file's {name} line is not numbers: {text.strip()!r}") from e
    if not all(math.isfinite(v) for v in values):
        raise ValueError(f"a chord file's {name} line holds a number that is not finite: {text.strip()!r}")
    return values


def _field(block: str, name: str) -> list[float] | None:
    m = re.search(rf"^\s*{name}\s+(.*)$", block, re.M)
    return None if m is None else _floats(m.group(1), name)


def chords(text: str) -> tuple[tuple[float, float, Chord], ...]:
    """Each chord's start and end in quarter notes, and the chord; refused for text with no ``ChordList`` or
    ``OrgChord`` line."""
    text = text.replace("\r", "")
    if "OrgChord" in text:
        rows = [_numbers(m.group(1), "OrgChord") for m in re.finditer(r"^\s*OrgChord\s+(.*)$", text, re.M)]
        if not rows:
            raise ValueError("a chord file that names OrgChord holds no OrgChord line")
        return tuple(_chord(root, bass, flag, start, None if i == len(rows) - 1 and end == 0 else end)
                     for i, (root, bass, flag, start, *_, end) in enumerate(rows))
    if "ChordList" not in text:
        raise ValueError("not a chord file: no ChordList or OrgChord line")
    out = []
    for block in re.split(r"Chord \{", text)[1:]:
        note, time, ttime = _field(block, "Note"), _field(block, "Time"), _field(block, "TTime")
        if time is None and ttime is not None and len(ttime) == 4:
            time = [ttime[0] + ttime[1] / TTIME_PER_QUARTER, ttime[2] + ttime[3] / TTIME_PER_QUARTER]
        if note is None or len(note) != 3 or time is None or len(time) != 2:
            raise ValueError("a chord file's Chord block needs Note root bass flag and Time start end")
        out.append(_chord(*note, *time))
    return tuple(out)


def _numbers(text: str, name: str) -> list[float]:
    values = _floats(text, name)
    if len(values) != 11:
        raise ValueError(f"a chord file's {name} line has {len(values)} numbers, not 11")
    return values


def _chord(root: float, bass: float, flag: float, start: float, end: float | None) -> tuple[float, float | None, Chord]:
    root, bass, flag = int(root), int(bass), int(flag)
    if not (0 <= root < 12 and 0 <= bass < 12 and flag in QUALITY and 0 <= start and (end is None or start < end)):
        raise ValueError(f"a chord file holds Note {root} {bass} {flag}, Time {start:g} {end or 0:g}: "
                         "pitch classes 0-11, a flag of 0 or 1, and a start before its end")
    return start, end, Chord(root, QUALITY[flag], None if bass == root else bass)


def columns(found: tuple[tuple[float, float | None, Chord], ...] | None, bars: int, ppq: int,
            length: float | None = None) -> dict:
    """A row's `CHORD_COLUMNS`: the chords as JSON ``[start, end, symbol]`` in ticks at ``ppq``, an open last chord
    ending at ``length`` quarters and left out when it starts there or later, chord changes per bar, and the first
    chord's quality — major or minor by its third, None when it has neither. All None with no chords."""
    found = tuple((s, length if e is None else e, c) for s, e, c in found or () if e is not None or length is not None)
    found = tuple((s, e, c) for s, e, c in found if s < e)
    if not found:
        return dict.fromkeys(CHORD_COLUMNS)
    third = found[0][2].third
    quality = None if third is None else QUALITIES[(third - found[0][2].root) % 12 == 3]
    changed = sum(a[2] != b[2] for a, b in pairwise(found))
    return {"chords": json.dumps([[round(s * ppq), round(e * ppq), str(c)] for s, e, c in found]),
            "changes": round(changed / bars, 3) if bars else None, "quality": quality}


def read_beside(groove: Path) -> tuple[tuple[float, float, Chord], ...] | None:
    """The chords in the chord file beside ``groove``; None when there is none."""
    path = groove.with_suffix(SIDECAR)
    return chords(path.read_text(encoding="utf-8", errors="replace")) if path.is_file() else None
