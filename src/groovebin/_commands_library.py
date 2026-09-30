"""The pattern library's commands: index, search, show and generate."""

from __future__ import annotations

import argparse
import json
import secrets

from pf_core.exceptions import InvalidInputError
from pf_core.utils.io import atomic_write_bytes

from . import _views_library
from ._files import is_file, named, refuse_overwrite
from ._parsers import default_db
from .library.generate import load_pool, parse_meter, phrase, phrase_song
from .library.groove import file_rhythm
from .library.groove_text import parse_rhythm, rhythm_text
from .library.index import build
from .library.search import get, pattern_rhythm, query_bars, search, similar
from .library.show import show
from .maps import NAMES, stroke
from .midi import write


def cmd_index(args: argparse.Namespace) -> int:
    if (args.folder is None) == (args.csv is None):
        raise InvalidInputError("index one source: a folder or --csv")
    db = args.db or default_db()
    print(f"indexing the MIDI index {args.csv.name}" if args.csv else f"indexing the .mid files under {args.folder}")
    counts = build(db, csv_path=args.csv, folder=args.folder, map_name=args.map)
    print(_views_library.indexed(counts))
    print(f"\nout : {db}")
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    db = args.db or default_db()
    filters = {"category": args.category, "role": args.role, "meter": args.meter, "tempo": args.tempo,
               "fill": args.fill or None, "beat": args.beat or None, "swing": args.swing, "intensity": args.intensity,
               "group": args.group, "variant": args.variant, "library": args.library, "subdivision": args.subdivision,
               "density": args.density, "syncopation": args.syncopation, "swing8": args.swing8,
               "swing16": args.swing16, "lag": args.lag, "quality": args.quality, "changes": args.changes}
    like, like_file = args.like, args.like is not None and is_file(args.like)
    if like is not None and args.rhythm is not None:
        raise InvalidInputError("rank by one query: --like or --rhythm")
    if args.like_map and not like_file:
        raise InvalidInputError("--like-map names the drum map of a --like file")
    voices = None
    if args.rhythm is not None:
        key, (query, voices) = None, parse_rhythm(args.rhythm)
    elif like is not None:
        if like_file and not args.like_map:
            raise InvalidInputError(f"--like {like}: name the drum map its notes follow with --like-map")
        key, query = ((None, named(like, lambda data: file_rhythm(data, args.like_map))) if like_file
                      else pattern_rhythm(db, like))
    if like is None and args.rhythm is None:
        rows, distinct = search(db, limit=args.limit or None, **filters), 0
    else:
        rows = similar(db, query, exclude=key, voices=voices, limit=args.limit or None, **filters)
        distinct = query_bars(query)[1]
    if args.json:
        print(json.dumps(rows, indent=1))
    else:
        print("\n".join(_views_library.found(rows, args.limit, distinct=distinct)))
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    if args.rhythm:
        if args.map:
            raise InvalidInputError("--rhythm prints kick, snare and hands lanes, not a lane per note: leave out --map")
        print(rhythm_text(pattern_rhythm(args.db or default_db(), args.id)[1]))
        return 0
    row = get(args.db or default_db(), args.id)
    map_name = args.map or row.get("map")
    print(show(row, (lambda pitch: stroke(map_name, pitch)) if map_name in NAMES else None))
    return 0


def cmd_generate(args: argparse.Namespace) -> int:
    refuse_overwrite(args.out, force=args.force)
    sig = parse_meter(args.meter)
    pool = load_pool(args.db or default_db(), sig=sig, category=args.category, role=args.role, tempo=args.tempo,
                     intensity=args.intensity, fills=args.fills)
    seed = args.seed if args.seed is not None else secrets.randbelow(2**32)
    ph = phrase(pool, bars=args.bars, seed=seed, fills=args.fills, map_name=args.map, unmapped=args.unmapped,
                crash=args.crash, level=args.level)
    atomic_write_bytes(args.out, write(phrase_song(ph)))
    print("\n".join(_views_library.picked(pool, ph)))
    print(f"out : {args.out}")
    return 0
