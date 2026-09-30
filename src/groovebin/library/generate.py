"""A drum phrase picked bar by bar from real library bars: a picker, not a model. After the first bar, each
pick has the kick and snare onsets nearest those of the bar after the previous pick in its own pattern (a
pattern's last bar is followed by its first). With fills, a fill bar stands in for every fourth bar and the
chain carries on from the groove bar it replaces. Fill rows give only their fill bar, to the fill pool."""

from __future__ import annotations

import math
import random
import re
import statistics
from collections import Counter
from collections.abc import Iterable
from itertools import pairwise
from dataclasses import dataclass, replace
from functools import cache
from pathlib import Path

from ..events import Event, Note
from ..maps import check_unmapped, drum_map, translate
from .groove import HANDS, voices
from ..song import Part, Song
from .index import MAX_BARS, PPQ
from .pattern import SIXTEENTH, bar_ticks, meter_text, pattern
from .search import full_rows

TIMING, VELOCITY = 5, 6
FILL_EVERY = 4
DEFAULT_TEMPO = 120.0


@dataclass(frozen=True, slots=True)
class Bar:
    key: str
    id: str
    index: int
    count: int
    notes: tuple[Note, ...]
    onsets: int
    tempo: float | None
    map: str


@dataclass(frozen=True)
class Pool:
    sig: tuple[int, int]
    patterns: dict[str, tuple[Bar, ...]]
    fills: tuple[Bar, ...]
    left_out: int

    @property
    def bars(self) -> tuple[Bar, ...]:
        return tuple(b for bars in self.patterns.values() for b in bars)

    @property
    def maps(self) -> tuple[str, ...]:
        return tuple(sorted({b.map for b in (*self.bars, *self.fills)}))

    def following(self, bar: Bar) -> Bar:
        bars = self.patterns[bar.key]
        return bars[(bar.index + 1) % len(bars)]


@dataclass(frozen=True, slots=True)
class Pick:
    bar: Bar
    fill: bool
    distance: int | None
    replaces: Bar | None = None


@dataclass(frozen=True)
class Phrase:
    seed: int
    sig: tuple[int, int]
    picks: tuple[Pick, ...]
    notes: tuple[Note, ...]
    unmapped: dict[int, int]
    tempo: float
    map: str
    unmapped_rule: str = "keep"
    crashes: tuple[int, ...] = ()
    level: float | None = None

    @property
    def ticks(self) -> int:
        return len(self.picks) * bar_ticks(self.sig)


def parse_meter(text: str) -> tuple[int, int]:
    m = re.fullmatch(r"\s*(\d+)\s*/\s*(\d+)\s*", text)
    num, den = (int(m.group(1)), int(m.group(2))) if m else (0, 0)
    if not (num and den and den & (den - 1) == 0 and bar_ticks((num, den)) >= SIXTEENTH):
        raise ValueError(f"bad meter {text!r}: N/D with D a power of two and a bar of at least a sixteenth note")
    return num, den


@cache
def families(map_name: str) -> tuple[frozenset[int], frozenset[int]]:
    """The notes ``map_name`` calls kick, and those it calls snare."""
    m = drum_map(map_name)
    return frozenset(m.family("kick")), frozenset(m.family("snare"))


