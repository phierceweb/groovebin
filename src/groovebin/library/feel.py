"""One part's feel laid on another, as a groove template: at each voice's eighth or sixteenth of the bar, where
a reference part strikes against that grid line and how hard against its voice's average. Voices come from the
drum map — kick, snare, hands and the rest; with no map every note is one voice."""

from __future__ import annotations

import json
import statistics
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import NamedTuple

from ..events import Note
from ..midi import read
from ..song import merged, meter_map
from ..timing import MeterMap
from .groove import VOICES, subdivision, voices
from .blobs import unpack_notes
from .index import PPQ

GRIDS = (8, 16)
ANY = "*"
OTHER = "other"
REACH = 1 / 3


@dataclass(frozen=True)
class Template:
    grid: int
    places: Mapping[tuple[str, int, int], tuple[float, float]]


@dataclass(frozen=True)
class Felt:
    notes: tuple[Note, ...]
    moved: int
    unmatched: int
    held: int


class Place(NamedTuple):
    bar: int
    steps: int
    step: int
    offset: float


def grid_of(notes: Iterable[Note], meters: MeterMap, map_name: str | None) -> int:
    """16 when the hands play sixteenths, or with no map to find the hands; else 8."""
    return 16 if map_name is None or subdivision(notes, meters, map_name) == "16ths" else 8


def _voice(pitch: int, table: Mapping[int, int] | None) -> str:
    if table is None:
        return ANY
    voice = table.get(pitch)
    return OTHER if voice is None else VOICES[voice]


def _place(tick: int, meters: MeterMap, grid: int) -> Place | None:
    """The grid line nearest ``tick``: its bar, the bar's grid steps, the step and the tick's offset from it. A
    tick rounding onto the next bar line is that bar's step 0; None in a bar with no whole number of steps."""
    spacing = meters.ppq * 4 / grid
    bar = meters.bar_of(tick)
    step = round((tick - meters.bar_line(bar)) / spacing)
    num, den = meters.meter_at(meters.bar_line(bar))
    if step >= grid * num / den:
        bar, step = bar + 1, 0
        num, den = meters.meter_at(meters.bar_line(bar))
    if grid * num % den:
        return None
    return Place(bar, grid * num // den, step, tick - meters.bar_line(bar) - step * spacing)


def template(notes: Iterable[Note], meters: MeterMap, bars: int, map_name: str | None, *, grid: int) -> Template:
    """The feel of ``notes`` in their first ``bars`` bars on a grid of ``grid`` to the whole note: at each voice's
    grid line in each length of bar, the median offset from it in ticks at 960 PPQ — so a triplet's first partial
    does not cancel a shuffle's off-beat — and the mean velocity over that voice's mean, and the same over every
    note together under `ANY`. A note halfway between lines is left out, and so is one whose voice (with no map, its
    pitch) strikes nearer the same line in its bar; of two as near, the later counts."""
    if grid not in GRIDS:
        raise ValueError(f"a grid of {grid}: a template takes a grid of 8 or 16")
    table = voices(map_name) if map_name else None
    spacing = meters.ppq * 4 / grid
    nearest: dict[tuple[str | int, int, int], tuple[tuple[float, float], Note, Place]] = {}
    for n in notes:
        place = _place(n.tick, meters, grid) if n.tick >= 0 else None
        if place is None or place.bar > bars or 2 * abs(place.offset) >= spacing:
            continue
        voice = _voice(n.pitch, table)
        rival, rank = (voice if voice in VOICES else n.pitch, place.bar, place.step), (abs(place.offset), -place.offset)
        if rival not in nearest or rank < nearest[rival][0]:
            nearest[rival] = (rank, n, place)
    offsets: dict[tuple[str, int, int], list[float]] = defaultdict(list)
    loud: dict[tuple[str, int, int], list[int]] = defaultdict(list)
    level: dict[str, list[int]] = defaultdict(list)
    for _rank, n, place in nearest.values():
        for voice in {_voice(n.pitch, table), ANY}:
            offsets[(voice, place.steps, place.step)].append(place.offset * PPQ / meters.ppq)
            loud[(voice, place.steps, place.step)].append(n.velocity)
            level[voice].append(n.velocity)
    means = {voice: statistics.fmean(v) for voice, v in level.items()}
    places = {key: (statistics.median(offsets[key]), statistics.fmean(loud[key]) / means[key[0]]) for key in offsets}
    return Template(grid, MappingProxyType(places))


def file_template(data: bytes, map_name: str | None, *, grid: int | None = None) -> Template:
    """The template of a whole file, its tracks merged, in its own meters; ``grid`` as `grid_of` finds it."""
    song = read(data)
    part, meters = merged(song), meter_map(song)
    bars = meters.bar_of(max(n.tick for n in part.notes)) if part.notes else 0
    return template(part.notes, meters, bars, map_name, grid=grid or grid_of(part.notes, meters, map_name))


def pattern_template(row: dict, *, grid: int | None = None) -> Template:
    """The template of a library row (`search.get`), read through the row's own map."""
    if row.get("error") or not row.get("bars"):
        raise ValueError(f"pattern {row['id']} holds no notes to take a feel from")
    notes = unpack_notes(row["notes"])
    meters = MeterMap(PPQ, tuple(tuple(c) for c in json.loads(row["meters"])))
    return template(notes, meters, row["bars"], row.get("map"), grid=grid or grid_of(notes, meters, row.get("map")))


def _entry(tpl: Template, voice: str, place: Place | None, spacing: float) -> tuple[str, int, int] | None:
    if place is None or abs(place.offset) > spacing * REACH:
        return None
    return next((key for key in ((voice, place.steps, place.step), (ANY, place.steps, place.step))
                 if key in tpl.places), None)


def apply_feel(notes: Iterable[Note], meters: MeterMap, tpl: Template, map_name: str | None, *,
               timing: float = 1.0, velocity: float = 1.0) -> Felt:
    """``notes`` given ``tpl``'s feel. A note within a third of a grid step of a line the template knows — for its
    voice, else for `ANY` — moves ``timing`` of the way to the template's offset there and ``velocity`` of the way to
    its accent around the notes' own mean for that voice. Any other note is left alone and counted, and a note
    that would move before tick 0 is held there and counted."""
    for share, name in ((timing, "timing"), (velocity, "velocity")):
        if not 0 <= share <= 1:
            raise ValueError(f"{name} {share:g}: a share from 0 to 1")
    notes, table = list(notes), voices(map_name) if map_name else None
    level: dict[str, list[int]] = defaultdict(list)
    for n in notes:
        for voice in {_voice(n.pitch, table), ANY}:
            level[voice].append(n.velocity)
    means = {voice: statistics.fmean(v) for voice, v in level.items()}
    out, moved, unmatched, held = [], 0, 0, 0
    for n in notes:
        place, voice = _place(n.tick, meters, tpl.grid) if n.tick >= 0 else None, _voice(n.pitch, table)
        key = _entry(tpl, voice, place, meters.ppq * 4 / tpl.grid)
        if key is None:
            unmatched += 1
            out.append(n)
            continue
        offset, accent = tpl.places[key]
        tick = round(n.tick + (offset * meters.ppq / PPQ - place.offset) * timing)
        if tick < 0:
            tick, held = 0, held + 1
        loudness = round(n.velocity + (means[voice] * accent - n.velocity) * velocity)
        moved += tick != n.tick
        out.append(replace(n, tick=tick, velocity=min(max(loudness, 1), 127)))
    return Felt(tuple(out), moved, unmatched, held)
