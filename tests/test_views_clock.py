from groovebin._views import clock


def test_a_clock_reads_minutes_seconds_and_milliseconds():
    assert [clock(ms) for ms in (0, 1875, 125250, -250)] == ["0:00.000", "0:01.875", "2:05.250", "-0:00.250"]
