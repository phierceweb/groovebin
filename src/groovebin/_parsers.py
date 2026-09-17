"""argparse construction for the `groovebin` command line."""

from __future__ import annotations

import argparse
from pathlib import Path

from pf_core.utils.env import resolve_str

from . import __version__
from .library.index import default_db as library_default_db
from .maps import NAMES


def default_db() -> Path:
    """The pattern library index when --db is not given: the library's own path under the user's
    cache folder, an empty ``XDG_CACHE_HOME`` read as unset."""
    return library_default_db(resolve_str(None, "XDG_CACHE_HOME"))


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="groovebin",
                                 description="MIDI files, note maps and a pattern library, with no DAW or plug-in involved.")
    ap.add_argument("--version", action="version", version=f"groovebin {__version__}")
    sub = ap.add_subparsers(dest="command")

    remap = sub.add_parser("remap", help="translate a MIDI file's notes from one note map to another")
    remap.add_argument("input", help="the .mid file to read")
    remap.add_argument("--from", dest="src", required=True, choices=NAMES, help="the map the notes follow now")
    remap.add_argument("--to", dest="dst", required=True, choices=NAMES, help="the map to translate them to")
    remap.add_argument("-o", "--out", required=True, help="the .mid file to write")
    remap.add_argument("--channel", type=int, action="append",
                       help="remap only notes on this channel, 1-16 (repeatable)")
    remap.add_argument("--track", type=int, action="append", help="remap only this track, from 1 (repeatable)")
    remap.add_argument("--unmapped", choices=("keep", "drop"), default="keep",
                       help="a note with no counterpart keeps its pitch (default) or is dropped")
    remap.add_argument("--force", action="store_true", help="overwrite an existing --out file")

    notes = sub.add_parser("notes", help="list a MIDI file's tracks and notes")
    notes.add_argument("input", help="the .mid file to read")
    notes.add_argument("--map", choices=NAMES, help="name each note's stroke from this map")
    notes.add_argument("--track", type=int, action="append", help="list only this track, from 1 (repeatable)")

    _transform(sub)
    _library(sub)
    return ap


class _Step(argparse.Action):
    """--op and --preset in command-line order, as (kind, text)."""

    def __call__(self, parser, namespace, values, option_string=None):
        namespace.steps = [*(namespace.steps or []), (option_string.lstrip("-"), values)]


def _transform(sub) -> None:
    tr = sub.add_parser("transform", help="select notes by their fields and change them, as Logic's Transform window does",
                        description="Each --op changes one field of every selected note; a --preset is a named set of "
                                    "operations. Consecutive --op flags apply in one pass, reading each note as it was; "
                                    "each --preset is its own pass. Notes outside the selection and every other event "
                                    "are written back unchanged.")
    tr.add_argument("input", nargs="?", help="the .mid file to read")
    tr.add_argument("-o", "--out", help="the .mid file to write")
    tr.add_argument("--track", type=int, action="append", help="transform only this track, from 1 (repeatable)")
    tr.add_argument("--select", metavar="COND[,COND…]",
                    help="which notes: FIELD=VALUE, FIELD=LO-HI, or FIELD<, <=, >, >=, != VALUE, over position (bars; a "
                         "whole number is the whole bar), pitch, velocity, length (ticks, 240t or 1/16) and channel; "
                         "default every note")
    tr.add_argument("--op", dest="steps", action=_Step, metavar="OP:FIELD[=VALUE]",
                    help="set, add, mul, min, max, random, flip, quantize, crescendo (LO..HI), exp, reverse (no value) "
                         "on position, pitch, velocity, length or channel; exp is velocity only, and crescendo "
                         "and reverse do not take channel (repeatable)")
    tr.add_argument("--preset", dest="steps", action=_Step, metavar="NAME[=VALUE]", help="a preset by name (repeatable); --presets lists them")
    tr.add_argument("--presets", action="store_true", help="list the presets and exit")
    tr.add_argument("--seed", default="0", metavar="N|random", help="the seed for random and humanize (default 0, so a run repeats)")
    tr.add_argument("--force", action="store_true", help="overwrite an existing --out file")


