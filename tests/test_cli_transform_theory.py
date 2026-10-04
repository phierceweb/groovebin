"""`groovebin transform` with the theory presets: which key, keyswitches, key signatures."""

from groovebin.cli import main
from groovebin.events import Event, Note
from groovebin.midi import read, write
from groovebin.song import Part, Song, key_map

METER = Event(0, b"\xff\x58\x04\x04\x02\x18\x08")


def signature(sharps, minor):
    return Event(0, bytes([0xFF, 0x59, 2, sharps & 0xFF, minor]))


def song_file(path, pitches, *conductor):
    notes = tuple(Note(k * 480, 240, 1, p, 90) for k, p in enumerate(pitches))
    path.write_bytes(write(Song(960, 1, (Part(960, (), (METER, *conductor)), Part(960, notes)))))
    return path


def run(capsys, *argv):
    rc = main([str(a) for a in argv])
    out, err = capsys.readouterr()
    return rc, out.splitlines(), err


def pitches(path):
    return [n.pitch for n in read(path.read_bytes()).tracks[1].notes]


def test_scale_quantize_takes_the_key_given(tmp_path, capsys):
    src, dst = song_file(tmp_path / "in.mid", (61, 63, 64)), tmp_path / "out.mid"
    rc, out, err = run(capsys, "transform", src, "-o", dst, "--preset", "scale-quantize", "--key", "C minor")
    assert (rc, err) == (0, "") and out[0] == "key  C minor (given)"
    assert pitches(dst) == [60, 63, 63]


def test_the_files_key_signature_is_the_key_when_none_is_given(tmp_path, capsys):
    src, dst = song_file(tmp_path / "in.mid", (61, 66), signature(1, 0)), tmp_path / "out.mid"
    rc, out, _err = run(capsys, "transform", src, "-o", dst, "--preset", "diatonic=1")
    assert rc == 0 and out[0] == "key  G major from bar 1 (the file's key signatures)"
    assert pitches(dst) == [63, 67]


def test_an_estimated_key_is_said_and_too_few_pitch_classes_ask_for_one(tmp_path, capsys):
    src, dst = song_file(tmp_path / "in.mid", (60, 62, 64, 65, 67, 69, 71, 61)), tmp_path / "out.mid"
    rc, out, _err = run(capsys, "transform", src, "-o", dst, "--preset", "scale-quantize")
    assert rc == 0 and out[0] == "key  C major / A minor (estimated)" and pitches(dst)[-1] == 60
    lone = song_file(tmp_path / "lone.mid", (60, 72))
    rc, _out, err = run(capsys, "transform", lone, "-o", tmp_path / "x.mid", "--preset", "diatonic=1")
    assert rc == 1 and "give --key" in err


def test_a_bass_maps_keyswitches_keep_their_pitch_and_without_it_they_move(tmp_path, capsys):
    src, kept, moved = song_file(tmp_path / "in.mid", (15, 61)), tmp_path / "kept.mid", tmp_path / "moved.mid"
    assert run(capsys, "transform", src, "-o", kept, "--preset", "scale-quantize", "--key", "C", "--map", "ezbass")[0] == 0
    assert pitches(kept) == [15, 60]
    assert run(capsys, "transform", src, "-o", moved, "--preset", "scale-quantize", "--key", "C")[0] == 0
    assert pitches(moved) == [14, 60]


def test_a_bass_map_keeps_keyswitches_out_of_a_pitch_operation_too(tmp_path, capsys):
    src, dst = song_file(tmp_path / "in.mid", (16, 40)), tmp_path / "out.mid"
    assert run(capsys, "transform", src, "-o", dst, "--op", "add:pitch=12", "--map", "ezbass")[0] == 0
    assert pitches(dst) == [16, 52]


def test_a_drum_map_refuses_the_theory_presets_and_key_needs_one(tmp_path, capsys):
    src, dst = song_file(tmp_path / "in.mid", (60,)), tmp_path / "out.mid"
    rc, _out, err = run(capsys, "transform", src, "-o", dst, "--preset", "diatonic=1", "--key", "C", "--map", "gm")
    assert rc == 1 and "gm is a drum map" in err
    rc, _out, err = run(capsys, "transform", src, "-o", dst, "--op", "add:pitch=1", "--key", "C")
    assert rc == 1 and "--key is the key scale-quantize, diatonic and change-key read" in err
    rc, _out, err = run(capsys, "transform", "--presets", "--key", "C")
    assert rc == 1 and "takes nothing else" in err


