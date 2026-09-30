"""A bassline picked bar by bar from a bass library's own bars — a picker, not a model. Each drum bar takes the
library bar whose onsets best meet its kicks, or the bar that followed the last pick in its own groove when that
is within a step of the best; the picked notes are re-voiced from the chords they were played over onto the
chart's. Keyswitches and controllers travel as they are, a poly-aftertouch key following its note, and each bar
starts under the vibrato, sustain, damping and pitch bend its source played it with."""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, replace
from pathlib import Path

from ..events import Event, Note
from ..harmony import Chord, Span, parse_chord, revoice
from ..maps import note_map
from ..timing import MeterMap
from .groove import Bar, bar_distance
from .index import PPQ
from .pattern import SIXTEENTH, Pattern, bar_ticks, meter_text, pattern
from .search import full_rows

FOLLOW_SLACK = 1.0
CHANNEL = 1
CHASED = (1, 64, 67)
REST = {**{("control", n): (n, 0) for n in CHASED}, ("bend",): (0, 64)}


@dataclass(frozen=True, slots=True)
class BassBar:
    key: str
    id: str
    index: int
    count: int
    steps: int
    onsets: int
    notes: tuple[Note, ...]
    chords: tuple[tuple[int, int, Chord], ...]
    map: str
    events: tuple[Event, ...] = ()
    chase: tuple[Event, ...] = ()


@dataclass(frozen=True, slots=True)
class BassPick:
    bar: BassBar
    distance: float


