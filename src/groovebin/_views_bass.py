"""Terminal output for the bass commands."""

from __future__ import annotations

from .library.bassline import BassReport
from .library.show import note_name


def rooted(name: str, bars: int, notes: int, keyswitches: int) -> str:
    left = f", {keyswitches} keyswitch(es) left out" if keyswitches else ""
    return f"{name}: {bars} bar(s), {notes} note(s){left}"


def written(drums: str, bars: int, line) -> str:
    text = (f"bass over {bars} bar(s) of {drums}: {len(line.notes) - line.mutes} note(s), {line.on_kicks} on a kick, "
            f"{line.on_changes} chord change(s), {line.approaches} approach note(s)")
    return text + (f", {line.mutes} snare mute(s)" if line.mutes else "")


def from_library(drums: str, bars: int, notes: int, keyswitches: int) -> str:
    return f"bass over {bars} bar(s) of {drums} from the library: {notes} note(s), {keyswitches} keyswitch(es)"


def picked(picks) -> list[str]:
    return [f"  bar {k:<3d} {p.bar.id} bar {p.bar.index + 1} of {p.bar.count}, {p.distance:g} onset step(s) from the kicks"
            for k, p in enumerate(picks, 1)]


def _share(value: float | None) -> str:
    return "-" if value is None else f"{round(100 * value)}%"


def analyzed(name: str, r: BassReport) -> list[str]:
    lines = [f"{name}: {r.bars} bar(s), {r.notes} note(s), {note_name(r.register[0])} to {note_name(r.register[1])}",
             f"rhythm  {r.onsets_per_bar:g} onset(s) a bar, {_share(r.on_beat)} on the beat"]
    if r.scale:
        lines.append(f"scale   {r.scale}")
    if r.with_kick is not None or r.kicks_followed is not None:
        lines.append(f"drums   {_share(r.with_kick)} of bass onsets on a kick, {_share(r.kicks_followed)} of kicks with a "
                     f"bass onset, {_share(r.on_snare)} of snares with one")
    if r.tones is not None:
        held = ", ".join(f"{degree} {_share(share)}" for degree, share in r.tones.items())
        change = ("no chord change to score" if r.on_change is None
                  else f"the new chord's bass note on {_share(r.on_change)} of {r.changes} change(s)")
        lines.append(f"chords  {change}; held on the {held}")
    if r.keyswitches:
        lines.append("keyswitches  " + ", ".join(f"{term} x{count}" for term, count in r.keyswitches.items()))
    return lines
