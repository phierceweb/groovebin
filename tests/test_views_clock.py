from groovebin._views import clock


def test_a_clock_reads_minutes_seconds_and_milliseconds():
    assert [clock(s) for s in (0.0, 1.875, 125.25, -0.25)] == ["0:00.000", "0:01.875", "2:05.250", "-0:00.250"]
