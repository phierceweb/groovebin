"""A bassline by rules, over a drum part's kicks and a chord chart. The rates are EZbass's own grooves' (docs):
the chord's bass note on every change, chord tones between changes by how often those grooves play them, and an
approach note one or two sixteenths before a change."""

from __future__ import annotations

import random
from dataclasses import dataclass
from itertools import pairwise

from ..events import Note
from ..harmony import Chord, Span

DEGREES = {"root": 54.3, "fifth": 12.8, "third": 7.0, "seventh": 6.5}
APPROACHES = {-1: 13.1, 2: 11.4, 1: 11.3, -2: 8.0, 7: 15.0}
APPROACH_RATE = 0.588
REGISTER = (28, 50)
CHANNEL = 1
CHANGE_VELOCITY = 85
APPROACH_SHARE = 0.8
MUTE_LENGTH = 10
NO_APPROACH = "approach notes are not written with a push, roots only or a rest in the chart: give an approach rate of 0"


@dataclass(frozen=True)
class BassLine:
    notes: tuple[Note, ...]
    on_kicks: int
    on_changes: int
    approaches: int
    mutes: int
    on_snares: int | None = None
    pushes: int | None = None


def _degree(chord: Chord, rng: random.Random) -> int:
    targets = {"root": chord.root, "fifth": chord.fifth, "third": chord.third, "seventh": chord.seventh}
    kind = rng.choices(list(DEGREES), weights=list(DEGREES.values()))[0]
    return chord.root if targets[kind] is None else targets[kind]


def _nearest(pc: int, previous: int | None, register: tuple[int, int]) -> int:
    """The pitch of ``pc`` inside ``register`` nearest the note before it — the first a third of the way up."""
    aim = register[0] + (register[1] - register[0]) // 3 if previous is None else previous
    return min((p for p in range(register[0], register[1] + 1) if p % 12 == pc), key=lambda p: (abs(p - aim), p))


