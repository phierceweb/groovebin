"""`groovebin transform`: select notes, change them by operations and presets, write the file back."""

from __future__ import annotations

import argparse
import random
import secrets
from dataclasses import replace
from pathlib import Path

from pf_core.exceptions import InvalidInputError
from pf_core.utils.io import atomic_write_bytes

from . import _views
from ._files import read_song, refuse_overwrite, track_indices
from .harmony import MODES, Scale, from_signature, parse_key, scale_name, scale_of
from .maps import note_map
from .midi import write
from .song import (KEY_SIGNATURE, Part, Song, key_map, key_signature, meter_map, nested_overlaps, skipped_keys,
                   skipped_meters)
from .transforms import (BY_NAME, PRESETS, THEORY, WHOLE_PART, apply_all, key_at, parse_operation, parse_select,
                         parse_value, position_ticks, run, select)


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


def _never(pitch: int) -> bool:
    return False


def _source(song: Song, indices: list[int], given: str | None, hold, meters) -> tuple[object, str, int | None]:
    """The key the notes are in, the report line naming it, and the estimated major tonic when it was estimated."""
    if given is not None:
        key = parse_key(given)
        return key, f"key  {key} (given)", None
    if (keys := key_map(song)).points:
        points = list(dict.fromkeys((t, from_signature(s, m)) for t, s, m in keys.points))
        named = ", ".join(f"{scale} from bar {meters.bar(t):g}" for t, scale in points)
        return points, f"key  {named} (the file's key signatures)", None
    major = scale_of(n for i in indices for n in song.tracks[i].notes if not hold(n.pitch))
    if major is None:
        raise InvalidInputError("no key to move notes in: the file has no key signature and too few pitch classes "
                                "to estimate one; give --key")
    return Scale(major), f"key  {scale_name(major)} (estimated)", major


def _in_mode(major: int, target: Scale) -> Scale:
    """An estimated key in ``target``'s mode: notes alone cannot tell C major from A minor."""
    if target.kind not in MODES:
        raise InvalidInputError(f"change-key to {target} needs the key the notes are in: give --key")
    return Scale((major + MODES[target.kind]) % 12, target.kind)


def _reads_moved_keys(steps: list[tuple[str, object]], keys: object) -> None:
    """Refuse a theory preset reading the file's changing keys after a speed change has moved the notes off them."""
    if not isinstance(keys, list) or len({scale for _t, scale in keys}) < 2:
        return
    moved = None
    for kind, payload in steps:
        name, value = payload if kind == "preset" else (None, None)
        if name in ("half-speed", "double-speed"):
            moved = name
        elif moved and name in THEORY and not (name == "scale-quantize" and value is not None):
            raise InvalidInputError(f"{name} reads the file's key signatures at each note, and {moved} has moved the "
                                    f"notes off them: put {name} first, or run it on the {moved} copy")
        if name == "change-key":
            return


def _selected(part: Part, wanted: set[int] | None) -> frozenset[int] | None:
    """--select is read once, off the file; a step can reorder the notes, so a tag carries the selection into the
    next step where an index would not."""
    return None if wanted is None else frozenset(k for k, n in enumerate(part.notes) if n.tag in wanted)


def _unheld(part: Part, mask: frozenset[int] | None, hold) -> frozenset[int]:
    return frozenset(k for k in (range(len(part.notes)) if mask is None else mask) if not hold(part.notes[k].pitch))


def _landed(before: dict[int, int], part: Part, hold, map_name: str | None) -> None:
    """Refuse a step that moved a played note onto one of the bass map's keyswitches."""
    for n in part.notes:
        if not hold(before[n.tag]) and hold(n.pitch):
            raise InvalidInputError(f"note {before[n.tag]} would move to {n.pitch}, an {map_name} keyswitch: it would "
                                    "play an articulation, not a note")


