"""Queries over the pattern library index `index.build` writes: filtered search, rows ranked by how near
their rhythm is to a query, one row by id, and a group by name."""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterable
from pathlib import Path

from .groove import SUBDIVISIONS, Bar, distance, from_json
from .index import COLUMNS, SCHEMA
from .sidecar import QUALITIES

SHOWN = ("id", "library", "category", "group_name", "variant", "role", "meter", "tempo", "is_beat", "is_fill",
         "swing", "intensity", "bars", "ppq", "map", "file", "density", "syncopation", "subdivision", "swing8",
         "swing16", "lag", "chords", "changes", "quality")
NUMBER = r"(-?(?:\d+(?:\.\d*)?|\.\d+))"
_RANGE = re.compile(rf"^{NUMBER}\s*-\s*{NUMBER}$")
_COMPARE = re.compile(rf"^(<=|>=|<|>)\s*{NUMBER}$")
_EXACT = re.compile(rf"^{NUMBER}$")
DECIMALS = 3
SHOWN_GROUPS = 5
MAX_QUERY_BARS = 16
RANGES = ("tempo", "swing", "intensity", "density", "syncopation", "swing8", "swing16", "lag", "changes")


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


def _where(*, category: str | None = None, meter: str | None = None, fill: bool | None = None,
           beat: bool | None = None, group: str | None = None, variant: str | None = None, library: str | None = None,
           role: str | None = None, subdivision: str | None = None, quality: str | None = None,
           **ranges: str | None) -> tuple[str, list]:
    if unknown := sorted(set(ranges) - set(RANGES)):
        raise TypeError(f"no filter {', '.join(unknown)}")
    where, args = ["error IS NULL"], []
    if subdivision is not None:
        if subdivision not in SUBDIVISIONS:
            raise ValueError(f"no subdivision {subdivision!r}: {', '.join(SUBDIVISIONS[:-1])} or {SUBDIVISIONS[-1]}")
        where.append("subdivision = ?")
        args.append(subdivision)
    if quality is not None:
        if quality not in QUALITIES:
            raise ValueError(f"no quality {quality!r}: major or minor")
        where.append("quality = ?")
        args.append(quality)
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
    for column, value in ranges.items():
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


MAX_LIMIT = 2**63 - 1                    # sqlite's LIMIT is a signed 64-bit integer


def _checked(limit: int | None) -> int | None:
    if limit is not None and not 0 <= limit <= MAX_LIMIT:
        raise ValueError(f"a limit of {limit} rows is not 0 to {MAX_LIMIT}")
    return limit


def search(db_path: Path, *, limit: int | None = 50, **filters: str | bool | None) -> list[dict]:
    """Rows matching every filter given, the columns a listing shows. ``category``, ``meter``, ``library``
    and ``role`` match whole values, case aside; ``group`` and ``variant`` match a substring; ``fill`` and
    ``beat`` a flag; ``subdivision`` one of `groove.SUBDIVISIONS`; the `RANGES` take `parse_range` syntax."""
    where, args = _where(**filters)
    sql = f"SELECT {', '.join(SHOWN)} FROM beats WHERE {where} ORDER BY library, category, group_name, variant, key"
    if _checked(limit) is not None:
        sql += f" LIMIT {int(limit)}"
    return _query(db_path, sql, args)


def query_bars(bars: Iterable[Bar]) -> tuple[tuple[Bar, ...], int]:
    """A query's distinct bars that strike anything, in order and at most `MAX_QUERY_BARS` of them, and how
    many distinct ones it had."""
    distinct = [b for b in dict.fromkeys(bars) if b.kick or b.snare or b.hands]
    return tuple(distinct[:MAX_QUERY_BARS]), len(distinct)


def similar(db_path: Path, query: Iterable[Bar], *, limit: int | None = 50, exclude: str | None = None,
            voices: Iterable[int] | None = None, **filters: str | bool | None) -> list[dict]:
    """Rows matching every filter, nearest ``query``'s `query_bars` first by `groove.distance` over ``voices``
    (all by default), each with its ``distance``. ``exclude`` is a key to leave out; so is a row with no bar the
    length of a query bar."""
    bars, _ = query_bars(query)
    if not bars:
        raise ValueError("the query has no kick, snare or hands onset to compare")
    _checked(limit)
    voices = None if voices is None else tuple(voices)
    where, args = _where(**filters)
    ranked = []
    for row in _query(db_path, f"SELECT key, rhythm, {', '.join(SHOWN)} FROM beats WHERE {where} AND rhythm IS NOT NULL",
                      args):
        key, grid = row.pop("key"), from_json(row.pop("rhythm"))
        if key != exclude and (d := distance(bars, grid, voices)) is not None:
            ranked.append((d, key, row | {"distance": d}))
    ranked.sort(key=lambda found: found[:2])
    return [row for _d, _key, row in ranked[:limit]]


def pattern_rhythm(db_path: Path, pattern_id: str) -> tuple[str, tuple[Bar, ...]]:
    """A pattern's key and rhythm by its id; refused, with the reason, when the row has none."""
    row = get(db_path, pattern_id)
    if not row["rhythm"]:
        why = ("it was not parsed" if row["error"] else "it holds no notes" if not row["bars"]
               else "its index was built without --map" if row["map"] is None
               else f"its map, {row['map']}, is not a drum map")
        raise ValueError(f"pattern {row['id']} has no rhythm to compare: {why}")
    return row["key"], from_json(row["rhythm"])


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
