import pytest

from groovebin.events import Event, Note
from groovebin.song import Part
from groovebin.timing import MeterMap
from groovebin.transforms import BY_NAME, PRESETS, WHOLE_PART, Operation, operations, parse_value, run


def note(at, pitch=60, velocity=80, length=240):
    return Note(at, length, 1, pitch, velocity)


FOUR_FOUR = MeterMap(960, ())
EIGHT = Part(960, [note(k * 240, 36 + k, 10 + k * 10, 100 + k) for k in range(8)], [Event(100, b"\xb0\x01\x40")])
ALL = frozenset(range(8))


def test_every_preset_has_a_name_a_kind_and_a_line():
    assert len({p.name for p in PRESETS}) == len(PRESETS) == 16
    assert all(p.takes in ("none", "int", "int?", "float", "ticks", "lo..hi", "percent", "swing", "humanize") and p.about for p in PRESETS)
    assert all(name in BY_NAME for name in WHOLE_PART)


def test_parse_value_reads_each_kind_and_its_default():
    assert parse_value(BY_NAME["fixed-velocity"], "90", ppq=960) == 90
    assert parse_value(BY_NAME["velocity-limit"], None, ppq=960) == (20, 110)
    assert parse_value(BY_NAME["velocity-limit"], "30..100", ppq=960) == (30, 100)
    assert parse_value(BY_NAME["exp-velocity"], "1.6", ppq=960) == 1.6
    assert parse_value(BY_NAME["fixed-length"], "1/8", ppq=960) == 480
    assert parse_value(BY_NAME["legato"], "110%", ppq=960) == 110.0
    assert parse_value(BY_NAME["swing"], "60%", ppq=960) == (0.6, 16)
    assert parse_value(BY_NAME["swing"], "58:1/8", ppq=960) == (0.58, 8)
    assert parse_value(BY_NAME["humanize"], None, ppq=960) == (10, 8, 5)
    assert parse_value(BY_NAME["humanize"], "vel=20,pos=1/32", ppq=960) == (120, 20, 5)
    assert parse_value(BY_NAME["half-speed"], None, ppq=960) is None
    assert parse_value(BY_NAME["reverse-pitch"], None, ppq=960) is None
    assert parse_value(BY_NAME["reverse-pitch"], "60", ppq=960) == 60


@pytest.mark.parametrize(("name", "text", "message"), [
    ("half-speed", "2", "takes no value"), ("fixed-velocity", None, "needs a value"), ("velocity-limit", "20", "LO..HI"),
    ("humanize", "speed=3", "humanize takes pos="), ("legato", "-5%", "0 or more"), ("swing", "60:1/12", "not a grid"),
    ("fixed-velocity", "loud", "not a whole number"),
])
def test_bad_values_are_named(name, text, message):
    with pytest.raises(ValueError, match=message):
        parse_value(BY_NAME[name], text, ppq=960)


def test_operations_expand_each_preset():
    assert operations("humanize", (10, 8, 0)) == [Operation("tick", "random", 10), Operation("velocity", "random", 8)]
    assert operations("fixed-velocity", 90) == [Operation("velocity", "set", 90)]
    assert operations("velocity-limit", (20, 110)) == [Operation("velocity", "min", 20), Operation("velocity", "max", 110)]
    assert operations("random-velocity", 20) == [Operation("velocity", "random", 20)]
    assert operations("crescendo", (40, 120)) == [Operation("velocity", "crescendo", (40, 120))]
    assert operations("reverse-position") == [Operation("tick", "reverse")]
    assert operations("reverse-pitch") == [Operation("pitch", "reverse")]
    assert operations("reverse-pitch", 60) == [Operation("pitch", "flip", 60)]
    assert operations("exp-velocity", 1.5) == [Operation("velocity", "exp", 1.5)]
    assert operations("fixed-length", 480) == [Operation("length", "set", 480)]
    assert operations("max-length", 480) == [Operation("length", "max", 480)]
    assert operations("min-length", 480) == [Operation("length", "min", 480)]
    for name in ("half-speed", "legato", "swing"):
        with pytest.raises(ValueError, match="not built from operations"):
            operations(name)
    with pytest.raises(ValueError, match="no preset 'loud'"):
        operations("loud")


def test_a_backwards_band_and_an_impossible_pivot_are_refused():
    for value in ((110, 20), (21, 20)):
        with pytest.raises(ValueError, match="runs backwards"):
            operations("velocity-limit", value)
    for pivot in (-1, 128, 200):
        with pytest.raises(ValueError, match="is not a note number 0-127"):
            operations("reverse-pitch", pivot)
    with pytest.raises(ValueError, match="runs backwards"):
        run(EIGHT, ALL, "velocity-limit", (110, 20))
    with pytest.raises(ValueError, match="not a note number"):
        run(EIGHT, ALL, "reverse-pitch", 200)
    assert velocities(run(EIGHT, ALL, "crescendo", (120, 40))) == [120, 109, 97, 86, 74, 63, 51, 40]


