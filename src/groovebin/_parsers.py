"""argparse construction for the `groovebin` command line."""

from __future__ import annotations

import argparse
from pathlib import Path

from pf_core.utils.env import resolve_str

from . import __version__
from .library.groove import SUBDIVISIONS
from .library.index import default_db as library_default_db
from .maps import ALL_NAMES, NAMES


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
    remap.add_argument("--from", dest="src", required=True, choices=NAMES, help="the drum map the notes follow now")
    remap.add_argument("--to", dest="dst", required=True, choices=NAMES, help="the drum map to translate them to")
    remap.add_argument("-o", "--out", required=True, help="the .mid file to write")
    remap.add_argument("--channel", type=int, action="append",
                       help="remap only notes on this channel, 1-16 (repeatable)")
    remap.add_argument("--track", type=int, action="append", help="remap only this track, from 1 (repeatable)")
    remap.add_argument("--unmapped", choices=("keep", "drop"), default="keep",
                       help="a note with no counterpart keeps its pitch (default) or is dropped")
    remap.add_argument("--force", action="store_true", help="overwrite an existing --out file")

    notes = sub.add_parser("notes", help="list a MIDI file's tracks and notes")
    notes.add_argument("input", help="the .mid file to read")
    notes.add_argument("--map", choices=ALL_NAMES, help="name each note's stroke, or keyswitch, from this map")
    notes.add_argument("--track", type=int, action="append", help="list only this track, from 1 (repeatable)")

    _transform(sub)
    _timing(sub)
    _library(sub)
    return ap


class _Step(argparse.Action):
    """Repeatable flags kept in command-line order, as (flag, text)."""

    def __call__(self, parser, namespace, values, option_string=None):
        setattr(namespace, self.dest, [*(getattr(namespace, self.dest) or []), (option_string.lstrip("-"), values)])


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
    tr.add_argument("--key", metavar="KEY",
                    help='the key the notes are in, e.g. "A minor" or "F# dorian", for scale-quantize, diatonic and the '
                         "key change-key moves from (default: the file's key signatures, else one estimated)")
    tr.add_argument("--map", choices=ALL_NAMES,
                    help="the note map the notes follow: a bass map's keyswitches never change pitch; a drum map "
                         "refuses the theory presets")
    tr.add_argument("--force", action="store_true", help="overwrite an existing --out file")


def _timing(sub) -> None:
    te = sub.add_parser("tempo", help="a file's tempo points and ramps, or a copy with tempo changes written in")
    te.add_argument("input", help="the .mid file to read")
    te.add_argument("--set", dest="edits", action=_Step, metavar="BPM@BAR",
                    help="this tempo from this bar line until the next tempo point (repeatable)")
    te.add_argument("--ramp", dest="edits", action=_Step, metavar="BAR-BAR:BPM-BPM[/STEP]",
                    help="a ramp from the first bar line to the second, a point each STEP: a note value or ticks "
                         "(default 1/16) (repeatable)")
    te.add_argument("-o", "--out", help="the .mid file to write; needed with --set or --ramp")
    te.add_argument("--force", action="store_true", help="overwrite an existing --out file")

    ke = sub.add_parser("key", help="a file's key signatures and the scale its notes hold, or a copy with signatures set")
    ke.add_argument("input", help="the .mid file to read")
    ke.add_argument("--set", dest="keys", action="append", metavar="KEY@BAR",
                    help='a major or minor key from that bar line, e.g. "A minor@1" or "Bb@9" (repeatable)')
    ke.add_argument("--map", choices=ALL_NAMES, help="the bass map the notes follow; its keyswitches stay out of the scale")
    ke.add_argument("--track", type=int, action="append", metavar="N", help="find the scale in this track only (repeatable)")
    ke.add_argument("-o", "--out", help="the .mid file to write; needed with --set")
    ke.add_argument("--force", action="store_true", help="overwrite an existing --out file")


