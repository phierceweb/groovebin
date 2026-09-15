# Using groovebin

## Table of contents

- [Install](#install)
- [Commands](#commands)
  - [groovebin remap](#groovebin-remap)
  - [groovebin notes](#groovebin-notes)
  - [groovebin index](#groovebin-index)
  - [groovebin search](#groovebin-search)
  - [groovebin show](#groovebin-show)
  - [groovebin generate](#groovebin-generate)
- [Note maps](#note-maps)
- [What a read and write keeps](#what-a-read-and-write-keeps)

## Install

    pip install groovebin
    groovebin --version

groovebin needs Python 3.12 or newer. From a checkout, for development:

    bin/run setup
    bin/run groovebin --version

## Commands

`groovebin --version` prints the installed version. A MIDI file a command reads or writes is a Standard
MIDI File, format 0 or 1. An error is one line on stderr and exit status 1; a malformed command line
prints its usage and exits 2.

### groovebin remap

    groovebin remap IN.mid --from gm --to addictive-drums-2 -o OUT.mid

Translates each note's pitch, and each polyphonic aftertouch key, from one note map to another
and writes a new file. Every other event, and each note's timing, channel and velocities, is
written back unchanged. A note with no counterpart in the destination map is counted in the report and
keeps its pitch, or with `--unmapped drop` is left out along with its aftertouch — a kept pitch can
land on an unrelated sound in the destination (a cymbal choke on a GM cuica).

| Flag | |
|---|---|
| `--from MAP` | the map the notes follow now (required) |
| `--to MAP` | the map to translate them to; must differ from `--from` (required) |
| `-o`, `--out FILE` | the file to write (required); never the input |
| `--channel N` | remap only notes on channel N, 1–16; repeat for more channels |
| `--track N` | remap only track N, counting from 1; repeat for more tracks |
| `--unmapped keep\|drop` | a note with no counterpart keeps its pitch (default) or is dropped |
| `--force` | replace an existing `--out` file |

Notes or polyphonic aftertouch on more than one channel are refused unless `--channel` says which to
translate, so a drum map never rewrites a bass or keys part; `--track` alone is enough when the named
tracks use one channel. With both, only the named channels on the named tracks change.

The report names what it could not translate, and says when two notes of one pitch now overlap so
that one starts inside the other and ends before it (a many-to-one translation can do that): a
reader closes the earlier note first, so those two lengths read back swapped.

### groovebin notes

    groovebin notes IN.mid --map drum-kit-designer

Lists the file's format, PPQ, starting tempo and meter, then each track's notes with bar position,
channel, pitch, velocity and length.

| Flag | |
|---|---|
| `--map MAP` | name each note's stroke from this map (`-` when the map has none) |
| `--track N` | list only track N, counting from 1; repeat for more tracks |

### groovebin index

    groovebin index ~/Grooves --map addictive-drums-2
    groovebin index --csv MidiDb.csv --map addictive-drums-2

Builds the pattern library index from every `.mid` file under a folder, or from a `MidiDb.csv` (which
carries each pattern's file). The index is replaced whole only when the build succeeds; a file that
cannot be read or does not parse, or a subfolder that cannot be listed, is kept as a row that says why
and is left out of searches. A folder that cannot be listed at all fails the build.

A folder's patterns are labelled from their paths:

- a name `<group>_V_<variant>_C_<category>` gives group, variant and category, and a trailing `_F_`
  marks a fill; otherwise the parent folder is the group, the file name the variant and the first
  folder the category
- a fill is that flag, or the word "fill" or "fills" in the variant or its folder
- the role is the first section word — intro, verse, pre-chorus, chorus, bridge, outro (or ending) —
  in the variant, else in the nearest folder that has one
- the fill and section words and `bpm` may be joined to the name by `_` or digits (`Fill_01`,
  `Verse2`, `120bpm_Funk`), never by letters (`Refill`, `Choruses`)
- meter and tempo come from the file; a meter (`6-8`, `3:4`) or tempo (`92bpm`) in the path is used
  only when the file has none, and a file with neither is in 4/4, the file format's default. A number
  pair with a numerator of 1 (`1-8`) is not read as a meter

| Flag | |
|---|---|
| `--csv FILE` | read a `MidiDb.csv` instead of a folder; its columns label each pattern |
| `--map MAP` | the drum map the patterns follow, stored with each; leave out for a library that is not drums |
| `--db FILE` | the index file (default `$XDG_CACHE_HOME/groovebin/library.sqlite`, or under `~/.cache`) |

### groovebin search

    groovebin search --role verse --meter 4/4 --tempo 90-110

Lists the patterns matching every filter given, with id, meter, tempo, beat or fill, bars, role,
category, group and variant.

| Flag | |
|---|---|
| `--category TEXT` | whole value, any case |
| `--role ROLE` | intro, verse, pre-chorus, chorus, bridge or outro |
| `--meter N/D` | e.g. `4/4` |
| `--tempo RANGE` | `100-130`, `<90`, `>=140` or `98`; bounds match to the digits written |
| `--fill` | fills only |
| `--beat` | beats only |
| `--swing RANGE` | as `--tempo` |
| `--intensity RANGE` | as `--tempo` |
| `--group TEXT` | a substring of the group |
| `--variant TEXT` | a substring of the variant |
| `--library NAME` | whole value, any case |
| `--limit N` | at most N rows (default 50; 0 for all) |
| `--json` | the rows as JSON |
| `--db FILE` | the index file |

### groovebin show

    groovebin show 3f2a9c

Draws one pattern, a cell per sixteenth and `|` at each bar: a lane per note number named by its
drum map, or, for a pattern with no drum map, a piano roll with note names and held notes (`=`).
`X` is velocity 100 and up, `x` 64–99, `o` below.

| Flag | |
|---|---|
| `--map MAP` | name each lane from this map instead of the pattern's own |
| `--db FILE` | the index file |

### groovebin generate

    groovebin generate --meter 4/4 --bars 16 --fills --role verse -o verse.mid

Writes a drum phrase picked bar by bar from the library: a picker over real bars, not a model. The
first bar starts a pattern; each next bar has the kick and snare onsets (the notes each pattern's drum
map calls kick and snare, on a sixteenth grid) nearest those of the bar that followed the last pick in
its own pattern. With `--fills`, every fourth bar is the fill bar nearest the groove bar it replaces; a
fill whose last bar is only a landing gives the bar before it. Timing moves up to 5 ticks and velocity
up to 6. The file holds the first pick's tempo and the meter, at 960 PPQ.

The listing names the pool, the seed, and every bar's source pattern; the same seed and index give the
same file. Patterns need a drum map (`groovebin index --map`).

| Flag | |
|---|---|
| `--meter N/D` | the phrase's meter; patterns with any bar in another meter are left out (required) |
| `--bars N` | the phrase's length, 1–4096 (required) |
| `-o`, `--out FILE` | the file to write (required) |
| `--category TEXT` | whole value, any case |
| `--role ROLE` | intro, verse, pre-chorus, chorus, bridge or outro |
| `--tempo RANGE` | as `groovebin search` takes it |
| `--intensity RANGE` | as `groovebin search` takes it |
| `--fills` | every fourth bar from a fill pattern |
| `--seed N` | 0 or more; without it a new seed is chosen and printed |
| `--map MAP` | write the notes in this drum map; required when the pool mixes maps |
| `--unmapped keep\|drop` | with `--map`, a note with no counterpart keeps its pitch (default) or is dropped |
| `--force` | replace an existing `--out` file |
| `--db FILE` | the index file |

## Note maps

| Map | Source |
|---|---|
| `gm` | General MIDI Level 1 percussion, notes 35–81 |
| `addictive-drums-2` | the Addictive Drums 2 keymap published by its vendor |
| `drum-kit-designer` | Logic Pro's Drum Kit Designer, GM Standard input mapping, from Apple's published keymap |

Each map gives notes a term such as `hihat open`. A note translates to the destination note with
the same term, else one whose term extends it, else the term less its last word. A choke or a
stick click never falls back onto a strike, nor to its first word alone, so a ride choke never
stops a crash. Terms and pairings are these tables' own choices, not the vendors'. Translation is
not always reversible: several Addictive Drums 2 snare strokes become one GM snare.

## What a read and write keeps

Reading a file and writing it back keeps every note (start, length, channel, pitch, velocity and
note-off velocity), every other event at its tick, and each track's end. Events of different
kinds at one tick are written in a fixed order (controllers before a program change, so a bank select
applies to it), a note-off with no note before it is dropped, and an
F7 escape is written as a SysEx event (`F0 … F7`). A SysEx split into packets, or one holding a data
byte of 0x80 or more, is refused.
