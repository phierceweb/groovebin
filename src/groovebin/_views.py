"""Terminal output for the `groovebin` commands."""

from __future__ import annotations

from collections import Counter

from .harmony import signature_name
from .maps import stroke
from .song import Song, key_map, meter_map, tempo_map


def joined(items: list[object]) -> str:
    words = [str(i) for i in items]
    return words[0] if len(words) == 1 else f"{', '.join(words[:-1])} and {words[-1]}"


def ambiguous_warning(count: int) -> str:
    """The line a command prints when its input left same-pitch notes' pairing open."""
    return (f"{count} note-off(s) in the input found more than one note of their pitch open: a reader pairs them "
            "first in, first out, so those lengths are one reading of the file")


def nested_warning(count: int) -> str:
    """The line a command prints when its output holds same-pitch notes a reader cannot pair back."""
    return (f"{count} same-pitch note pair(s) now start inside a longer one and end before it: "
            "a reader pairs note-offs first in, first out, so those lengths read back swapped")


def orphan_warning(count: int) -> str:
    return f"{count} note-off(s) with no note before them were dropped"


def meter_warning(count: int) -> str:
    """The line a command that shows bar positions prints when the file holds a time signature the
    meter map cannot use."""
    return (f"{count} time signature(s) were skipped — too few bytes to read, a zero numerator, a "
            "denominator past 64, or a bar this PPQ cannot hold in whole ticks: bars are counted in "
            "the meters that remain")


def clock(seconds: float) -> str:
    """``m:ss.mmm``, a minus sign below 0."""
    ms = round(abs(seconds) * 1000)
    return f"{'-' if seconds < 0 else ''}{ms // 60_000}:{ms % 60_000 / 1000:06.3f}"


def tempo_warning(count: int) -> str:
    return f"{count} tempo event(s) were skipped — a tempo of 0, or not three bytes"


def key_warning(count: int) -> str:
    return (f"{count} key signature(s) were skipped — not two bytes, more than seven sharps or flats, or a mode "
            "other than major or minor")


def remap_report(*, notes: int, unmapped: Counter, src: str, dst: str, nested: int, orphans: int,
                 rule: str = "keep", folded: dict[int, list[int]] | None = None, ambiguous: int = 0) -> list[str]:
    line = f"{notes - sum(unmapped.values())} of {notes} note(s) remapped {src} -> {dst}"
    if unmapped:
        kept = ", ".join(f"{pitch} x{count}" for pitch, count in sorted(unmapped.items()))
        line += f"; no {dst} counterpart, {'pitch kept' if rule == 'keep' else 'dropped'}: {kept}"
    lines = [line]
    for target, sources in sorted((folded or {}).items()):
        lines.append(f"{src} pitches {', '.join(map(str, sources))} all land on {dst} {target}")
    if ambiguous:
        lines.append(ambiguous_warning(ambiguous))
    if nested:
        lines.append(nested_warning(nested))
    if orphans:
        lines.append(orphan_warning(orphans))
    return lines


def listing(name: str, song: Song, tracks: list[int], map_name: str | None) -> list[str]:
    meters, tempos = meter_map(song), tempo_map(song)
    num, den = meters.meter_at(0)
    head = (f"{name}: format {song.format}, PPQ {song.ppq}, {len(song.tracks)} track(s), "
            f"{tempos.bpm(0):g} bpm, {num}/{den}")
    if (key := key_map(song).at(0)) is not None:
        head += f", {signature_name(*key)}"
    lines = [head]
    for i in tracks:
        part = song.tracks[i]
        label = f" {part.name!r}" if part.name else ""
        lines.append(f"track {i + 1}{label}: {len(part.notes)} note(s), {len(part.events)} other event(s)")
        for n in part.notes:
            line = (f"  bar {meters.bar(n.tick):8.3f}  {clock(tempos.seconds(n.tick, song.ppq)):>9}  "
                    f"ch {n.channel:2d}  note {n.pitch:3d}  vel {n.velocity:3d}  len {n.length:6d}")
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
        elif p.takes in ("int?", "key?"):
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


def felt(source: str, grid: int, notes: int, moved: int, unmatched: int, held: int) -> str:
    line = f"feel of {source} on {'an eighth' if grid == 8 else 'a sixteenth'}-note grid: {moved} of {notes} note(s) moved"
    if unmatched:
        line += f", {unmatched} left as they were, with no reference feel at their place"
    if held:
        line += f", {held} held at the start"
    return line


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