def test_change_key_moves_the_notes_and_the_signatures_on_the_tracks_it_changes(tmp_path, capsys):
    src, dst = song_file(tmp_path / "in.mid", (60, 64), signature(0, 0)), tmp_path / "out.mid"
    rc, _out, _err = run(capsys, "transform", src, "-o", dst, "--preset", "change-key=D")
    assert rc == 0 and pitches(dst) == [62, 66] and key_map(read(dst.read_bytes())).points == ((0, 2, False),)
    only = tmp_path / "only.mid"
    rc, out, _err = run(capsys, "transform", src, "-o", only, "--track", "2", "--preset", "change-key=D")
    assert rc == 0 and "key signatures on track(s) 1 were not changed" in out[-2]


def test_change_key_to_a_mode_and_from_an_estimate(tmp_path, capsys):
    src, dst = song_file(tmp_path / "in.mid", (60, 64), signature(0, 0)), tmp_path / "out.mid"
    rc, out, _err = run(capsys, "transform", src, "-o", dst, "--preset", "change-key=D dorian")
    assert rc == 0 and pitches(dst) == [62, 65]
    assert "key signatures left as they were: a file's key signature cannot say dorian" in out
    plain, minor = song_file(tmp_path / "plain.mid", (60, 62, 64, 65, 67)), tmp_path / "minor.mid"
    assert run(capsys, "transform", plain, "-o", minor, "--preset", "change-key=E minor")[0] == 0
    assert pitches(minor)[0] == 55
    rc, _out, err = run(capsys, "transform", plain, "-o", tmp_path / "x.mid", "--preset", "change-key=A harmonic-minor")
    assert rc == 1 and "give --key" in err


def test_one_run_moves_every_track_by_the_same_interval(tmp_path, capsys):
    conductor = Part(960, (), (METER, signature(0, 0), Event(4 * 3840, bytes([0xFF, 0x59, 2, 1, 0]))))
    piano = Part(960, (Note(0, 240, 1, 60, 90), Note(4 * 3840, 240, 1, 67, 90)))
    bass = Part(960, (Note(5 * 3840, 240, 2, 43, 90),))
    src, dst = tmp_path / "in.mid", tmp_path / "out.mid"
    src.write_bytes(write(Song(960, 1, (conductor, piano, bass))))
    assert run(capsys, "transform", src, "-o", dst, "--preset", "change-key=D")[0] == 0
    out = read(dst.read_bytes())
    assert [n.pitch for n in out.tracks[2].notes] == [45]
    assert key_map(out).points == ((0, 2, False), (4 * 3840, 3, False))


def test_scale_quantize_with_its_own_key_needs_no_other(tmp_path, capsys):
    src, dst = song_file(tmp_path / "in.mid", (61, 73)), tmp_path / "out.mid"
    rc, out, err = run(capsys, "transform", src, "-o", dst, "--preset", "scale-quantize=C")
    assert (rc, err) == (0, "") and not out[0].startswith("key ") and pitches(dst) == [60, 72]


def test_a_bass_map_refuses_a_step_that_lands_a_note_on_a_keyswitch(tmp_path, capsys):
    src = song_file(tmp_path / "in.mid", (21, 40))
    rc, _out, err = run(capsys, "transform", src, "-o", tmp_path / "a.mid", "--preset", "diatonic=-2", "--key", "C",
                        "--map", "ezbass")
    assert rc == 1 and "note 21 would move to 17, an ezbass keyswitch" in err
    rc, _out, err = run(capsys, "transform", src, "-o", tmp_path / "b.mid", "--op", "add:pitch=-3", "--map", "ezbass")
    assert rc == 1 and "note 21 would move to 18, an ezbass keyswitch" in err


def test_a_keyswitch_keeps_its_pitch_but_moves_in_time_with_its_pass(tmp_path, capsys):
    src, dst = song_file(tmp_path / "in.mid", (15, 40)), tmp_path / "out.mid"
    assert run(capsys, "transform", src, "-o", dst, "--op", "add:pitch=12", "--op", "add:position=240",
               "--map", "ezbass")[0] == 0
    assert [(n.tick, n.pitch) for n in read(dst.read_bytes()).tracks[1].notes] == [(240, 15), (720, 52)]