def _db(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--db", type=Path, help=f"the library index file (default {default_db()})")


def _library(sub) -> None:
    ix = sub.add_parser("index", help="build the pattern library index from a folder of .mid files or a MidiDb.csv")
    ix.add_argument("folder", nargs="?", type=Path, help="a folder of .mid files, labelled from their paths")
    ix.add_argument("--csv", type=Path, help="a MidiDb.csv instead of a folder: its columns label each pattern")
    ix.add_argument("--map", choices=NAMES, help="the drum map the patterns follow (leave out for a library that is not drums)")
    _db(ix)

    se = sub.add_parser("search", help="patterns matching every filter given")
    se.add_argument("--category", help="whole value, any case")
    se.add_argument("--role", help="intro, verse, pre-chorus, chorus, bridge or outro")
    se.add_argument("--meter", metavar="N/D", help="e.g. 4/4")
    se.add_argument("--tempo", metavar="RANGE",
                    help="100-130, <90, >=140 or 98, each bound to the digits written (98 is 97.5 up to 98.5)")
    kind = se.add_mutually_exclusive_group()
    kind.add_argument("--fill", action="store_true", help="fills only")
    kind.add_argument("--beat", action="store_true", help="beats only")
    se.add_argument("--swing", metavar="RANGE", help="0-1, as --tempo")
    se.add_argument("--intensity", metavar="RANGE", help="0-1, as --tempo")
    se.add_argument("--group", metavar="TEXT", help="a substring of the group")
    se.add_argument("--variant", metavar="TEXT", help="a substring of the variant")
    se.add_argument("--library", metavar="NAME", help="whole value, any case")
    se.add_argument("--limit", type=int, default=50, metavar="N", help="at most N rows (default 50; 0 for all)")
    se.add_argument("--json", action="store_true", help="the rows as JSON")
    _db(se)

    ge = sub.add_parser("generate", help="a drum phrase picked bar by bar from real library bars, as a MIDI file",
                        description="Every bar is a real bar of a matching pattern: the first starts a pattern; each "
                                    "next has the kick and snare onsets nearest those of the bar that followed the last "
                                    "pick in its own pattern. Timing moves up to 5 ticks and velocity up to 6.")
    ge.add_argument("--meter", required=True, metavar="N/D", help="e.g. 4/4; patterns with any bar in another meter are left out")
    ge.add_argument("--bars", required=True, type=int, metavar="N", help="the phrase's length in bars")
    ge.add_argument("-o", "--out", required=True, help="the .mid file to write")
    ge.add_argument("--category", help="whole value, any case")
    ge.add_argument("--role", help="intro, verse, pre-chorus, chorus, bridge or outro")
    ge.add_argument("--tempo", metavar="RANGE", help="as `groovebin search` takes it")
    ge.add_argument("--intensity", metavar="RANGE", help="as `groovebin search` takes it")
    ge.add_argument("--fills", action="store_true", help="every fourth bar from a fill pattern")
    ge.add_argument("--seed", type=int, metavar="N", help="0 or more; the same seed and index give the same phrase (default: a new one, printed)")
    ge.add_argument("--map", choices=NAMES, help="write the notes in this drum map (default: the patterns' own)")
    ge.add_argument("--unmapped", choices=("keep", "drop"), default="keep",
                    help="with --map, a note with no counterpart keeps its pitch (default) or is dropped")
    ge.add_argument("--force", action="store_true", help="overwrite an existing --out file")
    _db(ge)

    sh = sub.add_parser("show", help="one pattern as text: drum lanes, or a piano roll when it has no drum map")
    sh.add_argument("id", help="the id search prints, or a unique prefix of it")
    sh.add_argument("--map", choices=NAMES, help="name each lane's stroke from this map instead of the pattern's own")
    _db(sh)
