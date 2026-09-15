# Changelog

All notable changes to this project are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versioning: [SemVer](https://semver.org/).

## [Unreleased]

## [0.1.0] — 2026-09-14

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
