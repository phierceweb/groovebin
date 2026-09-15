"""Terminal output for the `groovebin` commands."""

from __future__ import annotations

from collections import Counter

from .maps import stroke
from .song import Song, meter_map, tempo_map


def joined(items: list[object]) -> str:
    words = [str(i) for i in items]
    return words[0] if len(words) == 1 else f"{', '.join(words[:-1])} and {words[-1]}"


def remap_report(*, notes: int, unmapped: Counter, src: str, dst: str, nested: int, orphans: int,
                 rule: str = "keep") -> list[str]:
    line = f"{notes - sum(unmapped.values())} of {notes} note(s) remapped {src} -> {dst}"
    if unmapped:
        kept = ", ".join(f"{pitch} x{count}" for pitch, count in sorted(unmapped.items()))
        line += f"; no {dst} counterpart, {'pitch kept' if rule == 'keep' else 'dropped'}: {kept}"
    lines = [line]
    if nested:
        lines.append(f"{nested} same-pitch note(s) now start inside a longer one and end before it: "
                     "a reader pairs note-offs first in, first out, so those lengths read back swapped")
    if orphans:
        lines.append(f"{orphans} note-off(s) with no note before them were dropped")
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
