"""Note maps — what each note plays on an instrument — and translation between them.

Each map gives some notes a term, space-separated words from general to specific ("hihat",
"hihat open", "hihat open b"). A note translates to the destination note with the same term;
failing that, one whose term extends it; failing that, the term less its last word, and so on.
Among several candidates the map's ``prefer`` names the note, else the lowest wins. A stroke that
is not a strike (a choke, a stick click) leads its term with that word, and dropping words stops
before that word stands alone, so it never lands on a hit or on another piece's stroke of that kind.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable, Iterator, Mapping
from typing import Any
from dataclasses import dataclass, replace
from functools import cache
from importlib.resources import files
from types import MappingProxyType

from .events import Event
from .song import Part

NAMES = ("gm", "addictive-drums-2", "drum-kit-designer")
NOT_STRIKES = ("choke", "sticks")
POLYTOUCH = 0xA0
UNMAPPED = ("keep", "drop")


@dataclass(frozen=True)
class DrumMap:
    name: str
    source: str
    notes: Mapping[int, Mapping[str, Any]]
    prefer: Mapping[str, int]

    def term(self, note: int) -> str | None:
        """The note's term; a duplicate takes its original's."""
        row = self.notes.get(note, {})
        if "duplicate_of" in row:
            row = self.notes[row["duplicate_of"]]
        return row.get("term")

    def stroke(self, note: int) -> str | None:
        """What the note plays, in the source's own words."""
        row = self.notes.get(note)
        if row is None:
            return None
        if "name" in row:
            return row["name"]
        if row["stroke"] == "(brushes only)":
            return f"{row['piece']} {row['brushes']} (brushes only)"
        return row["piece"] if row["stroke"] == "-" else f"{row['piece']} {row['stroke']}"

    def terms(self) -> tuple[str, ...]:
        return tuple(sorted({row["term"] for row in self.notes.values() if "term" in row}))

    def find(self, term: str) -> int | None:
        """The note for ``term``: an exact match, else one that extends it, ``prefer`` first."""
        own = {n: row["term"] for n, row in self.notes.items() if "term" in row}
        for hits in ([n for n, t in own.items() if t == term],
                     [n for n, t in own.items() if t.startswith(term + " ")]):
            if hits:
                return self.prefer[term] if self.prefer.get(term) in hits else min(hits)
        return None

    def family(self, word: str) -> tuple[int, ...]:
        """Every note, duplicates included, whose term starts with ``word``."""
        return tuple(sorted(n for n in self.notes if (self.term(n) or "").split()[:1] == [word]))


@cache
def drum_map(name: str) -> DrumMap:
    if name not in NAMES:
        raise ValueError(f"no note map {name!r}; one of {', '.join(NAMES)}")
    raw = json.loads(files("groovebin").joinpath(f"data/maps/{name}.json").read_text(encoding="utf-8"))
    notes = {int(n): MappingProxyType(row) for n, row in raw["notes"].items()}
    return DrumMap(name, raw["source"], MappingProxyType(notes), MappingProxyType(raw["prefer"]))


def maps() -> dict[str, DrumMap]:
    return {name: drum_map(name) for name in NAMES}


def stroke(map_name: str, note: int) -> str | None:
    return drum_map(map_name).stroke(note)


@cache
def translate(note: int, src: str, dst: str) -> int | None:
    """The ``dst`` note for ``src``'s ``note``, or None when no term leads there."""
    term, target = drum_map(src).term(note), drum_map(dst)
    words = term.split() if term else []
    fewest = 2 if len(words) > 1 and words[0] in NOT_STRIKES else 1
    while len(words) >= fewest:
        found = target.find(" ".join(words))
        if found is not None:
            return found
        words.pop()
    return None


