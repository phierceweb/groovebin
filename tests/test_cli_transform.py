"""`groovebin transform` on files the test builds: the selection and operations land, and everything else
comes back as the Song it was."""

from transform_fixture import NOTES, build, mid, run

from groovebin.events import Note
from groovebin.midi import read
from groovebin.transforms import PRESETS, Operation, apply_all


def test_selected_notes_change_and_the_rest_of_the_file_survives(tmp_path, capsys):
    src, out = build(tmp_path / "in.mid", NOTES), tmp_path / "out.mid"
    rc, text, _ = run(capsys, "transform", src, "-o", out, "--select", "velocity<50,position=1", "--op", "add:velocity=10",
                      "--op", "set:length=1/8")
    assert rc == 0, text
    assert "track 1: 2 of 5 note(s) selected; add:velocity=10; set:length=1/8" in text
    before, after = read(src.read_bytes()).tracks[0], read(out.read_bytes()).tracks[0]
    assert [(n.tick, n.pitch, n.velocity, n.length) for n in after.notes] == \
        [(0, 36, 100, 120), (480, 38, 50, 240), (960, 42, 40, 240), (1440, 36, 90, 120), (2280, 38, 20, 120)]
    assert after.events == before.events and after.end == before.end


def test_a_position_in_time_is_read_through_the_files_tempo(tmp_path, capsys):
    """At 60 bpm and PPQ 480 a second is 480 ticks; at the default 120 bpm the same times would pick 960 and 1440."""
    src, out = build(tmp_path / "in.mid", NOTES, tempo=1_000_000), tmp_path / "out.mid"
    rc, text, _ = run(capsys, "transform", src, "-o", out, "--select", "position=0:01-2s", "--op", "set:velocity=1")
    assert rc == 0, text
    assert "track 1: 2 of 5 note(s) selected" in text
    assert [(n.tick, n.velocity) for n in read(out.read_bytes()).tracks[0].notes] == \
        [(0, 100), (480, 1), (960, 1), (1440, 90), (2280, 20)]


def test_a_time_copied_from_notes_selects_that_note(tmp_path, capsys):
    """At PPQ 960 and 120 bpm a tick is about half a millisecond, so a printed time often names two ticks, and tick 24
    falls on 12.5 ms exactly, which prints rounded up."""
    notes = [(0, 36, 100, 60), (24, 37, 100, 60), (320, 38, 100, 60), (641, 42, 100, 60), (2119, 40, 100, 60)]
    src = build(tmp_path / "in.mid", notes, ppq=960)
    _rc, text, _ = run(capsys, "notes", src)
    printed = [line.split()[2] for line in text.splitlines() if " note " in line]
    assert printed[:3] == ["0:00.000", "0:00.013", "0:00.167"]
    for at in printed:
        rc, text, _ = run(capsys, "transform", src, "-o", tmp_path / "out.mid", "--force", "--select", f"position={at}",
                          "--op", "set:velocity=1")
        assert rc == 0 and "track 1: 1 of 5 note(s) selected" in text, (at, text)


def test_the_selection_is_read_once_and_every_step_works_on_those_notes(tmp_path, capsys):
    src, out = build(tmp_path / "in.mid", NOTES), tmp_path / "out.mid"
    rc, text, _ = run(capsys, "transform", src, "-o", out, "--select", "velocity<50", "--op", "add:velocity=20",
                      "--preset", "fixed-velocity=100")
    assert rc == 0, text
    assert "track 1: 3 of 5 note(s) selected" in text
    assert [(n.tick, n.velocity) for n in read(out.read_bytes()).tracks[0].notes] == \
        [(0, 100), (480, 100), (960, 100), (1440, 90), (2280, 100)]


def test_the_selection_follows_the_notes_through_a_step_that_reorders_them(tmp_path, capsys):
    src, out = build(tmp_path / "in.mid", NOTES), tmp_path / "out.mid"
    rc, text, _ = run(capsys, "transform", src, "-o", out, "--select", "pitch=36", "--op", "add:position=1000",
                      "--preset", "fixed-velocity=1")
    assert rc == 0, text
    assert [(n.tick, n.pitch, n.velocity) for n in read(out.read_bytes()).tracks[0].notes] == \
        [(480, 38, 40), (960, 42, 30), (1000, 36, 1), (2280, 38, 20), (2440, 36, 1)]


def test_a_position_quantize_lands_on_a_grid_line_of_its_bar(tmp_path, capsys):
    src, out = build(tmp_path / "in.mid", [(1600, 36, 100, 120)], meter=(7, 8)), tmp_path / "out.mid"
    rc, text, _ = run(capsys, "transform", src, "-o", out, "--op", "quantize:position=1/4")
    assert rc == 0, text
    assert [n.tick for n in read(out.read_bytes()).tracks[0].notes] == [1680]     # bar 2's line, not 1440


