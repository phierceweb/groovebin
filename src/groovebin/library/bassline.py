"""What a bassline does: its rhythm on its own, against a drum part's kick and snare, and against the chords it
plays under. Every share counts an onset within a 32nd note of the other as with it."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from itertools import pairwise
from dataclasses import dataclass, field, replace

from ..events import Note
from ..harmony import Span, scale_name, scale_of
from ..maps import drum_map as load_drum_map
from ..maps import note_map
from ..timing import MeterMap
from .groove import VOICES, beat_ticks, voices

@dataclass(frozen=True)
class BassReport:
    bars: int
    notes: int
    onsets_per_bar: float
    on_beat: float
    register: tuple[int, int]
    with_kick: float | None = None
    kicks_followed: float | None = None
    on_snare: float | None = None
    on_change: float | None = None
    changes: int | None = None
    tones: dict[str, float] | None = None
    keyswitches: dict[str, int] = field(default_factory=dict)
    scale: str | None = None


def _near(ticks: list[int], others: list[int], window: int) -> float | None:
    """The share of ``ticks`` within ``window`` of one of ``others``."""
    if not ticks:
        return None
    return round(sum(any(abs(t - o) <= window for o in others) for t in ticks) / len(ticks), 3)


def _beat_lines(meters: MeterMap, bars: int) -> list[int]:
    lines = []
    for bar in range(1, bars + 1):
        lo = meters.bar_line(bar)
        beat = beat_ticks(meters.meter_at(lo), meters.ppq)
        lines += [round(lo + k * beat) for k in range(round(meters.bar_ticks(lo) / beat))]
    return lines


def _tones(played: list[Note], spans: list[Span]) -> dict[str, float]:
    """How long the bass holds each of the chord's own degrees; a tone the chord lacks is "other"."""
    held: Counter[str] = Counter()
    for s in spans:
        c = s.chord
        degrees = {c.seventh: "seventh", c.fifth: "fifth", c.third: "third", c.root: "root"}
        for n in played:
            if n.tick < s.end and n.end > s.start:
                held[degrees.get(n.pitch % 12, "other")] += min(n.end, s.end) - max(n.tick, s.start)
    total = sum(held.values()) or 1
    return {degree: round(held[degree] / total, 3) for degree in ("root", "third", "fifth", "seventh", "other")}


def _on_change(played: list[Note], spans: list[Span], window: int) -> float | None:
    changes = [s for before, s in pairwise(spans) if s.chord.lowest != before.chord.lowest]
    if not changes:
        return None
    return round(sum(any(abs(n.tick - s.start) <= window and n.pitch % 12 == s.chord.lowest for n in played)
                     for s in changes) / len(changes), 3)


def analyze(bass: Iterable[Note], meters: MeterMap, bars: int, *, bass_map: str | None = None,
            drums: Iterable[Note] | None = None, drum_map: str | None = None,
            spans: list[Span] | None = None) -> BassReport:
    """``bass`` over its first ``bars`` bars, a keyswitch of ``bass_map`` counted by its term rather than played.
    With ``drums`` (read through ``drum_map``), how the bass sits with the kick and the snare; with chord ``spans``,
    how often a change has the new chord's bass note on it and how long the bass holds each chord degree."""
    kit = note_map(bass_map) if bass_map else None
    if kit is not None and kit.kind != "bass":
        raise ValueError(f"{bass_map} is a {kit.kind} map, not a bass map")
    end = meters.bar_line(bars + 1)
    notes = [n for n in bass if 0 <= n.tick < end]
    played = [n for n in notes if kit is None or not kit.is_keyswitch(n.pitch)]
    switches = Counter(kit.term(n.pitch) for n in notes if kit is not None and kit.is_keyswitch(n.pitch))
    onsets, window = sorted({n.tick for n in played}), meters.ppq // 8
    report = BassReport(bars, len(played), round(len(onsets) / bars, 2) if bars else 0.0,
                        _near(onsets, _beat_lines(meters, bars), window) or 0.0,
                        (min(n.pitch for n in played), max(n.pitch for n in played)) if played else (0, 0),
                        keyswitches=dict(sorted(switches.items())),
                        scale=None if (major := scale_of(played)) is None else scale_name(major))
    if drums is not None:
        if drum_map is None:
            raise ValueError("reading drums needs a drum map to find their kick and snare")
        load_drum_map(drum_map)
        table, drum_notes = voices(drum_map), [n for n in drums if 0 <= n.tick < end]
        kicks = sorted({n.tick for n in drum_notes if table.get(n.pitch) == VOICES.index("kick")})
        snares = sorted({n.tick for n in drum_notes if table.get(n.pitch) == VOICES.index("snare")})
        report = replace(report, with_kick=_near(onsets, kicks, window), kicks_followed=_near(kicks, onsets, window),
                         on_snare=_near(snares, onsets, window))
    if spans:
        changes = sum(s.chord.lowest != before.chord.lowest for before, s in pairwise(spans))
        report = replace(report, on_change=_on_change(played, spans, window), changes=changes, tones=_tones(played, spans))
    return report