def test_a_change_of_mode_says_which_signatures_it_left(tmp_path, capsys):
    src = song_file(tmp_path / "in.mid", (57, 60, 64), signature(0, 1), Event(2 * 3840, bytes([0xFF, 0x59, 2, 0, 0])))
    rc, out, _err = run(capsys, "transform", src, "-o", tmp_path / "out.mid", "--preset", "change-key=A major")
    assert rc == 0 and "1 key signature(s) in other keys were left as they were" in "\n".join(out)


def test_a_change_to_the_same_key_reports_no_signature_left(tmp_path, capsys):
    src = song_file(tmp_path / "in.mid", (60, 64), signature(0, 0), Event(2 * 3840, bytes([0xFF, 0x59, 2, 1, 0])))
    rc, out, _err = run(capsys, "transform", src, "-o", tmp_path / "out.mid", "--preset", "change-key=C")
    assert rc == 0 and not any("left as they were" in line for line in out)


def test_a_change_of_mode_counts_what_it_left_when_the_first_signature_comes_after_the_first_note(tmp_path, capsys):
    src = song_file(tmp_path / "in.mid", (60, 64, 67), Event(960, bytes([0xFF, 0x59, 2, 0, 0])),
                    Event(1920, bytes([0xFF, 0x59, 2, 3, 1])))
    rc, out, _err = run(capsys, "transform", src, "-o", tmp_path / "out.mid", "--preset", "change-key=A minor")
    assert rc == 0 and "1 key signature(s) in other keys were left as they were" in "\n".join(out)


def test_a_theory_preset_after_a_speed_change_is_refused_when_the_files_keys_change(tmp_path, capsys):
    src = song_file(tmp_path / "in.mid", (65,), signature(0, 0), Event(3840, bytes([0xFF, 0x59, 2, 1, 0])))
    rc, _out, err = run(capsys, "transform", src, "-o", tmp_path / "a.mid", "--preset", "half-speed",
                        "--preset", "scale-quantize")
    assert rc == 1 and "half-speed has moved the notes" in err and "put scale-quantize first" in err
    assert run(capsys, "transform", src, "-o", tmp_path / "b.mid", "--preset", "scale-quantize",
               "--preset", "half-speed")[0] == 0
    one_key = song_file(tmp_path / "one.mid", (65,), signature(0, 0))
    assert run(capsys, "transform", one_key, "-o", tmp_path / "c.mid", "--preset", "double-speed",
               "--preset", "diatonic=1")[0] == 0
    assert run(capsys, "transform", src, "-o", tmp_path / "d.mid", "--preset", "change-key=D",
               "--preset", "half-speed", "--preset", "diatonic=1")[0] == 0


def test_key_is_refused_when_scale_quantize_names_its_own(tmp_path, capsys):
    src = song_file(tmp_path / "in.mid", (61,))
    rc, _out, err = run(capsys, "transform", src, "-o", tmp_path / "out.mid", "--key", "D",
                        "--preset", "scale-quantize=C")
    assert rc == 1 and "--key goes unread" in err


def test_an_unreadable_key_signature_is_said_when_the_run_reads_the_files_keys(tmp_path, capsys):
    src = song_file(tmp_path / "in.mid", (60, 62, 64, 65, 67), Event(0, b"\xff\x59\x02\x00\x02"))
    rc, out, _err = run(capsys, "transform", src, "-o", tmp_path / "out.mid", "--preset", "diatonic=1")
    assert rc == 0 and any(line.startswith("1 key signature(s) were skipped") for line in out)
    rc, out, _err = run(capsys, "transform", src, "-o", tmp_path / "given.mid", "--preset", "diatonic=1", "--key", "C")
    assert rc == 0 and not any("key signature(s) were skipped" in line for line in out)


def test_one_signature_on_several_tracks_is_named_once(tmp_path, capsys):
    src, dst = tmp_path / "in.mid", tmp_path / "out.mid"
    src.write_bytes(write(Song(960, 1, (Part(960, (), (METER, signature(0, 0))),
                                        Part(960, (Note(0, 240, 1, 60, 90),), (signature(0, 0),))))))
    rc, out, _err = run(capsys, "transform", src, "-o", dst, "--preset", "diatonic=1")
    assert rc == 0 and out[0] == "key  C major from bar 1 (the file's key signatures)"


def test_the_estimated_keys_relative_minor_is_spelled_as_its_signature(tmp_path, capsys):
    src = song_file(tmp_path / "in.mid", (64, 66, 68, 69, 71, 73, 75))
    rc, out, _err = run(capsys, "transform", src, "-o", tmp_path / "out.mid", "--preset", "scale-quantize")
    assert rc == 0 and out[0] == "key  E major / C# minor (estimated)"
