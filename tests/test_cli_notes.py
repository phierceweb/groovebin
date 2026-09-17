"""`groovebin notes`: the listing, on files the test writes."""

from groovebin.cli import main
from groovebin.events import Event, Note
from groovebin.midi import write
from groovebin.song import Part, Song


def test_notes_lists_each_track_with_bars_and_strokes(tmp_path, capsys):
    conductor = Part(480, (), (Event(0, b"\xff\x51\x03\x07\xa1\x20"), Event(0, b"\xff\x58\x04\x03\x02\x18\x08")))
    drums = Part(480, (Note(0, 120, 10, 36, 100), Note(1800, 60, 10, 42, 79)), (Event(0, b"\xff\x03\x03Kit"),))
    path = tmp_path / "in.mid"
    path.write_bytes(write(Song(480, 1, (conductor, drums))))
    assert main(["notes", str(path), "--map", "gm"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "in.mid: format 1, PPQ 480, 2 track(s), 120 bpm, 3/4"
    assert lines[1] == "track 1: 0 note(s), 2 other event(s)"
    assert lines[2] == "track 2 'Kit': 2 note(s), 1 other event(s)"
    assert lines[3] == "  bar    1.000  ch 10  note  36  vel 100  len    120  Bass Drum 1"
    assert lines[4] == "  bar    2.250  ch 10  note  42  vel  79  len     60  Closed Hi Hat"


def test_notes_without_a_map_lists_no_strokes_and_track_picks_one(tmp_path, capsys):
    path = tmp_path / "in.mid"
    path.write_bytes(write(Song(96, 1, (Part(96, (Note(0, 10, 1, 60, 50),)), Part(96, (Note(0, 10, 1, 127, 50),))))))
    assert main(["notes", str(path), "--track", "2"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[1:] == ["track 2: 1 note(s), 0 other event(s)", "  bar    1.000  ch  1  note 127  vel  50  len     10"]


def test_a_meter_the_file_cannot_hold_is_skipped_and_the_notes_still_list(tmp_path, capsys):
    path = tmp_path / "odd.mid"
    path.write_bytes(write(Song(1, 0, (Part(1, (Note(0, 1, 1, 60, 50),), (Event(0, b"\xff\x58\x04\x03\x03\x18\x08"),)),))))
    assert main(["notes", str(path)]) == 0
    out, err = capsys.readouterr()
    assert err == "" and "60" in out


def test_notes_says_when_a_time_signature_was_skipped(tmp_path, capsys):
    """The header prints a meter either way, so a file whose signature the PPQ cannot hold in whole
    ticks must not read as a plain 4/4 file."""
    sixty_fourth = Event(0, b"\xff\x58\x04\x01\x06\x18\x08")
    path = tmp_path / "in.mid"
    path.write_bytes(write(Song(120, 1, (Part(120, (Note(0, 12, 10, 36, 100),), (sixty_fourth,)),))))
    assert main(["notes", str(path)]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].endswith("4/4")
    assert "1 time signature(s) were skipped" in lines[-1]


def test_notes_says_nothing_when_every_time_signature_is_usable(tmp_path, capsys):
    path = tmp_path / "in.mid"
    path.write_bytes(write(Song(960, 1, (Part(960, (Note(0, 12, 10, 36, 100),),
                                              (Event(0, b"\xff\x58\x04\x01\x06\x18\x08"),)),))))
    assert main(["notes", str(path)]) == 0
    assert "skipped" not in capsys.readouterr().out


def test_notes_says_when_the_lengths_it_lists_are_one_reading_of_an_ambiguous_file(tmp_path, capsys):
    """`notes` prints the lengths FIFO pairing chose; where the file left the pairing open, and where
    it dropped a note-off, the listing says so — as `remap` and `transform` do."""
    ambiguous = Part(480, (Note(0, 20, 10, 38, 100), Note(10, 20, 10, 38, 100)))
    path = tmp_path / "in.mid"
    path.write_bytes(write(Song(480, 1, (ambiguous,))))
    assert main(["notes", str(path)]) == 0
    out = capsys.readouterr().out
    assert "1 same-pitch note pair(s)" in out


def test_notes_says_nothing_extra_about_an_unambiguous_file(tmp_path, capsys):
    path = tmp_path / "in.mid"
    path.write_bytes(write(Song(480, 1, (Part(480, (Note(0, 20, 10, 38, 100),)),))))
    assert main(["notes", str(path)]) == 0
    out = capsys.readouterr().out
    assert "same-pitch" not in out and "note-off(s)" not in out and "skipped" not in out
