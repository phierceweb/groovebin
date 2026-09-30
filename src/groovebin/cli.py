"""`groovebin` command line: dispatch and the exception boundary."""

from __future__ import annotations

import argparse
import os
import random
import secrets
import sqlite3
import sys
from collections import Counter
from dataclasses import replace
from pathlib import Path

from pf_core.exceptions import FlowException, InvalidInputError
from pf_core.log import get_logger, setup_logging
from pf_core.utils.io import atomic_write_bytes

from . import _views
from ._commands_library import cmd_generate, cmd_index, cmd_search, cmd_show
from ._commands_bass import cmd_analyze, cmd_bass, cmd_roots
from ._files import is_file, named, read_song, refuse_overwrite, track_indices
from ._parsers import build_parser, default_db
from .library.feel import apply_feel, file_template, pattern_template
from .library.search import get
from .maps import folds, landings, remap
from .midi import write
from .song import Song, meter_map, nested_overlaps, skipped_meters
from .transforms import (BY_NAME, PRESETS, WHOLE_PART, PartWording, apply_all, parse_operation, parse_select,
                         parse_value, position_ticks, run, select)


def refuse_mixed_channels(song: Song, indices: list[int], name: str, *, tracks_named: bool) -> None:
    """A remap with no --channel changes every note and aftertouch key on the tracks it covers, so those
    tracks must use one channel between them."""
    notes = {i: {n.channel for n in song.tracks[i].notes} for i in indices}
    touched = {i: notes[i] | {e.channel for e in song.tracks[i].events if e.kind == "polytouch"} for i in indices}
    used = sorted(set().union(*touched.values()))
    if len(used) < 2:
        return
    what = "notes" if used == sorted(set().union(*notes.values())) else "notes and aftertouch"
    if tracks_named:
        holding = [i + 1 for i in indices if touched[i]]
        scope = f"track{'s' * (len(holding) > 1)} {_views.joined(holding)} of {name} hold{'s' * (len(holding) == 1)}"
        flags = "--channel"
    else:
        scope = f"{name} holds"
        flags = "--channel or --track" if any(len(c) == 1 for c in touched.values()) else "--channel"
    raise InvalidInputError(f"{scope} {what} on channels {_views.joined(used)}: say which to remap with {flags}")


def cmd_remap(args: argparse.Namespace) -> int:
    refuse_overwrite(args.out, args.input, force=args.force)
    song, name = read_song(args.input), Path(args.input).name
    indices = track_indices(song, args.track, name)
    channels = set(args.channel) if args.channel else None
    if channels is None:
        refuse_mixed_channels(song, indices, name, tracks_named=args.track is not None)
    tracks, unmapped, count = list(song.tracks), Counter(), 0
    ambiguous, nested = sum(t.nested_ons for t in song.tracks), 0
    landed: dict[tuple[int, int], set[int]] = {}
    for i in indices:
        new, missing = remap(tracks[i], args.src, args.dst, channels=channels, unmapped=args.unmapped)
        count += sum(1 for n in tracks[i].notes if channels is None or n.channel in channels)
        unmapped += missing
        nested += len(nested_overlaps(new))
        for key, sources in landings(tracks[i], args.src, args.dst, channels=channels,
                                     unmapped=args.unmapped).items():
            landed.setdefault(key, set()).update(sources)
        tracks[i] = new
    atomic_write_bytes(args.out, write(replace(song, tracks=tuple(tracks))))
    orphans = sum(t.orphan_offs for t in song.tracks)
    for line in _views.remap_report(notes=count, unmapped=unmapped, src=args.src, dst=args.dst,
                                    nested=nested, ambiguous=ambiguous, orphans=orphans, rule=args.unmapped,
                                    folded=folds(landed)):
        print(line)
    print(f"out : {args.out}")
    return 0