def onsets(notes: Iterable[Note], steps: int, kick_snare: tuple[frozenset[int], frozenset[int]]) -> int:
    """Kick onsets as bits 0 to ``steps - 1``, snare onsets above them; a note rounding onto the bar's
    end belongs to the next downbeat and is not counted."""
    kick, snare = kick_snare
    bits = 0
    for n in notes:
        step = (n.tick + SIXTEENTH // 2) // SIXTEENTH
        if step < steps and n.pitch in kick:
            bits |= 1 << step
        elif step < steps and n.pitch in snare:
            bits |= 1 << (steps + step)
    return bits


def _bar(row: dict, index: int, count: int, notes: list[Note], sig: tuple[int, int]) -> Bar:
    return Bar(row["key"], row["id"], index, count, tuple(notes),
               onsets(notes, bar_ticks(sig) // SIXTEENTH, families(row["map"])), row["tempo"], row["map"])


def load_pool(db_path: Path, *, sig: tuple[int, int], category: str | None = None, role: str | None = None,
              tempo: str | None = None, intensity: str | None = None, fills: bool = False) -> Pool:
    """The bars the filters give; an empty beat pool, or an empty fill pool when ``fills``, is refused
    with the filters named. ``role`` holds groove patterns to it and fills to it or to no role."""
    filters = {"category": category, "meter": meter_text(sig), "role": role, "tempo": tempo, "intensity": intensity}
    patterns, fill_bars, left_out = {}, [], 0
    for row in full_rows(db_path, **{k: v for k, v in filters.items() if k != "role"}):
        if role is not None and (row["role"] or "") != role.strip().lower() and not (row["is_fill"] and row["role"] is None):
            continue
        if not row["map"]:
            raise ValueError(f"pattern {row['id']} has no drum map: generating needs one to find its kick and snare")
        p = pattern(row)
        if any(s != sig for s in p.bars):
            left_out += 1
        elif p.is_fill:
            if (index := p.fill_bar_index()) is not None:
                fill_bars.append(_bar(row, index, len(p.bars), p.fill_bar(), sig))
        else:
            patterns[row["key"]] = tuple(_bar(row, i, len(p.bars), p.bar_notes(i), sig) for i in range(len(p.bars)))
    echo = ", ".join(f"{k} {v}" if k == "meter" else f"{k} {v!r}" for k, v in filters.items() if v is not None)
    if not patterns:
        raise ValueError(f"no beat bars in the index for {echo}")
    if fills and not fill_bars:
        raise ValueError(f"no fill bars in the index for {echo}")
    return Pool(sig, patterns, tuple(fill_bars), left_out)


def _nearest(candidates: tuple[Bar, ...], target: int, rng: random.Random) -> tuple[Bar, int]:
    distances = [(b.onsets ^ target).bit_count() for b in candidates]
    low = min(distances)
    return rng.choice([b for b, d in zip(candidates, distances, strict=True) if d == low]), low


def generate(pool: Pool, bars: int, rng: random.Random, *, fills: bool = False) -> list[Pick]:
    if not 1 <= bars <= MAX_BARS:
        raise ValueError(f"a phrase of {bars} bar(s): 1 to {MAX_BARS}")
    grooves, picks, prev = pool.bars, [], None
    for i in range(bars):
        if prev is None:
            prev, distance = rng.choice([b for b in grooves if b.index == 0]), None
        else:
            prev, distance = _nearest(grooves, pool.following(prev).onsets, rng)
        if fills and (i + 1) % FILL_EVERY == 0:
            fill, near = _nearest(pool.fills, prev.onsets, rng)
            picks.append(Pick(fill, True, near, prev))
        else:
            picks.append(Pick(prev, False, distance))
    return picks


def humanise(notes: Iterable[Note], rng: random.Random, end: int, *, timing: int = TIMING,
             velocity: int = VELOCITY) -> list[Note]:
    """Each note moved by up to ``timing`` ticks and ``velocity``, in order, held to 0 up to ``end``
    and to 1-127."""
    return [replace(n, tick=min(max(n.tick + rng.randint(-timing, timing), 0), end - 1),
                    velocity=min(max(n.velocity + rng.randint(-velocity, velocity), 1), 127)) for n in notes]


def _level(notes: list[Note], map_name: str) -> float | None:
    kick, snare = families(map_name)
    velocities = [n.velocity for n in notes if n.pitch in kick or n.pitch in snare]
    return statistics.median(velocities) if velocities else None


def levelled(bars: list[list[Note]], maps: list[str]) -> tuple[list[list[Note]], float | None]:
    """Each bar's velocities scaled so its kick-and-snare median meets the first bar's that has one, and that
    median; a bar with no kick or snare is left as it is."""
    levels = [_level(bar, m) for bar, m in zip(bars, maps, strict=True)]
    target = next((lv for lv in levels if lv), None)
    if target is None:
        return bars, None
    return [[replace(n, velocity=min(max(round(n.velocity * target / lv), 1), 127)) for n in bar] if lv else bar
            for bar, lv in zip(bars, levels, strict=True)], target


def crashed(picks: list[Pick], bars: list[list[Note]], maps: list[str]) -> tuple[list[list[Note]], tuple[int, ...]]:
    """A crash — the bar's map's ``cymbal 1`` — on the downbeat of each bar after a fill, at the velocity of the
    loudest note there and on its channel (the bar's, else the fill's), and the bars (0-based) that took one. It
    takes a hat or ride stroke's place; a bar with a cymbal on its downbeat already is left alone."""
    bars, added = list(bars), []
    for k in range(1, len(picks)):
        kit = drum_map(maps[k])
        crash, on = kit.find("cymbal 1"), [n for n in bars[k] if n.tick < SIXTEENTH // 2]
        if not picks[k - 1].fill or crash is None or any(n.pitch in kit.family("cymbal") for n in on):
            continue
        hands = voices(maps[k])
        velocity = max((n.velocity for n in on), default=max((n.velocity for n in bars[k - 1]), default=100))
        kept = [n for n in bars[k] if not (n.tick < SIXTEENTH // 2 and hands.get(n.pitch) == HANDS)]
        channel = next((group[0].channel for group in (on, bars[k], bars[k - 1]) if group), 10)
        bars[k] = [*kept, Note(0, SIXTEENTH, channel, crash, velocity)]
        added.append(k)
    return bars, tuple(added)


def _ended(notes: list[Note]) -> list[Note]:
    """Each note ending by the next start of its channel and pitch, so a reader pairs every note-off with its own."""
    order: dict[tuple[int, int], list[int]] = {}
    for i, n in enumerate(notes):
        order.setdefault((n.channel, n.pitch), []).append(i)
    out = list(notes)
    for same in order.values():
        same.sort(key=lambda i: notes[i].tick)
        for a, b in pairwise(same):
            if notes[a].end > notes[b].tick:
                out[a] = replace(notes[a], length=max(notes[b].tick - notes[a].tick, 1))
    return out


def phrase(pool: Pool, *, bars: int, seed: int, fills: bool = False, map_name: str | None = None,
           unmapped: str = "keep", crash: bool = False, level: bool = False) -> Phrase:
    """``bars`` bars from ``pool``, humanised and written in ``map_name`` (the pool's own map when it has
    one); a note with no counterpart there is kept at its pitch or dropped, per ``unmapped``. With ``level``
    the bars are `levelled` first, and with ``crash`` each fill is followed by one (`crashed`). Every note ends by
    the next of its pitch (`_ended`). The same pool, seed and options give the same phrase; ``level`` leaves the
    picks and the timing as they are."""
    check_unmapped(unmapped)
    if seed < 0:
        raise ValueError(f"seed {seed}: a seed is 0 or more")
    if map_name is None and len(pool.maps) > 1:
        raise ValueError(f"the pool's patterns follow {' and '.join(pool.maps)}: name the map to write the phrase in")
    target_map = map_name or pool.maps[0]
    rng = random.Random(seed)
    picks = generate(pool, bars, rng, fills=fills)
    span, maps = bar_ticks(pool.sig), [p.bar.map for p in picks]
    per_bar, target, added = [list(p.bar.notes) for p in picks], None, ()
    if level:
        per_bar, target = levelled(per_bar, maps)
    if crash:
        per_bar, added = crashed(picks, per_bar, maps)
    laid = [replace(n, tick=k * span + n.tick) for k, bar in enumerate(per_bar) for n in bar]
    sources = [maps[k] for k, bar in enumerate(per_bar) for _n in bar]
    notes, missing = [], Counter()
    for n, src in zip(humanise(laid, rng, bars * span), sources, strict=True):
        new = n.pitch if src == target_map else translate(n.pitch, src, target_map)
        missing[n.pitch] += new is None
        if new is not None:
            notes.append(replace(n, pitch=new))
        elif unmapped == "keep":
            notes.append(n)
    tempo = picks[0].bar.tempo
    usable = tempo is not None and math.isfinite(tempo) and 60_000_000 / 0xFFFFFF < tempo <= 60_000_000
    return Phrase(seed, pool.sig, tuple(picks), tuple(_ended(notes)), dict(sorted((+missing).items())),
                  tempo if usable else DEFAULT_TEMPO, target_map, unmapped, added, target)


def phrase_song(ph: Phrase) -> Song:
    """``ph`` as a format 1 song at 960 PPQ: its tempo and meter on the conductor track, the notes after."""
    usec = round(60_000_000 / ph.tempo)
    num, den = ph.sig
    conductor = Part(PPQ, (), (Event(0, b"\xff\x51\x03" + usec.to_bytes(3, "big")),
                               Event(0, bytes([0xFF, 0x58, 4, num, den.bit_length() - 1, 24, 8]))))
    name = f"Generated {ph.seed}".encode("latin-1")
    drums = Part(PPQ, ph.notes, (Event(0, bytes([0xFF, 0x03, len(name)]) + name),), end=ph.ticks)
    return Song(PPQ, 1, (conductor, drums))
