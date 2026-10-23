"""`groovebin transform` reports what the input or the run did to note pairing, and what the read skipped."""

import struct

from transform_fixture import mid, run

from groovebin.events import Event, Note
from groovebin.midi import read, write
from groovebin.song import Part, Song


def test_notes_that_now_nest_inside_one_of_their_pitch_are_reported(tmp_path, capsys):
    src = mid(tmp_path, Note(0, 960, 1, 36, 100), Note(240, 120, 1, 38, 80))
    out = tmp_path / "out.mid"
    rc, text, _ = run(capsys, "transform", src, "-o", out, "--op", "set:pitch=36")
    assert rc == 0, text
    assert "1 same-pitch note pair(s) now start inside a longer one and end before it" in text


def test_the_inputs_ambiguity_and_the_runs_nesting_are_counted_apart(tmp_path, capsys):
    """One pair the file left ambiguous that the run then nests is one of each, not two of either."""
    src = tmp_path / "in.mid"
    src.write_bytes(write(Song(480, 1, (Part(480, (Note(0, 60, 1, 38, 50), Note(10, 20, 1, 38, 100))),))))
    assert read(src.read_bytes()).tracks[0].nested_ons == 1
    rc, text, _ = run(capsys, "transform", src, "-o", tmp_path / "out.mid", "--select", "velocity>60",
                      "--op", "set:length=10")
    assert rc == 0, text
    assert [line.split(":")[0] for line in text.splitlines() if "same-pitch" in line or "the input" in line] == [
        "1 note-off(s) in the input found more than one note of their pitch open",
        "1 same-pitch note pair(s) now start inside a longer one and end before it"]


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
    assert "1 note-off(s) in the input found more than one note of their pitch open" in text and "same-pitch" not in text


def test_a_skipped_tempo_is_reported_when_the_selection_reads_times(tmp_path, capsys):
    zero_tempo = Event(0, b"\xff\x51\x03\x00\x00\x00")
    path = tmp_path / "in.mid"
    path.write_bytes(write(Song(480, 1, (Part(480, (Note(0, 120, 1, 36, 100),), (zero_tempo,)),))))
    warning = "1 tempo event(s) were skipped — a tempo of 0, or not three bytes"
    rc, text, _ = run(capsys, "transform", path, "--select", "position<0:02", "--op", "set:velocity=90",
                      "-o", tmp_path / "out.mid")
    assert rc == 0 and warning in text, text
    rc, text, _ = run(capsys, "transform", path, "--select", "position=1", "--op", "set:velocity=90",
                      "-o", tmp_path / "out.mid", "--force")
    assert rc == 0 and warning not in text, text


def test_a_skipped_time_signature_is_reported_by_transform(tmp_path, capsys):
    sixty_fourth = Event(0, b"\xff\x58\x04\x01\x06\x18\x08")
    path = tmp_path / "in.mid"
    path.write_bytes(write(Song(120, 1, (Part(120, (Note(0, 12, 1, 36, 100),), (sixty_fourth,)),))))
    rc, text, _ = run(capsys, "transform", path, "--op", "set:velocity=90", "-o", tmp_path / "out.mid")
    assert rc == 0, text
    assert "1 time signature(s) were skipped" in text