def cmd_notes(args: argparse.Namespace) -> int:
    song, name = read_song(args.input), Path(args.input).name
    indices = track_indices(song, args.track, name)
    try:
        lines = _views.listing(name, song, indices, args.map)
    except ValueError as e:
        raise ValueError(f"{name}: {e}") from e
    print("\n".join(lines))
    if ambiguous := sum(t.nested_ons for t in song.tracks):
        print(_views.ambiguous_warning(ambiguous))
    if orphans := sum(t.orphan_offs for t in song.tracks):
        print(_views.orphan_warning(orphans))
    if skipped := skipped_meters(song):
        print(_views.meter_warning(skipped))
    return 0


def _steps(given: list[tuple[str, str]], ppq: int) -> list[tuple[str, object]]:
    """--op and --preset in order, consecutive --op flags grouped into one pass: ("ops", [Operation…])
    or ("preset", (name, value))."""
    out: list[tuple[str, object]] = []
    for kind, text in given:
        if kind == "op":
            op, sep, spec = text.partition(":")
            if not sep:
                raise InvalidInputError(f"--op {text!r}: OP:FIELD[=VALUE]")
            operation = parse_operation(op.strip(), spec, ppq=ppq)
            if out and out[-1][0] == "ops":
                out[-1][1].append(operation)
            else:
                out.append(("ops", [operation]))
        else:
            name, sep, value = text.partition("=")
            if name.strip() not in BY_NAME:
                raise InvalidInputError(f"--preset {name.strip()!r}: no such preset; --presets lists them")
            preset = BY_NAME[name.strip()]
            out.append(("preset", (preset.name, parse_value(preset, value if sep else None, ppq=ppq))))
    return out


def cmd_transform(args: argparse.Namespace) -> int:
    if args.presets:
        if args.input or args.out or args.steps or args.select or args.track or args.force or args.seed != "0":
            raise InvalidInputError("--presets lists the presets and takes nothing else")
        print("\n".join(_views.presets(PRESETS)))
        return 0
    if not args.input or not args.out:
        raise InvalidInputError("transform takes IN.mid and -o OUT.mid (--presets alone lists the presets)")
    refuse_overwrite(args.out, args.input, force=args.force)
    song, name = read_song(args.input), Path(args.input).name
    indices = track_indices(song, args.track, name)
    steps = _steps(args.steps or [], song.ppq)
    if not steps:
        raise InvalidInputError("transform needs at least one --op or --preset")
    ranges = parse_select(args.select, ppq=song.ppq) if args.select else {}
    whole = [p for kind, (p, _v) in ((k, v) for k, v in steps if k == "preset") if p in WHOLE_PART]
    if ranges and whole:
        raise InvalidInputError(f"{whole[0]} takes the whole track; drop --select")
    if args.seed == "random":
        seed = secrets.randbelow(2**32)
    elif not args.seed.isdecimal():
        raise InvalidInputError(f"--seed {args.seed!r}: 0 or more, or random")
    else:
        seed = int(args.seed)
    rng, meters, tracks, lines = random.Random(seed), meter_map(song), list(song.tracks), []
    conditions = {f: (position_ticks(r, meters) if f == "tick" else r) for f, r in ranges.items()}
    ambiguous, nested = sum(t.nested_ons for t in song.tracks), 0
    for i in indices:
        part = replace(tracks[i], notes=tuple(replace(n, tag=k) for k, n in enumerate(tracks[i].notes)))
        wanted = set(select(part, **conditions)) if ranges else None
        selected = len(part.notes) if wanted is None else len(wanted)
        for kind, payload in steps:
            # --select is read once, off the file; a step can reorder the notes, so a tag carries the
            # selection into the next step where an index would not
            mask = None if wanted is None else frozenset(k for k, n in enumerate(part.notes) if n.tag in wanted)
            if kind == "ops":
                part = apply_all(part, mask, payload, seed=rng, meters=meters)
            else:
                part = run(part, mask, payload[0], payload[1], seed=rng, meters=meters)
        nested += len(nested_overlaps(part))
        tracks[i] = part
        lines.append(_views.transform_report(i + 1, part.name, selected, len(part.notes),
                                             [text for _k, text in args.steps]))
    atomic_write_bytes(args.out, write(replace(song, tracks=tuple(tracks))))
    print("\n".join(lines))
    if ambiguous:
        print(_views.ambiguous_warning(ambiguous))
    if nested:
        print(_views.nested_warning(nested))
    if orphans := sum(t.orphan_offs for t in song.tracks):
        print(_views.orphan_warning(orphans))
    if skipped := skipped_meters(song):
        print(_views.meter_warning(skipped))
    if args.seed == "random":
        print(f"seed {seed}")
    print(f"out : {args.out}")
    return 0


