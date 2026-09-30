"""Pitch classes, chords and chord charts, and the chords a bassline implies. A pitch class is 0-11 from C."""

from __future__ import annotations

import re
import statistics
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

from .events import Note
from .timing import MeterMap

NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
CHORD_NAMES = ("C", "Db", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B")
LETTERS = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
QUALITIES = {"maj": (0, 4, 7), "min": (0, 3, 7), "dim": (0, 3, 6), "aug": (0, 4, 8), "sus2": (0, 2, 7),
             "sus4": (0, 5, 7), "5": (0, 7), "6": (0, 4, 7, 9), "min6": (0, 3, 7, 9), "7": (0, 4, 7, 10),
             "maj7": (0, 4, 7, 11), "min7": (0, 3, 7, 10), "m7b5": (0, 3, 6, 10), "dim7": (0, 3, 6, 9)}
SUFFIXES = {"maj": "", "min": "m", "dim": "dim", "aug": "aug", "sus2": "sus2", "sus4": "sus4", "5": "5", "6": "6",
            "min6": "m6", "7": "7", "maj7": "maj7", "min7": "m7", "m7b5": "m7b5", "dim7": "dim7"}
SPELLINGS = {"": "maj", "maj": "maj", "m": "min", "min": "min", "-": "min", "dim": "dim", "°": "dim", "aug": "aug",
             "+": "aug", "sus2": "sus2", "sus4": "sus4", "sus": "sus4", "5": "5", "6": "6", "m6": "min6",
             "min6": "min6", "7": "7", "maj7": "maj7", "M7": "maj7", "m7": "min7", "min7": "min7", "-7": "min7",
             "m7b5": "m7b5", "ø": "m7b5", "dim7": "dim7", "°7": "dim7"}
MAJOR_PROFILE = (6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88)
MINOR_PROFILE = (6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17)
SPLIT_SHARE = 0.8
START_WEIGHT = 3
THIRD_SHARE = 0.05
_NOTE = r"[A-Ga-g][#b]?"
_SYMBOL = re.compile(rf"^({_NOTE})([^/]*?)(?:/({_NOTE}))?$")


def _semitones(name: str) -> int:
    """A note name's semitones above the C of its octave: ``Cb`` is -1 and ``B#`` 12."""
    if not re.fullmatch(_NOTE, name):
        raise ValueError(f"{name!r} is not a note name")
    return LETTERS[name[0].upper()] + {"#": 1, "b": -1}.get(name[1:], 0)


def pitch_class(name: str) -> int:
    """``C#``, ``Db`` or ``db`` as its pitch class; one sharp or flat at most."""
    return _semitones(name) % 12


def note_number(text: str) -> int:
    """A note as its MIDI number: a name with its octave, C4 being 60 (``E1``, ``Bb0``), or the number itself."""
    text = text.strip()
    m = re.fullmatch(rf"({_NOTE})(-?\d+)", text)
    if not (m or text.isdigit()):
        raise ValueError(f"{text!r} is not a note: a name with its octave, such as E1, or a number")
    number = int(text) if text.isdigit() else _semitones(m.group(1)) + 12 * (int(m.group(2)) + 1)
    if not 0 <= number <= 127:
        raise ValueError(f"{text} is note {number}, not 0-127")
    return number


def scale_of(notes: Iterable[Note]) -> int | None:
    """The scale a line holds, by the tonic of its major key: Krumhansl and Kessler's key profiles against each
    pitch class's held length, the best of the 24 keys, a minor key given by its relative major. None for a line of
    fewer than two pitch classes, or of all twelve held as long."""
    held = [0.0] * 12
    for n in notes:
        held[n.pitch % 12] += n.length
    if sum(v > 0 for v in held) < 2 or min(held) == max(held):
        return None
    fits = [(statistics.correlation(held, [profile[(pc - tonic) % 12] for pc in range(12)]), (tonic + shift) % 12)
            for tonic in range(12) for profile, shift in ((MAJOR_PROFILE, 0), (MINOR_PROFILE, 3))]
    return max(fits)[1]


def scale_name(major: int) -> str:
    return f"{CHORD_NAMES[major]} major / {CHORD_NAMES[(major + 9) % 12]} minor"


def pitch_name(pitch: int) -> str:
    return NOTE_NAMES[pitch % 12]


@dataclass(frozen=True, slots=True)
class Chord:
    root: int
    quality: str = "maj"
    bass: int | None = None

    @property
    def tones(self) -> tuple[int, ...]:
        return tuple((self.root + step) % 12 for step in QUALITIES[self.quality])

    @property
    def lowest(self) -> int:
        """The pitch class a bass plays under the chord: the slash note, else the root."""
        return self.root if self.bass is None else self.bass

    @property
    def third(self) -> int | None:
        found = [s for s in QUALITIES[self.quality] if s in (3, 4)]
        return (self.root + found[0]) % 12 if found else None

    @property
    def fifth(self) -> int | None:
        found = [s for s in QUALITIES[self.quality] if s in (6, 7, 8)]
        return (self.root + found[0]) % 12 if found else None

    @property
    def seventh(self) -> int | None:
        found = [s for s in QUALITIES[self.quality] if s in (10, 11) or s == 9 and self.quality == "dim7"]
        return (self.root + found[0]) % 12 if found else None

    def __str__(self) -> str:
        slash = "" if self.bass is None else f"/{CHORD_NAMES[self.bass]}"
        return f"{CHORD_NAMES[self.root]}{SUFFIXES[self.quality]}{slash}"


def parse_chord(text: str) -> Chord:
    """A chord symbol — a root, a quality spelled as `SPELLINGS` knows it, an optional ``/bass`` — as a Chord."""
    m = _SYMBOL.match(text.strip())
    if not m or m.group(2) not in SPELLINGS:
        raise ValueError(f"{text.strip()!r} is not a chord symbol: a root, a quality such as m, 7 or maj7, and an "
                         "optional /bass")
    bass = None if m.group(3) is None else pitch_class(m.group(3))
    return Chord(pitch_class(m.group(1)), SPELLINGS[m.group(2)], bass)


def chart(text: str) -> list[tuple[Chord, ...]]:
    """A chord chart as bars of chords that share the bar evenly: ``| Am | F G | % |``, where ``%`` repeats the
    bar before it; without bar lines, a chord a bar."""
    if "|" in text:
        cells = [cell.split() for cell in text.split("|")]
        cells = cells[1:] if not cells[0] else cells
        cells = cells[:-1] if cells and not cells[-1] else cells
    else:
        cells = [[token] for token in text.split()]
    if not cells:
        raise ValueError("a chart with no chords: give chords, e.g. \"Am F C G\" or \"| Am | F G |\"")
    bars: list[tuple[Chord, ...]] = []
    for number, cell in enumerate(cells, 1):
        if not cell:
            raise ValueError(f"bar {number} of the chart is an empty bar")
        if cell == ["%"]:
            if not bars:
                raise ValueError("the chart's first bar is %: nothing to repeat")
            bars.append(bars[-1])
        else:
            bars.append(tuple(parse_chord(token) for token in cell))
    return bars



def revoice(pitch: int, source: Chord, target: Chord) -> int:
    """``pitch``, played over ``source``, moved to fit ``target``: the bass note to the new bass note, a third, fifth or
    seventh to the target's own, any other note with the root. The octave is the one nearest the pitch moved by the
    shorter of the two ways between the chords."""
    if (pitch - source.lowest) % 12 == 0:
        pc, move = target.lowest, target.lowest - source.lowest
    else:
        interval = (pitch - source.root) % 12
        degree = {3: target.third, 4: target.third, 6: target.fifth, 7: target.fifth, 8: target.fifth,
                  10: target.seventh, 11: target.seventh}.get(interval)
        pc, move = (target.root + interval) % 12 if degree is None else degree, target.root - source.root
    aim = pitch + (move + 6) % 12 - 6
    return min((aim + d for d in range(-6, 6) if (aim + d) % 12 == pc), key=lambda p: (abs(p - aim), p))


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
    if not held:
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