def cmd_transform(args: argparse.Namespace) -> int:
    if args.presets:
        if (args.input or args.out or args.steps or args.select or args.track or args.force or args.seed != "0"
                or args.key or args.map):
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
    presets = [payload for kind, payload in steps if kind == "preset"]
    theory = [p for p, _v in presets if p in THEORY]
    sourced = [p for p, v in presets if p in THEORY and not (p == "scale-quantize" and v is not None)]
    kit = note_map(args.map) if args.map else None
    if kit is not None and kit.kind == "drums" and theory:
        raise InvalidInputError(f"{theory[0]} moves notes in a key, and {args.map} is a drum map: its notes name pieces")
    if args.key is not None and not sourced:
        raise InvalidInputError("--key goes unread: scale-quantize=KEY names its own key" if theory else
                                "--key is the key scale-quantize, diatonic and change-key read: give one of them")
    hold = kit.is_keyswitch if kit is not None and kit.kind == "bass" else _never
    if args.seed == "random":
        seed = secrets.randbelow(2**32)
    elif not args.seed.isdecimal():
        raise InvalidInputError(f"--seed {args.seed!r}: 0 or more, or random")
    else:
        seed = int(args.seed)
    rng, meters, tracks, lines = random.Random(seed), meter_map(song), list(song.tracks), []
    conditions = {f: (position_ticks(r, meters) if f == "tick" else r) for f, r in ranges.items()}
    ambiguous, nested = sum(t.nested_ons for t in song.tracks), 0
    keys, said, major = _source(song, indices, args.key, hold, meters) if sourced else (None, "", None)
    if sourced:
        lines.append(said)
        _reads_moved_keys(steps, keys)
    first = min((n.tick for i in indices for n in song.tracks[i].notes if not hold(n.pitch)), default=0)
    changed: list[Scale] = []
    for i in indices:
        part = replace(tracks[i], notes=tuple(replace(n, tag=k) for k, n in enumerate(tracks[i].notes)))
        wanted = set(select(part, **conditions)) if ranges else None
        selected = len(part.notes) if wanted is None else len(wanted)
        track_keys, track_major = keys, major
        for kind, payload in steps:
            before = {n.tag: n.pitch for n in part.notes}
            if kind == "ops":
                pitched = [o for o in payload if o.field == "pitch"] if hold is not _never else []
                if pitched:
                    part = apply_all(part, _unheld(part, _selected(part, wanted), hold), pitched, seed=rng, meters=meters)
                rest = [o for o in payload if o not in pitched]
                if rest:
                    part = apply_all(part, _selected(part, wanted), rest, seed=rng, meters=meters)
                _landed(before, part, hold, args.map)
                continue
            preset, value = payload
            mask = _selected(part, wanted)
            if hold is not _never and preset == "reverse-pitch":
                mask = _unheld(part, mask, hold)
            if preset == "change-key":
                source = _in_mode(track_major, value) if track_major is not None else key_at(track_keys, first)
                part = run(part, mask, preset, value, seed=rng, meters=meters, keys=source, hold=hold, at=first)
                track_keys, track_major = value, None
                changed.append(value)
            else:
                part = run(part, mask, preset, value, seed=rng, meters=meters, keys=track_keys, hold=hold)
            _landed(before, part, hold, args.map)
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
    if sourced and args.key is None and (skipped := skipped_keys(song)):
        print(_views.key_warning(skipped))
    if changed:
        target, signed = changed[-1], key_map(song)
        base = signed.at(first) or (signed.points[0][1:] if signed.points else None)
        others = [k + 1 for k, t in enumerate(song.tracks)
                  if k not in indices and any(e.meta_type == KEY_SIGNATURE for e in t.events)]
        mode_change = base is not None and base[1] != (target.kind == "minor")
        left = mode_change and sum(1 for i in indices for e in tracks[i].events if (found := key_signature(e))
                                   and e in song.tracks[i].events and from_signature(*found) != target)
        if target.kind not in ("major", "minor"):
            print(f"key signatures left as they were: a file's key signature cannot say {target.kind}")
        elif left:
            print(f"{left} key signature(s) in other keys were left as they were: a change of mode does not say where "
                  "they go")
        if others and target.kind in ("major", "minor"):
            print(f"key signatures on track(s) {_views.joined(others)} were not changed: transform those tracks too, "
                  "or set them with `groovebin key --set`")
    if args.seed == "random":
        print(f"seed {seed}")
    print(f"out : {args.out}")
    return 0
