"""What a bassline by rules never does, over generated charts with rests in three meters: the rules' promises as
checks that run on every case, not on the few a test names."""

import random

import pytest

from groovebin.harmony import chart, chart_spans
from groovebin.library.bass_rules import APPROACH_RATE, bass_line
from groovebin.timing import MeterMap

PPQ, WINDOW = 960, 120
NAMES = ("Am", "F", "C", "G", "E5", "D5", "C/G", "A5", "-", "-", "N.C.")
CASES = range(400)


def case(number, names=NAMES):
    """A chart of one to four bars, its spans, and humanised kicks and snares, in 4/4, 3/4 or 6/8."""
    rng = random.Random(number)
    num, den = rng.choice(((4, 4), (4, 4), (3, 4), (6, 8)))
    meters, bar = MeterMap(PPQ, ((0, num, den),)), PPQ * 4 * num // den
    bars = rng.randint(1, 4)
    text = "| " + " | ".join(" ".join(rng.choice(names) for _ in range(rng.choice((1, 1, 2, 2, 4, 8, 16))))
                             for _ in range(bars)) + " |"
    spans = chart_spans(chart(text, rests=True), meters, bars)
    grid = rng.choice((480, 240))
    kicks, snares = ([(max(t + rng.randint(-40, 40), 0), rng.randint(60, 120)) for t in range(0, bars * bar, grid)
                      if rng.random() < share] for share in (0.45, 0.3))
    return rng, spans, kicks, snares


def line(spans, kicks, snares, seed, *, on=False, **options):
    return bass_line(kicks, [t for t, _v in snares], spans, PPQ, seed=seed, snare_hits=snares if on else None, **options)


def span_at(spans, tick):
    return next((s for s in spans if s.start <= tick < s.end), None)


def run_start(spans, tick):
    """Where the unbroken stretch of chords holding ``tick`` begins."""
    start, last = None, None
    for s in spans:
        if s.start != last:
            start = s.start
        last = s.end
        if s.start <= tick < s.end:
            return start
    return None


def after_rests(spans):
    return [s for before, s in zip([None, *spans], spans, strict=False) if (before.end if before else 0) != s.start]


def rested(spans):
    return bool(after_rests(spans))


@pytest.mark.parametrize("number", CASES)
def test_no_note_starts_or_rings_in_a_rest(number):
    rng, spans, kicks, snares = case(number)
    if not spans:
        return
    got = line(spans, kicks, snares, number, on=rng.random() < 0.5, root_only=rng.random() < 0.5, push=rng.random() < 0.5)
    for n in got.notes:
        inside = span_at(spans, n.tick)
        assert inside is not None and n.tick >= 0 and n.length >= 1, (number, n)
        end = inside.end
        for s in spans:
            end = s.end if s.start == end else end
        assert n.tick + n.length <= end, (number, n)


@pytest.mark.parametrize("number", CASES)
def test_with_roots_only_every_note_is_its_chords_bass_note(number):
    rng, spans, kicks, snares = case(number)
    if not spans:
        return
    got = line(spans, kicks, snares, number, on=rng.random() < 0.5, root_only=True)
    assert all(n.pitch % 12 == span_at(spans, n.tick).chord.lowest for n in got.notes), number


@pytest.mark.parametrize("number", CASES)
def test_the_first_note_after_a_rest_is_its_chords_bass_note_on_a_stroke(number):
    rng, spans, kicks, snares = case(number)
    if not spans:
        return
    on = rng.random() < 0.5
    got = line(spans, kicks, snares, number, on=on, root_only=rng.random() < 0.5, push=rng.random() < 0.5)
    played = [*kicks, *(snares if on else [])]
    for s in after_rests(spans):
        first = min((n for n in got.notes if n.tick >= s.start and run_start(spans, n.tick) == s.start),
                    key=lambda n: n.tick, default=None)
        if first is None:
            continue
        here = span_at(spans, first.tick)
        if here.chord.lowest == s.chord.lowest and all(b.chord.lowest == s.chord.lowest for b in spans
                                                        if s.start <= b.start <= here.start):
            assert first.pitch % 12 == s.chord.lowest, (number, first)
            assert any(abs(first.tick - t) <= WINDOW for t, _v in played), (number, first)


@pytest.mark.parametrize("number", CASES)
def test_a_push_changes_pitches_and_drops_only_a_changes_own_note(number):
    rng, spans, kicks, snares = case(number)
    if not spans:
        return
    options = dict(on=rng.random() < 0.5, root_only=rng.random() < 0.5, approach=0)
    plain = line(spans, kicks, snares, number, **options).notes
    pushed = line(spans, kicks, snares, number, push=True, **options).notes
    assert {n.tick for n in pushed} <= {n.tick for n in plain}, number
    assert {n.tick for n in plain} - {n.tick for n in pushed} <= {s.start for s in spans}, number
    assert {(n.tick, n.velocity) for n in pushed} <= {(n.tick, n.velocity) for n in plain}, number


@pytest.mark.parametrize("number", CASES)
def test_a_pushed_note_plays_the_next_change_of_its_own_stretch_of_chords(number):
    rng, spans, kicks, snares = case(number)
    if not spans:
        return
    got = line(spans, kicks, snares, number, on=rng.random() < 0.5, root_only=True, push=True)
    for n in got.notes:
        own = span_at(spans, n.tick)
        if n.pitch % 12 != own.chord.lowest:
            change = next(s for s in spans if s.start > n.tick and s.chord.lowest != own.chord.lowest)
            assert change.chord.lowest == n.pitch % 12, (number, n)
            assert run_start(spans, change.start) == run_start(spans, n.tick), (number, n)
            assert change.start - n.tick <= PPQ // 2 + WINDOW, (number, n)


@pytest.mark.parametrize("number", CASES)
def test_approach_notes_never_meet_a_push_or_a_rest(number):
    rng, spans, kicks, snares = case(number)
    if not spans:
        return
    options = dict(push=rng.random() < 0.4, root_only=rng.random() < 0.4)
    if options["push"] or options["root_only"] or rested(spans):
        assert line(spans, kicks, snares, number, **options).approaches == 0, number
        with pytest.raises(ValueError, match="approach notes are not written"):
            line(spans, kicks, snares, number, approach=rng.choice((0.588, 1)), **options)
    else:
        assert line(spans, kicks, snares, number).notes == line(spans, kicks, snares, number, approach=APPROACH_RATE).notes