def _db(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--db", type=Path, help=f"the library index file (default {default_db()})")


def _library(sub) -> None:
    ix = sub.add_parser("index", help="build the pattern library index from a folder of .mid files or a MidiDb.csv")
    ix.add_argument("folder", nargs="?", type=Path, help="a folder of .mid files, labelled from their paths")
    ix.add_argument("--csv", type=Path, help="a MidiDb.csv instead of a folder: its columns label each pattern")
    ix.add_argument("--map", choices=ALL_NAMES, help="the note map the patterns follow; a drum map records their feel")
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
    se.add_argument("--swing", metavar="RANGE", help="the source's own swing label, 0-1, as --tempo")
    se.add_argument("--intensity", metavar="RANGE", help="0-1, as --tempo")
    se.add_argument("--group", metavar="TEXT", help="a substring of the group")
    se.add_argument("--variant", metavar="TEXT", help="a substring of the variant")
    se.add_argument("--library", metavar="NAME", help="whole value, any case")
    se.add_argument("--subdivision", choices=SUBDIVISIONS, help="what the hi-hat and ride play against the quarter note")
    se.add_argument("--density", metavar="RANGE", help="kick, snare and hand onsets a bar, as --tempo")
    se.add_argument("--syncopation", metavar="RANGE", help="a bar's kick and snare syncopation, 0 on the beat, as --tempo")
    se.add_argument("--swing8", metavar="RANGE", help="where the off-beat eighth sits: 0.5 straight, 0.667 a triplet shuffle")
    se.add_argument("--swing16", metavar="RANGE", help="where the off-beat sixteenth sits in its eighth, as --swing8")
    se.add_argument("--lag", metavar="RANGE", help="the snare behind the beat in ticks at 960 PPQ, below 0 ahead of it")
    se.add_argument("--accent", metavar="RANGE",
                    help="the hands' mean velocity on the beats less their mean off them, 0.4 to 0.72 of the way "
                         "through a beat: above 0 the beat is accented, below 0 the off-beat, as --tempo")
    se.add_argument("--quality", choices=("major", "minor"), help="the first chord a groove was played over")
    se.add_argument("--changes", metavar="RANGE", help="chord changes a bar, 0 for one chord throughout, as --tempo")
    se.add_argument("--like", metavar="ID|FILE", help="rank by rhythm, nearest first, against a pattern or a .mid file")
    se.add_argument("--like-map", choices=NAMES, metavar="MAP", help="the drum map a --like file's notes follow")
    se.add_argument("--rhythm", metavar="LANES",
                    help='rank by rhythm against typed lanes, e.g. "kick=x.......x....... snare=....x.......x..."')
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
    ge.add_argument("--crash", action="store_true",
                    help="a crash on the downbeat after each fill, in place of the hat or ride stroke there")
    ge.add_argument("--level", action="store_true",
                    help="scale each bar's velocities to the first bar's kick and snare median")
    ge.add_argument("--seed", type=int, metavar="N", help="0 or more; the same seed and index give the same phrase (default: a new one, printed)")
    ge.add_argument("--map", choices=NAMES, help="write the notes in this drum map (default: the patterns' own)")
    ge.add_argument("--unmapped", choices=("keep", "drop"), default="keep",
                    help="with --map, a note with no counterpart keeps its pitch (default) or is dropped")
    ge.add_argument("--force", action="store_true", help="overwrite an existing --out file")
    _db(ge)

    fe = sub.add_parser("feel", help="another part's feel laid on this file's notes: a groove template",
                        description="At each voice's eighth or sixteenth of the bar, the reference's offset from the "
                                    "grid and its accent against the voice's average; a note near a grid line the "
                                    "reference plays moves toward them.")
    fe.add_argument("file", help="the MIDI file to change")
    fe.add_argument("--from", dest="source", required=True, metavar="FILE|ID",
                    help="the reference: a .mid file, or a pattern id from the index")
    fe.add_argument("-o", "--out", required=True, help="the .mid file to write")
    fe.add_argument("--map", choices=NAMES, help="the drum map the notes follow, for a feel per voice; a reference "
                                                 "file follows it too")
    fe.add_argument("--grid", type=int, choices=(8, 16), help="the template's grid (default: the reference's own)")
    fe.add_argument("--timing", type=float, default=100, metavar="PCT", help="how far each note moves, 0-100 (default 100)")
    fe.add_argument("--velocity", type=float, default=100, metavar="PCT",
                    help="how far each velocity moves to the reference's accent, 0-100 (default 100)")
    fe.add_argument("--track", type=int, action="append", metavar="N", help="change only this track (repeatable)")
    fe.add_argument("--force", action="store_true", help="overwrite an existing --out file")
    _db(fe)

    anc = sub.add_parser("anchors", help="where a drum file's kick, snare and hands strike, a sixteenth grid a bar")
    anc.add_argument("input", help="the .mid file to read")
    anc.add_argument("--map", required=True, choices=NAMES, help="the drum map the notes follow")
    anc.add_argument("--bars", type=int, metavar="N", help="the first N bars (default: through the last note)")
    anc.add_argument("--track", type=int, action="append", metavar="N", help="read only this track (repeatable)")
    anc.add_argument("--json", action="store_true", help="a record per bar, as JSON")

    ro = sub.add_parser("roots", help="the chords a bassline implies, as a chart",
                        description="Each bar's root is the pitch class held longest, the note on the bar or half bar "
                                    "counting three times; a bar splits in half when each half has its own root. A "
                                    "chord is major or minor when the bass holds its third, else a power chord.")
    ro.add_argument("input", help="the MIDI file holding the bassline")
    ro.add_argument("--map", choices=ALL_NAMES, help="the bass map its notes follow; its keyswitches are left out")
    ro.add_argument("--track", type=int, action="append", metavar="N", help="read only this track (repeatable)")
    ro.add_argument("--json", action="store_true", help="each chord with its ticks and bar, as JSON")
    ro.add_argument("-o", "--out", help="also write a .mid file of a note per chord, at its slash bass or else its root")
    ro.add_argument("--octave", type=int, metavar="N", help="the -o file's octave, C4 being 60 (default 2: notes 36-47)")
    ro.add_argument("--force", action="store_true", help="overwrite an existing --out file")

    an = sub.add_parser("analyze", help="what a bassline does: its rhythm, against drums and against chords")
    an.add_argument("input", help="the MIDI file holding the bassline")
    an.add_argument("--map", choices=ALL_NAMES, help="the bass map its notes follow; keyswitches are counted, not played")
    an.add_argument("--track", type=int, action="append", metavar="N", help="read only this track (repeatable)")
    an.add_argument("--drums", metavar="FILE", help="a MIDI file holding the drums on the same timeline")
    an.add_argument("--drum-map", choices=NAMES, help="the drum map the --drums notes follow")
    an.add_argument("--drum-track", type=int, action="append", metavar="N", help="read only this track of --drums")
    an.add_argument("--chords", metavar="CHART", help="the chords under the line, e.g. \"| Am | F G |\"; a shorter "
                                                      "chart repeats")
    an.add_argument("--json", action="store_true", help="the report as JSON")

    ba = sub.add_parser("bass", help="a bassline over a drum file's kicks and a chord chart",
                        description="A note on every kick; the chord's bass note on every change; a chord tone between, "
                                    "as often as EZbass's own grooves play each; approach notes into changes.")
    ba.add_argument("--drums", required=True, metavar="FILE", help="the MIDI file holding the drums")
    ba.add_argument("--drum-map", required=True, choices=NAMES, help="the drum map the drums follow")
    ba.add_argument("--drum-track", type=int, action="append", metavar="N", help="read only this track of --drums")
    ba.add_argument("--chords", metavar="CHART", help="the chords, e.g. \"| Am | F G |\"; a shorter chart repeats")
    ba.add_argument("--roots-from", metavar="FILE", help="take the chords a bassline implies, as `groovebin roots` does")
    ba.add_argument("-o", "--out", required=True, help="the .mid file to write")
    ba.add_argument("--map", choices=ALL_NAMES, help="the bass map to write in; also read for --roots-from's keyswitches")
    ba.add_argument("--mute", action="store_true", help="the map's loud-mute keyswitch on every snare the bass leaves open")
    ba.add_argument("--approach", type=float, metavar="PCT", help="how often a change gets an approach note, 0-100 "
                                                                   "(default 58.8)")
    ba.add_argument("--library", metavar="DB", help="pick real bars from a bass library index instead of the rules")
    ba.add_argument("--role", help="with --library, only patterns of this role")
    ba.add_argument("--tempo", metavar="RANGE", help="with --library, only patterns in this tempo range")
    ba.add_argument("--low", default="E1", metavar="NOTE", help="the lowest note (default E1)")
    ba.add_argument("--high", default="D3", metavar="NOTE", help="the highest note (default D3)")
    ba.add_argument("--seed", type=int, metavar="N", help="0 or more; the same seed and files give the same line")
    ba.add_argument("--force", action="store_true", help="overwrite an existing --out file")

    sh = sub.add_parser("show", help="one pattern as text: drum lanes, or a piano roll when it has no drum map")
    sh.add_argument("id", help="the id search prints, or a unique prefix of it")
    sh.add_argument("--map", choices=NAMES, help="name each lane's stroke from this map instead of the pattern's own")
    sh.add_argument("--rhythm", action="store_true", help="print its kick, snare and hands as lanes search --rhythm reads")
    _db(sh)
