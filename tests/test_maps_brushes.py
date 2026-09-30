"""Drum Kit Designer's brush snare kits: the GM Standard keys, plus brush keys that never become a strike."""

from groovebin.events import Note
from groovebin.maps import NAMES, NOT_STRIKES, drum_map, remap, translate
from groovebin.song import Part

BRUSHES = "drum-kit-designer-brushes"
BRUSH_KEYS = {17: "Sweep Stroke", 18: "Snare Sweep Accents Hit", 19: "Snare Sweep Accents", 21: "Snare 1/4 Note Circles",
              22: "Snare 1/2 Note Circles", 23: "Snare Sweeps 16th Note", 24: "Snare Sweeps 8th Note",
              25: "Snare Center Mute 2", 27: "Snare Center Mute 1", 30: "Snare Drag"}


def test_it_is_a_drum_map_beside_the_others():
    assert NAMES == ("gm", "addictive-drums-2", "drum-kit-designer", BRUSHES)
    assert "brush" in NOT_STRIKES


def test_every_gm_standard_key_plays_as_it_does_in_drum_kit_designer():
    standard, brushes = drum_map("drum-kit-designer"), drum_map(BRUSHES)
    for note in standard.notes:
        assert (brushes.stroke(note), brushes.term(note)) == (standard.stroke(note), standard.term(note)), note


def test_the_brush_keys_are_named_from_the_figure_and_lead_with_brush():
    m = drum_map(BRUSHES)
    assert {n: m.stroke(n) for n in BRUSH_KEYS} == BRUSH_KEYS
    assert all(m.term(n).split()[0] == "brush" for n in BRUSH_KEYS)


def test_a_brush_key_never_lands_on_a_strike():
    for note in BRUSH_KEYS:
        for dst in ("gm", "addictive-drums-2", "drum-kit-designer"):
            assert translate(note, BRUSHES, dst) is None, (note, dst)


def test_a_strike_translates_as_drum_kit_designers():
    for note in drum_map("drum-kit-designer").notes:
        assert translate(note, BRUSHES, "addictive-drums-2") == translate(note, "drum-kit-designer", "addictive-drums-2")


def test_a_brush_part_remapped_keeps_its_sweeps_and_its_hands():
    part = Part(960, (Note(0, 960, 2, 24, 80), Note(0, 120, 1, 36, 100), Note(480, 120, 3, 38, 90)))
    new, missing = remap(part, BRUSHES, "addictive-drums-2")
    assert missing == {24: 1}
    assert sorted((n.channel, n.pitch, n.length) for n in new.notes) == [(1, 36, 120), (2, 24, 960), (3, 38, 120)]
