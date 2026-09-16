"""`groovebin remap`: scope, the report, and the file guards, on files the test writes."""

import pytest

from groovebin.cli import main
from groovebin.events import Event, Note
from groovebin.midi import read, write
from groovebin.song import Part, Song


def notes(*pitches, channel=10):
    return tuple(Note(i * 480, 120, channel, p, 100) for i, p in enumerate(pitches))


def mid(tmp_path, *tracks, name="in.mid"):
    path = tmp_path / name
    path.write_bytes(write(Song(480, 1, tracks)))
    return path


def run(capsys, *argv):
    rc = main([str(a) for a in argv])
    out, err = capsys.readouterr()
    return rc, out, err


def test_a_single_channel_file_is_remapped_and_reported(tmp_path, capsys):
    source = mid(tmp_path, Part(480, (), (Event(0, b"\xff\x03\x03Kit"),)), Part(480, notes(42, 60, 60, 36)))
    out = tmp_path / "out.mid"
    rc, text, _ = run(capsys, "remap", source, "--from", "gm", "--to", "addictive-drums-2", "-o", out)
    assert rc == 0
    assert "2 of 4 note(s) remapped gm -> addictive-drums-2; no addictive-drums-2 counterpart, pitch kept: 60 x2" in text
    assert f"out : {out}" in text
    song = read(out.read_bytes())
    assert [n.pitch for n in song.tracks[1].notes] == [49, 60, 60, 36]
    assert song.tracks[0] == read(source.read_bytes()).tracks[0]


def test_unmapped_drop_removes_notes_with_no_counterpart_and_says_so(tmp_path, capsys):
    source = mid(tmp_path, Part(480, notes(42, 60, 60, 36)))
    out = tmp_path / "out.mid"
    rc, text, _ = run(capsys, "remap", source, "--from", "gm", "--to", "addictive-drums-2", "--unmapped", "drop", "-o", out)
    assert rc == 0
    assert "2 of 4 note(s) remapped gm -> addictive-drums-2; no addictive-drums-2 counterpart, dropped: 60 x2" in text
    assert [n.pitch for n in read(out.read_bytes()).tracks[0].notes] == [49, 36]


def test_notes_on_several_channels_need_a_scope_and_nothing_is_written(tmp_path, capsys):
    source = mid(tmp_path, Part(480, notes(42, channel=10)), Part(480, notes(60, channel=1)))
    out = tmp_path / "out.mid"
    rc, _, err = run(capsys, "remap", source, "--from", "gm", "--to", "addictive-drums-2", "-o", out)
    assert rc == 1
    assert "holds notes on channels 1 and 10: say which to remap with --channel or --track" in err
    assert not out.exists()


def test_the_refusal_offers_track_only_when_a_track_holds_one_channel(tmp_path, capsys):
    source = mid(tmp_path, Part(480, notes(42, channel=10) + notes(60, channel=1)))
    _, _, err = run(capsys, "remap", source, "--from", "gm", "--to", "addictive-drums-2", "-o", tmp_path / "out.mid")
    assert err == "groovebin: in.mid holds notes on channels 1 and 10: say which to remap with --channel\n"


def test_the_refusal_names_only_the_named_tracks_that_hold_notes(tmp_path, capsys):
    source = mid(tmp_path, Part(480), Part(480, notes(42, channel=10) + notes(60, channel=1)))
    _, _, err = run(capsys, "remap", source, "--from", "gm", "--to", "addictive-drums-2", "--track", 1, "--track", 2,
                    "-o", tmp_path / "out.mid")
    assert err == "groovebin: track 2 of in.mid holds notes on channels 1 and 10: say which to remap with --channel\n"


def test_aftertouch_on_a_channel_with_no_notes_counts_as_a_channel_the_remap_would_change(tmp_path, capsys):
    source = mid(tmp_path, Part(480, notes(42, channel=10)), Part(480, (), (Event(0, b"\xa0\x2a\x40"),)))
    out = tmp_path / "out.mid"
    rc, _, err = run(capsys, "remap", source, "--from", "gm", "--to", "addictive-drums-2", "-o", out)
    assert (rc, out.exists()) == (1, False)
    assert "holds notes and aftertouch on channels 1 and 10: say which to remap with --channel or --track" in err


