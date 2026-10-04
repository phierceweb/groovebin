import pytest

from groovebin.harmony import Chord, chart, note_number, parse_chord, pitch_class, pitch_name, revoice

CHORDS = {
    "C": Chord(0, "maj"), "Am": Chord(9, "min"), "F#m7": Chord(6, "min7"), "Bb7": Chord(10, "7"),
    "Ebmaj7": Chord(3, "maj7"), "Bm7b5": Chord(11, "m7b5"), "Gdim": Chord(7, "dim"), "Gdim7": Chord(7, "dim7"),
    "Caug": Chord(0, "aug"), "Dsus4": Chord(2, "sus4"), "Dsus2": Chord(2, "sus2"), "A6": Chord(9, "6"),
    "Am6": Chord(9, "min6"), "E5": Chord(4, "5"), "C/G": Chord(0, "maj", 7), "Am7/G": Chord(9, "min7", 7),
}


@pytest.mark.parametrize(("text", "chord"), CHORDS.items())
def test_symbols_read_and_write_back(text, chord):
    assert parse_chord(text) == chord
    assert str(chord) == text


@pytest.mark.parametrize(("text", "chord"), [("Amin", Chord(9, "min")), ("A-", Chord(9, "min")),
                                             ("Cmaj", Chord(0, "maj")), ("Db", Chord(1, "maj")),
                                             ("C#", Chord(1, "maj")), ("Gb/Bb", Chord(6, "maj", 10)),
                                             ("CM7", Chord(0, "maj7")), ("Cø", Chord(0, "m7b5")),
                                             ("C°", Chord(0, "dim")), ("C+", Chord(0, "aug")), (" am ", Chord(9, "min"))])
def test_other_spellings(text, chord):
    assert parse_chord(text) == chord


@pytest.mark.parametrize("bad", ["", "H", "Cx", "C/", "C/H", "Am/7", "C##"])
def test_a_symbol_that_is_not_a_chord_is_refused(bad):
    with pytest.raises(ValueError, match="not a chord symbol"):
        parse_chord(bad)


def test_tones_and_the_lowest_note():
    assert Chord(9, "min7").tones == (9, 0, 4, 7)
    assert Chord(0, "maj", 7).tones == (0, 4, 7)
    assert (Chord(0, "maj", 7).lowest, Chord(9, "min").lowest) == (7, 9)
    assert Chord(9, "min").third == 0 and Chord(0, "maj").third == 4 and Chord(2, "sus4").third is None
    assert Chord(9, "min").fifth == 4 and Chord(7, "dim").fifth == 1


def test_pitch_classes_and_names():
    assert [pitch_class(p) for p in ("C", "c#", "Db", "B", "Cb", "E#")] == [0, 1, 1, 11, 11, 5]
    assert [pitch_name(p) for p in (0, 1, 10, 40)] == ["C", "C#", "A#", "E"]
    assert str(Chord(10, "7")) == "Bb7" and str(Chord(1, "maj")) == "Db"


def test_a_chart_is_bars_of_evenly_split_chords():
    assert chart("| Am | F G | % | C |") == [(Chord(9, "min"),), (Chord(5, "maj"), Chord(7, "maj")),
                                          (Chord(5, "maj"), Chord(7, "maj")), (Chord(0, "maj"),)]


def test_a_chart_without_bar_lines_is_a_chord_a_bar():
    assert chart("Am F C G") == [(Chord(9, "min"),), (Chord(5, "maj"),), (Chord(0, "maj"),), (Chord(7, "maj"),)]


def test_a_chart_needs_a_chord_and_a_repeat_needs_a_bar_before_it():
    for bad, message in (("", "no chords"), ("| |", "an empty bar"), ("% Am", "nothing to repeat"),
                         ("| Am | X |", "not a chord symbol")):
        with pytest.raises(ValueError, match=message):
            chart(bad)


def test_the_seventh_is_a_sevenths_and_not_a_sixths():
    assert [Chord(0, q).seventh for q in ("7", "maj7", "min7", "m7b5", "dim7", "6", "maj")] == [10, 11, 10, 10, 9, None, None]



AM, F, C_OVER_G = Chord(9, "min"), Chord(5, "maj"), Chord(0, "maj", 7)


@pytest.mark.parametrize(("pitch", "source", "target", "expected"), [
    (45, AM, F, 41),
    (40, AM, F, 36),
    (48, AM, F, 45),
    (45, AM, C_OVER_G, 43),
    (41, Chord(7, "7"), Chord(0, "7"), 46),
    (41, Chord(7, "7"), Chord(0, "maj7"), 47),
    (47, AM, F, 43),
])
def test_revoice_moves_a_note_from_its_chord_to_another(pitch, source, target, expected):
    """The bass note goes to the new bass note, a third, fifth or seventh to the new chord's own, anything else
    moves with the root; the octave keeps the line's contour, moved the shorter way."""
    assert revoice(pitch, source, target) == expected


@pytest.mark.parametrize(("name", "number"), [("Cb1", 23), ("B#0", 24), ("Cb4", 59), ("B#3", 60), ("B1", 35),
                                              ("C1", 24), ("Bb0", 22), ("E1", 28)])
def test_a_note_name_across_the_octave_line_keeps_its_octave(name, number):
    assert note_number(name) == number
