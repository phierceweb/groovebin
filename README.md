# groovebin

A drum groove programmed for one kit plays the wrong sounds on another, a folder of thousands of patterns can
only be browsed by file name, and a bassline has to be written against the drums by hand. groovebin does these
jobs on the MIDI files themselves, in Python, with no DAW or plug-in installed or running.

It reads and writes Standard MIDI Files and keeps every event in them. It translates notes between instrument
maps, so a groove made for one kit plays on another: General MIDI drums, Addictive Drums 2, Logic's Drum Kit
Designer and its brush kits, and EZbass's keyswitches. It transforms notes by selection (velocity curves,
humanize, swing, note lengths) and lays one part's feel on another. It moves a part within a key, too: stray
notes onto the scale, every note a step along it, or the whole part into another key or mode. It reads a file's
tempo changes, ramps included, and its key signatures, gives each note's time in seconds, and writes new tempo
changes and key signatures into a copy. It indexes a folder of patterns so they can be searched by section,
meter, tempo and feel, or ranked by how close their rhythm is to a groove you give it, and it strings real bars
together into new phrases.

For bass, it reads the chords a bassline implies and can write their roots out as a MIDI part for another line
to follow, reports how a line sits with the kick and with the chords, and writes a new line over a drum part,
by rules or by picking real bars from a bass library and moving them onto your chords. On the 1,256 grooves
EZbass installs, the root it reads from each bassline matches the bass note of EZbass's own chord labels on
89.7% of beats; that is one vendor's library, and other styles may read differently. It calls a chord major or
minor only where the bass plays the third.

Status: alpha. Commands, the library API and the index format may change before 1.0.

## Install

    pip install groovebin
    groovebin --version

Needs Python 3.12 or newer.

## Commands

    groovebin remap IN.mid --from drum-kit-designer --to addictive-drums-2 -o OUT.mid
    groovebin notes IN.mid --map gm
    groovebin tempo IN.mid --ramp 17-25:100-132 -o OUT.mid
    groovebin transform IN.mid -o OUT.mid --preset humanize --seed 7
    groovebin transform IN.mid -o OUT.mid --track 2 --map ezbass --preset change-key="E minor"
    groovebin index ~/Grooves --map addictive-drums-2
    groovebin search --role verse --meter 4/4 --tempo 90-110
    groovebin generate --meter 4/4 --bars 16 --fills --role verse -o verse.mid
    groovebin search --like 3f2a9c --beat
    groovebin anchors groove.mid --map addictive-drums-2
    groovebin feel programmed.mid --from played.mid --map gm -o felt.mid
    groovebin roots bassline.mid --map ezbass -o roots.mid
    groovebin bass --drums verse.mid --drum-map gm --chords "| Am | F G |" -o bass.mid

Usage: [docs/usage.md](https://github.com/phierceweb/groovebin/blob/main/docs/usage.md).
Python API: [docs/api.md](https://github.com/phierceweb/groovebin/blob/main/docs/api.md).
Changes: [CHANGELOG.md](https://github.com/phierceweb/groovebin/blob/main/CHANGELOG.md).

## Develop

From a checkout:

    bin/run setup
    bin/run pytest
    bin/run lint        # ruff + the pf-core structural gate (300 soft / 500 hard lines)

See [CONTRIBUTING.md](https://github.com/phierceweb/groovebin/blob/main/CONTRIBUTING.md).

groovebin ships note-number tables only: no sounds, patterns or MIDI content from any vendor.
