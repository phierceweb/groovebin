"""Transforms that know a key: scale quantize, diatonic transpose, and a change of key or mode. Each moves a note by
its pitch and the key in force at its tick and leaves every other field alone."""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Callable, Sequence
from dataclasses import replace

from ..events import Event
from ..harmony import Scale, from_signature
from ..song import Part, key_signature
from .edits import POLYTOUCH, Mask, masked

Keys = Scale | Sequence[tuple[int, Scale]]
Hold = Callable[[int], bool]


def _never(pitch: int) -> bool:
    return False


def key_at(keys: Keys, tick: int) -> Scale:
    """The key in force at ``tick``: a single Scale, or the last of tick-ordered key points at or before it, the
    first applying before it."""
    if isinstance(keys, Scale):
        return keys
    if not keys:
        raise ValueError("no key to move notes in")
    ticks = [t for t, _ in keys]
    if ticks != sorted(ticks):
        raise ValueError("key points are not in tick order")
    return keys[max(bisect_right(ticks, tick) - 1, 0)][1]


def quantized(pitch: int, scale: Scale) -> int:
    """``pitch`` itself when ``scale`` holds it, else the nearer scale note inside 0-127, the lower on a tie."""
    step, offset = scale.below(pitch)
    if not offset:
        return pitch
    lower, upper = pitch - offset, scale.at(step + 1)
    if lower < 0 or upper > 127:
        return upper if lower < 0 else lower
    return lower if offset <= upper - pitch else upper


def stepped(pitch: int, scale: Scale, steps: int) -> int:
    """``pitch`` moved ``steps`` along ``scale``; one outside it keeps its offset above the scale note below it."""
    step, offset = scale.below(pitch)
    return scale.at(step + steps) + offset


def _move(source: Scale, target: Scale) -> int:
    return (target.tonic - source.tonic + 6) % 12 - 6


def moved_key(pitch: int, source: Scale, target: Scale) -> int:
    """``pitch`` at its degree and offset in ``target``, the tonic moved the shorter way, down on a tritone."""
    if len(source.steps) != len(target.steps):
        raise ValueError(f"{source} has {len(source.steps)} notes and {target} {len(target.steps)}: a change of key "
                         "keeps each degree, so the scales need as many notes")
    step, offset = source.below(pitch)
    octave, degree = divmod(step, len(source.steps))
    return source.tonic + _move(source, target) + 12 * octave + target.steps[degree] + offset


def _checked(pitch: int, new: int, what: str) -> int:
    if not 0 <= new <= 127:
        raise ValueError(f"{what} {pitch} would move to {new}, outside 0-127")
    return new


def _pitched(part: Part, mask: Mask | None, move: Callable[[int, int], int], hold: Hold) -> Part:
    """Each chosen note at ``move(pitch, tick)`` and, with no mask, each polyphonic aftertouch key; a held pitch
    stays."""
    chosen = masked(part, mask)
    notes = tuple(replace(n, pitch=_checked(n.pitch, move(n.pitch, n.tick), "note"))
                  if i in chosen and not hold(n.pitch) else n for i, n in enumerate(part.notes))
    if mask is not None:
        return replace(part, notes=notes)
    events = tuple(replace(e, data=bytes([e.data[0], _checked(e.pitch, move(e.pitch, e.tick), "aftertouch key"),
                                          e.data[2]]))
                   if e.data[0] & 0xF0 == POLYTOUCH and not hold(e.pitch) else e for e in part.events)
    return replace(part, notes=notes, events=events)


def scale_quantize(part: Part, mask: Mask | None, keys: Keys, *, hold: Hold = _never) -> Part:
    """Each selected note outside its key moved to the nearer scale note, the lower on a tie."""
    return _pitched(part, mask, lambda pitch, tick: quantized(pitch, key_at(keys, tick)), hold)


def diatonic(part: Part, mask: Mask | None, steps: int, keys: Keys, *, hold: Hold = _never) -> Part:
    """Each selected note moved ``steps`` along its key's scale."""
    return _pitched(part, mask, lambda pitch, tick: stepped(pitch, key_at(keys, tick), steps), hold)


def change_key(part: Part, source: Keys, target: Scale, *, hold: Hold = _never, at: int | None = None) -> Part:
    """Every note and aftertouch key from the key in force at ``at`` — the part's first note, else tick 0 — to
    ``target``. With a major or minor ``target``, the key signature in force at ``at`` becomes the target's and the
    part's others move by the same interval; on a change of mode, those in other keys are left as they were."""
    at = (part.notes[0].tick if part.notes else 0) if at is None else at
    first = key_at(source, at)
    moved = _pitched(part, None, lambda pitch, tick: moved_key(pitch, first, target), hold)
    signatures = [(e.tick, found) for e in moved.events if (found := key_signature(e))]
    if target.kind not in ("major", "minor") or not signatures:
        return moved
    base = from_signature(*next((found for t, found in reversed(signatures) if t <= at), signatures[0][1]))
    events = tuple(_resigned(e, found, base, target) if (found := key_signature(e)) else e for e in moved.events)
    return replace(moved, events=events)


def _resigned(e: Event, found: tuple[int, bool], base: Scale, target: Scale) -> Event:
    """A key signature after ``base``, the one in force where the change is read, becomes ``target``: ``base``
    itself is the target's, another key moves by the same interval, or stays when the change is one of mode."""
    key = from_signature(*found)
    if (key.tonic, key.kind) == (base.tonic, base.kind):
        new = target
    elif base.kind != target.kind:
        return e
    else:
        new = Scale((key.tonic + target.tonic - base.tonic) % 12, key.kind)
    sharps, minor = new.signature()
    return replace(e, data=bytes([0xFF, 0x59, 2, sharps & 0xFF, int(minor)]))
