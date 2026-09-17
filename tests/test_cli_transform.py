"""`groovebin transform` on files the test builds: the selection and operations land, everything else
comes back byte for byte as a Song, and the refusals name their rule."""

import struct

import pytest
from mido import Message, MetaMessage, MidiFile, MidiTrack

from groovebin.cli import main
from groovebin.events import Event, Note
from groovebin.midi import read, write
from groovebin.song import Part, Song
from groovebin.transforms import PRESETS, Operation, apply_all


def build(path, notes, ppq=480, meter=None):
    """``(tick, pitch, velocity, length)`` notes on channel 1 plus a controller and a program change."""
    mf = MidiFile(ticks_per_beat=ppq)
    track = MidiTrack()
    events = [(0, MetaMessage("set_tempo", tempo=500000)), (0, Message("program_change", program=5)),
              (10, Message("control_change", control=7, value=100))]
    if meter:
        events.append((0, MetaMessage("time_signature", numerator=meter[0], denominator=meter[1])))
    events += [(t, Message("note_on", note=p, velocity=v)) for t, p, v, _l in notes]
    events += [(t + n, Message("note_off", note=p, velocity=0)) for t, p, _v, n in notes]
    events.sort(key=lambda e: (e[0], e[1].type == "note_on"))
    last = 0
    for t, msg in events:
        msg.time = t - last
        track.append(msg)
        last = t
    mf.tracks.append(track)
    mf.save(str(path))
    return path


NOTES = [(0, 36, 100, 120), (480, 38, 40, 120), (960, 42, 30, 60), (1440, 36, 90, 120), (1920 + 360, 38, 20, 120)]


def run(capsys, *argv):
    rc = main([str(a) for a in argv])
    out, err = capsys.readouterr()
    return rc, out, err


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


def test_a_value_a_preset_cannot_use_is_a_message_not_a_traceback(tmp_path, capsys):
    src = build(tmp_path / "in.mid", [(0, 36, 1, 120), (480, 38, 40, 120)])
    for argv, message in ((["--preset", "exp-velocity=-1"], "not a number above 0"),
                          (["--preset", "velocity-limit=110..20"], "runs backwards"),
                          (["--preset", "reverse-pitch=200"], "not a note number 0-127"),
                          (["--select", "position=0-1", "--op", "add:velocity=1"], "before bar 1")):
        rc, _, err = run(capsys, "transform", src, "-o", tmp_path / "out.mid", *argv)
        assert rc == 1 and message in err, err
        assert not (tmp_path / "out.mid").exists()


def test_a_position_quantize_lands_on_a_grid_line_of_its_bar(tmp_path, capsys):
    src, out = build(tmp_path / "in.mid", [(1600, 36, 100, 120)], meter=(7, 8)), tmp_path / "out.mid"
    rc, text, _ = run(capsys, "transform", src, "-o", out, "--op", "quantize:position=1/4")
    assert rc == 0, text
    assert [n.tick for n in read(out.read_bytes()).tracks[0].notes] == [1680]     # bar 2's line, not 1440


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


