"""A small synthetic pattern library for the pattern, show, compose and generate tests."""

from pathlib import Path

from smf_bytes import csv_row, pattern_file, write_csv

from groovebin.library.index import build
from groovebin.library.search import get, search

BAR = 3840
KICK, SNARE, HAT, TOM, STICKS = 0x24, 0x26, 0x31, 0x47, 0x4B
GROUP = "Test Kit"

INTRO = pattern_file(240, [(0, KICK, 100, 120), (480, SNARE, 90, 60), (960, KICK, 100, 120), (1440, SNARE, 110, 60)])
VERSE_1 = pattern_file(480, [(0, KICK, 100, 240), (0, HAT, 70, 120), (960, SNARE, 96, 120), (1440, HAT, 60, 120)])
VERSE_2 = pattern_file(960, [(0, KICK, 120, 240), (1920, SNARE, 100, 240), (2880, STICKS, 50, 60)])
FILL = pattern_file(240, [(0, KICK, 127, 120), (960, TOM, 90, 60), (1200, TOM, 100, 60), (1440, SNARE, 120, 60)])
VERSE_FILL = pattern_file(240, [(0, TOM, 100, 60), (240, TOM, 100, 60), (480, SNARE, 110, 60)])
LANDING = pattern_file(240, [(0, TOM, 90, 60), (480, SNARE, 120, 60), (960, 0x31, 127, 120)])
WALTZ = pattern_file(240, [(0, KICK, 100, 120), (240, HAT, 60, 60), (480, HAT, 60, 60)], (3, 4))
TAIL = pattern_file(9600, [(0, KICK, 100, 2400), (38399, SNARE, 80, 3)])


def index(folder: Path) -> Path:
    """One group with an intro, two verses, a plain fill, a verse fill, a fill that ends on a landing and a
    3/4 chorus; a second group whose name holds the first's; a pattern whose last note rounds to its end."""
    rows = [csv_row("kit/intro.mid", GROUP, "Intro", "Rock", "4/4", "120", True, "0.5", "0.5", INTRO),
            csv_row("kit/verse-2.mid", GROUP, "Verse 02", "Rock", "4/4", "120", True, "0.5", "0.5", VERSE_2),
            csv_row("kit/verse-1.mid", GROUP, "Verse 01", "Rock", "4/4", "120", True, "0.5", "0.5", VERSE_1),
            csv_row("kit/fill.mid", GROUP, "Fills 01", "Rock", "4/4", "120", False, "0.5", "0.5", FILL),
            csv_row("kit/verse-fill.mid", GROUP, "Verse Fill 01", "Rock", "4/4", "120", False, "0.5", "0.5", VERSE_FILL),
            csv_row("kit/landing.mid", GROUP, "Fills 02", "Rock", "4/4", "120", False, "0.5", "0.5", LANDING),
            csv_row("kit/waltz.mid", GROUP, "Chorus", "Rock", "3/4", "96", True, "0.5", "0.5", WALTZ),
            csv_row("two/verse.mid", GROUP + " Two", "Verse", "Rock", "4/4", "120", True, "0.5", "0.5", VERSE_1),
            csv_row("tails/tail.mid", "Tails", "", "Rock", "4/4", "120", True, "0.5", "0.5", TAIL)]
    db = folder / "library.sqlite"
    build(db, csv_path=write_csv(folder / "acct" / "MidiDb.csv", rows), map_name="addictive-drums-2")
    return db


def row(db: Path, variant: str, group: str = GROUP) -> dict:
    (hit,) = [r for r in search(db, group=group, limit=None) if (r["variant"] or r["file"]) == variant]
    return get(db, hit["id"])
