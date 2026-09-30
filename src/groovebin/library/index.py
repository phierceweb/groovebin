"""A searchable index of MIDI patterns in sqlite, built from a folder of .mid files or from a
`MidiDb.csv` (which carries each pattern's whole file as hex in `MidiData`).

Every row keeps the parsed file: its PPQ, meters and a note histogram as JSON, its bar count, and its
notes rescaled to 960 PPQ as a blob of `NOTE` records, with the note map its patterns follow. A row's
key is the SHA-1 of its file name and bytes, so ids survive a rebuild; `id` is the key's first ten
hex digits.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import sqlite3
from collections import Counter
from collections.abc import Iterator
from pathlib import Path, PurePosixPath

from ..maps import note_map
from ..midi import read
from ..song import merged, meter_map, rescale, skipped_meters, tempo_map
from ..timing import MeterMap
from .blobs import pack_events, pack_notes
from .groove import columns
from .names import describe, role_of
from .sidecar import CHORD_COLUMNS, read_beside
from .sidecar import columns as chord_columns

DEFAULT_CACHE = "~/.cache"


def default_db(cache_home: str | None = None) -> Path:
    """The pattern library index when none is named: ``groovebin/library.sqlite`` under
    ``cache_home`` — the caller's ``$XDG_CACHE_HOME`` — or under ``~/.cache`` when that is None or
    empty. The library reads no environment itself; a consumer passes the variable in."""
    return Path(cache_home or DEFAULT_CACHE).expanduser() / "groovebin" / "library.sqlite"

PPQ = 960
SCHEMA = 4
ID_LENGTH = 10
MAX_BARS = 4096
CSV_TYPE_ROW = "string"

CSV_COLUMNS = {
    "FileName": ("file", str), "Group": ("group_name", str), "Variant": ("variant", str),
    "IsMainVariant": ("is_main", bool), "Library": ("library", str), "ProductId": ("product_id", str),
    "Category": ("category", str), "TimeSign": ("meter", str), "Tempo": ("tempo", float),
    "IsBeat": ("is_beat", bool), "IsFill": ("is_fill", bool), "Swing": ("swing", float),
    "Complexity": ("complexity", float), "Intensity": ("intensity", float),
    "HH_Type": ("hh_type", int), "SN_Type": ("sn_type", int), "HH_Vel": ("hh_vel", int),
    "SN_Vel": ("sn_vel", int), "KK_Vel": ("kk_vel", int), "IsWhitelisted": ("whitelisted", bool),
    "MidiMD5": ("midi_md5", str),
}
LABELS = ("role", "map")
GROOVE = ("rhythm", "density", "syncopation", "subdivision", "swing8", "swing16", "lag")
PARSED = ("ppq", "bars", "meters", "histogram", "notes", "events", "error", *GROOVE)
COLUMNS = ("key", "id", "source") + tuple(c for c, _ in CSV_COLUMNS.values()) + LABELS + CHORD_COLUMNS + PARSED
REQUIRED_CSV = ("FileName", "MidiData")
INTEGERS = {"ppq", "bars", *(c for c, kind in CSV_COLUMNS.values() if kind in (int, bool))}
REALS = {c for c, kind in CSV_COLUMNS.values() if kind is float} | {"density", "syncopation", "swing8", "swing16", "lag",
                                                                     "changes"}


def _sql_type(column: str) -> str:
    return "INTEGER" if column in INTEGERS else "REAL" if column in REALS else "BLOB" if column in ("notes", "events") else "TEXT"


def _value(text: str, kind):
    text = text.strip()
    if kind is str:
        return text
    if kind is bool:
        return {"true": 1, "false": 0, "1": 1, "0": 0}.get(text.lower())
    try:
        value = kind(float(text)) if kind is int else kind(text)
    except ValueError:
        return None
    if kind is int and not -2**63 <= value < 2**63:
        raise OverflowError("out of the 64-bit integer range")
    return value


def _stand_in(text: str | None) -> tuple[int, int] | None:
    num, _, den = (text or "").partition("/")
    return (int(num), int(den)) if num.strip().isdigit() and den.strip().isdigit() and int(num) and int(den) else None


def _parse(data: bytes, meter_hint: tuple[int, int] | None, map_name: str | None) -> tuple[dict, dict]:
    """The parsed columns of one file, and the tempo and bar 1's meter the file itself carries. ``meter_hint``
    stands in for bar counting when the file has no time signature; with neither, the meter is 4/4. The feel
    columns need ``map_name`` to be a drum map."""
    try:
        song = read(data)
        meters = meter_map(song)
        hinted = meters.defaulted and meter_hint is not None
        if hinted:
            meters = MeterMap(song.ppq, ((0, *meter_hint),))
        part = merged(song)
        at_index = rescale(part, PPQ)
        packed, events = pack_notes(at_index.notes), pack_events(at_index.events)
        bars = meters.bar_of(max(n.tick for n in part.notes)) if part.notes else 0
        if bars > MAX_BARS:
            raise ValueError(f"the last note is past bar {MAX_BARS}: not a groove pattern")
    except (ValueError, OverflowError) as e:
        return dict.fromkeys(PARSED) | {"error": str(e)}, {}
    scaled = [[(t * PPQ + song.ppq // 2) // song.ppq, n, d] for t, n, d in meters.changes]
    histogram = dict(sorted(Counter(n.pitch for n in part.notes).items()))
    _, num, den = meters.changes[0]
    tempos = tempo_map(song)
    # 4/4 here is the map's fallback, not the file's: nothing usable was read
    unknown = hinted or (meters.defaulted and skipped_meters(song) > 0)
    own = {"meter": None if unknown else f"{num}/{den}",
           "tempo": None if tempos.defaulted else round(tempos.bpm(tempos.points[0][0]), 6)}
    drums = map_name is not None and note_map(map_name).kind == "drums"
    feel = columns(part.notes, meters, bars, map_name) if drums else dict.fromkeys(GROOVE)
    return {"ppq": song.ppq, "bars": bars, "meters": json.dumps(scaled), "histogram": json.dumps(histogram),
            "notes": packed, "events": events, "error": None} | feel, own


def _csv_rows(path: Path) -> Iterator[tuple[str, dict, bytes, str | None]]:
    csv.field_size_limit(2**31 - 1)
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        missing = [c for c in REQUIRED_CSV if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"{path.name} has no {', '.join(missing)} column: not a MidiDb.csv")
        for row in reader:
            if row.get("MidiData") == CSV_TYPE_ROW:
                continue
            meta, problem = {}, None
            for name, (col, kind) in CSV_COLUMNS.items():
                if row.get(name) is not None:
                    try:
                        meta[col] = _value(row[name], kind)
                    except OverflowError as e:
                        problem = problem or f"{name} {row[name].strip()!r}: {e}"
            meta["role"] = role_of(meta.get("variant") or "")
            try:
                data = bytes.fromhex(row["MidiData"] or "")
            except ValueError:
                data, problem = b"", problem or "MidiData is not hex"
            yield meta.get("file") or "", meta, data, problem


def _folder_rows(folder: Path) -> Iterator[tuple[str, dict, bytes, str | None]]:
    """A row per .mid file under ``folder``, and a failed row per subfolder that cannot be listed."""
    unlisted: dict[Path, OSError] = {}

    def not_listed(e: OSError) -> None:
        if Path(e.filename) == folder:
            raise e
        unlisted[Path(e.filename)] = e

    found = [Path(root, name) for root, _, names in os.walk(folder, onerror=not_listed) for name in names]
    midi = [p for p in found if p.suffix.lower() in (".mid", ".midi") and p.is_file()]
    for path in sorted([*midi, *unlisted]):
        name = path.relative_to(folder).as_posix()
        info = describe(PurePosixPath(name))
        meta = {"file": name, "group_name": info.group, "variant": info.variant, "category": info.category,
                "role": info.role, "is_fill": int(info.is_fill), "is_beat": int(not info.is_fill),
                "meter": f"{info.meter_hint[0]}/{info.meter_hint[1]}" if info.meter_hint else None,
                "tempo": info.tempo_hint}
        if path in unlisted:
            yield name, meta, b"", f"not listed: {unlisted[path].strerror or unlisted[path]}"
            continue
        try:
            data, problem = path.read_bytes(), None
        except OSError as e:
            data, problem = b"", f"not read: {e.strerror or e}"
        try:
            meta["_chords"], meta["_unread"] = read_beside(path), False
        except (OSError, ValueError):
            meta["_chords"], meta["_unread"] = None, True
        yield name, meta, data, problem


def _is_index(path: Path) -> bool:
    try:
        con = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    except sqlite3.Error:
        return False
    try:
        return con.execute("SELECT value FROM meta WHERE name = 'schema'").fetchone() is not None
    except sqlite3.Error:
        return False
    finally:
        con.close()


def _check_target(db_path: Path, source: Path, is_csv: bool) -> None:
    target, source = db_path.resolve(), source.resolve()
    if is_csv and target == source:
        raise ValueError(f"{target} is the CSV it reads: give the index another path")
    if not is_csv and target.is_relative_to(source):
        raise ValueError(f"{target} is inside the folder it reads: give the index a path outside {source}")
    if db_path.exists() and not (db_path.is_file() and _is_index(db_path)):
        raise ValueError(f"{db_path} exists and is not a pattern library index: move it or give another path")


def build(db_path: Path, *, csv_path: Path | None = None, folder: Path | None = None, map_name: str | None) -> dict:
    """Index ``csv_path`` or ``folder``, whose patterns follow the note map ``map_name`` (None for a library
    with none), into a fresh ``db_path``, replaced whole on success. Returns the counts of rows, parsed, failed and
    duplicate patterns, grooves with chords, and chord files not read."""
    if (csv_path is None) == (folder is None):
        raise ValueError("index one source: a MidiDb.csv or a folder of .mid files")
    if map_name is not None:
        note_map(map_name)
    source = Path(csv_path or folder)
    if not (source.is_file() if csv_path else source.is_dir()):
        raise FileNotFoundError(f"no {'CSV file' if csv_path else 'folder'} at {source}")
    db_path = Path(db_path)
    _check_target(db_path, source, csv_path is not None)
    rows = _csv_rows(source) if csv_path else _folder_rows(source)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = db_path.with_name(f".{db_path.name}.{os.getpid()}.tmp")
    tmp.unlink(missing_ok=True)
    counts = {"rows": 0, "parsed": 0, "failed": 0, "duplicates": 0, "chords": 0, "unread_chords": 0}
    try:
        con = sqlite3.connect(tmp)
        try:
            with con:
                _write(con, rows, "csv" if csv_path else "folder", map_name, counts)
        finally:
            con.close()
        os.replace(tmp, db_path)
    finally:
        tmp.unlink(missing_ok=True)
    return counts


def _write(con: sqlite3.Connection, rows, source: str, map_name: str | None, counts: dict) -> None:
    con.execute(f"CREATE TABLE beats ({', '.join(f'{c} {_sql_type(c)}' for c in COLUMNS)}, PRIMARY KEY (key))")
    con.execute("CREATE TABLE meta (name TEXT PRIMARY KEY, value TEXT)")
    insert = f"INSERT OR IGNORE INTO beats ({', '.join(COLUMNS)}) VALUES ({', '.join('?' * len(COLUMNS))})"
    for name, meta, data, problem in rows:
        key = hashlib.sha1(name.encode() + b"\0" + data).hexdigest()
        if problem:
            parsed = dict.fromkeys(PARSED) | {"error": problem}
        else:
            hint = _stand_in(meta.get("meter"))
            parsed, own = _parse(data, hint, map_name)
            if source == "folder":
                meta = meta | {k: v for k, v in own.items() if v is not None}
            elif not meta.get("meter") and own.get("meter"):
                meta = meta | {"meter": own["meter"]}
        length = (MeterMap(PPQ, tuple(tuple(c) for c in json.loads(parsed["meters"]))).bar_line(parsed["bars"] + 1) / PPQ
                  if parsed["bars"] else None)
        chords = chord_columns(meta.get("_chords"), parsed["bars"] or 0, PPQ, length)
        row = {"key": key, "id": key[:ID_LENGTH], "source": source, "map": map_name} | meta | chords | parsed
        cur = con.execute(insert, [row.get(c) for c in COLUMNS])
        counts["chords"] += cur.rowcount == 1 and chords["chords"] is not None
        counts["unread_chords"] += cur.rowcount == 1 and bool(meta.get("_unread"))
        counts["rows"] += 1
        counts["duplicates"] += cur.rowcount == 0
        counts["failed" if parsed["error"] else "parsed"] += cur.rowcount == 1
    con.executemany("INSERT INTO meta VALUES (?, ?)", [("schema", str(SCHEMA)), ("source", source)])
    for col in ("id", "category", "meter", "tempo", "library", "role"):
        con.execute(f"CREATE INDEX beats_{col} ON beats ({col})")
