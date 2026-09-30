"""`groovebin analyze`: what a bassline does, alone, against drums and against a chord chart."""

import json

from groovebin.cli import main
from groovebin.events import Event, Note
from groovebin.midi import write
from groovebin.song import Part, Song

BAR = 3840
METER = Event(0, bytes([0xFF, 0x58, 4, 4, 2, 24, 8]))
BASS = [(0, 45), (1920, 45), (2400, 40), (3360, 48), (BAR, 41), (BAR + 1920, 41), (BAR + 2400, 48), (BAR + 3360, 45)]
DRUMS = [(b + t, p) for b in (0, BAR) for t, p in ((0, 36), (1920, 36), (960, 38), (2880, 38))]


def run(capsys, *argv):
    rc = main([str(a) for a in argv])
    out, err = capsys.readouterr()
    return rc, out, err


def song(path, pairs, *, ppq=960, channel=1, extra=()):
    scale = ppq / 960
    notes = tuple(Note(round(t * scale), round(480 * scale), channel, p, 90) for t, p in pairs) + tuple(extra)
    path.write_bytes(write(Song(ppq, 0, (Part(ppq, notes, (METER,)),))))
    return path


def test_alone(tmp_path, capsys):
    rc, out, err = run(capsys, "analyze", song(tmp_path / "b.mid", BASS))
    assert (rc, err) == (0, "")
    assert out.splitlines() == ["b.mid: 2 bar(s), 8 note(s), E2 to C3", "rhythm  4 onset(s) a bar, 50% on the beat",
                                "scale   C major / A minor"]


def test_against_drums_at_another_ppq_and_a_chart(tmp_path, capsys):
    rc, out, _err = run(capsys, "analyze", song(tmp_path / "b.mid", BASS),
                        "--drums", song(tmp_path / "d.mid", DRUMS, ppq=480, channel=10), "--drum-map", "gm",
                        "--chords", "| Am | F |")
    assert rc == 0
    assert out.splitlines()[3:] == [
        "drums   50% of bass onsets on a kick, 100% of kicks with a bass onset, 0% of snares with one",
        "chords  the new chord's bass note on 100% of 1 change(s); held on the root 50%, third 25%, fifth 25%, "
        "seventh 0%, other 0%"]


def test_keyswitches_and_json(tmp_path, capsys):
    ghost = (Note(3360, 5, 1, 16, 100),)
    rc, out, _err = run(capsys, "analyze", song(tmp_path / "b.mid", BASS, extra=ghost), "--map", "ezbass")
    assert out.splitlines()[-1] == "keyswitches  keyswitch repeat ghost x1"
    rc, out, _err = run(capsys, "analyze", song(tmp_path / "b.mid", BASS, extra=ghost), "--map", "ezbass", "--json")
    report = json.loads(out)
    assert (report["notes"], report["keyswitches"], report["with_kick"]) == (8, {"keyswitch repeat ghost": 1}, None)


def test_drums_need_their_map(tmp_path, capsys):
    rc, _out, err = run(capsys, "analyze", song(tmp_path / "b.mid", BASS), "--drums", song(tmp_path / "d.mid", DRUMS))
    assert rc == 1 and "--drum-map" in err


def test_a_track_of_only_keyswitches_is_refused(tmp_path, capsys):
    rc, _out, err = run(capsys, "analyze", song(tmp_path / "k.mid", [(0, 16), (960, 17)]), "--map", "ezbass")
    assert rc == 1 and "no notes to analyze" in err
