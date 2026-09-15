"""What a pattern file's path, relative to the library root, says about it: group, variant, category, fill
flag and section role, from Addictive Drums 2's export naming (``<group>_V_<variant>_C_<category>[_F_]``)
or else the folders, and tempo and meter hints for a file that carries none of its own."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath

EXPORT_NAME = re.compile(r"^(?P<group>.*)_V_(?P<variant>.*)_C_(?P<category>.*?)(?P<fill>_F_)?$")
ROLES = (("pre-chorus", r"pre[\s_-]?chorus"), ("intro", r"intro"), ("verse", r"verse"), ("chorus", r"chorus"),
         ("bridge", r"bridge"), ("outro", r"outro|ending"))
# a word edge is any non-letter: "_" and digits join words in file names
ROLE_WORDS = [(role, re.compile(rf"(?<![a-z])(?:{pattern})(?![a-z])", re.I)) for role, pattern in ROLES]
FILL_WORD = re.compile(r"(?<![a-z])fills?(?![a-z])", re.I)
TEMPO_HINT = re.compile(r"(\d+(?:\.\d+)?)\s*bpm(?![a-z])", re.I)
METER_HINT = re.compile(r"(?<![\d.])(\d{1,2})\s*[:/-]\s*(\d{1,2})(?![\d.])")


@dataclass(frozen=True, slots=True)
class Described:
    group: str | None
    variant: str
    category: str | None
    is_fill: bool
    role: str | None
    tempo_hint: float | None
    meter_hint: tuple[int, int] | None


def role_of(text: str) -> str | None:
    """The earliest section word in ``text``, as its role."""
    found = [(m.start(), role) for role, word in ROLE_WORDS if (m := word.search(text))]
    return min(found)[1] if found else None


def _meter(text: str) -> tuple[int, int] | None:
    """The first N/D in ``text`` that reads as a meter: ``1-8`` or ``4-1`` is a count or a range, not one."""
    for m in METER_HINT.finditer(text):
        num, den = int(m.group(1)), int(m.group(2))
        if 2 <= num <= 32 and den in (2, 4, 8, 16, 32):
            return num, den
    return None


def describe(path: PurePosixPath) -> Described:
    folders = list(path.parts[:-1])
    parent = folders[-1] if folders else ""
    exported = EXPORT_NAME.match(path.stem)
    if exported:
        group, variant, category = (exported.group(k).strip() for k in ("group", "variant", "category"))
    else:
        group, variant, category = parent or None, path.stem, folders[0] if folders else None
    is_fill = bool(exported and exported.group("fill")) or bool(FILL_WORD.search(variant) or FILL_WORD.search(parent))
    role = next((r for text in [variant, *reversed(folders)] if (r := role_of(text))), None)
    nearest_first = [path.stem, *reversed(folders)]
    tempo = next((float(m.group(1)) for text in nearest_first if (m := TEMPO_HINT.search(text))), None)
    meter = next((hint for text in nearest_first if (hint := _meter(text))), None)
    return Described(group, variant, category, is_fill, role, tempo, meter)
