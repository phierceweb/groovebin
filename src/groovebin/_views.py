"""Terminal output for the `groovebin` commands."""

from __future__ import annotations

from collections import Counter

from .maps import stroke
from .song import Song, meter_map, tempo_map


def joined(items: list[object]) -> str:
    words = [str(i) for i in items]
    return words[0] if len(words) == 1 else f"{', '.join(words[:-1])} and {words[-1]}"


def nested_warning(count: int) -> str:
    """The line a command prints when its input or output holds same-pitch notes a reader cannot
    pair back with certainty."""
    return (f"{count} same-pitch note pair(s) start inside a longer one and end before it: "
            "a reader pairs note-offs first in, first out, so those lengths read as swapped")


def orphan_warning(count: int) -> str:
    return f"{count} note-off(s) with no note before them were dropped"


def meter_warning(count: int) -> str:
    """The line a command that shows bar positions prints when the file holds a time signature the
    meter map cannot use."""
    return (f"{count} time signature(s) were skipped — too few bytes to read, a zero numerator, a "
            "denominator past 64, or a bar this PPQ cannot hold in whole ticks: bars are counted in "
            "the meters that remain")


def remap_report(*, notes: int, unmapped: Counter, src: str, dst: str, nested: int, orphans: int,
                 rule: str = "keep", folded: dict[int, list[int]] | None = None) -> list[str]:
    line = f"{notes - sum(unmapped.values())} of {notes} note(s) remapped {src} -> {dst}"
    if unmapped:
        kept = ", ".join(f"{pitch} x{count}" for pitch, count in sorted(unmapped.items()))
        line += f"; no {dst} counterpart, {'pitch kept' if rule == 'keep' else 'dropped'}: {kept}"
    lines = [line]
    for target, sources in sorted((folded or {}).items()):
        lines.append(f"{src} pitches {', '.join(map(str, sources))} all land on {dst} {target}")
    if nested:
        lines.append(nested_warning(nested))
    if orphans:
        lines.append(orphan_warning(orphans))
    return lines


def listing(name: str, song: Song, tracks: list[int], map_name: str | None) -> list[str]:
    meters = meter_map(song)
    num, den = meters.meter_at(0)
    lines = [f"{name}: format {song.format}, PPQ {song.ppq}, {len(song.tracks)} track(s), "
             f"{tempo_map(song).bpm(0):g} bpm, {num}/{den}"]
    for i in tracks:
        part = song.tracks[i]
        label = f" {part.name!r}" if part.name else ""
        lines.append(f"track {i + 1}{label}: {len(part.notes)} note(s), {len(part.events)} other event(s)")
        for n in part.notes:
            line = (f"  bar {meters.bar(n.tick):8.3f}  ch {n.channel:2d}  note {n.pitch:3d}  "
                    f"vel {n.velocity:3d}  len {n.length:6d}")
            if map_name:
                line += f"  {stroke(map_name, n.pitch) or '-'}"
            lines.append(line)
    return lines


def presets(items) -> list[str]:
    width = max(len(p.name) for p in items)
    out = []
    for p in items:
        if p.takes == "none":
            value = ""
        elif p.takes == "int?":
            value = "  (=VALUE, optional)"
        elif p.default is None:
            value = "  (=VALUE, required)"
        else:
            shown = ",".join(f"{k}={v}" for k, v in zip(("pos", "vel", "len"), p.default, strict=True)) if p.takes == "humanize" \
                else (f"{p.default[0]:.0%}:1/{p.default[1]}" if p.takes == "swing"
                      else (f"{p.default[0]}..{p.default[1]}" if p.takes == "lo..hi" else f"{p.default:g}"))
            value = f"  (=VALUE, default {shown})"
        out.append(f"{p.name:{width}s}  {p.about}{value}")
    return out


def transform_report(number: int, name: str | None, selected: int, total: int, steps: list[str]) -> str:
    label = f" {name!r}" if name else ""
    return f"track {number}{label}: {selected} of {total} note(s) selected; {'; '.join(steps)}"


# The library says "part"; the command line says "track".
SPOKEN = (("the part's", "the track's"), ("the part is", "the track is"), ("a part at", "a track at"),
          ("the whole part", "the whole track"), ("where a part starts", "where a track starts"))


def spoken(text: str) -> str:
    for inner, outer in SPOKEN:
        text = text.replace(inner, outer)
    return text
