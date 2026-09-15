# groovebin

MIDI files, note maps and a pattern library in Python. It reads and writes Standard MIDI Files,
translates notes between instrument maps — General MIDI drums, Addictive Drums 2, Logic's Drum Kit
Designer — and indexes a folder of MIDI patterns so they can be searched, shown and recombined.
Nothing needs a DAW or a plug-in installed or running.

Status: alpha. Commands, the library API and the index format may change before 1.0.

## Install

    pip install groovebin
    groovebin --version

Needs Python 3.12 or newer.

## Commands

    groovebin remap IN.mid --from drum-kit-designer --to addictive-drums-2 -o OUT.mid
    groovebin notes IN.mid --map gm
    groovebin index ~/Grooves --map addictive-drums-2
    groovebin search --role verse --meter 4/4 --tempo 90-110
    groovebin generate --meter 4/4 --bars 16 --fills --role verse -o verse.mid

Usage: [docs/usage.md](https://github.com/phierceweb/groovebin/blob/main/docs/usage.md).
Changes: [CHANGELOG.md](https://github.com/phierceweb/groovebin/blob/main/CHANGELOG.md).

## Develop

From a checkout:

    bin/run setup
    bin/run pytest
    bin/run lint        # ruff + the pf-core structural gate (300 soft / 500 hard lines)

See [CONTRIBUTING.md](https://github.com/phierceweb/groovebin/blob/main/CONTRIBUTING.md).

groovebin ships note-number tables only: no sounds, patterns or MIDI content from any vendor.