def test_channel_keeps_the_remap_to_that_channel(tmp_path, capsys):
    source = mid(tmp_path, Part(480, notes(42, channel=10) + notes(42, channel=1)))
    out = tmp_path / "out.mid"
    assert run(capsys, "remap", source, "--from", "gm", "--to", "addictive-drums-2", "--channel", 10, "-o", out)[0] == 0
    assert sorted((n.channel, n.pitch) for n in read(out.read_bytes()).tracks[0].notes) == [(1, 42), (10, 49)]


def test_track_keeps_the_remap_to_that_track(tmp_path, capsys):
    source = mid(tmp_path, Part(480, notes(42, channel=1)), Part(480, notes(42, channel=10)))
    out = tmp_path / "out.mid"
    assert run(capsys, "remap", source, "--from", "gm", "--to", "addictive-drums-2", "--track", 2, "-o", out)[0] == 0
    song = read(out.read_bytes())
    assert (song.tracks[0].notes[0].pitch, song.tracks[1].notes[0].pitch) == (42, 49)


def test_a_track_the_file_does_not_hold_is_refused(tmp_path, capsys):
    source = mid(tmp_path, Part(480, notes(42)))
    rc, _, err = run(capsys, "remap", source, "--from", "gm", "--to", "addictive-drums-2", "--track", 3,
                     "-o", tmp_path / "out.mid")
    assert rc == 1
    assert "track 3 is not in in.mid, which holds 1 track(s)" in err


def test_an_existing_output_needs_force_and_the_input_is_never_overwritten(tmp_path, capsys):
    source = mid(tmp_path, Part(480, notes(42)))
    out = tmp_path / "out.mid"
    out.write_bytes(b"keep me")
    rc, _, err = run(capsys, "remap", source, "--from", "gm", "--to", "addictive-drums-2", "-o", out)
    assert rc == 1 and "already exists; pass --force to overwrite it" in err and out.read_bytes() == b"keep me"
    assert run(capsys, "remap", source, "--from", "gm", "--to", "addictive-drums-2", "-o", out, "--force")[0] == 0
    rc, _, err = run(capsys, "remap", source, "--from", "gm", "--to", "addictive-drums-2", "-o", source, "--force")
    assert rc == 1 and "would overwrite the input" in err


def test_a_remap_to_the_same_map_is_refused(tmp_path, capsys):
    source = mid(tmp_path, Part(480, notes(42)))
    rc, _, err = run(capsys, "remap", source, "--from", "gm", "--to", "gm", "-o", tmp_path / "out.mid")
    assert rc == 1 and "groovebin: a remap from gm to gm would still move notes" in err


def test_an_unreadable_file_is_one_line_on_stderr(tmp_path, capsys):
    source = tmp_path / "in.mid"
    source.write_bytes(b"RIFF....")
    rc, _, err = run(capsys, "remap", source, "--from", "gm", "--to", "addictive-drums-2", "-o", tmp_path / "o.mid")
    assert (rc, err) == (1, "groovebin: in.mid: no MThd header: not a Standard MIDI File\n")


def test_an_unknown_map_is_an_argument_error(tmp_path, capsys):
    with pytest.raises(SystemExit) as e:
        main(["remap", str(tmp_path / "x.mid"), "--from", "sd3", "--to", "gm", "-o", str(tmp_path / "o.mid")])
    assert e.value.code == 2


def test_nested_overlaps_a_remap_creates_are_reported(tmp_path, capsys):
    source = mid(tmp_path, Part(480, (Note(0, 960, 10, 35, 90), Note(240, 240, 10, 36, 90))))
    rc, text, _ = run(capsys, "remap", source, "--from", "gm", "--to", "addictive-drums-2", "-o", tmp_path / "out.mid")
    assert rc == 0
    assert "1 same-pitch note pair(s) now start inside a longer one and end before it" in text


def test_a_track_with_notes_on_several_channels_still_needs_a_channel(tmp_path, capsys):
    source = tmp_path / "in.mid"
    source.write_bytes(write(Song(480, 0, (Part(480, notes(42, channel=10) + notes(60, channel=1)),))))
    out = tmp_path / "out.mid"
    rc, _, err = run(capsys, "remap", source, "--from", "gm", "--to", "addictive-drums-2", "--track", 1, "-o", out)
    assert rc == 1 and not out.exists()
    assert "track 1 of in.mid holds notes on channels 1 and 10: say which to remap with --channel" in err
    assert run(capsys, "remap", source, "--from", "gm", "--to", "addictive-drums-2", "--track", 1, "--channel", 10,
               "-o", out)[0] == 0
