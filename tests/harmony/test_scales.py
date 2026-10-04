"""Scales and keys, and the scale a line holds."""

import pytest

from groovebin.events import Note
from groovebin.harmony import Scale, from_signature, parse_key, scale_name, scale_of, signature_name


def held(pitches, length=480):
    return [Note(i * length, length, 1, p, 90) for i, p in enumerate(pitches)]


def test_the_scale_a_line_holds_is_named_by_its_major():
    assert scale_of(held([48, 50, 52, 53, 55, 57, 59, 60])) == 0
    assert scale_of(held([45, 48, 50, 52, 55, 57, 45, 45])) == 0
    assert scale_of(held([43, 47, 50, 54, 55, 57, 43])) == 7


def test_a_line_of_one_pitch_class_has_no_scale():
    assert scale_of(held([45, 57, 45])) is None
    assert scale_of([]) is None


def test_scale_names():
    assert scale_name(0) == "C major / A minor" and scale_name(7) == "G major / E minor" and scale_name(10) == "Bb major / G minor"
    assert [scale_name(t) for t in (1, 4, 6, 11)] == ["Db major / Bb minor", "E major / C# minor", "F# major / D# minor",
                                                     "B major / G# minor"]


def test_a_line_holding_every_pitch_class_as_long_has_no_scale():
    assert scale_of(held(range(40, 52))) is None


def test_a_key_reads_with_its_tonic_as_written():
    assert parse_key("A minor") == Scale(9, "minor") and parse_key("A minor").spelling == "A"
    assert parse_key("f# Dorian") == Scale(6, "dorian")
    assert parse_key("Bb") == Scale(10) and str(parse_key("Bb")) == "Bb major"
    assert (parse_key("C ionian"), parse_key("A aeolian")) == (Scale(0), Scale(9, "minor"))


@pytest.mark.parametrize(("text", "message"), [
    ("", "is not a key"), ("A minor scale", "is not a key"), ("H", "is not a note name"),
    ("A klingon", "no scale 'klingon'"),
])
def test_what_is_not_a_key_is_refused(text, message):
    with pytest.raises(ValueError, match=message):
        parse_key(text)


def test_steps_count_along_the_scale_and_at_reads_them_back():
    c = Scale(0)
    assert (c.below(60), c.below(61), c.below(59)) == ((35, 0), (35, 1), (34, 0))
    assert all(c.at(c.below(p)[0]) + c.below(p)[1] == p for p in range(128))
    assert sorted(Scale(9, "blues").pitch_classes) == [0, 2, 3, 4, 7, 9]


def test_a_major_or_minor_key_gives_its_signature_as_spelled():
    assert (parse_key("Gb").signature(), parse_key("F#").signature()) == ((-6, False), (6, False))
    assert parse_key("C minor").signature() == (-3, True)
    assert (Scale(8, "minor").signature(), str(Scale(8, "minor"))) == ((5, True), "G# minor")
    assert Scale(6).signature() == (6, False)
    with pytest.raises(ValueError, match="D# major has no key signature: spell it Eb major"):
        parse_key("D#").signature()
    with pytest.raises(ValueError, match="D dorian has no key signature"):
        parse_key("D dorian").signature()


def test_a_signature_names_its_key():
    assert (signature_name(-6, False), signature_name(3, True), signature_name(0, False)) == \
        ("Gb major", "F# minor", "C major")
    assert from_signature(-1, True) == Scale(2, "minor") and from_signature(-1, True).spelling == "D"
    with pytest.raises(ValueError, match="a key signature of 8 sharps is not -7 to 7"):
        from_signature(8, False)
