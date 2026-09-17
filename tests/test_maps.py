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


def test_collisions_name_the_pitches_that_fold_together():
    from groovebin.events import Note
    from groovebin.maps import collisions, translate
    from groovebin.song import Part
    toms = [p for p in (41, 43, 45, 47, 48, 50) if translate(p, "gm", "drum-kit-designer") is not None]
    part = Part(96, tuple(Note(k * 10, 5, 10, p, 100) for k, p in enumerate(toms)))
    folded = collisions(part, "gm", "drum-kit-designer")
    assert folded, "the General MIDI toms fold onto fewer Drum Kit Designer notes"
    for target, sources in folded.items():
        assert len(sources) > 1
        assert all(translate(p, "gm", "drum-kit-designer") == target for p in sources)
    assert collisions(Part(96, (Note(0, 5, 10, 36, 100),)), "gm", "drum-kit-designer") == {}


def test_collisions_name_a_kept_pitch_that_a_mapped_one_lands_on():
    """`--unmapped keep` leaves a pitch with no counterpart at its own value, where a mapped pitch
    can land on it. Dropped, it cannot."""
    from groovebin.events import Note
    from groovebin.maps import collisions, translate
    from groovebin.song import Part
    kept = next(p for p in range(128) if translate(p, "gm", "addictive-drums-2") is None
                and any(translate(q, "gm", "addictive-drums-2") == p for q in range(128)))
    onto = next(q for q in range(128) if translate(q, "gm", "addictive-drums-2") == kept)
    part = Part(96, (Note(0, 5, 10, onto, 100), Note(10, 5, 10, kept, 100)))
    assert collisions(part, "gm", "addictive-drums-2") == {kept: sorted({kept, onto})}
    assert collisions(part, "gm", "addictive-drums-2", unmapped="drop") == {}


def test_collisions_see_a_polytouch_key_the_remap_would_translate():
    from groovebin.events import Event, Note
    from groovebin.maps import collisions, translate
    from groovebin.song import Part
    a, b = 35, 36
    target = translate(a, "gm", "addictive-drums-2")
    assert target == translate(b, "gm", "addictive-drums-2")
    part = Part(96, (Note(0, 5, 10, a, 100),), (Event(0, bytes([0xA9, b, 64])),))
    assert collisions(part, "gm", "addictive-drums-2") == {target: [a, b]}
    assert collisions(part, "gm", "addictive-drums-2", channels=[1]) == {}


def test_collisions_refuse_an_unmapped_rule_that_is_not_one():
    import pytest
    from groovebin.maps import collisions
    from groovebin.song import Part
    with pytest.raises(ValueError, match="kept or dropped"):
        collisions(Part(96), "gm", "addictive-drums-2", unmapped="delete")


def test_collisions_do_not_fold_pitches_that_meet_only_across_channels():
    """One pitch on two channels is two voices; they do not collide. Only pitches that land together
    on one channel fold."""
    from groovebin.events import Note
    from groovebin.maps import collisions
    from groovebin.song import Part
    apart = Part(96, (Note(0, 5, 1, 51, 100), Note(10, 5, 2, 60, 100)))
    assert collisions(apart, "gm", "addictive-drums-2", channels=[1, 2]) == {}
    assert collisions(apart, "gm", "addictive-drums-2") == {}
    together = Part(96, (Note(0, 5, 1, 51, 100), Note(10, 5, 1, 60, 100)))
    assert collisions(together, "gm", "addictive-drums-2") == {60: [51, 60]}


def test_landings_key_on_channel_so_a_caller_can_merge_tracks():
    from groovebin.events import Note
    from groovebin.maps import folds, landings
    from groovebin.song import Part
    one = Part(96, (Note(0, 5, 10, 51, 100),))
    two = Part(96, (Note(0, 5, 10, 60, 100),))
    merged: dict[tuple[int, int], set[int]] = {}
    for part in (one, two):
        for key, sources in landings(part, "gm", "addictive-drums-2").items():
            merged.setdefault(key, set()).update(sources)
    assert folds(merged) == {60: [51, 60]}
    assert folds(landings(one, "gm", "addictive-drums-2")) == {}     # neither track folds alone
