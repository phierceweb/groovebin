"""Queries over the pattern library index `index.build` writes: filtered search, one row by id, and
a group by name."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from .index import COLUMNS, SCHEMA

SHOWN = ("id", "library", "category", "group_name", "variant", "role", "meter", "tempo", "is_beat", "is_fill",
         "swing", "intensity", "bars", "ppq", "map", "file")
NUMBER = r"(\d+(?:\.\d*)?|\.\d+)"
_RANGE = re.compile(rf"^{NUMBER}\s*-\s*{NUMBER}$")
_COMPARE = re.compile(rf"^(<=|>=|<|>)\s*{NUMBER}$")
_EXACT = re.compile(rf"^{NUMBER}$")
DECIMALS = 3
SHOWN_GROUPS = 5


def _half(digits: str) -> float:
    return 0.5 * 10 ** -(len(digits) - digits.index(".") - 1) if "." in digits else 0.5


def parse_range(text: str) -> tuple[str, list[float]]:
    """A numeric filter as an SQL condition on ``{col}`` and its bounds. A bare number and a range's
    ends match to the digits written (``98`` is 97.5 up to 98.5, ``120-140`` takes 140.4); a
    comparison reads the value to three decimals, so 97.999985 is 98 and ``>0.7`` takes 0.72."""
    text = text.strip()
    if m := _RANGE.match(text):
        lo, hi = float(m.group(1)), float(m.group(2))
        if lo > hi:
            raise ValueError(f"bad range {text!r}: {m.group(1)} is above {m.group(2)}")
        return "{col} >= ? AND {col} < ?", [lo - _half(m.group(1)), hi + _half(m.group(2))]
    if m := _COMPARE.match(text):
        return f"ROUND({{col}}, {DECIMALS}) {m.group(1)} ?", [float(m.group(2))]
    if m := _EXACT.match(text):
        value, half = float(m.group(1)), _half(m.group(1))
        return "{col} >= ? AND {col} < ?", [value - half, value + half]
    raise ValueError(f"bad number filter {text!r}: use 100-130, <0.55, >0.7, <=, >= or a bare number")


def connect(db_path: Path) -> sqlite3.Connection:
    db_path = Path(db_path)
    if not db_path.is_file():
        raise FileNotFoundError(f"no pattern library index at {db_path}: build it with `groovebin index`")
    con = sqlite3.connect(db_path.resolve().as_uri() + "?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        schema = dict(con.execute("SELECT name, value FROM meta").fetchall()).get("schema")
    except sqlite3.DatabaseError:
        schema = None
    if schema != str(SCHEMA):
        con.close()
        raise ValueError(f"{db_path} is not a pattern library index this version reads: rebuild it with `groovebin index`")
    return con


def like(text: str) -> str:
    return "%" + re.sub(r"([\\%_])", r"\\\1", text) + "%"


def _where(*, category: str | None = None, meter: str | None = None, tempo: str | None = None,
           fill: bool | None = None, beat: bool | None = None, swing: str | None = None, intensity: str | None = None,
           group: str | None = None, variant: str | None = None, library: str | None = None,
           role: str | None = None) -> tuple[str, list]:
    where, args = ["error IS NULL"], []
    for column, value in (("category", category), ("meter", meter), ("library", library), ("role", role)):
        if value is not None:
            where.append(f"{column} = ? COLLATE NOCASE")
            args.append(value.strip())
    for column, value in (("group_name", group), ("variant", variant)):
        if value is not None:
            where.append(f"{column} LIKE ? ESCAPE '\\'")
            args.append(like(value))
    for column, value in (("is_fill", fill), ("is_beat", beat)):
        if value is not None:
            where.append(f"{column} = ?")
            args.append(int(value))
    for column, value in (("tempo", tempo), ("swing", swing), ("intensity", intensity)):
        if value is not None:
            condition, bounds = parse_range(value)
            where.append(condition.format(col=column))
            args += bounds
    return " AND ".join(where), args


def _query(db_path: Path, sql: str, args: list) -> list[dict]:
    con = connect(db_path)
    try:
        return [dict(r) for r in con.execute(sql, args)]
    finally:
        con.close()


def search(db_path: Path, *, limit: int | None = 50, **filters: str | bool | None) -> list[dict]:
    """Rows matching every filter given, the columns a listing shows. ``category``, ``meter``, ``library``
    and ``role`` match whole values, case aside; ``group`` and ``variant`` match a substring; ``fill`` and
    ``beat`` a flag; ``tempo``, ``swing`` and ``intensity`` take `parse_range` syntax."""
    where, args = _where(**filters)
    sql = f"SELECT {', '.join(SHOWN)} FROM beats WHERE {where} ORDER BY library, category, group_name, variant, key"
    if limit is not None:
        if limit < 0:
            raise ValueError(f"a limit of {limit} rows is below 0")
        sql += f" LIMIT {int(limit)}"
    return _query(db_path, sql, args)


def full_rows(db_path: Path, **filters: str | bool | None) -> list[dict]:
    """Every column of the parsed rows with notes that `search` would match, in key order."""
    where, args = _where(**filters)
    return _query(db_path, f"SELECT {', '.join(COLUMNS)} FROM beats WHERE {where} AND bars > 0 ORDER BY key", args)


def get(db_path: Path, pattern_id: str) -> dict:
    """One row, every column, by its id or any unique prefix of its key."""
    pattern_id = pattern_id.strip().lower()
    if not re.fullmatch(r"[0-9a-f]{4,40}", pattern_id):
        raise ValueError(f"bad pattern id {pattern_id!r}: the hex id `groovebin search` prints")
    con = connect(db_path)
    try:
        rows = con.execute(f"SELECT {', '.join(COLUMNS)} FROM beats WHERE key LIKE ? LIMIT 2", [pattern_id + "%"]).fetchall()
    finally:
        con.close()
    if not rows:
        raise ValueError(f"no pattern {pattern_id} in the index")
    if len(rows) > 1:
        raise ValueError(f"pattern id {pattern_id} is ambiguous: give more of it")
    return dict(rows[0])


def find_group(db_path: Path, text: str) -> tuple[str | None, str]:
    """The one (library, group) ``text`` names: a whole name, any case, or else a substring of exactly
    one group."""
    con = connect(db_path)
    try:
        found = con.execute("SELECT DISTINCT library, group_name FROM beats WHERE error IS NULL AND group_name LIKE ? "
                            "ESCAPE '\\' ORDER BY library, group_name", [like(text.strip())]).fetchall()
    finally:
        con.close()
    found = [(r["library"], r["group_name"]) for r in found]
    hits = [g for g in found if g[1].lower() == text.strip().lower()] or found
    if not hits:
        raise ValueError(f"no group in the index matches {text!r}")
    if len(hits) > 1:
        shown = ", ".join(repr(g) for _lib, g in hits[:SHOWN_GROUPS]) + (", ..." if len(hits) > SHOWN_GROUPS else "")
        raise ValueError(f"{len(hits)} groups match {text!r} ({shown}): give more of the name")
    return hits[0]


def group_rows(db_path: Path, library: str | None, group: str) -> list[dict]:
    """Every parsed row of one group, every column, in key order."""
    con = connect(db_path)
    try:
        return [dict(r) for r in con.execute(
            f"SELECT {', '.join(COLUMNS)} FROM beats WHERE error IS NULL AND bars > 0 "
            "AND group_name = ? AND library IS ? ORDER BY key", [group, library])]
    finally:
        con.close()