def cmd_feel(args: argparse.Namespace) -> int:
    source_file = is_file(args.source)
    refuse_overwrite(args.out, args.file, *([args.source] if source_file else []), force=args.force)
    for flag, share in (("--timing", args.timing), ("--velocity", args.velocity)):
        if not 0 <= share <= 100:
            raise InvalidInputError(f"{flag} {share:g}: 0 to 100")
    song, name = read_song(args.file), Path(args.file).name
    indices = track_indices(song, args.track, name)
    if source_file:
        tpl = named(args.source, lambda data: file_template(data, args.map, grid=args.grid))
        label = Path(args.source).name
    else:
        row = get(args.db or default_db(), args.source)
        tpl, label = pattern_template(row, grid=args.grid), f"pattern {row['id']}"
    meters, tracks, totals = meter_map(song), list(song.tracks), Counter()
    for i in indices:
        felt = apply_feel(tracks[i].notes, meters, tpl, args.map, timing=args.timing / 100, velocity=args.velocity / 100)
        tracks[i] = replace(tracks[i], notes=felt.notes)
        totals.update(notes=len(felt.notes), moved=felt.moved, unmatched=felt.unmatched, held=felt.held)
    atomic_write_bytes(args.out, write(replace(song, tracks=tuple(tracks))))
    print(_views.felt(label, tpl.grid, totals["notes"], totals["moved"], totals["unmatched"], totals["held"]))
    if ambiguous := sum(t.nested_ons for t in song.tracks):
        print(_views.ambiguous_warning(ambiguous))
    if nested := sum(len(nested_overlaps(tracks[i])) for i in indices):
        print(_views.nested_warning(nested))
    print(f"out : {args.out}")
    return 0


COMMANDS = {"remap": cmd_remap, "notes": cmd_notes, "index": cmd_index, "search": cmd_search, "show": cmd_show,
            "generate": cmd_generate, "transform": cmd_transform, "feel": cmd_feel, "roots": cmd_roots,
            "analyze": cmd_analyze, "bass": cmd_bass}


def main(argv: list[str] | None = None) -> int:
    """Entry point: pf-core logging and the one exception boundary. Runs log at debug; set
    ``LOG_FILE=path`` for a JSON-lines trail."""
    setup_logging(app_logger_name="groovebin")
    log = get_logger("groovebin")
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    log.debug("invoke", argv=argv if argv is not None else sys.argv[1:])
    try:
        rc = COMMANDS[args.command](args)
        sys.stdout.flush()
    except BrokenPipeError:
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return 0
    except PartWording as e:
        log.debug("error", error=str(e), exc_info=True)
        print(f"groovebin: {_views.spoken(str(e))}", file=sys.stderr)
        return 1
    except (FlowException, OSError, ValueError, KeyError, ArithmeticError, sqlite3.Error) as e:
        log.debug("error", error=str(e), exc_info=True)
        print(f"groovebin: {e}", file=sys.stderr)
        return 1
    log.debug("done", rc=rc)
    return rc


if __name__ == "__main__":
    sys.exit(main())
