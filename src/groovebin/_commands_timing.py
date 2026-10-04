"""The timing commands: tempo and key."""

from __future__ import annotations

import argparse
from pathlib import Path

from pf_core.exceptions import InvalidInputError
from pf_core.utils.io import atomic_write_bytes

from . import _views, _views_timing
from ._files import read_song, refuse_overwrite, track_indices
from .harmony import parse_key, scale_of
from .maps import note_map
from .midi import write
from .song import (key_map, meter_map, skipped_keys, skipped_meters, skipped_tempos, tempo_map, with_keys,
                   with_tempo)
from .timing import MeterMap
from .transforms.select_parse import number, ticks_of, whole_number


def _bar(text: str, meters: MeterMap, flag: str, given: str) -> int:
    """The tick where bar ``text`` starts; one below bar 1 is refused, naming ``flag`` and its value."""
    bar = whole_number(text)
    if bar < 1:
        raise InvalidInputError(f"{flag} {given}: bar {bar} is before bar 1")
    return meters.bar_line(bar)


def _set(text: str, meters: MeterMap) -> tuple[int, float]:
    bpm, at, bar = text.rpartition("@")
    if not at:
        raise InvalidInputError(f"--set {text}: BPM@BAR, e.g. 100@9")
    return _bar(bar, meters, "--set", text), number(bpm)


def _ramp(text: str, meters: MeterMap, ppq: int) -> tuple[int, int, float, float, int]:
    bars, colon, rest = text.partition(":")
    first, dash, last = bars.partition("-")
    bpms, slash, step = rest.partition("/")
    lo, dash_too, hi = bpms.partition("-")
    if not (colon and dash and dash_too):
        raise InvalidInputError(f"--ramp {text}: BAR-BAR:BPM-BPM[/STEP], e.g. 9-17:100-120/1/16")
    start, end = _bar(first, meters, "--ramp", text), _bar(last, meters, "--ramp", text)
    if end <= start:
        raise InvalidInputError(f"--ramp {text}: the second bar is not after the first")
    ticks = ticks_of(step if slash else "1/16", ppq)
    if ticks > ppq:
        raise InvalidInputError(f"--ramp {text}: a step longer than a quarter note writes separate tempo steps, not a "
                                "ramp; give 1/4 or less")
    if end - start <= ticks:
        raise InvalidInputError(f"--ramp {text}: bars {first.strip()} to {last.strip()} are one step or less, so the "
                                "ramp has no point between its ends; give a shorter step")
    return start, end, number(lo), number(hi), ticks


def cmd_tempo(args: argparse.Namespace) -> int:
    song, name = read_song(args.input), Path(args.input).name
    meters, tempos = meter_map(song), tempo_map(song)
    if args.edits:
        if not args.out:
            raise InvalidInputError("--set and --ramp write a new file: give -o OUT.mid")
        refuse_overwrite(args.out, args.input, force=args.force)
        for kind, text in args.edits:
            tempos = (tempos.with_point(*_set(text, meters)) if kind == "set"
                      else tempos.with_ramp(*_ramp(text, meters, song.ppq)))
        atomic_write_bytes(args.out, write(with_tempo(song, tempos)))
    elif args.out:
        raise InvalidInputError("-o writes what --set or --ramp change: give one")
    print("\n".join(_views_timing.tempo_listing(name, tempos, meters, song.ppq)))
    if skipped := skipped_tempos(song):
        print(_views.tempo_warning(skipped) + ("; they are left out of the written file" if args.edits else ""))
    if skipped := skipped_meters(song):
        print(_views.meter_warning(skipped))
    if args.edits:
        print(f"out : {args.out}")
    return 0


def cmd_key(args: argparse.Namespace) -> int:
    song, name = read_song(args.input), Path(args.input).name
    kit = note_map(args.map) if args.map else None
    if kit is not None and kit.kind == "drums":
        raise InvalidInputError(f"{args.map} is a drum map: a key is estimated from pitched notes")
    meters, keys, skipped = meter_map(song), key_map(song), skipped_keys(song)
    indices = track_indices(song, args.track, name)
    if args.keys:
        if not args.out:
            raise InvalidInputError("--set writes a new file: give -o OUT.mid")
        refuse_overwrite(args.out, args.input, force=args.force)
        for text in args.keys:
            key, at, bar = text.rpartition("@")
            if not at:
                raise InvalidInputError(f'--set {text}: KEY@BAR, e.g. "A minor@1"')
            keys = keys.with_point(_bar(bar, meters, "--set", text), *parse_key(key).signature())
        song = with_keys(song, keys)
        atomic_write_bytes(args.out, write(song))
    elif args.out:
        raise InvalidInputError("-o writes what --set changes: give one")
    notes = [n for i in indices for n in song.tracks[i].notes if kit is None or not kit.is_keyswitch(n.pitch)]
    print("\n".join(_views_timing.key_listing(name, keys, meters, scale_of(notes))))
    if skipped:
        print(_views.key_warning(skipped) + ("; they are left out of the written file" if args.keys else ""))
    if skipped := skipped_meters(song):
        print(_views.meter_warning(skipped))
    if args.keys:
        print(f"out : {args.out}")
    return 0
