# Contributing to groovebin

Bug reports, map corrections backed by a source, and fixes with tests are all welcome.

## The one rule: every note and event survives

groovebin reads each track into notes (start, length, channel, pitch, velocity, release
velocity) and every other event — controllers, program changes, pitch bend, aftertouch, meta
and SysEx — at its tick. Writing a file back and reading it again gives the same notes and the
same events, track for track. Three things are normalised, not kept: events of different kinds at
one tick are written in a fixed order, a note-off with no note before it is dropped and reported,
and an F7 escape is written as a SysEx event. A remap changes note pitches and aftertouch keys and nothing else. A change that loses
or alters any other note or event on a real file is a bug, no matter what else it fixes.

If you find a file that does not survive a round trip, that is the most valuable report you
can file. Describe what wrote the file and which events changed; you don't need to attach the
file itself.

## Setup

```bash
bin/run setup          # venv (needs python3.12 on PATH), editable install, pf-core docs link
bin/run pytest
bin/run lint           # ruff + pf-core's structural gate
```

## Conventions

- **A map entry needs a source.** A vendor's published keymap, a standard's own table, or
  notes measured from files the instrument's software wrote — named in the map's `source`. A
  note no source names stays out of the map.
- **Library code is quiet.** The library imports the standard library only; logging,
  printing, environment variables and pf-core belong to the CLI modules.
  `tests/test_package_layering.py` enforces this and the module layers.
- **One concern per file.** `bin/run lint` runs pf-core's file-size gate; if a file is over,
  split it rather than grandfathering it.
- **Edit commands never overwrite their input.** They write a new file.
- **Docs travel with code.** A new command or flag is documented in `docs/usage.md`;
  `tests/test_docs.py` fails when one is missing. User-visible changes go in `CHANGELOG.md`
  under Unreleased.
- `X | None` types, src-layout, no `sys.path` manipulation.

## Tests

New behaviour needs a test, and a bug fix needs a test that fails without the fix. Tests pass
on a fresh clone with no DAW, no plug-in and no user files: build the MIDI in the test with
mido. Never commit a `.mid` file or a real pattern, song or pack name.

## Reporting security issues

Email **oss@phierceweb.com** rather than opening a public issue.

## License

Contributions are accepted under the Apache License 2.0. Opening a pull request licenses your
work to the project under those terms.
