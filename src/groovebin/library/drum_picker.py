"""Drum bars picked to a typed kick and snare — a picker, not a model. The sequence of pool bars with the fewest
sixteenths where a typed lane and the bar differ, a change of pattern costing one such step, so one pattern plays
in its own order for as long as it fits."""

from __future__ import annotations

import random
from collections.abc import Sequence

from . import groove
from .generate import FILL_EVERY, Pick, Pool, nearest
from .index import MAX_BARS
from .pattern import SIXTEENTH, bar_ticks

CHANGE = 1
KICK, SNARE = groove.VOICES.index("kick"), groove.VOICES.index("snare")


def pick_drums(pool: Pool, bars: int, rng: random.Random, *, fills: bool = False, rhythm: Sequence[groove.Bar],
               voices: Sequence[int]) -> list[Pick]:
    """``bars`` picks for ``rhythm``, its bars repeating, read on the ``voices`` given (kick, snare or both). Each
    step where a bar's lane differs from the typed one costs 1, and so does each bar that is not the one after the
    pick before it in its own pattern; among sequences of equal cost, the one entering fewer patterns past their
    first bar, then the one ``rng`` favours. With ``fills`` every fourth bar is the fill nearest the bar it
    replaces, as `generate` picks it. A pick's distance is its steps off."""
    if not 1 <= bars <= MAX_BARS:
        raise ValueError(f"a phrase of {bars} bar(s): 1 to {MAX_BARS}")
    if not rhythm or not set(voices) <= {KICK, SNARE} or not voices:
        raise ValueError("a typed rhythm gives a kick lane, a snare lane or both")
    steps = bar_ticks(pool.sig) // SIXTEENTH
    for number, typed in enumerate(rhythm, 1):
        if typed.steps != steps:
            raise ValueError(f"bar {number} of the rhythm has {typed.steps} step(s): a bar of {pool.sig[0]}/{pool.sig[1]} "
                             f"has {steps}")
    lane = (1 << steps) - 1
    care = (lane if KICK in voices else 0) | (lane << steps if SNARE in voices else 0)
    targets = [(typed.kick | typed.snare << steps) & care for typed in rhythm]
    states = pool.bars
    count = len(states)
    at = {id(b): i for i, b in enumerate(states)}
    before = [at[id(pool.patterns[b.key][(b.index - 1) % b.count])] for b in states]
    rank = list(range(count))
    rng.shuffle(rank)
    late, unit = count * (bars + 1), count * (bars + 1) * (bars + 1)
    entry = [rank[i] + (late if b.index else 0) for i, b in enumerate(states)]
    off = [[((b.onsets ^ t) & care).bit_count() for b in states] for t in targets]
    cost = [off[0][i] * unit + entry[i] for i in range(count)]
    came: list[list[int]] = []
    for k in range(1, bars):
        steps_off = off[k % len(targets)]
        best = min(range(count), key=cost.__getitem__)
        jump = cost[best] + CHANGE * unit
        new, back = [0] * count, [0] * count
        for i in range(count):
            stay = cost[before[i]]
            if stay <= jump + entry[i]:
                new[i], back[i] = steps_off[i] * unit + stay, before[i]
            else:
                new[i], back[i] = steps_off[i] * unit + jump + entry[i], best
        cost = new
        came.append(back)
    i = min(range(count), key=cost.__getitem__)
    path = [i]
    for back in reversed(came):
        i = back[i]
        path.append(i)
    picks = []
    for k, i in enumerate(reversed(path)):
        bar = states[i]
        if fills and (k + 1) % FILL_EVERY == 0:
            fill, near = nearest(pool.fills, bar.onsets, rng)
            picks.append(Pick(fill, True, near, bar))
        else:
            picks.append(Pick(bar, False, off[k % len(targets)][i]))
    return picks
