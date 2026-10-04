"""Pitch classes, chords and charts (`chords`), the chords a bassline implies (`roots`), and scales and keys
(`scales`). A pitch class is 0-11 from C."""

from .chords import (CHORD_NAMES, LETTERS, NOTE_NAMES, QUALITIES, SPELLINGS, SUFFIXES, Chord, chart, note_number,
                     parse_chord, pitch_class, pitch_name, revoice)
from .roots import SPLIT_SHARE, START_WEIGHT, THIRD_SHARE, Span, chart_spans, chart_text, root_notes, roots
from .scales import (KIND_ALIASES, MAJOR_KEYS, MAJOR_PROFILE, MINOR_KEYS, MINOR_PROFILE, MODES, SCALES, Scale,
                     from_signature, parse_key, scale_name, scale_of, signature_name)

__all__ = ["CHORD_NAMES", "LETTERS", "NOTE_NAMES", "QUALITIES", "SPELLINGS", "SUFFIXES", "Chord", "chart",
           "note_number", "parse_chord", "pitch_class", "pitch_name", "revoice",
           "SPLIT_SHARE", "START_WEIGHT", "THIRD_SHARE", "Span", "chart_spans", "chart_text", "root_notes", "roots",
           "MAJOR_PROFILE", "MINOR_PROFILE", "scale_name", "scale_of", "KIND_ALIASES", "MAJOR_KEYS", "MINOR_KEYS", "MODES",
           "SCALES", "Scale", "from_signature", "parse_key", "signature_name"]
