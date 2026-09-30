# Using groovebin from Python

How to build on groovebin as a library: which layer to import for a job, the rules every function keeps, and how to add a note map.

This page is about code that imports `groovebin`. For the `groovebin` command, see [usage.md](usage.md); every command there is one call into the library described here.

---

## Table of Contents

- [The rules every layer keeps](#the-rules-every-layer-keeps)
- [Files and the note model](#files-and-the-note-model)
- [Note maps](#note-maps)
- [Transforms](#transforms)
- [Harmony](#harmony)
- [The pattern library](#the-pattern-library)
- [Drum feel](#drum-feel)
- [Bass](#bass)
- [Adding a note map](#adding-a-note-map)

## The rules every layer keeps

Do:
- Do your own file IO. The library reads and returns `bytes` (`midi.read`, `midi.write`) and never opens a file except the pattern index and the files you ask it to index. Write output atomically if a failed run must not leave half a file.
- Catch `ValueError` for anything the library refuses: malformed files (`midi.MidiFileError`, a subclass), out-of-range values, unknown map names. Expect `OSError` for a folder or index that is not there, `OverflowError` for a tick past what the index stores, and `sqlite3.Error` from a damaged index.
- Treat every function as pure: a transform returns a new `Part`, and `maps.remap` a new `Part` with a count of the notes that had no counterpart; each leaves its input alone, so you can keep both.
- Pass seeds for anything random (`generate`, `bass_line`, humanize presets). The same inputs and seed give the same result.

Do not:
- Expect logging, printing or environment reads below the command line. The library says nothing; `library.default_db(cache_home)` takes the cache folder from you instead of reading `XDG_CACHE_HOME`.
- Hard-code note numbers for a drum piece. Ask the map (`drum_map(name).family("kick")`, `library.groove.voices(name)`), so the same code works for every kit.

## Files and the note model

`midi.read(data)` gives a `song.Song`: its PPQ, its format (0 or 1) and a `Part` per track. A `Part` holds `events.Note`s — a note-on and its note-off paired into a start, a length, a channel 1–16, a pitch, velocities — and `events.Event`s, every other event kept as its file bytes. `midi.write(song)` gives the bytes back. A read and a write keep every note and event; only the order of different kinds at one tick is normalised.

Rules the model keeps, which callers get wrong:
- Pairing is first in, first out: a note-off closes the earliest open note of its channel and pitch. `Part.nested_ons` counts the note-offs that found more than one open, where the file left the pairing ambiguous; `song.nested_overlaps(part)` finds pairs a transform has nested so that a reader would swap their lengths.
- A `Part` sorts its notes and events on construction. Build one from any order.
- Ticks are the file's own. Use `song.rescale(part, ppq)` to bring parts from files of different PPQ onto one timeline, and `song.meter_map(song)` / `tempo_map(song)` for bars and tempo; bar 1 starts at tick 0.
- `song.merged(song)` gives every track as one `Part`, for anything that reads a whole file.

## Note maps

A note map says what each note plays. Load one with `maps.note_map(name)`; use `maps.drum_map(name)` where only a drum map will do, since it refuses a bass map by name. `maps.NAMES` lists the drum maps, `maps.BASS_NAMES` the bass maps, `maps.ALL_NAMES` both.

- A drum map names every note it plays with a term — words from general to specific, `hihat open b`. `maps.translate(note, src, dst)` finds the destination note with the same term, else one that extends it, else the term less its last word; a term that leads with a non-strike word (`maps.NOT_STRIKES`: a choke, a stick click, a brush stroke) never falls back onto a strike. None means no counterpart.
- A bass map (`kind == "bass"`) plays any pitch in its `range` and names only its keyswitches, below the range, and the `controllers` it reserves. Use `NoteMap.is_keyswitch(pitch)` before moving a note's pitch: a transposed keyswitch is a different articulation.
- `maps.remap(part, src, dst, channels=, unmapped=)` translates a Part's notes and poly-aftertouch keys and counts what had no counterpart; it refuses a bass map and a drum map as a pair. `maps.landings` and `maps.folds` say which destination notes several source pitches reach.

## Transforms

`groovebin.transforms` edits Parts: whole-part edits in `edits` (transpose, quantize, shift, stretch, swing, velocity curves, merge, delete), selection and per-note operations in `select`, and Logic's Transform presets in `presets`.

- Select with `select(part, **conditions)`, which gives note indices, and pass them as a mask to `apply_all(part, mask, operations, seed=, meters=)`. A mask of None means every note.
- Carry note identity across several passes in `Note.tag`: every transform keeps a note's tag, while indices change when notes re-sort.
- A refusal whose wording names the Part is a `transforms.PartWording`, a `ValueError`. Rewrite its wording for your users if you call the Part something else; leave every other message alone, since it may quote the user's own input.

## Harmony

`groovebin.harmony` is pitch classes, chords and charts in plain Python.

- Read chords with `parse_chord("Am7/G")` and charts with `chart("| Am | F G | % |")` — bars of chords that share each bar evenly. `chart_spans(chart, meters, bars)` lays a chart over bars as `Span`s, repeating a shorter chart.
- `roots(notes, meters, bars)` gives the chords a bassline implies, and `chart_text` prints them as a chart. Expect the root to match EZbass's labelled bass note on about nine beats in ten, and a power chord (`A5`) where the bass never plays the third; see [usage.md](usage.md#groovebin-roots) for the measurement.
- `scale_of(notes)` names the scale a line holds by the tonic of its major key; `scale_name` gives the major and relative-minor pair. Do not present the tonic as the key — a bassline seldom says which of the pair is home.
- `revoice(pitch, source, target)` moves a note played over one chord to fit another, keeping its role: the bass note, a third, fifth or seventh.

## The pattern library

`library.index.build(db, folder=… | csv_path=…, map_name=…)` indexes a folder of `.mid` files or a `MidiDb.csv` into SQLite, replaced whole on success. Rows keep the notes and channel events at the index's 960 PPQ (`library.blobs`), labels from the paths, and — with a drum map — each pattern's feel; a folder index also reads the EZbass chord file beside each groove.

- Search with `library.search.search(db, **filters)`, rank by rhythm with `similar(db, bars)`, and fetch one row with `get(db, id)`; `library.pattern.pattern(row)` turns a row into bars you can lay out.
- Check the schema error, not the SQL error: an index an older groovebin wrote is refused with a `ValueError` that says to build it again.
- `library.generate` picks drum bars into a phrase (`load_pool`, `phrase`, `phrase_song`); `library.compose` plans a part over a song's sections from one group. Neither writes a file.

## Drum feel

`library.groove` reads what a drum part plays through its map: `rhythm` gives each bar's kick, snare and hands onsets on a sixteenth grid, and `features` its density, syncopation, subdivision, eighth and sixteenth swing and snare lag. `bar_distance` and `distance` compare rhythms as `search --like` does; pass `voices` to count only some of them. `library.groove_text.parse_rhythm` reads typed lanes into bars and the voices they give, and `rhythm_text` writes bars back out. `library.feel` takes a groove template from one part (`template`, `file_template`, `pattern_template`) and applies it to another (`apply_feel`).

## Bass

- `library.bassline.analyze(notes, meters, bars, bass_map=, drums=, drum_map=, spans=)` reports a line's rhythm, its lock with a drum part's kick and snare, and how it plays chord spans.
- `library.bass_rules.bass_line(kicks, snares, spans, ppq, seed=)` writes a line by rules; `library.bass_picker` picks bars from a bass library (`load_bass_bars`, `pick_bass`) and lays them onto a chart (`lay`), re-voiced, with their keyswitches and controllers.
- Kicks and snares come from `library.groove.voices(drum_map)`, never from note numbers.

## Adding a note map

1. Find a source first: a vendor's published keymap, a standard, or counts measured from files the instrument's own software wrote. A note no source names stays out — None beats a guess.
2. Write `src/groovebin/data/maps/<name>.json` with `source` (the document, its date or version, and any counts — never a private file or pack name), `note` (what is the source's and what is this table's choice), `prefer` and `notes`, each note with the source's `name` and a `term`. A bass map adds `"kind": "bass"`, `range` and `controllers`, and lists only its keyswitches, with terms that lead with `keyswitch`.
3. Choose terms that translate: reuse the words the other maps use for the same stroke, and lead a stroke that is not a strike with a word in `NOT_STRIKES`.
4. Add the name to `maps.NAMES` or `maps.BASS_NAMES`. The map-wide tests in `tests/test_maps.py` run over every drum map; for a bass map, pin its range, keyswitches and controllers as `tests/test_maps_bass.py` does. Add tests that pin how its notes translate to each other map of its kind.
5. Add a row to the note map table in [usage.md](usage.md#note-maps).
