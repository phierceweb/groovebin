"""The command line's file handling: reading a MIDI file with its name on any refusal, telling a file from a
pattern id, and never writing over an input."""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

from pf_core.exceptions import InvalidInputError

from .midi import read
from .song import Song

T = TypeVar("T")


def read_song(path: str) -> Song:
    return named(path, read)


def is_file(text: str) -> bool:
    """Whether ``text`` names a file rather than a pattern id; one that looks like a path and is not there is
    refused."""
    path = Path(text)
    if path.is_file():
        return True
    if path.suffix.lower() in (".mid", ".midi") or os.sep in text:
        raise FileNotFoundError(f"no file at {text}")
    return False


def named(path: str, parse: Callable[[bytes], T]) -> T:
    """``parse`` of the file's bytes, a refusal naming the file."""
    try:
        return parse(Path(path).read_bytes())
    except ValueError as e:
        raise ValueError(f"{Path(path).name}: {e}") from e


def refuse_overwrite(out: str, *inputs: str, force: bool) -> None:
    """A command never writes over its input, and needs --force to replace any other file."""
    for source in inputs:
        try:
            same = os.path.exists(out) and os.path.samefile(out, source)
        except OSError:
            same = False
        if same or os.path.realpath(out) == os.path.realpath(source):
            raise InvalidInputError(f"-o {out} would overwrite the input {source}; write a new file instead")
    if not force and os.path.lexists(out):
        raise InvalidInputError(f"{out} already exists; pass --force to overwrite it")


def track_indices(song: Song, wanted: list[int] | None, name: str) -> list[int]:
    if wanted is None:
        return list(range(len(song.tracks)))
    for number in wanted:
        if not 1 <= number <= len(song.tracks):
            raise InvalidInputError(f"track {number} is not in {name}, which holds {len(song.tracks)} track(s)")
    return sorted({number - 1 for number in wanted})