def _translated_keys(part: Part) -> Iterator[tuple[int, int]]:
    """Every (pitch, channel) a remap translates: a note's pitch, a polytouch event's key."""
    for n in part.notes:
        yield n.pitch, n.channel
    for e in part.events:
        if e.data[0] & 0xF0 == POLYTOUCH:
            yield e.pitch, e.channel


def landings(part: Part, src: str, dst: str, *, channels: Iterable[int] | None = None,
             unmapped: str = "keep") -> dict[tuple[int, int], set[int]]:
    """{(channel, destination pitch): the ``src`` pitches that land there} for one Part. A pitch with
    no counterpart lands on itself while ``unmapped`` keeps it; dropped, it lands nowhere. A caller
    covering several Parts merges these before asking `folds`, since a channel is one instrument
    however many tracks drive it."""
    check_unmapped(unmapped)
    scope = None if channels is None else set(channels)
    landed: dict[tuple[int, int], set[int]] = {}
    for pitch, channel in _translated_keys(part):
        if scope is not None and channel not in scope:
            continue
        new = translate(pitch, src, dst)
        if new is None:
            if unmapped == "drop":
                continue
            new = pitch
        landed.setdefault((channel, new), set()).add(pitch)
    return landed


def folds(landed: Mapping[tuple[int, int], set[int]]) -> dict[int, list[int]]:
    """The destination notes more than one source pitch lands on, on one channel: {target: [sources]}.
    A remap says nothing about these on its own — three toms to one is still "3 of 3 remapped"."""
    out: dict[int, set[int]] = {}
    for (_channel, target), sources in landed.items():
        if len(sources) > 1:
            out.setdefault(target, set()).update(sources)
    return {target: sorted(sources) for target, sources in sorted(out.items())}


def collisions(part: Part, src: str, dst: str, *, channels: Iterable[int] | None = None,
               unmapped: str = "keep") -> dict[int, list[int]]:
    """`folds` of one Part's `landings`. One pitch on two channels is two voices and does not fold."""
    return folds(landings(part, src, dst, channels=channels, unmapped=unmapped))


def check_unmapped(rule: str) -> None:
    if rule not in UNMAPPED:
        raise ValueError(f"unmapped notes are kept or dropped, not {rule!r}")


def remap(part: Part, src: str, dst: str, *, channels: Iterable[int] | None = None,
          unmapped: str = "keep") -> tuple[Part, Counter]:
    """The Part with every note's pitch, and every polyphonic aftertouch key, translated from
    ``src`` to ``dst`` on ``channels`` (all when None). A note with no counterpart is counted by
    pitch and kept at its pitch, or dropped with its aftertouch when ``unmapped`` is "drop"; nothing
    else changes."""
    for name in (src, dst):
        drum_map(name)
    check_unmapped(unmapped)
    if src == dst:
        raise ValueError(f"a remap from {src} to {src} would still move notes: its duplicates and "
                         "prefers translate too; name two different maps")
    scope = None if channels is None else set(channels)
    for channel in scope or ():
        if not 1 <= channel <= 16:
            raise ValueError(f"channel {channel} is not 1-16")
    missing: Counter = Counter()
    notes = []
    for n in part.notes:
        if scope is None or n.channel in scope:
            new = translate(n.pitch, src, dst)
            if new is None:
                missing[n.pitch] += 1
                if unmapped == "drop":
                    continue
            else:
                n = replace(n, pitch=new)
        notes.append(n)
    events = [e for e in (_polytouch(e, src, dst, scope, unmapped) for e in part.events) if e is not None]
    return replace(part, notes=tuple(notes), events=tuple(events)), missing


def _polytouch(e: Event, src: str, dst: str, scope: set[int] | None, unmapped: str) -> Event | None:
    if e.data[0] & 0xF0 != POLYTOUCH or (scope is not None and e.channel not in scope):
        return e
    new = translate(e.pitch, src, dst)
    if new is None:
        return None if unmapped == "drop" else e
    return replace(e, data=bytes([e.data[0], new, e.data[2]]))
