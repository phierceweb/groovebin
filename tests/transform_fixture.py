"""Files and a runner for the `groovebin transform` tests."""

from mido import Message, MetaMessage, MidiFile, MidiTrack

from groovebin.cli import main
from groovebin.midi import write
from groovebin.song import Part, Song

NOTES = [(0, 36, 100, 120), (480, 38, 40, 120), (960, 42, 30, 60), (1440, 36, 90, 120), (1920 + 360, 38, 20, 120)]


def build(path, notes, ppq=480, meter=None, tempo=500000):
    """``(tick, pitch, velocity, length)`` notes on channel 1 plus a controller and a program change."""
    mf = MidiFile(ticks_per_beat=ppq)
    track = MidiTrack()
    events = [(0, MetaMessage("set_tempo", tempo=tempo)), (0, Message("program_change", program=5)),
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


def mid(tmp_path, *notes, name="in.mid"):
    """A file written from Notes the test names, so a length of 0 survives to the command."""
    path = tmp_path / name
    path.write_bytes(write(Song(480, 0, (Part(480, notes),))))
    return path


def run(capsys, *argv):
    rc = main([str(a) for a in argv])
    out, err = capsys.readouterr()
    return rc, out, err
