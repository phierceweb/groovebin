"""Reading a transform off a command line: conditions into Ranges, operations into Operations, and
the values each refuses."""

import pytest

from groovebin.transforms import Operation, Range, parse_operation, parse_select, ticks_of


def test_parse_select_reads_every_comparator_and_the_units():
    got = parse_select("pitch=36-47,velocity<40,position>=9,length=1/16-1/8,channel!=10", ppq=960)
    assert got == {"pitch": Range(36, 47), "velocity": Range(None, 40, hi_open=True), "tick": Range(9, None),
                   "length": Range(240, 480), "channel": Range(10, 10, outside=True)}
    assert parse_select("velocity<=40", ppq=960) == {"velocity": Range(None, 40)}
    assert parse_select("velocity>40", ppq=960) == {"velocity": Range(40, None, lo_open=True)}
    assert parse_select("velocity=64", ppq=960) == {"velocity": Range(64, 64)}
    assert parse_select("length=120t", ppq=960) == {"length": Range(120, 120)}


@pytest.mark.parametrize(("text", "message"), [
    ("pitch", "bad condition 'pitch'"), ("size=3", "no note field 'size'"), ("pitch=47-36", "runs backwards"),
    ("pitch=x", "'x' is not a number"), ("pitch=1,pitch=2", "pitch is given twice"), ("length=1/12", "not a grid"),
])
def test_bad_conditions_are_named(text, message):
    with pytest.raises(ValueError, match=message):
        parse_select(text, ppq=960)


def test_ticks_of_reads_ticks_and_note_values():
    assert (ticks_of("240", 960), ticks_of("240t", 960), ticks_of("1/16", 960), ticks_of("-10", 960)) == (240, 240, 240, -10)
    with pytest.raises(ValueError, match="not a tick count or a note value"):
        ticks_of("fast", 960)


def test_parse_operation_reads_each_shape():
    assert parse_operation("set", "velocity=64", ppq=960) == Operation("velocity", "set", 64)
    assert parse_operation("add", "velocity=-10", ppq=960) == Operation("velocity", "add", -10)
    assert parse_operation("mul", "length=0.5", ppq=960) == Operation("length", "mul", 0.5)
    assert parse_operation("random", "position=30t", ppq=960) == Operation("tick", "random", 30)
    assert parse_operation("quantize", "position=1/16", ppq=960) == Operation("tick", "quantize", 240)
    assert parse_operation("crescendo", "velocity=40..120", ppq=960) == Operation("velocity", "crescendo", (40, 120))
    assert parse_operation("reverse", "pitch", ppq=960) == Operation("pitch", "reverse")
    assert parse_operation("flip", "pitch=60", ppq=960) == Operation("pitch", "flip", 60)


@pytest.mark.parametrize(("op", "spec", "message"), [
    ("grow", "velocity=1", "no operation 'grow'"), ("set", "size=1", "no note field"), ("reverse", "pitch=60", "no value"),
    ("set", "velocity", "takes FIELD=VALUE"), ("crescendo", "velocity=40", "LO..HI"), ("random", "velocity=-1", "0 or more"),
    ("quantize", "position=0", "1 tick or more"), ("mul", "velocity=inf", "not a number"),
])
def test_bad_operations_are_named(op, spec, message):
    with pytest.raises(ValueError, match=message):
        parse_operation(op, spec, ppq=960)


@pytest.mark.parametrize(("op", "spec"), [("add", "position=" + "9" * 310), ("set", "length=" + "9" * 310),
                                          ("crescendo", "length=1.." + "9" * 310)])
def test_a_tick_past_what_a_file_can_hold_is_refused_where_it_is_read(op, spec):
    with pytest.raises(ValueError, match="is past"):
        parse_operation(op, spec, ppq=960)


def test_the_tick_limit_is_put_only_on_a_value_a_file_has_to_hold():
    """A `--select` bound is compared, never written; a 7-bit field holds to its own range instead;
    a grid denominator is not a tick count."""
    assert parse_select("length>" + "9" * 310, ppq=960)["length"].lo == int("9" * 310)
    assert parse_operation("set", "velocity=" + "9" * 310, ppq=960).value == int("9" * 310)
    with pytest.raises(ValueError, match="is not a grid of 1/1 to 1/64"):
        parse_operation("add", "position=1/300000000", ppq=960)
