# Usage
# ~~~~~
# $ python
# >>> import utc_iso8601
# >>> utc_iso8601.datetime_epoch()[0]
#     datetime.datetime(1970, 1, 1, 0, 0)
# >>> utc_iso8601.datetime_epoch()[1]
#     '1970-01-01T00:00:00.000000'
# >>> utc_iso8601.datetime_now_utc_iso()
#     '2024-10-29T11:31:22.000000'
# >>> utc_iso8601.epoch_to_utc_iso(1.0)
#     '1970-01-01T00:00:01'
# >>> utc_iso8601.local_iso_now()
#     '2024-10-29 11:31:22'
# >>> utc_iso8601.utc_iso_since_epoch("1970-01-01T00:00:01")
#     1.0
# >>> utc_iso8601.utc_iso_to_datetime("1970-01-01T00:00:01")
#     datetime.datetime(1970, 1, 1, 0, 0, 1)
# >>> utc_iso8601.utc_iso_to_local("1970-01-01T00:00:01")
#     '1970-01-01 10:00:01'
# >>> utc_iso8601.display_time("2026-11-05T06:20:00Z")
#     '2026-11-05 17:20:00 AEDT'
# >>> utc_iso8601.display_time("2026-11-05T06:20:00Z", utc=True)
#     '2026-11-05T06:20:00Z'
#
# Reference
# ~~~~~~~~~
# Note 1: Epoch is 1970-01-01 00:00:00
# Note 2: "datetime format" is that used by the Python "datatime" module
# Note 3: UTC ISO 8601 combined date and time: "yyyy-mm-ddThh:mm:ss.ssssss"
#
# https://en.wikipedia.org/wiki/ISO_8601#Combined_date_and_time_representations
#
# datetime_epoch()[0]: Epoch in datetime format
# datetime_epoch()[1]: Epoch in UTC ISO format
#
# datetime_now_utc_iso(): Current date/time in UTC ISO format
#
# epoch_to_utc_iso(seconds_since_epoch): Seconds since epoch in UTC ISO format
#
# local_iso_now(): Current date/time in local datetime format
#
# utc_iso_since_epoch(datetime_utc_iso): UTC ISO format in seconds since epoch
#
# utc_iso_to_datetime(datetime_utc_iso): UTC ISO format in date/time format
#
# utc_iso_to_local(datetime_utc_iso): UTC ISO format in local UTC ISO format
#
# display_time(value, utc): A date/time for a person to read.  Local time
# is the default, because that is what a person compares against a clock
# on a wall.  Anything that is not a date/time with a known offset is
# returned unchanged, so this is safe to apply to every value on display
# 
# Notes
# ~~~~~
# No longer using utcnow and utcfromtimestamp
# - https://blog.ganssle.io/articles/2019/11/utcnow.html

from datetime import date, datetime, timezone
import re

__all__ = [
   "datetime_epoch", "datetime_now_utc_iso", "display_time",
   "epoch_to_utc_iso", "local_iso_now", "utc_iso_since_epoch",
   "utc_iso_to_datetime", "utc_iso_to_local"
]

# A date and time that carries its own offset, and nothing else.  The
# match is anchored, so a sentence that merely contains a date is left
# alone.  An offset is required: a date/time without one states no zone,
# and guessing UTC for it would move a reading by hours
_DATETIME_AWARE = re.compile(
    r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:?\d{2})$")

# --------------------------------------------------------------------------- #

def datetime_epoch():
    epoch = "1970-01-01T00:00:00.000000"
    return datetime(1970, 1, 1), epoch

def datetime_now_utc_iso():
    return datetime.now(tz=timezone.utc).isoformat()

def display_time(value, utc=False):
    """A date/time for a person to read, in local time by default.

    "utc" returns the value as it is stored, which is what comparing two
    hosts in different zones needs.  Everything else is returned
    unchanged, so a caller can apply this to every value it displays
    without first asking which ones are date/times"""

    if utc or not isinstance(value, str):
        return value
    text = value.strip()
    if not _DATETIME_AWARE.fullmatch(text):
        return value
    try:                              # "Z" is only native from Python 3.11
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return value
    local = moment.astimezone()
    zone = local.tzname() or ""
    if not zone.isalpha():            # a numeric name reads worse than +11:00
        offset = local.strftime("%z")
        zone = f"{offset[:3]}:{offset[3:]}" if offset else ""
    return f"{local:%Y-%m-%d %H:%M:%S}" + (f" {zone}" if zone else "")

def epoch_to_utc_iso(seconds_since_epoch):
    utc = datetime.fromtimestamp(seconds_since_epoch, tz=timezone.utc)
    return utc.isoformat()

def local_iso_now():
  return utc_iso_to_local(datetime_now_utc_iso())

def utc_iso_since_epoch(datetime_utc_iso):
    """Seconds since the epoch, for an aware UTC ISO 8601 string.

    It used to subtract datetime_epoch(), which is naive, from an aware
    datetime, and every call raised TypeError.  Nothing called it, so
    nothing reported it.  datetime.timestamp() is exact and needs no
    epoch of our own"""

    return utc_iso_to_datetime(datetime_utc_iso).timestamp()

def utc_iso_to_datetime(datetime_utc_iso):
#   datetime_utc = date.fromisoformat(datetime_utc_iso)  # should work :(
    if len(datetime_utc_iso) == 25:
        strp_isoformat = "%Y-%m-%dT%H:%M:%S%z"
    else:
        strp_isoformat = "%Y-%m-%dT%H:%M:%S.%f%z"
    datetime_utc = datetime.strptime(datetime_utc_iso, strp_isoformat)
    return datetime_utc

def utc_iso_to_local(datetime_utc_iso):
    datetime_utc = utc_iso_to_datetime(datetime_utc_iso)
    datetime_local = datetime_utc.replace(
        tzinfo=timezone.utc).astimezone(tz=None)
    return datetime_local.isoformat().replace("T", " ")[:19]

# --------------------------------------------------------------------------- #
