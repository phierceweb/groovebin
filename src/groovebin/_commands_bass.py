"""The bass commands: roots, analyze and bass."""

from __future__ import annotations

import argparse
import json
import secrets
from dataclasses import asdict
from pathlib import Path

from pf_core.exceptions import InvalidInputError
from pf_core.utils.io import atomic_write_bytes

from . import _views_bass
from ._files import read_song, refuse_overwrite, track_indices
from .harmony import chart, chart_spans, chart_text, note_number, roots, scale_name, scale_of
from .library.bass_picker import lay, load_bass_bars, pick_bass
from .library.bass_rules import APPROACH_RATE, bass_line
from .library.bassline import analyze
from .library.groove import VOICES, rhythm, voices
from .maps import note_map
from .events import Event
from .midi import write
from .song import Part, Song, meter_map, rescale

CONDUCTOR = (0x51, 0x58)


def cmd_roots(args: argparse.Namespace) -> int:
    song, name = read_song(args.input), Path(args.input).name
    bass = note_map(args.map) if args.map else None
    if bass is not None and bass.kind == "drums":
        raise InvalidInputError(f"{args.map} is a drum map: roots reads a bassline")
    notes = [n for i in track_indices(song, args.track, name) for n in song.tracks[i].notes]
    played = [n for n in notes if bass is None or not bass.is_keyswitch(n.pitch)]
    if not played:
        raise InvalidInputError(f"{name} has no notes to find chords in on the tracks read")
    meters = meter_map(song)
    bars = meters.bar_of(max(n.tick for n in played))
    spans = roots(played, meters, bars)
    if args.json:
        print(json.dumps([{"start": s.start, "end": s.end, "bar": meters.bar_of(s.start), "chord": str(s.chord)}
                          for s in spans], indent=1))
        return 0
    print(_views_bass.rooted(name, bars, len(played), len(notes) - len(played)))
    print(chart_text(spans, meters, bars))
    if (major := scale_of(played)) is not None:
        print(f"scale  {scale_name(major)}")
    return 0


def cmd_analyze(args: argparse.Namespace) -> int:
    song, name = read_song(args.input), Path(args.input).name
    notes = [n for i in track_indices(song, args.track, name) for n in song.tracks[i].notes]
    kit = note_map(args.map) if args.map else None
    played = [n for n in notes if kit is None or not kit.is_keyswitch(n.pitch)]
    if not played:
        raise InvalidInputError(f"{name} has no notes to analyze on the tracks read")
    drums = None
    if args.drums:
        if not args.drum_map:
            raise InvalidInputError("--drums needs --drum-map to find the kick and snare")
        drum_song = read_song(args.drums)
        picked = [n for i in track_indices(drum_song, args.drum_track, Path(args.drums).name)
                  for n in drum_song.tracks[i].notes]
        drums = rescale(Part(drum_song.ppq, tuple(picked)), song.ppq).notes
    meters = meter_map(song)
    bars = meters.bar_of(max(n.tick for n in played))
    spans = chart_spans(chart(args.chords), meters, bars) if args.chords else None
    report = analyze(notes, meters, bars, bass_map=args.map, drums=drums, drum_map=args.drum_map, spans=spans)
    print(json.dumps(asdict(report), indent=1) if args.json else "\n".join(_views_bass.analyzed(name, report)))
    return 0


def _chord_spans(args: argparse.Namespace, meters, bars: int, ppq: int):
    if (args.chords is None) == (args.roots_from is None):
        raise InvalidInputError("bass takes --chords or --roots-from, not both" if args.chords is not None
                                else "bass needs --chords or --roots-from")
    if args.chords is not None:
        return chart_spans(chart(args.chords), meters, bars), None
    song = read_song(args.roots_from)
    kit = note_map(args.map) if args.map else None
    notes = [n for t in song.tracks for n in t.notes if kit is None or not kit.is_keyswitch(n.pitch)]
    if not notes:
        raise InvalidInputError(f"{Path(args.roots_from).name} has no notes to take chords from")
    notes = rescale(Part(song.ppq, tuple(notes)), ppq).notes
    spans = roots(notes, meters, bars)
    return spans, chart_text(spans, meters, bars)


