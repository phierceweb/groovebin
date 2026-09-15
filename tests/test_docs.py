"""Doc-sync gates: every subcommand has a `groovebin <command>` heading in `docs/usage.md` whose
section names each of its long flags; links to the repo's own files, relative or as GitHub URLs, resolve
inside the repo and never into `.ai/`."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from groovebin.cli import build_parser

ROOT = Path(__file__).resolve().parents[1]
USAGE = ROOT / "docs" / "usage.md"
LINK = re.compile(r"\]\(([^)\s]+)\)")
REPO_BLOB = "https://github.com/phierceweb/groovebin/blob/main/"
HEADING = re.compile(r"(#+)\s+`?(.+?)`?\s*$")


def tracked_docs() -> list[Path]:
    root = [p for p in sorted(ROOT.glob("*.md")) if p.name != "CLAUDE.md"]
    return root + sorted((ROOT / "docs").glob("*.md"))


def long_flags(parser: argparse.ArgumentParser) -> list[str]:
    return [s for a in parser._actions for s in a.option_strings
            if s.startswith("--") and s != "--help"]


def section(text: str, command: str) -> str | None:
    """The text under the heading that names `command`, up to the next heading at its level."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        m = HEADING.fullmatch(line.strip())
        if m and m.group(2) == command:
            level, body = len(m.group(1)), []
            for rest in lines[i + 1:]:
                n = HEADING.fullmatch(rest.strip())
                if n and len(n.group(1)) <= level:
                    break
                body.append(rest)
            return "\n".join(body)
    return None


def undocumented(parser: argparse.ArgumentParser, text: str, command: str = "groovebin") -> list[str]:
    body = text if command == "groovebin" else section(text, command)
    if body is None:
        return [f"no heading for {command!r}"]
    missing = [f"{command} {flag}" for flag in long_flags(parser)
               if not re.search(rf"(?<![\w-]){re.escape(flag)}(?![\w-])", body)]
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for name, sub in action.choices.items():
                missing += undocumented(sub, text, f"{command} {name}")
    return missing


def broken_links(doc: Path, root: Path = ROOT) -> list[str]:
    out = []
    for target in LINK.findall(doc.read_text(encoding="utf-8")):
        if target.startswith(REPO_BLOB):
            path = (root / target.removeprefix(REPO_BLOB).split("#", 1)[0]).resolve()
        elif target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        else:
            path = (doc.parent / target.split("#", 1)[0]).resolve()
        if path.is_relative_to(root.resolve() / ".ai"):
            out.append(f"{doc.name}: {target} links into .ai/, which does not ship")
        elif not path.is_relative_to(root.resolve()):
            out.append(f"{doc.name}: {target} resolves outside the repository")
        elif not path.exists():
            out.append(f"{doc.name}: {target} does not exist")
    return out


def test_usage_names_every_command_and_flag():
    assert undocumented(build_parser(), USAGE.read_text(encoding="utf-8")) == []


def abbreviation_hits(root: Path = ROOT) -> list[str]:
    """Lines in shipped text that shorten Addictive Drums 2 to its three-character form."""
    short = re.compile(r"\b" + "A" + "D2" + r"\b")
    paths = [*root.glob("*.md"), *(root / "docs").glob("*.md"), *(root / "src").rglob("*.py"),
             *(root / "src").rglob("*.json"), *(root / "tests").rglob("*.py")]
    return [f"{p.relative_to(root)}:{i}" for p in sorted(paths) if p.name != "CLAUDE.md"
            for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1) if short.search(line)]


def test_nothing_shipped_shortens_the_plugins_name():
    assert abbreviation_hits() == []


def test_the_abbreviation_check_finds_one(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "x.py").write_text("MAP = 'A" + "D2'\n")
    assert abbreviation_hits(tmp_path) == ["src/x.py:1"]


def test_tracked_docs_link_only_to_files_that_ship():
    assert [b for doc in tracked_docs() for b in broken_links(doc)] == []


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="groovebin")
    ap.add_argument("--version", action="store_true")
    sub = ap.add_subparsers(dest="command")
    remap = sub.add_parser("remap")
    remap.add_argument("--from", dest="src")
    remap.add_argument("--to", dest="dst")
    sub.add_parser("notes").add_argument("--map")
    return ap


DOCUMENTED = """`--version` prints it.

## groovebin remap

`--from` and `--to` name maps.

## groovebin notes

`--map` names strokes.
"""


def test_a_documented_parser_passes():
    assert undocumented(_parser(), DOCUMENTED) == []


def test_a_command_without_a_heading_is_caught():
    text = DOCUMENTED.replace("## groovebin notes", "## notes")
    assert undocumented(_parser(), text) == ["no heading for 'groovebin notes'"]


def test_a_flag_documented_only_under_another_command_is_caught():
    text = """`--version` prints it.

## groovebin remap

`--from` names a map.

## groovebin notes

`--map` names strokes; `--to` is not this command's flag.
"""
    assert undocumented(_parser(), text) == ["groovebin remap --to"]


def test_a_longer_flag_does_not_document_its_prefix():
    text = DOCUMENTED.replace("`--from` and `--to` name maps.", "`--from` and `--tolerance`.")
    assert undocumented(_parser(), text) == ["groovebin remap --to"]


def test_a_top_level_flag_is_caught():
    assert undocumented(_parser(), DOCUMENTED.replace("`--version` prints it.", "")) == [
        "groovebin --version"]


def test_links_are_checked(tmp_path):
    root = tmp_path / "repo"
    (root / ".ai" / "plans").mkdir(parents=True)
    (root / ".ai" / "plans" / "PLAN.md").write_text("")
    (root / "docs").mkdir()
    (root / "docs" / "usage.md").write_text("")
    (tmp_path / "outside.md").write_text("")
    doc = root / "README.md"
    doc.write_text("[a](docs/usage.md) [b](docs/gone.md) [c](.ai/plans/PLAN.md) "
                   "[d](https://example.com) [e](#top) [f](../outside.md) "
                   f"[g]({REPO_BLOB}docs/usage.md#install) [h]({REPO_BLOB}docs/gone.md)")
    assert broken_links(doc, root) == [
        "README.md: docs/gone.md does not exist",
        "README.md: .ai/plans/PLAN.md links into .ai/, which does not ship",
        "README.md: ../outside.md resolves outside the repository",
        f"README.md: {REPO_BLOB}docs/gone.md does not exist",
    ]
