"""Pitch classes, note names, chords and chord charts. A pitch class is 0-11 from C."""

from __future__ import annotations

import re
from dataclasses import dataclass

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
