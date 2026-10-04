"""Key signatures as a map over a part's ticks."""

import pytest

from groovebin.timing import KeyMap

KEYS = KeyMap(((0, -3, True), (3840, 2, False)))


def test_a_key_map_gives_the_signature_in_force_and_none_before_the_first():
    assert (KEYS.at(0), KEYS.at(3839), KEYS.at(3840)) == ((-3, True), (-3, True), (2, False))
    assert KeyMap(((960, 1, False),)).at(0) is None
    assert KeyMap(()).defaulted and not KEYS.defaulted


def test_the_tonic_is_counted_round_the_circle_of_fifths():
    assert (KEYS.tonic(0), KEYS.tonic(3840)) == (0, 2)
    assert [KeyMap(((0, s, False),)).tonic(0) for s in (-6, -1, 0, 1, 6, 7)] == [6, 5, 0, 7, 6, 1]
    assert KeyMap(((0, 0, True),)).tonic(0) == 9
    assert KeyMap(()).tonic(0) is None


def test_with_point_replaces_a_signature_on_its_tick():
    assert KEYS.with_point(3840, 0, True).points == ((0, -3, True), (3840, 0, True))
    assert KEYS.with_point(1920, 1, False).points == ((0, -3, True), (1920, 1, False), (3840, 2, False))


@pytest.mark.parametrize(("make", "message"), [
    (lambda: KeyMap(((0, 8, False),)), "a key signature of 8 sharps is not -7 to 7"),
    (lambda: KeyMap(((960, 0, False), (0, 0, False))), "key signatures are not in tick order: 0 after 960"),
    (lambda: KEYS.with_point(-1, 0, False), "a key signature at tick -1 is before bar 1"),
])
def test_what_a_file_cannot_hold_is_refused(make, message):
    with pytest.raises(ValueError, match=message):
        make()