@pytest.mark.parametrize(("argv", "message"), [
    (["--op", "add:velocity=10"], "takes IN.mid and -o"),
    (["--presets", "--force"], "takes nothing else"),
    (["--presets", "--seed", "5"], "takes nothing else"),
    (["in.mid", "-o", "out.mid", "--op", "crescendo:velocity=-5..500"], "not inside 1..127"),
    (["in.mid", "-o", "out.mid", "--select", "pitch=127", "--op", "reverse:channel"], "not channel"),
    (["in.mid", "-o", "out.mid", "--preset", "legato=" + "9" * 308], "not a finite number"),
    (["in.mid", "-o", "out.mid", "--op", "add:position=268435455", "--op", "add:position=268435455"],
     "is past the 268435455 a file can hold"),
    (["in.mid", "-o", "out.mid"], "at least one --op or --preset"),
    (["in.mid", "-o", "out.mid", "--op", "velocity=10"], "OP:FIELD"),
    (["in.mid", "-o", "out.mid", "--preset", "loud"], "no such preset"),
    (["in.mid", "-o", "out.mid", "--preset", "half-speed", "--select", "pitch=36"], "drop --select"),
    (["in.mid", "-o", "out.mid", "--preset", "fixed-velocity"], "needs a value"),
    (["in.mid", "-o", "out.mid", "--op", "grow:velocity=1"], "no operation 'grow'"),
    (["in.mid", "-o", "out.mid", "--op", "add:velocity=1", "--seed", "-1"], "--seed '-1'"),
    (["in.mid", "-o", "out.mid", "--op", "add:position=-9999"], "before the track's start"),
    (["in.mid", "-o", "out.mid", "--op", "add:velocity=1", "--seed", "\u00b2"], "--seed '\u00b2': 0 or more, or random"),
    (["in.mid", "-o", "out.mid", "--track", "3", "--op", "add:velocity=1"], "track 3 is not in"),
])
def test_refusals_name_the_rule_and_write_nothing(tmp_path, capsys, monkeypatch, argv, message):
    monkeypatch.chdir(tmp_path)
    build(tmp_path / "in.mid", NOTES)
    rc, _, err = run(capsys, "transform", *argv)
    assert rc == 1 and message in err, err
    assert not (tmp_path / "out.mid").exists()


def test_the_input_is_never_overwritten(tmp_path, capsys):
    src = build(tmp_path / "in.mid", NOTES)
    rc, _, err = run(capsys, "transform", src, "-o", src, "--op", "add:velocity=1")
    assert rc == 1 and "would overwrite the input" in err


def mid(tmp_path, *notes, name="in.mid"):
    """A file written from Notes the test names, so a length of 0 survives to the command."""
    path = tmp_path / name
    path.write_bytes(write(Song(480, 0, (Part(480, notes),))))
    return path


def test_notes_that_now_nest_inside_one_of_their_pitch_are_reported(tmp_path, capsys):
    src = mid(tmp_path, Note(0, 960, 1, 36, 100), Note(240, 120, 1, 38, 80))
    out = tmp_path / "out.mid"
    rc, text, _ = run(capsys, "transform", src, "-o", out, "--op", "set:pitch=36")
    assert rc == 0, text
    assert "1 same-pitch note pair(s) start inside a longer one and end before it" in text


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


HOSTILE = {"none": "5", "int": "9" * 310, "int?": "9" * 310, "float": "-1", "ticks": "9" * 310,
           "lo..hi": "-5..500", "percent": "9" * 310, "swing": "9" * 310, "humanize": "pos=" + "9" * 310}


def test_no_preset_value_reaches_the_user_as_a_traceback(tmp_path, capsys, monkeypatch):
    """Every preset over one file with a value it cannot use: a `groovebin:` line or a clean run,
    never a traceback. A value a field simply holds to its range is not an error."""
    monkeypatch.chdir(tmp_path)
    build(tmp_path / "in.mid", NOTES)
    for preset in PRESETS:
        rc, _, err = run(capsys, "transform", "in.mid", "-o", "out.mid", "--force",
                         "--preset", f"{preset.name}={HOSTILE[preset.takes]}")
        assert rc in (0, 1), (preset.name, err)
        assert err == "" or (err.startswith("groovebin: ") and len(err.strip().splitlines()) == 1), (preset.name, err)
        assert "Traceback" not in err, (preset.name, err)


def test_listing_the_presets_refuses_a_transform_in_the_same_breath(tmp_path, capsys):
    src = build(tmp_path / "in.mid", NOTES)
    rc, _, err = run(capsys, "transform", src, "-o", tmp_path / "out.mid", "--op", "add:velocity=1", "--presets")
    assert rc == 1 and "--presets lists the presets" in err
    assert not (tmp_path / "out.mid").exists()


