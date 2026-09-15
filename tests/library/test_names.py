from pathlib import PurePosixPath

import pytest

from groovebin.library.names import describe


def d(path):
    return describe(PurePosixPath(path))


def test_a_name_in_the_export_pattern_gives_group_variant_category_and_fill_flag():
    info = d("Pack/Rock/Big Beat/Big Beat_V_Verse 02_C_Hard Rock_F_.mid")
    assert (info.group, info.variant, info.category, info.is_fill, info.role) == \
           ("Big Beat", "Verse 02", "Hard Rock", True, "verse")


def test_a_plain_name_uses_its_folders():
    info = d("Rock/Grooves/Chorus/groove 03.mid")
    assert (info.group, info.variant, info.category, info.is_fill, info.role) == \
           ("Chorus", "groove 03", "Rock", False, "chorus")


def test_a_file_at_the_root_has_no_group_or_category():
    info = d("loop.mid")
    assert (info.group, info.variant, info.category, info.role) == (None, "loop", None, None)


@pytest.mark.parametrize(("path", "role"), [
    ("A/Song_V_Pre Chorus 1_C_Pop.mid", "pre-chorus"),
    ("A/Song_V_Pre-Chorus_C_Pop.mid", "pre-chorus"),
    ("A/Song_V_prechorus_C_Pop.mid", "pre-chorus"),
    ("A/Song_V_Chorus 2_C_Pop.mid", "chorus"),
    ("A/Song_V_Intro_C_Pop.mid", "intro"),
    ("A/Song_V_Bridge 4_C_Pop.mid", "bridge"),
    ("A/Song_V_Ending_C_Pop.mid", "outro"),
    ("A/Song_V_Outro_C_Pop.mid", "outro"),
    ("A/Song_V_Verse to Chorus Fill_C_Pop_F_.mid", "verse"),
    ("A/Verse/Song_V_Hats Closed 02_C_Pop.mid", "verse"),
    ("A/Bridge/Section/Song_V_Beat 01_C_Pop.mid", "bridge"),
    ("A/Grooves/Song_V_Ride 02_C_Pop.mid", None),
    ("A/Song_V_Choruses_C_Pop.mid", None),
    ("Rock/Verse_01.mid", "verse"),
    ("Rock/Chorus1.mid", "chorus"),
    ("Rock/2Intro.mid", "intro"),
    ("Rock/Pre_Chorus A.mid", "pre-chorus"),
    ("Funk_120bpm_Verse.mid", "verse"),
    ("Rock/Choruses_2.mid", None),
    ("Rock/Universe_1.mid", None),
    ("Rock/Bending2.mid", None),
])
def test_the_role_is_the_earliest_section_word_nearest_the_file(path, role):
    assert d(path).role == role


@pytest.mark.parametrize(("path", "is_fill"), [
    ("A/Song_V_Crash 01_C_Pop_F_.mid", True),
    ("A/Song_V_Fills 03_C_Pop.mid", True),
    ("A/Fill/Song_V_Tom Run_C_Pop.mid", True),
    ("A/Song_V_Verse 01_C_Pop.mid", False),
    ("A/Fills/Deeper/Song_V_Verse 01_C_Pop.mid", False),
    ("A/Song_V_Refill_C_Pop.mid", False),
    ("Rock/Fill_01.mid", True),
    ("Rock/Fills03.mid", True),
    ("Rock/2Fill.mid", True),
    ("Rock/Refill_01.mid", False),
    ("Rock/Filler2.mid", False),
])
def test_a_fill_is_the_flag_or_a_fill_word_in_the_variant_or_its_folder(path, is_fill):
    assert d(path).is_fill is is_fill


@pytest.mark.parametrize(("path", "tempo", "meter"), [
    ("Pack/Swing 6:8/Slow 92bpm/Verse/Song_V_Verse 01_C_Blues.mid", 92.0, (6, 8)),
    ("Pack/Song 02 6-8 066/Song_V_Verse 1_C_Soft.mid", None, (6, 8)),
    ("Pack/Straight 4:4 at 120.5 BPM/a.mid", 120.5, (4, 4)),
    ("Pack/Fills 1-3/a.mid", None, None),
    ("Pack/Verse/Verse 1-2.mid", None, None),
    ("Pack/Hats 1-8/a.mid", None, None),
    ("Pack/Groove 4-1/a.mid", None, None),
    ("Pack/Cut Time 2:2/a.mid", None, (2, 2)),
    ("Pack/Groove 07/a.mid", None, None),
    ("Funk_120bpm_Verse.mid", 120.0, None),
    ("Pack/Slow_92BPM2/a.mid", 92.0, None),
    ("Pack/Take2_96bpm/a.mid", 96.0, None),
    ("Pack/120bpms/a.mid", None, None),
])
def test_tempo_and_meter_hints_come_from_the_path(path, tempo, meter):
    info = d(path)
    assert (info.tempo_hint, info.meter_hint) == (tempo, meter)
