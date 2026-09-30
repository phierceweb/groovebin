# Using groovebin

## Table of contents

- [Install](#install)
- [Commands](#commands)
  - [groovebin remap](#groovebin-remap)
  - [groovebin notes](#groovebin-notes)
  - [groovebin transform](#groovebin-transform)
  - [groovebin feel](#groovebin-feel)
  - [groovebin roots](#groovebin-roots)
  - [groovebin analyze](#groovebin-analyze)
  - [groovebin bass](#groovebin-bass)
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
| `--from MAP` | the drum map the notes follow now (required) |
| `--to MAP` | the drum map to translate them to; must differ from `--from` (required) |
| `-o`, `--out FILE` | the file to write (required); never the input |
| `--channel N` | remap only notes on channel N, 1–16; repeat for more channels |
| `--track N` | remap only track N, counting from 1; repeat for more tracks |
| `--unmapped keep\|drop` | a note with no counterpart keeps its pitch (default) or is dropped |
| `--force` | replace an existing `--out` file |

Notes or polyphonic aftertouch on more than one channel are refused unless `--channel` says which to
translate, so a drum map never rewrites a bass or keys part; `--track` alone is enough when the named
tracks use one channel. With both, only the named channels on the named tracks change.

The report names what it could not translate, and names each destination note that more than one source
pitch lands on — including a kept pitch a translated one arrives at, which `--unmapped drop` avoids.
A channel is one instrument however many tracks drive it, so pitches that meet on one channel fold even
from different tracks; the same pitch on two channels is two voices and does not. It says, on
lines of their own, how many note-offs in the input found more than one note of their pitch open, so
that the lengths are one reading of the file, and how many pairs of one pitch the remap left overlapping
so that one starts inside the other and ends before it (a many-to-one translation can do that): a reader
closes the earlier note first, so those two lengths read back swapped. It also says how many note-offs
with no note before them the file dropped on read. All three count the whole file, not just the tracks
`--track` named: every track is written back.

### groovebin notes

    groovebin notes IN.mid --map drum-kit-designer

Lists the file's format, PPQ, starting tempo and meter, then each track's notes with bar position,
channel, pitch, velocity and length. A time signature the file's PPQ cannot hold in whole ticks, or one
too short to read, or one with a zero numerator or a denominator past 64, cannot be counted in: the
listing says how many were skipped, and bars follow the meters that remain. The lengths listed are the
ones first-in-first-out pairing chose: where a note-off found more than one note of its pitch open, or
the file dropped a note-off with no note before it, the listing says how many, as `groovebin remap` does.

| Flag | |
|---|---|
| `--map MAP` | name each note's stroke from this map (`-` when the map has none) |
| `--track N` | list only track N, counting from 1; repeat for more tracks |

### groovebin transform

    groovebin transform IN.mid -o OUT.mid --select "pitch=36-47,velocity<40" --op add:velocity=10
    groovebin transform IN.mid -o OUT.mid --track 2 --preset humanize --seed 7
    groovebin transform --presets

Logic's Transform window on a file: `--select` picks notes by their fields, each `--op` changes one field of
every selected note, and a `--preset` is a named set of operations with one value. Notes outside the
selection, and every other event, are written back unchanged, and a selected note keeps every field no
operation names. The selection is read once, from the file as it was; every step works on those notes.
Consecutive `--op` flags apply in one pass, each reading the note as it was (a second operation on one field
reads the first's result); each `--preset` is its own pass. A field an operation writes is held to its range —
pitch 0–127, velocity 1–127, channel 1–16, a length of at least one tick — and a note that would move before
the track's start is refused. As `groovebin remap` does, it says apart how many note-offs in the input found
more than one note of their pitch open and how many pairs of one pitch the result leaves nested inside one
another, since a reader pairs note-offs first in, first out and those lengths read back swapped. It also says how many
note-offs with no note before them the file dropped on read, as `groovebin remap` does, and how many time
signatures were skipped, as `groovebin notes` does. All three count the whole file, not just the tracks
`--track` named.

A condition is `FIELD=VALUE`, `FIELD=LO-HI`, or `FIELD` with `<`, `<=`, `>`, `>=` or `!=` and a value; several are
joined by commas and must all hold. The fields: `position` in bars, where a whole number means the whole bar
(`9-12` runs from bar 9's line up to bar 13's, `9.5` is that spot; bar 1 is the first); `pitch`; `velocity`; `length` in ticks
(`240`, `240t`) or as a note value (`1/16`); `channel`.

An operation is `OP:FIELD[=VALUE]`: `set`, `add`, `mul` (a factor), `min` (raise what is below), `max` (cut what
is above), `random` (±VALUE, uniform), `flip` (mirror around VALUE), `quantize` (a position to the nearest VALUE
grid line of its bar, a length to the nearest multiple of VALUE ticks), `crescendo` (`LO..HI` ramped across the
selection by position), `exp` (a velocity curve exponent), `reverse` (no value: the selection's span mirrored,
first for last). Position and length values are ticks or note values as above; one past the 268435455 ticks
a file can hold is refused as it is read, and so is a gap the result would leave between two events. `exp` takes velocity
only; `crescendo` and `reverse` take position, pitch, velocity or length, not channel. A `LO..HI` velocity
band is 1–127.

| Preset | Value | Does |
|---|---|---|
| `humanize` | `pos=10t,vel=8,len=5` (name any subset; the rest keep these) | each note's position, velocity and length moved at random within those |
| `fixed-velocity` | velocity, required | every selected note at one velocity |
| `velocity-limit` | `20..110` | velocities held inside the band |
| `random-velocity` | `20` | each velocity moved by up to ±N |
| `crescendo` | `40..120` | velocities ramped from LO at the first selected note to HI at the last |
| `reverse-position` | — | positions mirrored, first for last |
| `reverse-pitch` | a pivot note, optional | pitches mirrored around the pivot, else around the selection's lowest and highest |
| `exp-velocity` | `1.5` | velocities through a power curve; above 1 softens the middle |
| `fixed-length`, `max-length`, `min-length` | ticks or a note value, required | one length; longer notes cut; shorter notes stretched |
| `half-speed`, `double-speed` | — | every position and length doubled or halved — the whole track, events too; no `--select` |
| `legato` | `100%` | each note lasts that share of the way to the next note's start (100% touches it, more overlaps) |
| `staccato` | `50%` | each note's length times that share |
| `swing` | `58%[:1/16]` | notes on the grid, every second grid line of the bar late by grid × (2·swing − 1); 50% is straight; no `--select` |

| Flag | |
|---|---|
| `-o`, `--out FILE` | the file to write (required); never the input |
| `--track N` | transform only track N, counting from 1; repeat for more tracks |
| `--select COND[,COND…]` | which notes (default every note) |
| `--op OP:FIELD[=VALUE]` | an operation; repeat for more |
| `--preset NAME[=VALUE]` | a preset; repeat for more |
| `--presets` | list the presets and exit; takes no file, flag or operation |
| `--seed N\|random` | the seed for `random` and `humanize`; 0 by default so a run repeats, `random` prints the one it chose |
| `--force` | replace an existing `--out` file |

### groovebin feel

    groovebin feel programmed.mid --from played.mid --map gm -o felt.mid
    groovebin feel verse.mid --from 3f2a9c --map addictive-drums-2 --timing 70 -o verse-felt.mid

Lays another part's feel on this file's notes, as a groove template. The reference — a `.mid` file, or a
pattern from the index by its id — gives, at each eighth or sixteenth of the bar, how far its notes sit from
that grid line and how hard they strike against their voice's average. With `--map`, the voices are the
kick, the snare (sidestick included), the hands (the hi-hat but not its pedal, and the ride) and the rest,
each with its own feel, and a position a voice never plays in the reference takes every voice's feel there.
Without `--map`, one feel covers every note. A reference pattern is read through its own map.

A note within a third of a grid step of a grid line the reference plays moves `--timing` percent of the way
to the reference's offset there, and its velocity `--velocity` percent of the way to the reference's
accent, scaled to the average of the note's own voice so a soft part keeps its level. Any other note — a
sixteenth under an eighth-note template, a note in a bar of another length — is left as it was and
counted, and a note that would move before the file's start is held there. Where one voice of the reference
strikes near the same grid line twice in a bar, only the nearer stroke counts, so a ghost note does not
pull the backbeat. The grid is the reference's own: sixteenths when its hands play sixteenths, else eighths,
since a triplet shuffle's off-beat sits nearer the next sixteenth than the "and". Without `--map` there
are no hands to read and the grid is sixteenths, so name `--grid 8` for a shuffle. Every other event comes
back as it was. A `--from` ending in `.mid`, or holding a `/`, that is not a file is refused as a missing file.

| Flag | |
|---|---|
| `--from FILE\|ID` | the reference: a `.mid` file, or a pattern id from the index (required) |
| `-o`, `--out FILE` | the file to write (required) |
| `--map MAP` | the drum map the notes follow; a reference file follows it too |
| `--grid 8\|16` | the template's grid (default: the reference's own) |
| `--timing PCT` | how far each note moves toward the reference, 0–100 (default 100) |
| `--velocity PCT` | how far each velocity moves toward the reference's accent, 0–100 (default 100) |
| `--track N` | change only this track; repeat for more |
| `--force` | replace an existing `--out` file |
| `--db FILE` | the index file, for a pattern id |

### groovebin roots

    groovebin roots bassline.mid
    groovebin roots groove.mid --map ezbass --track 2 --json

Prints the chords a bassline implies, one chart cell a bar: `| Am | F G | E5 |`. A bar's root is the pitch
class held longest in it, the note on the bar counting three times; a bar splits into two chords when each
half has a root of its own that holds 80% of it. A chord is major or minor when the bass holds its third
for at least 5% of it, and otherwise a power chord (`A5`), since a bassline seldom says which. A bar with
no notes keeps the chord before it.

Measured beat by beat on the 9,018 chords EZbass labels the 1,256 grooves it installs with, the root read
matches the label's bass note on 89.7% of beats (the label's root on 87.7%, the gap being slash chords).
Where the label's bass note changes on a beat, the root read changes there too 87.5% of the time, and 77.5%
of the changes it reads are the label's. A major or minor call, made on 17.6% of the beats read right (the
rest print as power chords), is right 88.3% of the time. The chart is the syntax `groovebin` reads chords in.

A `scale` line follows: the major scale and its relative minor whose notes the line holds, found by
Krumhansl and Kessler's key profiles against each pitch class's held length. It names the pair because a
bassline seldom says which of the two is home: across EZbass's grooves, 96.9% of the chords they were
played over have their root in the scale found, while the tonic itself matches the first chord's root only
about two times in three.

| Flag | |
|---|---|
| `--map MAP` | the bass map the notes follow; its keyswitches are left out |
| `--track N` | read only this track; repeat for more |
| `--json` | each chord with its start and end ticks and its bar |

### groovebin analyze

    groovebin analyze bassline.mid
    groovebin analyze bassline.mid --drums drums.mid --drum-map addictive-drums-2 --chords "| Am | F G |"
    groovebin analyze song.mid --track 2 --drums song.mid --drum-track 1 --drum-map gm --map ezbass

Says what a bassline does. On its own: onsets a bar, the share on a beat of its meter (a dotted quarter in
6/8, 9/8 and 12/8), and its lowest and highest notes. With `--drums`, on the same timeline and rescaled to
the bassline's PPQ: the share of bass onsets on a kick, of kicks with a bass onset, and of snares with one.
A `scale` line names the scale the line holds, as `groovebin roots` finds it. With `--chords`, a chart that
repeats when it is shorter than the line: the share of chord changes with the new chord's bass note on
them, and how long the bass holds the chord's own root, third, fifth and seventh, and other notes — B is
not a seventh over C7, whose seventh is B flat. An onset within a 32nd note of another counts as with it,
and only the bassline's own bars count: drums that run past it are left out. With `--map ezbass`,
keyswitches are counted by what they do instead of being read as notes.

| Flag | |
|---|---|
| `--map MAP` | the bass map the notes follow |
| `--track N` | read only this track; repeat for more |
| `--drums FILE` | a MIDI file holding the drums |
| `--drum-map MAP` | the drum map the `--drums` notes follow; needed with `--drums` |
| `--drum-track N` | read only this track of `--drums`; repeat for more |
| `--chords CHART` | the chords under the line, as `groovebin roots` prints them |
| `--json` | the report as JSON |

### groovebin bass

    groovebin bass --drums verse.mid --drum-map addictive-drums-2 --chords "| Am | F G | C | E |" -o bass.mid
    groovebin bass --drums verse.mid --drum-map gm --roots-from my-bassline.mid --map ezbass --mute -o bass.mid

Writes a bassline over a drum file's kicks and a chord chart, by rules measured on EZbass's grooves and
the chords they are labelled with:

- a note on every kick, at the kick's velocity
- the chord's bass note on the first beat and on every change, with or without a kick there: those grooves
  put it on 94% of changes
- a chord tone between changes, drawn in the proportions they play them: root 54, fifth 13, third 7,
  seventh 6.5 (a tone the chord lacks becomes the root)
- with `--approach` percent likelihood (default 58.8, the share of their changes led into this way), an
  approach note one or two sixteenths before a change the line has not already reached: a half or whole
  step below or above the new bass note, or a fifth above it
- each note in the octave nearest the one before, inside `--low` to `--high`, and held to the next note,
  two beats at most

`--library` picks real bars from a bass library instead of the rules: an index built with a bass map and
the chord files beside its grooves (`groovebin index <folder> --map ezbass`). Each drum bar takes the
library bar whose onsets best meet its kicks — as `search --like` measures it — or the bar that followed the
last pick in its own groove when that is within a step of the best, so a groove's phrase carries on. Each
note is re-voiced from the chord it was played over onto the chart's chord at its new place: the bass note
to the new bass note, a third, fifth or seventh to the new chord's own, anything else with the root, the
line's contour kept and folded into the register. A note played just before a bar line, a downbeat pushed
early, belongs to the bar it anticipates, and where two picks come from different grooves the first one's
notes end by the next one's first note, so nothing is struck twice or rings over. Keyswitches and
controllers come as they were, a poly-aftertouch key following the note it touches, and each bar starts
under the vibrato (CC 1), sustain (CC 64), damping (CC 67) and pitch bend its source played it with, reset
to rest where its source had set none, so a pedal one groove held does not stay down in the next. `--role`
and `--tempo` narrow the bars it picks from, and the report names each bar's source.

`--roots-from` takes the chords from another bassline instead, as `groovebin roots` reads them, and prints
the chart it used. With `--map ezbass`, `--mute` puts EZbass's loud-mute keyswitch on each snare the bass
leaves open, as its own "snare to mute" does. The file holds the drum file's tempo and meter on a first
track and the line on a second, at its PPQ. The report counts the notes on kicks, the chord changes, the
approach notes and the mutes; the same seed and files give the same line.

| Flag | |
|---|---|
| `--drums FILE` | the MIDI file holding the drums (required) |
| `--drum-map MAP` | the drum map the drums follow (required) |
| `--drum-track N` | read only this track of `--drums`; repeat for more |
| `--chords CHART` | the chords, a chart that repeats when shorter than the drums |
| `--roots-from FILE` | take the chords from a bassline instead |
| `-o`, `--out FILE` | the file to write (required) |
| `--map MAP` | the bass map to write in, and to read `--roots-from`'s keyswitches with |
| `--mute` | the map's loud-mute keyswitch on each snare the bass leaves open; not with `--library` |
| `--approach PCT` | how often a change gets an approach note, 0–100 (default 58.8); not with `--library` |
| `--library DB` | pick real bars from a bass library index instead of the rules |
| `--role ROLE` | with `--library`, only patterns of this role |
| `--tempo RANGE` | with `--library`, only patterns in this tempo range, as `groovebin search` takes it |
| `--low NOTE`, `--high NOTE` | the register, at least an octave, as note names with C4 = 60 (default E1 to D3); with a bass map it starts above the map's keyswitches |
| `--seed N` | 0 or more; without it a new seed is chosen and printed |
| `--force` | replace an existing `--out` file |

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

With `--map`, the index also records each pattern's feel, read through the map: which sixteenths the
kick, the snare (sidestick included) and the hands (the hi-hat but not its pedal, and the ride) strike in
each bar, and the numbers `search` filters on and `show` prints — density, syncopation, subdivision,
eighth and sixteenth swing, and how far behind the beat the snare sits. A library indexed without a map
has none of these. Every pattern keeps its channel events — controllers, aftertouch, pitch bend, program
changes — beside its notes. An index written by an earlier groovebin is refused; build it again.

A folder index also reads the chord file EZbass keeps beside each of its grooves (`.midchordinfo`), from
the folder you pass and nowhere else: the chords the groove was played over, how often they change a bar,
and whether the first is major or minor. Both the chord file's layouts are read. The report counts the
grooves with chords and any chord file it could not read.

| Flag | |
|---|---|
| `--csv FILE` | read a `MidiDb.csv` instead of a folder; its columns label each pattern |
| `--map MAP` | the note map the patterns follow, stored with each: a drum map records each pattern's feel, a bass map (`ezbass`) makes a library `bass --library` picks from; leave out for any other library |
| `--db FILE` | the index file (default `$XDG_CACHE_HOME/groovebin/library.sqlite`, or under `~/.cache`) |

### groovebin search

    groovebin search --role verse --meter 4/4 --tempo 90-110
    groovebin search --subdivision 16ths --swing16 0.6-0.7 --lag ">5"
    groovebin search --like 3f2a9c --beat
    groovebin search --like my-groove.mid --like-map gm --category Funk
    groovebin search --rhythm "kick=x.....x.x....... snare=....x.......x..."

Lists the patterns matching every filter given, with id, meter, tempo, beat or fill, bars, role,
category, group and variant. `--json` adds every feel column.

The feel filters read what the index recorded with `--map`:

- **density**: kick, snare and hand onsets a bar, each voice counted once per sixteenth
- **syncopation**: a bar's kick and snare together, the bar heard as a loop (Longuet-Higgins and Lee):
  each onset followed by silence over a stronger beat position adds how much stronger it is; 0 when
  every silence falls on a weaker position than the note before it
- **subdivision**: what the hands play against the quarter note — `quarters`, `8ths`, `16ths`, or
  `triplets` when their off-beat strokes sit nearer a triplet grid
- **swing8**: where the off-beat eighth sits in its beat, 0.5 straight and 0.667 a triplet shuffle, over
  beats that hold a hand stroke on the beat and exactly one between 0.4 and 0.72 of it; at least four
  such beats, and only in meters whose beat is a quarter note
- **swing16**: where the off-beat sixteenth sits in its eighth, read the same way
- **lag**: how far behind the beat the snare strikes, in ticks at 960 PPQ, over strokes within an eighth
  of a beat of one; below 0 is ahead of it

`--swing` is the source's own label, a `MidiDb.csv`'s Swing column. Measured against the notes of
Addictive Drums 2's own library, its values below 0.5 go with swung eighths and those above 0.5 with
swung sixteenths; `--swing8` and `--swing16` read either from the notes of any library.

`--like` ranks by rhythm instead, nearest first, with the distance leading each row. For each of the
query's distinct bars that strike anything (the first 16), the nearest bar of the same length in a
pattern counts: each onset one bar has and the other lacks costs 1, or 0.5 for the hands, and half that
when it pairs with an unmatched onset of the other a sixteenth away, each onset pairing once. The
distance is that cost averaged over the query's bars. A pattern with no bar the length of a query bar is
left out, as is the query pattern itself; every other filter still applies. A `--like` ending in `.mid`,
or holding a `/`, that is not a file is refused as a missing file rather than read as an id.

`--rhythm` ranks the same way against a rhythm typed as lanes: `kick=`, `snare=` or `hands=`, then a
character per sixteenth, `x` for a stroke and `.` for none, and `|` between bars. Only the lanes given
count, so `--rhythm "kick=x.....x.x......."` finds that kick under any snare and hands. A lane of one bar
plays in every bar; lanes of several bars give the same number of them, and each bar has as many steps in
every lane — 16 for 4/4, 12 for 3/4. `show ID --rhythm` prints a pattern's lanes in this form, to edit and
search with.

| Flag | |
|---|---|
| `--category TEXT` | whole value, any case |
| `--role ROLE` | intro, verse, pre-chorus, chorus, bridge or outro |
| `--meter N/D` | e.g. `4/4` |
| `--tempo RANGE` | `100-130`, `<90`, `>=140` or `98`; bounds match to the digits written |
| `--fill` | fills only |
| `--beat` | beats only |
| `--swing RANGE` | the source's own swing label, as `--tempo` |
| `--intensity RANGE` | as `--tempo` |
| `--group TEXT` | a substring of the group |
| `--variant TEXT` | a substring of the variant |
| `--library NAME` | whole value, any case |
| `--subdivision KIND` | `quarters`, `8ths`, `16ths` or `triplets` |
| `--density RANGE` | as `--tempo` |
| `--syncopation RANGE` | as `--tempo` |
| `--swing8 RANGE` | as `--tempo` |
| `--swing16 RANGE` | as `--tempo` |
| `--lag RANGE` | as `--tempo`; a bound may be negative: `<-10`, and with `=` for a range that starts with one: `--lag=-20--5` |
| `--quality major\|minor` | the first chord a groove was played over, from its chord file |
| `--changes RANGE` | chord changes a bar, 0 for one chord throughout, as `--tempo` |
| `--like ID\|FILE` | rank by rhythm against a pattern's id or a `.mid` file |
| `--like-map MAP` | the drum map a `--like` file's notes follow; needed for a file, refused for an id |
| `--rhythm LANES` | rank by rhythm against typed lanes; only the lanes given count |
| `--limit N` | at most N rows (default 50; 0 for all) |
| `--json` | the rows as JSON |
| `--db FILE` | the index file |

### groovebin show

    groovebin show 3f2a9c

Draws one pattern, a cell per sixteenth and `|` at each bar: a lane per note number named by its
drum map, or, for a pattern with no drum map, a piano roll with note names and held notes (`=`).
`X` is velocity 100 and up, `x` 64–99, `o` below. A pattern indexed with a map has a `feel` line first:
its density, syncopation, subdivision, swing8, swing16 and lag, named as `search` filters them, `-`
where there was nothing to measure. A pattern with a chord file has a `chords` line: each chord and the bar
it starts in.

With `--rhythm`, it prints only the pattern's kick, snare and hands as the lanes `search --rhythm` reads,
all on one line.

| Flag | |
|---|---|
| `--map MAP` | name each lane from this map instead of the pattern's own |
| `--rhythm` | print its kick, snare and hands as `search --rhythm` lanes |
| `--db FILE` | the index file |

### groovebin generate

    groovebin generate --meter 4/4 --bars 16 --fills --role verse -o verse.mid

Writes a drum phrase picked bar by bar from the library: a picker over real bars, not a model. The
first bar starts a pattern; each next bar has the kick and snare onsets (the notes each pattern's drum
map calls kick and snare, on a sixteenth grid) nearest those of the bar that followed the last pick in
its own pattern. With `--fills`, every fourth bar is the fill bar nearest the groove bar it replaces; a
fill whose last bar is only a landing gives the bar before it. Timing moves up to 5 ticks and velocity
up to 6, and each note ends by the next note of its pitch, so a reader pairs every note-off with its own
note. The file holds the first pick's tempo and the meter, at 960 PPQ.

Bars from different patterns can join awkwardly, and two options smooth the joins. Without them, a seed
gives the same notes at the same times it always has:

- `--crash` puts a crash — the map's `cymbal 1` — on the downbeat after each fill, at the loudest
  velocity there, in place of the hat or ride stroke on that downbeat. A bar with a cymbal on its downbeat
  already is left alone, and a fill that ends the phrase gets none.
- `--level` scales each bar's velocities so its kick and snare median matches the first such median in
  the phrase, before the velocity is humanised. The picks and the timing stay as the seed gives them.

The listing names the pool, the seed, every bar's source pattern, and what `--crash` and `--level` did;
the same seed, options and index give the same file. Patterns need a drum map (`groovebin index --map`).

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
| `--crash` | a crash on the downbeat after each fill |
| `--level` | level each bar's velocities to the phrase's kick and snare median |
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
| `drum-kit-designer-brushes` | Drum Kit Designer's brush snare kits, from the same keymap: the GM Standard keys and the brush keys below them |
| `ezbass` | EZbass's key switch layout published by its vendor, and the controllers its manual reserves |

Each map gives notes a term such as `hihat open`. A note translates to the destination note with
the same term, else one whose term extends it, else the term less its last word. A choke or a
stick click never falls back onto a strike, nor to its first word alone, so a ride choke never
stops a crash. Terms and pairings are these tables' own choices, not the vendors'. Translation is
not always reversible: several Addictive Drums 2 snare strokes become one GM snare.

`drum-kit-designer-brushes` adds the brush keys below 31 — sweeps and circles that play for as long as the
key is held, a drag and two mutes — to the GM Standard keys, which translate as `drum-kit-designer`'s do. A
brush key never falls back onto a strike, so remapped to a kit without brushes it is counted, not turned into
a snare hit; a remap keeps each note's channel, which picks the hand. Drum Kit Designer's GM + ModWheel mode
has no map: it opens the hi-hat with the mod wheel, and a translation would have to guess where open starts.

`ezbass` is a bass map. It plays any pitch from 21 to 64 (A0 to E4) and names only the twelve keyswitches
below that range (9 to 20, from polyphony to legato: a ghost note is 16, a slide up 19) and the
controllers it reserves: 1 vibrato, 64 sustain, 67 damping. `groovebin notes --map ezbass` names each
keyswitch; `groovebin index --map ezbass` keeps the map with a bass library, which records no drum feel
and shows as a piano roll. A bass map and a drum map do not translate into each other, and `groovebin
remap` takes drum maps only.

## What a read and write keeps

Reading a file and writing it back keeps every note (start, length, channel, pitch, velocity and
note-off velocity), every other event at its tick, and each track's end. Events of different
kinds at one tick are written in a fixed order (controllers before a program change, so a bank
select applies to it), and a note-off with no note before it is dropped. An F7 escape is kept as an
escape and written back as one, and a SysEx split into packets is read as its packets and written
back the same way; a SysEx holding a data byte of 0x80 or more is refused.