def _above_keyswitches(register: tuple[int, int], map_name: str) -> None:
    switches = [n for n in range(128) if note_map(map_name).is_keyswitch(n)]
    if switches and register[0] <= max(switches):
        raise InvalidInputError(f"a register from note {register[0]} reaches {map_name}'s keyswitches "
                                f"({min(switches)}-{max(switches)}): start it above them")


def _library_line(args, drum_notes, meters, bars, spans, seed, register) -> tuple[tuple, tuple, list[str], int]:
    if args.mute or args.approach is not None:
        raise InvalidInputError("--library picks real bars, which bring their own approaches and articulations: drop "
                                "--mute and --approach")
    sigs = {meters.meter_at(meters.bar_line(b)) for b in range(1, bars + 1)}
    pool = [b for sig in sorted(sigs) for b in load_bass_bars(args.library, sig=sig, role=args.role, tempo=args.tempo)]
    maps = {b.map for b in pool}
    if args.map and maps != {args.map}:
        raise InvalidInputError(f"the library's bars follow {', '.join(sorted(maps))}, not --map {args.map}")
    _above_keyswitches(register, pool[0].map)
    picks = pick_bass(pool, rhythm(drum_notes, meters, bars, args.drum_map), seed=seed)
    notes, events = lay(picks, spans, meters, meters.ppq, register, pool[0].map)
    kit = note_map(pool[0].map)
    switches = sum(kit.is_keyswitch(n.pitch) for n in notes)
    return notes, events, _views_bass.picked(picks), switches


def cmd_bass(args: argparse.Namespace) -> int:
    refuse_overwrite(args.out, args.drums, *(p for p in (args.roots_from, args.library) if p), force=args.force)
    if args.approach is not None and not 0 <= args.approach <= 100:
        raise InvalidInputError(f"--approach {args.approach:g}: 0 to 100")
    kit = note_map(args.map) if args.map else None
    if kit is not None and kit.kind != "bass":
        raise InvalidInputError(f"{args.map} is a drum map: bass writes a line in a bass map")
    if args.mute and not args.library and (kit is None or kit.find("keyswitch repeat loud mute") is None):
        raise InvalidInputError("--mute needs --map ezbass: the mute is its keyswitch")
    drum_song, name = read_song(args.drums), Path(args.drums).name
    drum_notes = [n for i in track_indices(drum_song, args.drum_track, name) for n in drum_song.tracks[i].notes]
    if not drum_notes:
        raise InvalidInputError(f"{name} has no drum notes on the tracks read")
    meters = meter_map(drum_song)
    bars = meters.bar_of(max(n.tick for n in drum_notes))
    spans, found = _chord_spans(args, meters, bars, drum_song.ppq)
    seed = args.seed if args.seed is not None else secrets.randbelow(2**32)
    register = (note_number(args.low), note_number(args.high))
    if kit is not None:
        _above_keyswitches(register, args.map)
    if args.library:
        notes, events, picks, switches = _library_line(args, drum_notes, meters, bars, spans, seed, register)
        head = [_views_bass.from_library(name, bars, len(notes) - switches, switches), *picks]
    else:
        table = voices(args.drum_map)
        kicks = [(n.tick, n.velocity) for n in drum_notes if table.get(n.pitch) == VOICES.index("kick")]
        snares = [n.tick for n in drum_notes if table.get(n.pitch) == VOICES.index("snare")]
        line = bass_line(kicks, snares, spans, drum_song.ppq, seed=seed, register=register,
                         approach=APPROACH_RATE if args.approach is None else args.approach / 100,
                         mute=kit.find("keyswitch repeat loud mute") if args.mute else None)
        notes, events, head = line.notes, (), [_views_bass.written(name, bars, line)]
    conductor = tuple(e for t in drum_song.tracks for e in t.events if e.meta_type in CONDUCTOR)
    title = b"Bass"
    bass = Part(drum_song.ppq, notes, (Event(0, bytes([0xFF, 0x03, len(title)]) + title), *events), end=spans[-1].end)
    atomic_write_bytes(args.out, write(Song(drum_song.ppq, 1, (Part(drum_song.ppq, (), conductor), bass))))
    print("\n".join(head))
    if found:
        print(f"chords from {Path(args.roots_from).name}: {found}")
    print(f"seed {seed}")
    print(f"out : {args.out}")
    return 0
