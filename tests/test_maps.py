"""The packaged note maps: sources, rows, strokes and term lookup."""

import json
import re
from importlib.resources import files

import pytest

from groovebin.maps import NAMES, drum_map, maps, stroke

PIECE_OF_WORD = {"kick": "Kick", "snare": "Snare", "sidestick": "Snare", "hihat": "HiHat", "ride": "Ride",
                 "tom": "Tom", "cymbal": "Cymbal", "flexi": "Flexi", "choke": ("Cymbal", "Ride"), "sticks": "Snare"}
PLAYED = [36, 38, 42, 48, 49, 51, 60, 61, 62, *range(65, 73), *range(77, 82)]


def raw(name):
    return json.loads(files("groovebin").joinpath(f"data/maps/{name}.json").read_text())


def test_the_maps_come_in_a_fixed_order():
    assert NAMES == ("gm", "addictive-drums-2", "drum-kit-designer")
    assert list(maps()) == list(NAMES)


def test_each_map_names_its_source_and_says_the_terms_are_its_own():
    for name, m in maps().items():
        assert m.source
        assert "this table's choices" in raw(name)["note"]


def test_gm_calls_its_cymbal_slot_pairing_its_own_choice():
    note = raw("gm")["note"]
    assert "this table's choice" in next(s for s in re.split(r"(?<=\.) ", note) if "splash" in s)


def test_every_choke_term_is_choke_before_its_pieces_hit():
    ad2 = drum_map("addictive-drums-2")
    hits = {r["piece"]: r["term"] for r in ad2.notes.values() if r["stroke"] in ("Hit", "Tip")}
    chokes = {n: r for n, r in ad2.notes.items() if r["stroke"] == "Choke"}
    assert len(chokes) == 8
    assert all(row["term"] == "choke " + hits[row["piece"]] for row in chokes.values())
    assert ad2.term(75) == "sticks"


def test_note_ranges():
    assert sorted(drum_map("gm").notes) == list(range(35, 82))
    assert len(drum_map("addictive-drums-2").notes) == 80
    assert all(0 <= n <= 127 for m in maps().values() for n in m.notes)


def test_terms_are_lowercase_words_and_addictive_drums_2_terms_name_their_piece():
    for m in maps().values():
        assert all(re.fullmatch(r"[a-z0-9]+( [a-z0-9]+)*", t) for t in m.terms()), m.name
    for n, row in drum_map("addictive-drums-2").notes.items():
        if "term" in row:
            assert row["piece"].startswith(PIECE_OF_WORD[row["term"].split()[0]]), n


def test_every_prefer_names_a_note_whose_term_is_or_extends_the_key():
    for m in maps().values():
        for term, note in m.prefer.items():
            own = m.notes[note]["term"]
            assert own == term or own.startswith(term + " "), (m.name, term)


def test_every_duplicate_points_at_a_note_with_a_term_and_carries_none_itself():
    ad2 = drum_map("addictive-drums-2")
    dups = {n: r for n, r in ad2.notes.items() if "duplicate_of" in r}
    assert sorted(dups) == [39, 40, 45, 46]
    for n, row in dups.items():
        original = ad2.notes[row["duplicate_of"]]
        assert (original["piece"], original["stroke"] + " (dbl)") == (row["piece"], row["stroke"])
        assert ad2.term(n) == original["term"]
    for m in maps().values():
        for n, row in m.notes.items():
            if "duplicate_of" in row:
                assert "term" not in row and "term" in m.notes[row["duplicate_of"]], (m.name, n)


def test_brushes_only_and_cc_position_notes_have_no_term():
    ad2 = drum_map("addictive-drums-2")
    assert all(ad2.term(n) is None for n in [3, 4, 5, 6, 7, 8, 9, 26, *range(28, 36)])
    assert ad2.notes[5]["stroke"] == "CCpos [only brush] (Closed<>Shallow)"


def test_rows_cannot_be_changed():
    with pytest.raises(TypeError):
        drum_map("gm").notes[36]["term"] = "snare"


def test_strokes():
    assert all(stroke("addictive-drums-2", n) for n in PLAYED)
    assert stroke("addictive-drums-2", 36) == "Kick"
    assert stroke("addictive-drums-2", 49) == "HiHat Closed 1 Tip"
    assert stroke("addictive-drums-2", 71) == "Tom 1 Open Hit"
    assert stroke("addictive-drums-2", 26) == "Snare Sweep: Short 1 (brushes only)"
    assert stroke("gm", 42) == "Closed Hi Hat"
    assert stroke("drum-kit-designer", 34) == "Snare Edge"
    assert stroke("addictive-drums-2", 64) is None
    assert stroke("gm", 34) is None


def test_an_unknown_map_is_refused_with_the_names():
    with pytest.raises(ValueError, match="no note map 'sd3'; one of gm, addictive-drums-2, drum-kit-designer"):
        stroke("sd3", 36)


def test_gm_rows():
    gm = drum_map("gm")
    assert "MMA0007 / RP003" in gm.source and "Table 3" in gm.source
    rows = {35: ("Acoustic Bass Drum", "kick"), 37: ("Side Stick", "sidestick"), 38: ("Acoustic Snare", "snare"),
            42: ("Closed Hi Hat", "hihat closed"), 44: ("Pedal Hi-Hat", "hihat pedal"), 46: ("Open Hi-Hat", "hihat open"),
            41: ("Low Floor Tom", "tom 4"), 45: ("Low Tom", "tom 3"), 48: ("Hi Mid Tom", "tom 2"),
            50: ("High Tom", "tom 1"), 49: ("Crash Cymbal 1", "cymbal 1"), 51: ("Ride Cymbal 1", "ride")}
    assert {n: (gm.notes[n]["name"], gm.term(n)) for n in rows} == rows


def test_drum_kit_designer_rows_follow_apples_gm_standard_keymap():
    dkd = drum_map("drum-kit-designer")
    assert sorted(dkd.notes) == [28, 29, *range(31, 55), 56, 57, 59, 70]
    assert (dkd.term(35), dkd.term(33), dkd.term(28), dkd.term(70)) == ("kick", "hihat pedal", "choke cymbal 1", "maracas shaker")


def test_find_prefers_an_exact_term_then_the_prefer_then_the_lowest():
    gm, ad2 = drum_map("gm"), drum_map("addictive-drums-2")
    assert (gm.find("kick"), gm.find("cymbal"), gm.find("tom 2"), gm.find("tom 5")) == (36, 49, 48, None)
    assert (ad2.find("hihat open"), ad2.find("sidestick")) == (55, 42)


def test_a_family_is_every_note_whose_term_starts_with_the_word():
    ad2 = drum_map("addictive-drums-2")
    assert ad2.family("kick") == (36,)
    assert ad2.family("snare") == (37, 38, 39, 40, 41, 43)
    assert drum_map("gm").family("snare") == (38, 40)
