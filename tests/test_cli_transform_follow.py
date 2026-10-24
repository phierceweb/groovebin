"""`groovebin transform --preset follow=CHART`: a part moved from the chords it was played over onto a chart's."""

import pytest
from transform_fixture import run

from groovebin.events import Event, Note
from groovebin.midi import read, write
from groovebin.song import Part, Song

BAR = 1920
CONTROL = Event(10, b"\xb0\x07\x64")


def n(at, pitch, length=240, channel=1):
    return Note(at, length, channel, pitch, 90)


def song_file(tmp_path, *notes, name="in.mid"):
    path = tmp_path / name
    path.write_bytes(write(Song(480, 0, (Part(480, notes, (CONTROL,)),))))
    return path


def pitches(path):
    return [x.pitch for x in read(path.read_bytes()).tracks[0].notes]


def test_follow_moves_the_notes_from_the_given_chords_onto_the_new_ones(tmp_path, capsys):
    src, out = song_file(tmp_path, n(0, 60), n(480, 64), n(BAR, 55), n(BAR + 480, 59)), tmp_path / "out.mid"
    rc, text, err = run(capsys, "transform", src, "-o", out, "--chords", "| C | G |", "--preset", "follow=| Am | Em |")
    assert (rc, err) == (0, ""), err
    assert text.splitlines()[0] == "chords  | C | G | (given)"
    assert pitches(out) == [57, 60, 52, 55]
    assert read(out.read_bytes()).tracks[0].events == read(src.read_bytes()).tracks[0].events


def test_without_chords_it_reads_them_from_the_notes_and_says_so(tmp_path, capsys):
    src, out = song_file(tmp_path, n(0, 36, BAR), n(BAR, 43, BAR)), tmp_path / "out.mid"
    rc, text, err = run(capsys, "transform", src, "-o", out, "--preset", "follow=| Am | Em |")
    assert (rc, err) == (0, ""), err
    assert text.splitlines()[0] == "chords  | C5 | G5 | (read from the notes)"
    assert pitches(out) == [33, 40]


def test_the_notes_it_could_not_keep_are_counted(tmp_path, capsys):
    src = song_file(tmp_path, n(0, 63, channel=3), n(0, 64, channel=3), n(BAR - 480, 64, 960, channel=2),
                    n(BAR - 30, 60, 20))
    rc, text, _ = run(capsys, "transform", src, "-o", tmp_path / "out.mid", "--chords", "| C | C |",
                      "--preset", "follow=| Cm | F |")
    assert rc == 0, text
    assert {"1 note(s) just before a chord change took the chord they lead into",
            "1 note(s) ring into a chord they are not in",
            "1 note(s) landed on a pitch another note of their start and channel already had"} <= set(text.splitlines())


def test_a_second_follow_reads_the_first_ones_chords(tmp_path, capsys):
    src, out = song_file(tmp_path, n(0, 60), n(480, 64), n(960, 67)), tmp_path / "out.mid"
    rc, text, _ = run(capsys, "transform", src, "-o", out, "--chords", "C", "--preset", "follow=Am", "--preset", "follow=C")
    assert rc == 0, text
    assert pitches(out) == [60, 64, 67]


def test_follow_moves_only_the_selection_and_never_a_keyswitch(tmp_path, capsys):
    src, out = song_file(tmp_path, n(0, 16), n(0, 40), n(480, 43)), tmp_path / "out.mid"
    rc, text, _ = run(capsys, "transform", src, "-o", out, "--map", "ezbass", "--select", "pitch<43",
                      "--chords", "C", "--preset", "follow=Am")
    assert rc == 0, text
    assert pitches(out) == [16, 36, 43]


def test_with_a_bass_map_a_note_pushed_below_its_range_folds_back_up(tmp_path, capsys):
    src, out = song_file(tmp_path, n(0, 23)), tmp_path / "out.mid"
    rc, text, err = run(capsys, "transform", src, "-o", out, "--map", "ezbass", "--chords", "Bb", "--preset", "follow=Gm")
    assert (rc, err) == (0, ""), err
    assert pitches(out) == [32] and "1 note(s) moved an octave to stay inside ezbass's range" in text


