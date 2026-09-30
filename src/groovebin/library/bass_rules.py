"""A bassline by rules, over a drum part's kicks and a chord chart. The rates are EZbass's own grooves' (docs):
the chord's bass note on every change, chord tones between changes by how often those grooves play them, and an
approach note one or two sixteenths before a change."""

from __future__ import annotations

import random
from dataclasses import dataclass

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


@dataclass(frozen=True)
class BassLine:
    notes: tuple[Note, ...]
    on_kicks: int
    on_changes: int
    approaches: int
    mutes: int


def _degree(chord: Chord, rng: random.Random) -> int:
    targets = {"root": chord.root, "fifth": chord.fifth, "third": chord.third, "seventh": chord.seventh}
    kind = rng.choices(list(DEGREES), weights=list(DEGREES.values()))[0]
    return chord.root if targets[kind] is None else targets[kind]


def _nearest(pc: int, previous: int | None, register: tuple[int, int]) -> int:
    """The pitch of ``pc`` inside ``register`` nearest the note before it — the first a third of the way up."""
    aim = register[0] + (register[1] - register[0]) // 3 if previous is None else previous
    return min((p for p in range(register[0], register[1] + 1) if p % 12 == pc), key=lambda p: (abs(p - aim), p))


def bass_line(kicks: list[tuple[int, int]], snares: list[int], spans: list[Span], ppq: int, *, seed: int,
              approach: float = APPROACH_RATE, register: tuple[int, int] = REGISTER, mute: int | None = None) -> BassLine:
    """A note on every kick ``(tick, velocity)`` inside the chords; the chord's bass note on its first beat and on
    every change, whether a kick is there or not; a chord tone between. With probability ``approach`` a change the
    line has not reached in the two sixteenths before it gets an approach note there. Pitches take the octave
    nearest the note before, inside ``register``; each note lasts to the next, two beats at most. ``mute`` is a
    keyswitch put on every snare with no bass note within a 32nd of it. The same inputs and seed give the same
    line."""
    if not spans:
        raise ValueError("a bassline needs chords: no chords given")
    if seed < 0:
        raise ValueError(f"seed {seed}: a seed is 0 or more")
    if register[1] - register[0] < 11:
        raise ValueError(f"a register of {register[0]}-{register[1]}: a register spans at least an octave")
    if not 0 <= approach <= 1:
        raise ValueError(f"an approach rate of {approach:g}: 0 to 1")
    rng, window, end = random.Random(seed), ppq // 8, spans[-1].end
    changes = [s for i, s in enumerate(spans) if i == 0 or s.chord.lowest != spans[i - 1].chord.lowest]
    onsets: dict[int, tuple[int, bool]] = {}
    for tick, velocity in sorted(kicks):
        if spans[0].start <= tick < end and not any(abs(tick - t) <= window for t in onsets):
            onsets[tick] = (velocity, True)
    for s in changes:
        near = [onsets.pop(t) for t in [t for t in onsets if abs(t - s.start) <= window]]
        onsets[s.start] = (near[0][0], True) if near else (CHANGE_VELOCITY, False)
    starts = {s.start for s in changes}
    planned: list[tuple[int, int, int]] = []
    for tick in sorted(onsets):
        span = next(s for s in spans if s.start <= tick < s.end)
        pc = span.chord.lowest if tick in starts else _degree(span.chord, rng)
        planned.append((tick, pc, onsets[tick][0]))
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
        notes.append(Note(tick, min(following - tick, 2 * ppq), CHANNEL, pitch, min(max(velocity, 1), 127)))
        previous = pitch
    mutes = [t for t in sorted(set(snares)) if spans[0].start <= t < end and not any(abs(t - n.tick) <= window
                                                                                      for n in notes)]
    if mute is not None:
        notes += [Note(t, MUTE_LENGTH, CHANNEL, mute, CHANGE_VELOCITY) for t in mutes]
    return BassLine(tuple(sorted(notes, key=lambda n: (n.tick, n.pitch))), sum(on for _v, on in onsets.values()),
                    len(changes) - 1, approaches, len(mutes) if mute is not None else 0)