def test_note_offs_with_no_note_before_them_are_reported(tmp_path, capsys):
    """A note-off with nothing open is dropped on read; the run says so, as `remap` does."""
    body = b"".join([b"\x00\x90\x24\x64", b"\x78\x80\x24\x40", b"\x78\x80\x24\x40", b"\x00\xff\x2f\x00"])
    src = tmp_path / "in.mid"
    src.write_bytes(b"MThd" + struct.pack(">IHHH", 6, 0, 1, 480) + b"MTrk" + struct.pack(">I", len(body)) + body)
    rc, text, _ = run(capsys, "transform", src, "-o", tmp_path / "out.mid", "--op", "add:velocity=1")
    assert rc == 0 and "1 note-off(s) with no note before them were dropped" in text


def test_the_nested_warning_covers_a_track_the_transform_did_not_touch(tmp_path, capsys):
    """Every track is written back, so the input's ambiguous pairing is reported whether or not
    --track selected it — as the orphan warning already is."""
    ambiguous = Part(480, (Note(0, 20, 1, 38, 100), Note(10, 20, 1, 38, 100)))
    path = tmp_path / "in.mid"
    path.write_bytes(write(Song(480, 1, (Part(480, (Note(0, 120, 1, 36, 100),)), ambiguous))))
    assert read(path.read_bytes()).tracks[1].nested_ons == 1
    rc, text, _ = run(capsys, "transform", path, "--track", "1", "--op", "set:velocity=90",
                      "-o", tmp_path / "out.mid")
    assert rc == 0, text
    assert "1 same-pitch note pair(s)" in text


def test_a_refusal_the_command_line_prints_says_track_where_the_library_says_part(tmp_path, capsys):
    src, out = build(tmp_path / "in.mid", NOTES), tmp_path / "out.mid"
    rc, _text, err = run(capsys, "transform", src, "-o", out, "--select", "position=0-2",
                         "--op", "set:velocity=90")
    assert rc == 1
    assert "where a track starts" in err
    assert "part" not in err


def test_a_skipped_time_signature_is_reported_by_transform(tmp_path, capsys):
    sixty_fourth = Event(0, b"\xff\x58\x04\x01\x06\x18\x08")
    path = tmp_path / "in.mid"
    path.write_bytes(write(Song(120, 1, (Part(120, (Note(0, 12, 1, 36, 100),), (sixty_fourth,)),))))
    rc, text, _ = run(capsys, "transform", path, "--op", "set:velocity=90", "-o", tmp_path / "out.mid")
    assert rc == 0, text
    assert "1 time signature(s) were skipped" in text


def test_only_the_librarys_own_wording_is_rewritten_never_the_users_text(tmp_path, capsys):
    """Only a `PartWording` refusal is rewritten. A message that quotes the user's own --select or
    --op text back at them must come back exactly as they typed it."""
    src, out = build(tmp_path / "in.mid", NOTES), tmp_path / "out.mid"
    rc, _t, err = run(capsys, "transform", src, "-o", out, "--select", "the part's=3", "--op", "set:velocity=90")
    assert rc == 1 and "the part's=3" in err and "the track's" not in err
    rc, _t, err = run(capsys, "transform", src, "-o", out, "--op", "set:a part at=3")
    assert rc == 1 and "a part at" in err and "a track at" not in err


def test_a_path_holding_the_librarys_phrase_is_not_rewritten(tmp_path, capsys):
    """The same rule for a file name: data, not wording."""
    folder = tmp_path / "the part's mix"
    folder.mkdir()
    bad = folder / "a part at rest.mid"
    bad.write_bytes(b"not a Standard MIDI File")
    rc, _text, err = run(capsys, "notes", bad)
    assert rc == 1
    assert "a part at rest.mid" in err
    assert "a track at rest" not in err