def velocities(p):
    return [n.velocity for n in p.notes]


def test_run_applies_each_preset_with_a_known_answer():
    assert velocities(run(EIGHT, ALL, "fixed-velocity", 90)) == [90] * 8
    assert velocities(run(EIGHT, ALL, "velocity-limit", (25, 65))) == [25, 25, 30, 40, 50, 60, 65, 65]
    assert velocities(run(EIGHT, None, "velocity-limit")) == [20, 20, 30, 40, 50, 60, 70, 80]
    assert velocities(run(EIGHT, ALL, "crescendo")) == [40, 51, 63, 74, 86, 97, 109, 120]
    assert [n.pitch for n in run(EIGHT, ALL, "reverse-pitch", 60).notes] == [84, 83, 82, 81, 80, 79, 78, 77]
    assert [n.pitch for n in run(EIGHT, ALL, "reverse-position").notes] == [43, 42, 41, 40, 39, 38, 37, 36]
    assert velocities(run(EIGHT, ALL, "exp-velocity", 1.0)) == velocities(EIGHT)
    assert [n.length for n in run(EIGHT, ALL, "fixed-length", 480).notes] == [480] * 8
    assert [n.length for n in run(EIGHT, ALL, "max-length", 103).notes] == [100, 101, 102, 103, 103, 103, 103, 103]
    assert [n.length for n in run(EIGHT, ALL, "min-length", 103).notes] == [103, 103, 103, 103, 104, 105, 106, 107]
    assert [n.length for n in run(EIGHT, ALL, "staccato").notes] == [50, 51, 51, 52, 52, 53, 53, 54]
    assert [n.length for n in run(EIGHT, ALL, "legato").notes] == [240] * 7 + [107]
    assert [n.length for n in run(EIGHT, frozenset({0}), "legato", 150.0).notes] == [360] + [101 + k for k in range(7)]
    assert run(EIGHT, ALL, "random-velocity", 5, seed=1) == run(EIGHT, ALL, "random-velocity", 5, seed=1) != EIGHT
    assert run(EIGHT, None, "humanize", seed=2) != EIGHT


def test_half_and_double_speed_take_the_whole_part_events_included():
    half = run(EIGHT, None, "half-speed")
    assert [(n.tick, n.length) for n in half.notes] == [(k * 480, 2 * (100 + k)) for k in range(8)]
    assert half.events[0].tick == 200
    assert run(half, None, "double-speed") == EIGHT
    with pytest.raises(ValueError, match="takes the whole part"):
        run(EIGHT, ALL, "half-speed")


def test_swing_delays_every_second_grid_line_by_the_amount():
    p = Part(960, [note(0), note(240), note(480), note(1200), note(3840 + 240), note(250)])
    out = run(p, None, "swing", (0.6, 16), meters=FOUR_FOUR)
    assert [n.tick for n in out.notes] == [0, 288, 288, 480, 1248, 3840 + 288]
    straight = run(p, None, "swing", (0.5, 16), meters=FOUR_FOUR)
    assert [n.tick for n in straight.notes] == [0, 240, 240, 480, 1200, 3840 + 240]
    with pytest.raises(ValueError, match="needs a meter map"):
        run(p, None, "swing", (0.6, 16))
    with pytest.raises(ValueError, match="not 0 to 1"):
        run(p, None, "swing", (1.5, 16), meters=FOUR_FOUR)


def test_swing_counts_lines_from_the_parts_place_on_the_meter_map():
    p = Part(960, [note(240)])
    assert run(p, None, "swing", (0.6, 16), meters=FOUR_FOUR, start=3840 * 2).notes[0].tick == 288
    assert run(p, None, "swing", (0.6, 16), meters=FOUR_FOUR, start=240).notes[0].tick == 240


def test_an_unknown_preset_is_refused():
    with pytest.raises(ValueError, match="no preset 'loud'"):
        run(EIGHT, None, "loud")


@pytest.mark.parametrize("name", ["velocity-limit", "crescendo"])
def test_a_velocity_band_outside_1_to_127_is_refused(name):
    with pytest.raises(ValueError, match=r"not inside 1\.\.127"):
        operations(name, (-5, 500))
    with pytest.raises(ValueError, match=r"not inside 1\.\.127"):
        parse_value(BY_NAME[name], "-5..500", ppq=960)


def test_a_preset_line_says_track_and_never_repeats_its_own_default():
    assert not any("whole part" in p.about for p in PRESETS)
    assert "pos=10t" not in BY_NAME["humanize"].about
