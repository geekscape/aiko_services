#!/usr/bin/env python3
#
# Aiko Services tests: a date/time that a person reads
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# Date/times are stored in UTC and displayed in local time, because a
# person reads them against the clock on their own wall.  "display_time()"
# is the one place that converts, and the Dashboard's "--utc" turns it off.
#
# Every test here pins the zone with TZ, so a result does not depend on
# where the test runs.  Two zones are used deliberately:
#
# - "Asia/Tokyo" names itself "JST", which is the usual case
# - "Etc/GMT-10" names itself "+10", which is not a name a person wants
#   to read, so the offset is shown instead.  That branch exists only
#   because of this case, and nothing else would find it
#
# What is NOT converted matters as much as what is.  A value with no
# offset states no zone, and guessing UTC for it would move a reading by
# hours, so it is left exactly as it is.

import os
import time

import pytest

from aiko_services.main.utilities import display_time

TOKYO = "Asia/Tokyo"                   # JST, +09:00, and no daylight saving
PLUS_TEN = "Etc/GMT-10"                # names itself "+10", not a word

@pytest.fixture
def zone(monkeypatch):
    """Pin the zone for one test, and put the old one back"""

    if not hasattr(time, "tzset"):
        pytest.skip("TZ only takes effect where time.tzset() exists")

    def _zone(name):
        monkeypatch.setitem(os.environ, "TZ", name)
        time.tzset()
    yield _zone
    time.tzset()                       # monkeypatch has restored TZ by now

# What is converted ------------------------------------------------------- #

def test_utc_becomes_local_time(zone):
    zone(TOKYO)

    assert display_time("2026-11-05T06:20:00Z") == "2026-11-05 15:20:00 JST"

def test_a_date_rolls_over_with_the_clock(zone):
    """The point of the conversion: 23:30 UTC is the next day in Tokyo"""

    zone(TOKYO)

    assert display_time("2026-11-05T23:30:00Z") == "2026-11-06 08:30:00 JST"

def test_an_offset_other_than_zero_is_honored(zone):
    zone(TOKYO)

    assert display_time("2026-11-05T06:20:00+02:00") == \
        "2026-11-05 13:20:00 JST"

def test_sub_second_precision_is_dropped(zone):
    """A person reads seconds.  The stored value keeps the rest"""

    zone(TOKYO)

    assert display_time("2026-11-05T06:20:00.123456Z") == \
        "2026-11-05 15:20:00 JST"

def test_a_space_separator_is_accepted_too(zone):
    zone(TOKYO)

    assert display_time("2026-11-05 06:20:00Z") == "2026-11-05 15:20:00 JST"

def test_a_zone_that_has_no_name_shows_its_offset(zone):
    """"+10" is what the zone calls itself, and it is not worth reading"""

    zone(PLUS_TEN)

    assert display_time("2026-11-05T06:20:00Z") == "2026-11-05 16:20:00 +10:00"

# What is left alone ------------------------------------------------------ #

def test_utc_asked_for_is_returned_as_stored(zone):
    zone(TOKYO)

    assert display_time("2026-11-05T06:20:00Z", utc=True) == \
        "2026-11-05T06:20:00Z"

def test_a_date_time_with_no_offset_states_no_zone(zone):
    """Guessing UTC here would move the reading by nine hours"""

    zone(TOKYO)

    assert display_time("2026-11-05T06:20:00") == "2026-11-05T06:20:00"

def test_a_sentence_that_contains_a_date_is_not_rewritten(zone):
    zone(TOKYO)

    text = "sampled at 2026-11-05T06:20:00Z"

    assert display_time(text) == text

@pytest.mark.parametrize("value", [
    None, 12.5, 0, True, "", "power_manager", "9.9", "2026-11-05",
    ["2026-11-05T06:20:00Z"],
])
def test_anything_that_is_not_a_date_time_is_returned_unchanged(value, zone):
    """Every value on display goes through this, so it must be safe for
    all of them, and must not turn a value into a string on the way"""

    zone(TOKYO)
    result = display_time(value)

    assert result == value
    assert type(result) is type(value)

def test_a_date_time_that_cannot_be_parsed_is_returned_unchanged(zone):
    """It matches the shape and is still not a date.  Nothing on a
    display is worth an exception"""

    zone(TOKYO)

    assert display_time("2026-13-45T06:20:00Z") == "2026-13-45T06:20:00Z"

# --------------------------------------------------------------------------- #
