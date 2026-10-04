"""`groovebin key`: a file's key signatures and the scale its notes hold, and a copy with signatures set."""

from groovebin.cli import main
from groovebin.events import Event, Note
from groovebin.midi import read, write
from groovebin.song import Part, Song, key_map

METER = Event(0, b"\xff\x58\x04\x04\x02\x18\x08")
A_MINOR = (57, 59, 60, 62, 64, 65, 67)


def song_file(path, *events, pitches=A_MINOR):
    notes = tuple(Note(k * 480, 480 * (3 if p == 57 else 1), 1, p, 90) for k, p in enumerate(pitches))
    path.write_bytes(write(Song(960, 1, (Part(960, (), (METER, *events)), Part(960, notes)))))
    return path


def run(capsys, *argv):
    rc = main([str(a) for a in argv])
    out, err = capsys.readouterr()
    return rc, out.splitlines(), err


def test_a_file_lists_its_signatures_and_the_scale_its_notes_hold(tmp_path, capsys):
    f = song_file(tmp_path / "in.mid", Event(0, bytes([0xFF, 0x59, 2, 0, 1])))
    rc, out, err = run(capsys, "key", f)
    assert (rc, err) == (0, "")
    assert out == ["in.mid: 1 key signature(s)", "  bar    1.000  A minor", "scale  C major / A minor"]


def test_set_writes_signatures_and_moves_no_note(tmp_path, capsys):
    src, dst = song_file(tmp_path / "in.mid"), tmp_path / "out.mid"
    rc, out, _err = run(capsys, "key", src, "--set", "A minor@1", "--set", "Gb@2", "-o", dst)
    assert rc == 0 and out[:3] == ["in.mid: 2 key signature(s)", "  bar    1.000  A minor", "  bar    2.000  Gb major"]
    written = read(dst.read_bytes())
    assert key_map(written).points == ((0, 0, True), (3840, -6, False))
    assert written.tracks[1].notes == read(src.read_bytes()).tracks[1].notes


def test_no_signature_and_too_few_pitch_classes_say_so(tmp_path, capsys):
    rc, out, _err = run(capsys, "key", song_file(tmp_path / "in.mid", pitches=(60, 72)))
    assert rc == 0 and out == ["in.mid: no key signatures", "scale  - (too few pitch classes to estimate one)"]


def test_what_key_cannot_write_is_refused(tmp_path, capsys):
    src, dst = song_file(tmp_path / "in.mid"), tmp_path / "out.mid"
    for argv, message in ((["--set", "A minor@1"], "--set writes a new file: give -o OUT.mid"),
                          (["-o", dst], "-o writes what --set changes: give one"),
                          (["--set", "D dorian@1", "-o", dst], "D dorian has no key signature"),
                          (["--set", "A minor", "-o", dst], 'KEY@BAR, e.g. "A minor@1"'),
                          (["--map", "gm"], "gm is a drum map")):
        rc, _out, err = run(capsys, "key", src, *argv)
        assert rc == 1 and message in err, (argv, err)


def test_set_still_counts_an_unreadable_signature_and_says_the_copy_leaves_it_out(tmp_path, capsys):
    src, dst = song_file(tmp_path / "in.mid", Event(0, b"\xff\x59\x02\x00\x02")), tmp_path / "out.mid"
    rc, out, _err = run(capsys, "key", src, "--set", "G@3", "-o", dst)
    assert rc == 0 and "1 key signature(s) were skipped" in out[-2] and "left out of the written file" in out[-2]
    assert key_map(read(dst.read_bytes())).points == ((7680, 1, False),)


def test_a_track_the_file_lacks_is_refused_before_anything_is_written(tmp_path, capsys):
    src, dst = song_file(tmp_path / "in.mid"), tmp_path / "out.mid"
    rc, _out, err = run(capsys, "key", src, "--set", "G@1", "--track", "3", "-o", dst)
    assert rc == 1 and "track 3 is not in in.mid" in err and not dst.exists()


def test_a_skipped_time_signature_is_said_since_the_bars_are_counted_without_it(tmp_path, capsys):
    src = song_file(tmp_path / "in.mid", Event(1920, b"\xff\x58\x04\x00\x02\x18\x08"))
    rc, out, _err = run(capsys, "key", src)
    assert rc == 0 and "1 time signature(s) were skipped" in out[-1]
    rc, out, _err = run(capsys, "key", src, "--set", "G@2", "-o", tmp_path / "out.mid")
    assert rc == 0 and "1 time signature(s) were skipped" in out[-2]
