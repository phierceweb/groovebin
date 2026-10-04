"""`groovebin tempo`: a file's tempo points and ramps, and a copy with tempo written in."""

from groovebin.cli import main
from groovebin.events import Event, Note
from groovebin.midi import read, write
from groovebin.song import Part, Song, tempo_map

METER = Event(0, b"\xff\x58\x04\x04\x02\x18\x08")
TEMPO_120 = Event(0, b"\xff\x51\x03\x07\xa1\x20")


def song_file(path, *events):
    path.write_bytes(write(Song(960, 1, (Part(960, (), (METER, *events)), Part(960, (Note(0, 240, 1, 60, 90),))))))
    return path


def run(capsys, *argv):
    rc = main([str(a) for a in argv])
    out, err = capsys.readouterr()
    return rc, out.splitlines(), err


def test_a_file_with_no_tempo_says_so(tmp_path, capsys):
    rc, out, err = run(capsys, "tempo", song_file(tmp_path / "in.mid"))
    assert (rc, err, out) == (0, "", ["in.mid: no tempo events: 120 bpm throughout"])


def test_set_writes_a_point_on_a_bar_line_and_lists_the_result(tmp_path, capsys):
    src, dst = song_file(tmp_path / "in.mid", TEMPO_120), tmp_path / "out.mid"
    rc, out, err = run(capsys, "tempo", src, "--set", "100@3", "-o", dst)
    assert (rc, err) == (0, "")
    assert out == ["in.mid: PPQ 960, 2 tempo point(s), 0 ramp(s)",
                   "  bar    1.000   0:00.000  120 bpm",
                   "  bar    3.000   0:04.000  100 bpm",
                   f"out : {dst}"]
    written = read(dst.read_bytes())
    assert tempo_map(written).points == ((0, 500_000), (7680, 600_000))
    assert written.tracks[1].notes == read(src.read_bytes()).tracks[1].notes


def test_a_ramp_is_listed_as_one_line(tmp_path, capsys):
    src, dst = song_file(tmp_path / "in.mid", TEMPO_120), tmp_path / "out.mid"
    rc, out, _err = run(capsys, "tempo", src, "--ramp", "2-3:120-140/1/4", "-o", dst)
    assert rc == 0 and out[:3] == ["in.mid: PPQ 960, 6 tempo point(s), 1 ramp(s)",
                                   "  bar    1.000   0:00.000  120 bpm",
                                   "  bar    2.000   0:02.000  ramp 120 bpm -> 140 bpm to bar 3.000, 5 point(s)"]


def test_edits_apply_in_order(tmp_path, capsys):
    src, dst = song_file(tmp_path / "in.mid"), tmp_path / "out.mid"
    rc, _out, _err = run(capsys, "tempo", src, "--ramp", "1-2:100-120", "--set", "90@2", "-o", dst)
    assert rc == 0 and tempo_map(read(dst.read_bytes())).points[-1] == (3840, 666_667)


def test_what_tempo_cannot_do_is_refused(tmp_path, capsys):
    src, dst = song_file(tmp_path / "in.mid"), tmp_path / "out.mid"
    for argv, message in ((["--set", "100@3"], "--set and --ramp write a new file: give -o OUT.mid"),
                          (["-o", dst], "-o writes what --set or --ramp change: give one"),
                          (["--set", "100@0", "-o", dst], "--set 100@0: bar 0 is before bar 1"),
                          (["--set", "100", "-o", dst], "--set 100: BPM@BAR, e.g. 100@9"),
                          (["--ramp", "3-2:100-120", "-o", dst], "the second bar is not after the first"),
                          (["--ramp", "3:100", "-o", dst], "BAR-BAR:BPM-BPM[/STEP]")):
        rc, _out, err = run(capsys, "tempo", src, *argv)
        assert rc == 1 and message in err, (argv, err)


def test_two_ramps_meeting_at_a_bar_list_as_two_ramps(tmp_path, capsys):
    src, dst = song_file(tmp_path / "in.mid"), tmp_path / "out.mid"
    rc, out, _err = run(capsys, "tempo", src, "--ramp", "1-3:100-120", "--ramp", "3-5:120-100", "-o", dst)
    assert rc == 0 and out[1:3] == ["  bar    1.000   0:00.000  ramp 100 bpm -> 120 bpm to bar 3.000, 33 point(s)",
                                    "  bar    3.000   0:04.388  ramp 120 bpm -> 100 bpm to bar 5.000, 33 point(s)"]


def test_a_ramp_step_past_a_quarter_note_is_refused(tmp_path, capsys):
    src, dst = song_file(tmp_path / "in.mid"), tmp_path / "out.mid"
    rc, _out, err = run(capsys, "tempo", src, "--ramp", "1-3:100-120/1/2", "-o", dst)
    assert rc == 1 and "a step longer than a quarter note" in err and not dst.exists()


def test_a_ramp_no_longer_than_its_step_is_refused(tmp_path, capsys):
    src, dst = song_file(tmp_path / "in.mid"), tmp_path / "out.mid"
    src.write_bytes(write(Song(960, 1, (Part(960, (), (Event(0, b"\xff\x58\x04\x01\x02\x18\x08"),)),))))
    rc, _out, err = run(capsys, "tempo", src, "--ramp", "1-2:100-120/1/4", "-o", dst)
    assert rc == 1 and "no point between its ends" in err and not dst.exists()


def test_unreadable_tempo_events_are_counted_and_left_out_of_a_copy(tmp_path, capsys):
    src, dst = song_file(tmp_path / "in.mid", Event(0, b"\xff\x51\x03\x00\x00\x00"), Event(1920, b"\xff\x51\x02\x07\xa1")), \
        tmp_path / "out.mid"
    rc, out, _err = run(capsys, "tempo", src)
    assert rc == 0 and out == ["in.mid: no tempo events: 120 bpm throughout",
                               "2 tempo event(s) were skipped — a tempo of 0, or not three bytes"]
    rc, out, _err = run(capsys, "tempo", src, "--set", "100@2", "-o", dst)
    assert rc == 0 and out[-2] == ("2 tempo event(s) were skipped — a tempo of 0, or not three bytes; "
                                   "they are left out of the written file")
    rc, out, _err = run(capsys, "notes", src)
    assert rc == 0 and out[-1] == "2 tempo event(s) were skipped — a tempo of 0, or not three bytes"
