"""Session setup: bytecode compiled from a source this tree no longer holds is removed before
collection (`_bytecode`)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _bytecode import purge  # noqa: E402


def pytest_configure(config):
    removed = purge(Path(__file__).resolve().parents[1] / "src")
    if removed:
        print(f"\nremoved {len(removed)} stale bytecode cache(s): " + ", ".join(p.name for p in removed[:5]), file=sys.stderr)
