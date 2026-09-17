"""Bytecode that disagrees with its source. CPython trusts a `.pyc` whose recorded source mtime
and size match the file; an in-place edit restored with both preserved leaves the cache valid
and the interpreter running code the source no longer holds. Every pytest session removes such
caches under ``src`` before anything imports."""

from __future__ import annotations

import importlib.util
import marshal
from pathlib import Path

HEADER = 16                                   # magic, flags, source mtime, source size


def stale(source: Path) -> Path | None:
    """The source's cached bytecode when its code is not what the source compiles to, else None."""
    pyc = Path(importlib.util.cache_from_source(str(source)))
    if not pyc.exists():
        return None
    try:
        cached = marshal.loads(pyc.read_bytes()[HEADER:])
        fresh = compile(source.read_text(), str(source), "exec", dont_inherit=True)
    except (ValueError, EOFError, SyntaxError, OSError):
        return pyc
    return None if cached == fresh else pyc                  # code objects compare structurally; marshal bytes do not


def purge(root: Path) -> list[Path]:
    """Remove every stale cache under ``root``; the caches removed."""
    removed = []
    for source in sorted(root.rglob("*.py")):
        pyc = stale(source)
        if pyc is not None:
            pyc.unlink()
            removed.append(pyc)
    return removed