def bass_line(kicks: list[tuple[int, int]], snares: list[int], spans: list[Span], ppq: int, *, seed: int,
              approach: float | None = None, register: tuple[int, int] = REGISTER, mute: int | None = None,
              snare_hits: list[tuple[int, int]] | None = None, root_only: bool = False,
              push: bool = False) -> BassLine:
    """A note on the kicks ``(tick, velocity)`` inside the chords, and on ``snare_hits`` inside them; strokes within a
    32nd of each other or of a change can share one. The chord's bass note on its first beat and on every change (a
    new bass note), stroke or not; a chord tone between, or with ``root_only`` the bass note again. A gap between the
    chords is a rest: no note starts or rings in it, and the chord after it gets no note of its own: its first stroke
    takes its bass note. With ``push`` a note in the eighth before a change, or a 32nd ahead of that eighth, plays the
    new bass note — never across a rest, never a chord's first stroke after one, never a note on a change — and such a
    change loses the note it would get with no stroke's note on it. With probability ``approach`` (the measured rate
    by default) a change the line has not reached in the two sixteenths before it gets an approach note; with
    ``push``, ``root_only`` or a rest none is written: the default is 0 and a rate above it is refused. Pitches take
    the octave nearest the note before, inside ``register``; a note lasts to the next, two beats at most. ``mute`` is
    a keyswitch on every snare with no bass note within a 32nd of it, refused with ``snare_hits``. The same inputs and
    seed give the same line."""
    if not spans:
        raise ValueError("a bassline needs chords: no chords given")
    if seed < 0:
        raise ValueError(f"seed {seed}: a seed is 0 or more")
    if register[1] - register[0] < 11:
        raise ValueError(f"a register of {register[0]}-{register[1]}: a register spans at least an octave")
    rests = spans[0].start != 0 or any(before.end != s.start for before, s in pairwise(spans))
    apart = push or root_only or rests
    if approach is None:
        approach = 0 if apart else APPROACH_RATE
    if not 0 <= approach <= 1:
        raise ValueError(f"an approach rate of {approach:g}: 0 to 1")
    if approach and apart:
        raise ValueError(NO_APPROACH)
    if mute is not None and snare_hits is not None:
        raise ValueError("a mute goes on a snare the bass leaves open: with snare notes there is none")
    rng, window, end = random.Random(seed), ppq // 8, spans[-1].end

    def at(tick: int) -> Span | None:
        """The chord span ``tick`` plays in: its own, or the one starting within a 32nd after it."""
        return next((s for s in spans if s.start <= tick < s.end), None) or next(
            (s for s in spans if 0 < s.start - tick <= window), None)

    runs, begins = {}, {}
    for s in reversed(spans):
        runs[s.start] = runs.get(s.end, s.end)
    for before, s in pairwise([None, *spans]):
        begins[s.start] = begins[before.start] if before and before.end == s.start else s.start
    changes = [s for i, s in enumerate(spans) if i == 0 or s.chord.lowest != spans[i - 1].chord.lowest]
    onsets: dict[int, tuple[int, str | None]] = {}
    for source, strokes in (("kick", kicks), ("snare", snare_hits or ())):
        for tick, velocity in sorted(strokes):
            if at(tick) is not None and not any(abs(tick - t) <= window for t in onsets):
                onsets[tick] = (velocity, source)
    after_rest = {s.start for before, s in pairwise(spans) if before.end != s.start} | ({spans[0].start} - {0})
    starts, changed = set(), {s.start for s in changes}
    for s in spans:
        if s.start not in changed and s.start not in after_rest:
            continue
        near = [onsets.pop(t) for t in [t for t in onsets if abs(t - s.start) <= window]]
        if near or s.start not in after_rest:
            onsets[s.start] = near[0] if near else (CHANGE_VELOCITY, None)
        held = s.end
        for b in spans[spans.index(s) + 1:]:
            if b.start != held or b.chord.lowest != s.chord.lowest:
                break
            held = b.end
        starts.add(s.start if s.start in onsets else min((t for t in onsets if s.start <= t < held), default=s.start))
    planned: list[tuple[int, int, int]] = []
    for tick in sorted(onsets):
        span = at(tick)
        pc = span.chord.lowest if tick in starts or root_only else _degree(span.chord, rng)
        planned.append((tick, pc, onsets[tick][0]))
    moved = set()
    for s in changes[1:] if push else ():
        hit = [i for i, (tick, _pc, _v) in enumerate(planned)
               if s.start - ppq // 2 - window <= tick < s.start and tick not in starts and tick not in moved
               and begins[at(tick).start] == begins[s.start]]
        for i in hit:
            planned[i] = (planned[i][0], s.chord.lowest, planned[i][2])
        moved.update(planned[i][0] for i in hit)
        if hit and s.start in onsets and onsets[s.start][1] is None:
            planned = [p for p in planned if p[0] != s.start]
    approaches = 0
    for s in changes[1:]:
        lead = ppq // 4 * rng.choice((1, 2))
        if rng.random() >= approach or any(s.start - 2 * (ppq // 4) <= t < s.start for t, _pc, _v in planned):
            continue
        step = rng.choices(list(APPROACHES), weights=list(APPROACHES.values()))[0]
        before = max(((t, v) for t, _pc, v in planned if t < s.start), default=(0, CHANGE_VELOCITY))[1]
        planned.append((s.start - lead, (s.chord.lowest + step) % 12, round(before * APPROACH_SHARE)))
        approaches += 1
    planned.sort()
    notes, previous = [], None
    for i, (tick, pc, velocity) in enumerate(planned):
        pitch = _nearest(pc, previous, register)
        following = planned[i + 1][0] if i + 1 < len(planned) else end
        length = min(following - tick, 2 * ppq, max(runs[at(tick).start] - tick, 1))
        notes.append(Note(tick, length, CHANNEL, pitch, min(max(velocity, 1), 127)))
        previous = pitch
    mutes = [t for t in sorted(set(snares)) if any(s.start <= t < s.end for s in spans)
             and not any(abs(t - n.tick) <= window for n in notes)]
    if mute is not None:
        notes += [Note(t, MUTE_LENGTH, CHANNEL, mute, CHANGE_VELOCITY) for t in mutes]
    sources = [source for _v, source in onsets.values()]
    return BassLine(tuple(sorted(notes, key=lambda n: (n.tick, n.pitch))), sources.count("kick"), len(changes) - 1,
                    approaches, len(mutes) if mute is not None else 0,
                    sources.count("snare") if snare_hits is not None else None, len(moved) if push else None)
