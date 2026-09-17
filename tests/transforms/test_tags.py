"""Every transform keeps a note's and an event's ``tag``: a consumer hangs the bytes it must not
touch, and a selection's identity, on it."""

import pytest

from groovebin import transforms as t
from groovebin.events import Event, Note
from groovebin.maps import remap
from groovebin.song import Part
from groovebin.timing import MeterMap

METERS = MeterMap(960, ())


def tagged() -> Part:
    notes = tuple(Note(k * 480, 240, 10, 36 + k, 100, tag=f"n{k}") for k in range(4))
    events = (Event(0, b"\xb9\x07\x64", tag="e0"), Event(480, b"\xa9\x25\x30", tag="e1"))
    return Part(960, notes, events, end=3840)


CASES = {
    "transpose": lambda p: t.transpose(p, 2),
    "scale_velocity": lambda p: t.scale_velocity(p, 1.1, 2),
    "shift": lambda p: t.shift(p, 10),
    "delete": lambda p: t.delete(p, 36)[0],
    "quantize": lambda p: t.quantize(p, 240, METERS),
    "merge": lambda p: t.merge(p, tagged(), 3840),
    "stretch": lambda p: t.stretch(p, 2.0),
    "note_lengths": lambda p: t.note_lengths(p, None, percent=50.0),
    "velocity_curve": lambda p: t.velocity_curve(p, None, floor=10, ceiling=100),
    "swing": lambda p: t.swing(p, 480, 0.6, METERS),
    "apply_all": lambda p: t.apply_all(p, None, [t.Operation("velocity", "add", 1)]),
    "run": lambda p: t.run(p, None, "fixed-velocity", 100),
    "humanize": lambda p: t.humanize(p, None, position=1, seed=1),
    "remap": lambda p: remap(p, "gm", "addictive-drums-2")[0],
}


@pytest.mark.parametrize("name", sorted(CASES))
def test_every_transform_keeps_the_tags(name):
    part = tagged()
    out = CASES[name](part)
    assert out.notes, name
    assert all(n.tag is not None for n in out.notes), name
    assert {n.tag for n in out.notes} <= {n.tag for n in part.notes} | {n.tag for n in tagged().notes}
    assert all(e.tag is not None for e in out.events), name
    assert {e.tag for e in out.events} <= {e.tag for e in part.events}
