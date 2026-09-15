"""Standard MIDI File bytes built by hand for the library tests."""

import csv
import struct
from pathlib import Path

EOT = b"\xff\x2f\x00"
CSV_HEADER = ["FileName", "Group", "Variant", "IsMainVariant", "Library", "ProductId", "Category", "TimeSign", "Tempo",
              "IsBeat", "IsFill", "Swing", "Complexity", "Intensity", "HH_Type", "SN_Type", "HH_Vel", "SN_Vel", "KK_Vel",
              "IsWhitelisted", "MidiMD5", "MidiData"]


def vlq(n: int) -> bytes:
    out = [n & 0x7F]
    while n := n >> 7:
        out.append(n & 0x7F | 0x80)
    return bytes(reversed(out))


def smf(fmt: int, division: int, *tracks: list[tuple[int, bytes]]) -> bytes:
    out = b"MThd" + struct.pack(">IHHH", 6, fmt, len(tracks), division)
    for events in tracks:
        body = b"".join(vlq(delta) + msg for delta, msg in events)
        out += b"MTrk" + struct.pack(">I", len(body)) + body
    return out


def tempo(bpm: float) -> bytes:
    return b"\xff\x51\x03" + round(60_000_000 / bpm).to_bytes(3, "big")


# Format 0, 240 PPQ, two bars of 4/4; the bare two-byte messages ride running status.
TWO_BARS = smf(0, 240, [(0, tempo(120)), (0, b"\xff\x58\x04\x04\x02\x18\x08"), (0, b"\x99\x24\x64"), (0, b"\x2a\x50"),
                        (60, b"\x2a\x00"), (60, b"\x89\x24\x40"), (360, b"\x99\x26\x5a"), (60, b"\x26\x00"),
                        (660, b"\x2a\x30"), (60, b"\x2a\x00"), (600, b"\x24\x7f"), (40, b"\x24\x00"), (20, EOT)])
# Format 1, 480 PPQ, one bar of 3/4 over three tracks.
FORMAT_1 = smf(1, 480, [(0, b"\xff\x58\x04\x03\x02\x18\x08"), (0, tempo(100)), (480, tempo(150)), (0, EOT)],
               [(0, b"\x90\x3c\x64"), (240, b"\x80\x3c\x00"), (0, EOT)],
               [(240, b"\x99\x24\x70"), (480, b"\x89\x24\x00"), (0, EOT)])
# Format 0, 480 PPQ, no tempo and no meter: one bar of notes.
BARE = smf(0, 480, [(0, b"\x99\x24\x64"), (240, b"\x89\x24\x40"), (0, EOT)])


def csv_row(file, group, variant, category, meter, bpm, beat, swing, intensity, data, library="Lib One"):
    return [file, group, variant, "true", library, "", category, meter, bpm, "true" if beat else "false",
            "false" if beat else "true", swing, "0.000000", intensity, "0", "1", "0", "0", "0", "true", "0" * 32,
            data if isinstance(data, str) else data.hex().upper()]


def write_csv(path: Path, rows: list[list[str]], encoding: str = "utf-8") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding=encoding) as fh:
        csv.writer(fh).writerows([CSV_HEADER, ["string"] * len(CSV_HEADER), *rows])
    return path


def pattern_file(ppq: int, notes: list[tuple[int, int, int, int]], meter: tuple[int, int] | None = (4, 4)) -> bytes:
    """A format-0 file of ``(tick, pitch, velocity, length)`` notes on channel 10."""
    timed = [(t, b"\x99" + bytes([p, v])) for t, p, v, _l in notes] + [(t + n, b"\x89" + bytes([p, 0])) for t, p, _v, n in notes]
    timed.sort(key=lambda e: (e[0], e[1][0] == 0x99))
    events, last = [], 0
    if meter:
        events.append((0, b"\xff\x58\x04" + bytes([meter[0], meter[1].bit_length() - 1, 24, 8])))
    for t, msg in timed:
        events.append((t - last, msg))
        last = t
    return smf(0, ppq, events + [(0, EOT)])
