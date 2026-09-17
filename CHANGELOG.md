# Changelog

All notable changes to this project are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versioning: [SemVer](https://semver.org/).

## [0.3.0] — 2026-09-17

### Added
- `maps.landings`, `maps.folds` and `maps.collisions`: a Part's (channel, destination pitch) landings, the
  destinations more than one source pitch reaches, and the two over one Part. Landings take `unmapped` and
  read polyphonic aftertouch keys as well as notes.
- `song.skipped_meters`: how many of a song's time signatures `meter_map` leaves out.
- `Part.nested_ons`: the note-offs that found two of their key open.
- `library.default_db(cache_home)`: the index path, the cache root passed in, an empty one read as unset.
- `transforms.PartWording`: a refusal whose wording names the Part.

### Changed
- `write` is groovebin's own serializer; mido is a test dependency only.
- `remap` merges every covered track's landings and names each destination note more than one source pitch
  reaches, a kept unmapped pitch included.
- `notes` and `transform` print how many time signatures were skipped; `notes` also reports the same-pitch
  pairings the file left open and the note-offs it dropped, as `remap` and `transform` do.
- The note-off and same-pitch warnings count the whole file, not the tracks `--track` named.
- `index` records no meter for a file whose only time signatures the meter map cannot use, rather than the
  4/4 the map falls back to.
- The command line says "track" where the library says "part": it rewrites a `PartWording` refusal and
  leaves every other message as it reads.
- `_parsers.default_db` resolves `XDG_CACHE_HOME` through pf-core.

### Fixed
- A SysEx split into packets reads as its packets, and an F7 escape stays an escape, its bytes untouched,
  a status among them included.
- A time signature the file's PPQ cannot hold in whole ticks is skipped rather than failing `notes`,
  `transform` and the index.
- The nested same-pitch warning counts the input's ambiguous pairs, not only the output's.
- `apply`, `apply_all`, `operations` and `velocity_band` refuse a value of the wrong shape with a
  `ValueError`; `write` refuses a song with no track, and a `Song` a PPQ below 1.
- A date in a path (`2024-08-16`) no longer reads as a meter hint; a meter beside a hyphen or a slash
  (`Rock 6-8-A`, `3/4-Fill`) still does.
- `transforms.delete` drops a deleted key's polyphonic aftertouch with its notes.
- `transform --seed` refuses a non-decimal digit such as `²`; `search --limit` refuses a value past what
  sqlite counts before the query runs.
- A refusal that quotes a file name or a `--select` condition comes back as the user typed it.

## [0.2.0] — 2026-09-15

### Added
- `groovebin transform`: notes selected by position, pitch, velocity, length and channel (`--select`, read once
  for the whole run), changed by `--op` set, add, mul, min, max, random, flip, quantize, crescendo, exp and
  reverse, or by a `--preset`: humanize, fixed-velocity, velocity-limit, random-velocity, crescendo,
  reverse-position, reverse-pitch, exp-velocity, fixed-length, max-length, min-length, half-speed,
  double-speed, legato, staccato and swing; `--presets` lists them, `--seed` repeats a run. An operation writes
  only the field it names, a position quantize snaps to the grid lines of the note's bar, and the run reports
  same-pitch note pairs its result leaves nested and note-offs dropped on read, as `groovebin remap` does.
- Library: `transforms` is a package — `select`, `apply`, `apply_all`, `humanize`, `position_ticks`, `stretch`,
  `note_lengths`, `velocity_curve`, `swing`, and the preset table with `run`.

### Fixed
- A tick gap past the 268435455 a variable-length quantity can hold is refused on write, and a delta time of
  more than four bytes is refused on read.
- The nested-note report says "note pair(s)", which is what it counts.

## [0.1.0] — 2026-09-15

First release.

### Added
- `groovebin remap`: translate a MIDI file's drum notes and polyphonic aftertouch keys from one note map to
  another, scoped by `--track` and `--channel`; notes with no counterpart are kept or dropped (`--unmapped`).
- `groovebin notes`: a file's tracks and notes with bar positions and stroke names.
- `groovebin index`: a sqlite pattern library from a folder of `.mid` files, labelled from their paths, or
  from a `MidiDb.csv`.
- `groovebin search` and `groovebin show`: filter patterns by label, role, meter, tempo, swing and intensity;
  draw one as drum lanes or a piano roll.
- `groovebin generate`: a drum phrase picked bar by bar from library bars, with fills and a repeatable seed.
- Note maps `gm` (General MIDI Level 1 percussion), `addictive-drums-2` and `drum-kit-designer` (GM Standard
  input mapping).
- Library: Standard MIDI File read and write (format 0 and 1) through paired notes and every other event,
  tempo and meter maps, note transforms (transpose, velocity, shift, delete, quantize, merge), map
  translation, and section planning (`library.compose`).