def test_a_dotted_note_value_selects_lengths_and_sets_the_grid(tmp_path, capsys):
    """A 1/8. grid restarts at each bar line: in 4/4 its lines are 0, 360 … 1800, then the next bar's 1920."""
    notes = [(350, 36, 100, 180), (1700, 38, 100, 120), (1880, 40, 100, 180), (2300, 42, 100, 180)]
    src, out = build(tmp_path / "in.mid", notes), tmp_path / "out.mid"
    rc, text, _ = run(capsys, "transform", src, "-o", out, "--select", "length=1/16.", "--op", "quantize:position=1/8.",
                      "--op", "set:length=1/4.")
    assert rc == 0, text
    assert "track 1: 3 of 4 note(s) selected" in text
    assert [(n.tick, n.length) for n in read(out.read_bytes()).tracks[0].notes] == \
        [(360, 720), (1700, 120), (1920, 720), (2280, 720)]


def test_double_speed_never_writes_a_note_with_no_length(tmp_path, capsys):
    src, out = build(tmp_path / "in.mid", [(1, 36, 100, 1), (3, 38, 100, 1)]), tmp_path / "out.mid"
    rc, text, _ = run(capsys, "transform", src, "-o", out, "--preset", "double-speed")
    assert rc == 0, text
    assert [n.length for n in read(out.read_bytes()).tracks[0].notes] == [1, 1]


def test_a_preset_with_a_seed_repeats_and_random_prints_its_seed(tmp_path, capsys):
    src = build(tmp_path / "in.mid", NOTES)
    a, b, c = (tmp_path / f"{k}.mid" for k in "abc")
    assert run(capsys, "transform", src, "-o", a, "--preset", "humanize", "--seed", "7")[0] == 0
    assert run(capsys, "transform", src, "-o", b, "--preset", "humanize=pos=10,vel=8,len=5", "--seed", "7")[0] == 0
    assert a.read_bytes() == b.read_bytes()
    rc, text, _ = run(capsys, "transform", src, "-o", c, "--preset", "random-velocity=5", "--seed", "random")
    assert rc == 0 and any(line.startswith("seed ") for line in text.splitlines())
    assert read(a.read_bytes()).tracks[0].events == read(src.read_bytes()).tracks[0].events


def test_whole_track_presets_and_swing_by_bar(tmp_path, capsys):
    src, out = build(tmp_path / "in.mid", NOTES), tmp_path / "out.mid"
    rc, text, _ = run(capsys, "transform", src, "-o", out, "--preset", "half-speed")
    assert rc == 0, text
    after = read(out.read_bytes()).tracks[0]
    assert [n.tick for n in after.notes] == [0, 960, 1920, 2880, 4560] and after.events[-1].tick == 20
    rc, text, _ = run(capsys, "transform", src, "-o", tmp_path / "swing.mid", "--preset", "swing=60%:1/16")
    assert rc == 0, text
    assert [n.tick for n in read((tmp_path / "swing.mid").read_bytes()).tracks[0].notes] == [0, 480, 960, 1440, 2280 + 24]


def test_presets_are_listed(capsys):
    rc, text, _ = run(capsys, "transform", "--presets")
    assert rc == 0
    assert all(p.name in text for p in PRESETS) and "required" in text and "optional" in text and "default 20..110" in text


def test_an_operation_on_one_field_leaves_the_others_alone(tmp_path, capsys):
    src = mid(tmp_path, Note(0, 0, 1, 36, 100), Note(480, 240, 1, 38, 80))
    out = tmp_path / "out.mid"
    rc, text, _ = run(capsys, "transform", src, "-o", out, "--op", "add:velocity=5")
    assert rc == 0, text
    after = read(out.read_bytes()).tracks[0]
    assert [(n.pitch, n.velocity, n.length) for n in after.notes] == [(36, 105, 0), (38, 85, 240)]


def test_the_written_file_reads_back_to_the_notes_the_transform_made(tmp_path, capsys):
    src, out = build(tmp_path / "in.mid", NOTES), tmp_path / "out.mid"
    rc, text, _ = run(capsys, "transform", src, "-o", out, "--op", "add:velocity=10", "--op", "set:length=1/8")
    assert rc == 0, text
    wanted = apply_all(read(src.read_bytes()).tracks[0], None,
                       [Operation("velocity", "add", 10), Operation("length", "set", 240)])
    fields = lambda part: [(n.tick, n.pitch, n.velocity, n.length) for n in part.notes]  # noqa: E731
    assert fields(read(out.read_bytes()).tracks[0]) == fields(wanted)
