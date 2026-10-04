"""Scales and keys: the notes a key holds, steps along it, a file's key signatures named, and the scale a line
holds."""

from __future__ import annotations

import statistics
from collections.abc import Iterable
from dataclasses import dataclass, field

from ..events import Note
from .chords import CHORD_NAMES, pitch_class

MAJOR_PROFILE = (6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88)
MINOR_PROFILE = (6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17)


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
    """The major key and its relative minor, the minor spelled as the major's signature spells it."""
    name = _spelled(major, False)
    return f"{name} major / {from_signature(MAJOR_KEYS[name], True).name} minor"


SCALES = {"major": (0, 2, 4, 5, 7, 9, 11), "minor": (0, 2, 3, 5, 7, 8, 10), "dorian": (0, 2, 3, 5, 7, 9, 10),
          "phrygian": (0, 1, 3, 5, 7, 8, 10), "lydian": (0, 2, 4, 6, 7, 9, 11), "mixolydian": (0, 2, 4, 5, 7, 9, 10),
          "locrian": (0, 1, 3, 5, 6, 8, 10), "harmonic-minor": (0, 2, 3, 5, 7, 8, 11),
          "melodic-minor": (0, 2, 3, 5, 7, 9, 11), "major-pentatonic": (0, 2, 4, 7, 9),
          "minor-pentatonic": (0, 3, 5, 7, 10), "blues": (0, 3, 5, 6, 7, 10)}
KIND_ALIASES = {"ionian": "major", "aeolian": "minor"}
MODES = {"major": 0, "dorian": 2, "phrygian": 4, "lydian": 5, "mixolydian": 7, "minor": 9, "locrian": 11}
MAJOR_KEYS = {"Cb": -7, "Gb": -6, "Db": -5, "Ab": -4, "Eb": -3, "Bb": -2, "F": -1, "C": 0, "G": 1, "D": 2, "A": 3,
              "E": 4, "B": 5, "F#": 6, "C#": 7}
MINOR_KEYS = {"Ab": -7, "Eb": -6, "Bb": -5, "F": -4, "C": -3, "G": -2, "D": -1, "A": 0, "E": 1, "B": 2, "F#": 3,
              "C#": 4, "G#": 5, "D#": 6, "A#": 7}


def _spelled(tonic: int, minor: bool) -> str:
    """The tonic's name in a key signature: the fewer sharps or flats, `CHORD_NAMES`'s spelling on a tie."""
    table = MINOR_KEYS if minor else MAJOR_KEYS
    return min((n for n in table if pitch_class(n) == tonic), key=lambda n: (abs(table[n]), n != CHORD_NAMES[tonic]))


@dataclass(frozen=True, slots=True)
class Scale:
    tonic: int
    kind: str = "major"
    spelling: str | None = field(default=None, compare=False)

    def __post_init__(self) -> None:
        if self.kind not in SCALES:
            raise ValueError(f"no scale {self.kind!r}: {', '.join(SCALES)}")
        if not 0 <= self.tonic <= 11:
            raise ValueError(f"a tonic of {self.tonic} is not a pitch class 0-11")

    @property
    def steps(self) -> tuple[int, ...]:
        return SCALES[self.kind]

    @property
    def pitch_classes(self) -> frozenset[int]:
        return frozenset((self.tonic + s) % 12 for s in self.steps)

    @property
    def name(self) -> str:
        if self.spelling:
            return self.spelling
        return _spelled(self.tonic, self.kind == "minor") if self.kind in ("major", "minor") else CHORD_NAMES[self.tonic]

    def __str__(self) -> str:
        return f"{self.name} {self.kind}"

    def signature(self) -> tuple[int, bool]:
        """(sharps, minor) for a major or minor key, flats below 0, from the tonic as spelled."""
        if self.kind not in ("major", "minor"):
            raise ValueError(f"{self} has no key signature: a file's key signature is major or minor")
        table = MINOR_KEYS if self.kind == "minor" else MAJOR_KEYS
        if self.name not in table:
            raise ValueError(f"{self} has no key signature: spell it {_spelled(self.tonic, self.kind == 'minor')} "
                             f"{self.kind}")
        return table[self.name], self.kind == "minor"

    def below(self, pitch: int) -> tuple[int, int]:
        """(step, offset): the scale note at or below ``pitch`` as a step count `at` reads back, and ``pitch``'s
        semitones above that note."""
        octave, within = divmod(pitch - self.tonic, 12)
        degree = max(d for d, s in enumerate(self.steps) if s <= within)
        return octave * len(self.steps) + degree, within - self.steps[degree]

    def at(self, step: int) -> int:
        octave, degree = divmod(step, len(self.steps))
        return self.tonic + 12 * octave + self.steps[degree]


def parse_key(text: str) -> Scale:
    """``A minor``, ``F# dorian`` or a bare ``Bb`` (major) as a Scale, the tonic kept as written."""
    words = text.split()
    if not 1 <= len(words) <= 2:
        raise ValueError(f"{text.strip()!r} is not a key: a note and a scale, such as A minor or F# dorian")
    name = words[0][:1].upper() + words[0][1:]
    kind = words[1].lower() if len(words) == 2 else "major"
    return Scale(pitch_class(name), KIND_ALIASES.get(kind, kind), name)


def from_signature(sharps: int, minor: bool) -> Scale:
    """A file's key signature as its major or minor Scale, spelled as the signature spells it."""
    if not -7 <= sharps <= 7:
        raise ValueError(f"a key signature of {sharps} sharps is not -7 to 7")
    table = MINOR_KEYS if minor else MAJOR_KEYS
    name = next(n for n, s in table.items() if s == sharps)
    return Scale(pitch_class(name), "minor" if minor else "major", name)


def signature_name(sharps: int, minor: bool) -> str:
    return str(from_signature(sharps, minor))