def load_bass_bars(db_path: Path, *, sig: tuple[int, int], role: str | None = None, category: str | None = None,
                   tempo: str | None = None) -> list[BassBar]:
    """Every bar in ``sig`` of the patterns that follow a bass map and have chords, with a played note; each bar's
    notes and chords are in ticks from its bar line at the index's PPQ, a note played early for a bar's line in it
    (`_bar_notes`)."""
    steps, span, out = 16 * sig[0] // sig[1], bar_ticks(sig), []
    for row in full_rows(db_path, meter=meter_text(sig), role=role, category=category, tempo=tempo):
        if not row["chords"] or not row["map"] or note_map(row["map"]).kind != "bass":
            continue
        kit, p = note_map(row["map"]), pattern(row)
        if any(s != sig for s in p.bars):
            continue
        labels = [(s, e, parse_chord(c)) for s, e, c in json.loads(row["chords"])]
        for i in range(len(p.bars)):
            lo, notes = i * span, _bar_notes(p, i, span)
            played = [n for n in notes if not kit.is_keyswitch(n.pitch)]
            chords = tuple((max(s, lo) - lo, min(e, lo + span) - lo, c) for s, e, c in labels if s < lo + span and e > lo)
            if not played or not chords:
                continue
            onsets = 0
            for n in played:
                if (step := (n.tick + SIXTEENTH // 2) // SIXTEENTH) < steps:
                    onsets |= 1 << step
            out.append(BassBar(row["key"], row["id"], i, len(p.bars), steps, onsets, notes, chords, row["map"],
                               tuple(p.bar_events(i)), _chase(p.events, lo)))
    if not out:
        raise ValueError(f"no bass bars with chords in the index for {meter_text(sig)}: index a bass library with "
                         "its chord files and a bass map (--map ezbass)")
    return out


def _bar_notes(p: Pattern, index: int, span: int) -> tuple[Note, ...]:
    """Bar ``index``'s notes, ticks from its line: a note within half a sixteenth before a line starts the bar after
    it, at a negative tick, and the last bar's goes to the first, as the groove loops."""
    edge, total, lo = SIXTEENTH // 2, span * len(p.bars), index * span
    looped = (replace(n, tick=n.tick - total) if n.tick >= total - edge else n for n in p.notes)
    return tuple(sorted((replace(n, tick=n.tick - lo) for n in looped if lo - edge <= n.tick < lo + span - edge),
                        key=lambda n: n.tick))


def _follows(bar: BassBar, after: BassBar) -> bool:
    return bar.key == after.key and bar.index == (after.index + 1) % after.count


def pick_bass(pool: list[BassBar], targets: tuple[Bar, ...], *, seed: int) -> list[BassPick]:
    """For each drum bar, the pool bar whose onsets are nearest its kicks (`groove.bar_distance`), or the bar after
    the last pick in its own pattern when that is within `FOLLOW_SLACK` of the nearest; ties go to the seed."""
    if seed < 0:
        raise ValueError(f"seed {seed}: a seed is 0 or more")
    rng, picks, previous = random.Random(seed), [], None
    for number, target in enumerate(targets, 1):
        kicks = Bar(target.steps, target.kick, 0, 0)
        scored = [(bar_distance(Bar(b.steps, b.onsets, 0, 0), kicks), b) for b in pool if b.steps == target.steps]
        if not scored:
            raise ValueError(f"bar {number} of the drums has {target.steps} sixteenths and no bass bar has as many")
        best = min(d for d, _b in scored)
        follow = next(((d, b) for d, b in scored if previous and _follows(b, previous)), None)
        distance, chosen = (follow if follow and follow[0] <= best + FOLLOW_SLACK
                            else rng.choice([(d, b) for d, b in scored if d == best]))
        picks.append(BassPick(chosen, distance))
        previous = chosen
    return picks


def _state(e: Event) -> tuple | None:
    if e.kind == "control" and e.number in CHASED:
        return ("control", e.number)
    return ("bend",) if e.kind == "bend" else None


def _chase(events: tuple[Event, ...], before: int) -> tuple[Event, ...]:
    """The last event of each chased controller, and of pitch bend, before tick ``before``."""
    last = {key: e for e in sorted(events, key=lambda e: e.tick) if e.tick < before and (key := _state(e))}
    return tuple(last[key] for key in REST if key in last)


def _fold(pitch: int, register: tuple[int, int]) -> int:
    while pitch < register[0]:
        pitch += 12
    while pitch > register[1]:
        pitch -= 12
    return pitch


def _event(e: Event, tick: int, key: int | None) -> Event:
    data = bytes([e.data[0] & 0xF0 | CHANNEL - 1, *(e.data[1:] if key is None else (key, *e.data[2:]))])
    return Event(tick, data)


def lay(picks: list[BassPick], spans: list[Span], meters: MeterMap, ppq: int, register: tuple[int, int],
        map_name: str) -> tuple[tuple[Note, ...], tuple[Event, ...]]:
    """The picks laid bar after bar at ``ppq`` on ``meters``, on channel 1: each played note re-voiced from the chord
    under it in its source onto the chart's chord at its new place and folded by octaves into ``register``;
    keyswitches of ``map_name`` and channel events as they were, but for a poly-aftertouch key, which takes the new
    pitch of the note it touches. A note played early takes the chord at its bar's line. A pick not followed by the
    next bar of its own groove ends its notes by the next pick's first played note; a note before the first line is
    held there."""
    if register[1] - register[0] < 11:
        raise ValueError(f"a register of {register[0]}-{register[1]}: a register spans at least an octave")
    kit, notes, events, state = note_map(map_name), [], [], dict(REST)
    lines = [meters.bar_line(bar) for bar in range(1, len(picks) + 1)]
    firsts = [min((line + n.tick * ppq // PPQ for n in pick.bar.notes if not kit.is_keyswitch(n.pitch)), default=None)
              for line, pick in zip(lines, picks, strict=True)]
    for bar, pick in enumerate(picks, 1):
        line, moved = lines[bar - 1], {}
        cut = firsts[bar] if bar < len(picks) and not _follows(picks[bar].bar, pick.bar) else None
        wanted = REST | {_state(e): tuple(e.data[1:]) for e in pick.bar.chase}
        own = {_state(e) for e in pick.bar.events if e.tick == 0}
        for key, value in wanted.items():
            if state[key] != value and key not in own:
                status = 0xB0 if key[0] == "control" else 0xE0
                events.append(Event(line, bytes([status | CHANNEL - 1, *value])))
                state[key] = value
        for n in pick.bar.notes:
            tick, length = max(line + n.tick * ppq // PPQ, 0), max(n.length * ppq // PPQ, 1)
            if cut is not None:
                length = max(min(length, cut - tick), 1)
            pitch = n.pitch
            if not kit.is_keyswitch(n.pitch):
                source = next((c for s, e, c in pick.bar.chords if s <= n.tick < e), pick.bar.chords[0][2])
                target = next((s.chord for s in spans if s.start <= max(tick, line) < s.end), spans[-1].chord)
                pitch = _fold(revoice(n.pitch, source, target), register)
            moved[n] = pitch
            notes.append(replace(n, tick=tick, length=length, pitch=pitch, channel=CHANNEL))
        for e in pick.bar.events:
            touched = next((moved[n] for n in moved if e.kind == "polytouch" and n.pitch == e.pitch
                            and n.tick <= e.tick < n.end), None)
            events.append(_event(e, line + e.tick * ppq // PPQ, touched))
            if key := _state(e):
                state[key] = tuple(e.data[1:])
    return tuple(sorted(notes, key=lambda n: (n.tick, n.pitch))), tuple(events)
