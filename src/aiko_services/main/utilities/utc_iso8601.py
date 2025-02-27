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
# Notes
# ~~~~~
# No longer using utcnow and utcfromtimestamp
# - https://blog.ganssle.io/articles/2019/11/utcnow.html

from datetime import date, datetime, timezone

__all__ = [
   "datetime_epoch", "datetime_now_utc_iso", "epoch_to_utc_iso",
   "local_iso_now", "utc_iso_since_epoch", "utc_iso_to_datetime",
   "utc_iso_to_local"
]

# --------------------------------------------------------------------------- #

def datetime_epoch():
    epoch = "1970-01-01T00:00:00.000000"
    return datetime(1970, 1, 1), epoch

def datetime_now_utc_iso():
    return datetime.now(tz=timezone.utc).isoformat()

def epoch_to_utc_iso(seconds_since_epoch):
    utc = datetime.fromtimestamp(seconds_since_epoch, tz=timezone.utc)
    return utc.isoformat()

def local_iso_now():
  return utc_iso_to_local(datetime_now_utc_iso())

def utc_iso_since_epoch(datetime_utc_iso):
    datetime_utc = utc_iso_to_datetime(datetime_utc_iso)
    return (datetime_utc - datetime_epoch()[0]).total_seconds()

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
