"""The module layers stay ordered and the library stays quiet. pf_core.guards checks layering
only inside an `app/` tree, so this test owns it for src-layout."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src" / "groovebin"

BOUNDARY = 3
RANKS = {
    "cli": BOUNDARY, "_parsers": BOUNDARY, "_views": BOUNDARY,
    "library": 2,
    "maps": 1, "transforms": 1,
    "midi": 0, "events": 0, "timing": 0, "song": 0,
}
QUIET_MODULES = {"logging"}
ENV_ATTRS = {"environ", "getenv", "putenv"}


def unit_of(path: Path, src: Path) -> str:
    """The top-level module a file belongs to: `maps/translate.py` is `maps`."""
    return path.relative_to(src).parts[0].removesuffix(".py")


def rank(unit: str) -> int | None:
    if unit.startswith("_views"):
        return BOUNDARY
    return RANKS.get(unit)


def imported(path: Path, src: Path, node: ast.Import | ast.ImportFrom) -> list[str]:
    """Absolute module names an import names, relative imports resolved."""
    if isinstance(node, ast.Import):
        return [a.name for a in node.names]
    if not node.level:
        return [node.module or ""]
    package = ["groovebin", *path.parent.relative_to(src).parts]
    base = package[:len(package) - (node.level - 1)]
    if node.module:
        return [".".join([*base, node.module])]
    return [".".join([*base, a.name]) for a in node.names]


def violations(src: Path) -> list[str]:
    found = []
    edges: dict[str, set[str]] = {}
    for path in sorted(src.rglob("*.py")):
        if path.name == "__init__.py" and path.parent == src:
            continue
        where = str(path.relative_to(src))
        unit = unit_of(path, src)
        mine = rank(unit)
        if mine is None:
            found.append(f"{where}: no layer for module {unit!r} — rank it in RANKS and layering.md")
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"), where)):
            line = f"{where}:{getattr(node, 'lineno', 0)}"
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for mod in imported(path, src, node):
                    top = mod.split(".")[0]
                    if mine != BOUNDARY and (top == "pf_core" or top in QUIET_MODULES):
                        found.append(f"{line}: {unit} imports {mod} (boundary only)")
                    if mine != BOUNDARY and top == "os" and isinstance(node, ast.ImportFrom) \
                            and ENV_ATTRS & {a.name for a in node.names}:
                        found.append(f"{line}: {unit} reads the environment (boundary only)")
                    parts = mod.split(".")
                    if top != "groovebin" or len(parts) < 2:
                        if top == "groovebin" and mine != BOUNDARY:
                            found.append(f"{line}: {unit} imports the package root")
                        continue
                    target = parts[1]
                    theirs = rank(target)
                    if target != unit:
                        edges.setdefault(unit, set()).add(target)
                    if theirs is None and mine != BOUNDARY:
                        found.append(f"{line}: {unit} imports {target!r}, which has no layer")
                    elif theirs is not None and theirs > mine:
                        found.append(f"{line}: {unit} (layer {mine}) imports {target} (layer {theirs})")
            elif mine != BOUNDARY and isinstance(node, ast.Call) \
                    and isinstance(node.func, ast.Name) and node.func.id == "print":
                found.append(f"{line}: {unit} calls print() (boundary only)")
            elif mine != BOUNDARY and isinstance(node, ast.Attribute) \
                    and isinstance(node.value, ast.Name) and node.value.id == "os" \
                    and node.attr in ENV_ATTRS:
                found.append(f"{line}: {unit} reads the environment (boundary only)")
    found += [f"import cycle: {' -> '.join(c)}" for c in cycles(edges)]
    return found


def cycles(edges: dict[str, set[str]]) -> list[list[str]]:
    found = []

    def walk(node: str, path: list[str]) -> None:
        for nxt in sorted(edges.get(node, ())):
            if nxt in path:
                found.append(path[path.index(nxt):] + [nxt])
            else:
                walk(nxt, path + [nxt])

    for start in sorted(edges):
        walk(start, [start])
    return found


def test_the_package_obeys_its_layers():
    assert violations(SRC) == []


def tree(tmp_path: Path, files: dict[str, str]) -> Path:
    for name, body in files.items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(body)
    return tmp_path


@pytest.mark.parametrize(("files", "expected"), [
    ({"midi.py": "from .transforms import quantize\n"}, "midi (layer 0) imports transforms (layer 1)"),
    ({"maps/translate.py": "from ..library import search\n"}, "maps (layer 1) imports library (layer 2)"),
    ({"maps/translate.py": "from .. import cli\n"}, "maps (layer 1) imports cli (layer 3)"),
    ({"transforms.py": "import groovebin.library.index\n"}, "transforms (layer 1) imports library"),
    ({"transforms.py": "from pf_core.utils.io import atomic_write_bytes\n"}, "imports pf_core"),
    ({"library/index.py": "import logging\n"}, "imports logging"),
    ({"midi.py": "print('hi')\n"}, "calls print()"),
    ({"midi.py": "import os\nx = os.environ['A']\n"}, "reads the environment"),
    ({"midi.py": "from os import getenv\n"}, "reads the environment"),
    ({"model.py": ""}, "no layer for module 'model'"),
    ({"midi.py": "from . import __version__\n"}, "imports '__version__', which has no layer"),
    ({"midi.py": "from groovebin import __version__\n"}, "imports the package root"),
    ({"maps.py": "from . import transforms\n", "transforms.py": "from . import maps\n"},
     "import cycle: maps -> transforms -> maps"),
])
def test_each_violation_is_caught(tmp_path, files, expected):
    found = violations(tree(tmp_path, files))
    assert any(expected in v for v in found), found


def test_the_boundary_may_use_the_framework(tmp_path):
    src = tree(tmp_path, {
        "cli.py": "import os\nfrom pf_core.log import get_logger\nfrom . import midi\nprint(os.environ)\n",
        "_views_drums.py": "print('lanes')\n",
        "midi.py": "",
    })
    assert violations(src) == []