@pytest.mark.parametrize(("argv", "message"), [
    (["--chords", "| C |", "--op", "add:velocity=1"], "--chords is the chart follow reads: give --preset follow=CHART"),
    (["--map", "gm", "--chords", "C", "--preset", "follow=Am"], "follow moves notes onto chords, and gm is a drum map"),
    (["--chords", "C", "--preset", "half-speed", "--preset", "follow=Am"], "half-speed has moved them"),
    (["--chords", "C", "--preset", "double-speed", "--preset", "follow=Am"], "double-speed has moved them"),
    (["--chords", "C", "--op", "add:pitch=2", "--preset", "follow=Am"], "add:pitch has moved them"),
    (["--chords", "C", "--op", "quantize:position=1/8", "--preset", "follow=Am"], "quantize:position has moved them"),
    (["--key", "C", "--chords", "C", "--preset", "change-key=D", "--preset", "follow=Am"],
     "change-key has moved them"),
    (["--chords", "C", "--preset", "follow=| H |"], "is not a chord symbol"),
    (["--chords", "| X |", "--preset", "follow=Am"], "is not a chord symbol"),
    (["--preset", "follow"], "groovebin: follow needs a value: follow=VALUE"),
])
def test_what_follow_cannot_do_is_refused_and_nothing_is_written(tmp_path, capsys, argv, message):
    src = song_file(tmp_path, n(0, 60))
    rc, _text, err = run(capsys, "transform", src, "-o", tmp_path / "out.mid", *argv)
    assert rc == 1 and message in err, err
    assert not (tmp_path / "out.mid").exists()


def test_a_file_with_no_notes_has_no_chords_to_read(tmp_path, capsys):
    rc, _text, err = run(capsys, "transform", song_file(tmp_path), "-o", tmp_path / "out.mid", "--preset", "follow=Am")
    assert rc == 1 and "no chords to read from the notes: give --chords" in err


def test_a_step_after_follow_is_free_to_move_the_notes(tmp_path, capsys):
    src, out = song_file(tmp_path, n(0, 60)), tmp_path / "out.mid"
    rc, text, _ = run(capsys, "transform", src, "-o", out, "--chords", "C", "--preset", "follow=Am", "--op", "add:pitch=2")
    assert rc == 0 and pitches(out) == [59], text


def two_tracks(tmp_path, first, second):
    path = tmp_path / "two.mid"
    path.write_bytes(write(Song(480, 1, (Part(480, first), Part(480, second)))))
    return path


def test_the_chords_are_read_from_the_transformed_tracks_only_and_never_from_a_keyswitch(tmp_path, capsys):
    src = two_tracks(tmp_path, (n(0, 36, BAR),), (n(0, 16, BAR), n(0, 43, 480), n(960, 43, 480)))
    rc, text, _ = run(capsys, "transform", src, "-o", tmp_path / "out.mid", "--track", "2", "--map", "ezbass",
                      "--preset", "follow=Am")
    assert rc == 0 and text.splitlines()[0] == "chords  | G5 | (read from the notes)", text


def test_the_counts_add_up_over_every_track(tmp_path, capsys):
    src = two_tracks(tmp_path, (n(BAR - 20, 60, 10), n(BAR + 480, 60)), (n(BAR - 20, 64, 10), n(BAR + 480, 64)))
    rc, text, _ = run(capsys, "transform", src, "-o", tmp_path / "out.mid", "--chords", "| C | G |",
                      "--preset", "follow=| Am | Em |")
    assert rc == 0 and "2 note(s) just before a chord change took the chord they lead into" in text, text


def test_an_upper_part_reads_slash_chords_as_their_chords(tmp_path, capsys):
    src = song_file(tmp_path, n(0, 60), n(0, 64), n(0, 67))
    for argv, wanted in (([], [59, 59, 62]), (["--upper"], [55, 59, 62])):
        rc, text, _ = run(capsys, "transform", src, "-o", tmp_path / "out.mid", "--force", "--chords", "C",
                          "--preset", "follow=G/B", *argv)
        assert rc == 0 and pitches(tmp_path / "out.mid") == wanted, text


@pytest.mark.parametrize("step", [["--preset", "humanize"], ["--preset", "reverse-position"], ["--preset", "reverse-pitch"],
                                  ["--preset", "swing=60%"], ["--key", "C", "--preset", "scale-quantize"],
                                  ["--key", "C", "--preset", "diatonic=1"]])
def test_every_step_that_moves_the_notes_is_refused_before_follow(tmp_path, capsys, step):
    rc, _text, err = run(capsys, "transform", song_file(tmp_path, n(0, 60)), "-o", tmp_path / "out.mid",
                         "--chords", "C", *step, "--preset", "follow=Am")
    assert rc == 1 and "has moved them" in err, err


def test_a_humanize_that_moves_no_position_is_no_reason_to_refuse(tmp_path, capsys):
    rc, text, err = run(capsys, "transform", song_file(tmp_path, n(0, 60)), "-o", tmp_path / "out.mid",
                        "--chords", "C", "--preset", "humanize=pos=0", "--preset", "follow=Am")
    assert (rc, err) == (0, ""), err


def test_a_key_preset_after_follow_needs_the_key_named(tmp_path, capsys):
    src = song_file(tmp_path, n(0, 60))
    rc, _text, err = run(capsys, "transform", src, "-o", tmp_path / "out.mid", "--chords", "C", "--preset", "follow=Eb",
                         "--preset", "scale-quantize")
    assert rc == 1 and "scale-quantize reads the key the notes were in before follow moved them" in err, err
    for given in (["--key", "Eb", "--preset", "scale-quantize"], ["--preset", "scale-quantize=Eb"]):
        rc, text, err = run(capsys, "transform", src, "-o", tmp_path / "out.mid", "--force", "--chords", "C",
                            "--preset", "follow=Eb", *given)
        assert (rc, err) == (0, ""), err


@pytest.mark.parametrize(("argv", "message"), [
    (["--chords", "| C | |", "--preset", "follow=C"], "--chords: bar 2 of the chart is an empty bar"),
    (["--chords", "C", "--preset", "follow=| C | |"], "follow: bar 2 of the chart is an empty bar"),
    (["--upper", "--op", "add:velocity=1"], "--upper is for follow"),
    (["--upper", "--preset", "follow=Am"], "--upper needs --chords: the chords cannot be read from notes above the bass"),
    (["--upper", "--map", "ezbass", "--chords", "C", "--preset", "follow=Am"], "--upper says the notes are not the bass"),
])
def test_a_refusal_names_the_chart_or_flag_it_is_about(tmp_path, capsys, argv, message):
    rc, _text, err = run(capsys, "transform", song_file(tmp_path, n(0, 60)), "-o", tmp_path / "out.mid", *argv)
    assert rc == 1 and message in err, err


def test_aftertouch_moves_with_its_note_through_the_command(tmp_path, capsys):
    path, out = tmp_path / "in.mid", tmp_path / "out.mid"
    path.write_bytes(write(Song(480, 0, (Part(480, (n(0, 64, 480),), (Event(100, bytes([0xA0, 64, 40])),)),))))
    rc, text, _ = run(capsys, "transform", path, "-o", out, "--chords", "C", "--preset", "follow=Am")
    assert rc == 0 and [e.pitch for e in read(out.read_bytes()).tracks[0].events] == [60], text


@pytest.mark.parametrize("preset", ["change-key=D", "diatonic=1"])
def test_every_key_reading_preset_after_follow_needs_the_key(tmp_path, capsys, preset):
    rc, _text, err = run(capsys, "transform", song_file(tmp_path, n(0, 60)), "-o", tmp_path / "out.mid",
                         "--chords", "C", "--preset", "follow=Eb", "--preset", preset)
    assert rc == 1 and "before follow moved them" in err, err
