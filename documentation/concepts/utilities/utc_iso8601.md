---
title: UTC ISO 8601 utility
description: Conversions between epoch seconds, Python datetime, UTC
  ISO 8601 strings and local time — the framework's timestamp vocabulary
type: concept
audience: [developers]
status: work-in-progress
source:
  - src/aiko_services/main/utilities/utc_iso8601.py
related: [design_overview, pipeline, recorder]
version: "0.6"
last_updated: 2026-07-05
---

# UTC ISO 8601 utility

## Overview

This module is the framework's timestamp vocabulary: conversions between
seconds-since-epoch, Python `datetime` values, UTC
[ISO 8601](https://en.wikipedia.org/wiki/ISO_8601#Combined_date_and_time_representations)
strings (`yyyy-mm-ddThh:mm:ss.ssssss+00:00`) and local time. It follows
the modern timezone-aware idiom — `datetime.now(tz=timezone.utc)` — and
deliberately avoids the deprecated `utcnow()` / `utcfromtimestamp()`.

**Why you'd use it**: consistent, human-readable timestamps in shared
state and diagnostics. [Pipeline](../pipeline.md) stamps its lifecycle
and frame diagnostics this way:

```python
# src/aiko_services/main/pipeline.py
self.share["lifecycle"] = {
    "time": local_iso_now(), "latest_frame_id": frame_id}
```

## For application developers

### Command-line usage

There is no CLI and no `__main__` block; the usage header at the top of
the source file doubles as an interactive `python3` session walkthrough.

### Public API

```python
__all__ = [
   "datetime_epoch", "datetime_now_utc_iso", "epoch_to_utc_iso",
   "local_iso_now", "utc_iso_since_epoch", "utc_iso_to_datetime",
   "utc_iso_to_local"
]
```

Working functions (verified against the implementation):

```python
from aiko_services.main.utilities import *

datetime_now_utc_iso()   # '2026-07-05T01:03:16.091619+00:00'  (UTC, aware)
epoch_to_utc_iso(1.0)    # '1970-01-01T00:00:01+00:00'
local_iso_now()          # '2026-07-05 11:03:16'  (local wall clock, 19 chars)
datetime_epoch()         # (datetime(1970, 1, 1), '1970-01-01T00:00:00.000000')
utc_iso_to_datetime('2024-10-29T11:31:22+10:00')   # aware datetime
utc_iso_to_local('1970-01-01T00:00:01+00:00')      # '1970-01-01 10:00:01' AEST
```

Notes on formats:

- `datetime_now_utc_iso()` and `epoch_to_utc_iso()` return **aware** UTC
  strings ending in `+00:00`. (The usage comments in the source show the
  older offset-less form — the code has since moved on; trust the
  `+00:00` form.)
- `local_iso_now()` returns a *space-separated*, second-resolution local
  time (`"yyyy-mm-dd hh:mm:ss"`) — the form used in Pipeline `share[]`
  diagnostics.
- `utc_iso_to_datetime()` accepts exactly two shapes: a 25-character
  string with offset and no microseconds
  (`2024-10-29T11:31:22+10:00`), or a string with *both* microseconds
  and offset (`...T11:31:22.091619+00:00`). Anything else — notably a
  plain 19-character `1970-01-01T00:00:01` — raises `ValueError`, even
  though the source usage comments claim it works (see limitations).

**Broken (do not use): `utc_iso_since_epoch()`.** It subtracts the naive
epoch `datetime(1970, 1, 1)` from the parsed datetime, but
`utc_iso_to_datetime()` only successfully parses *offset-bearing*
(aware) strings — and Python refuses to subtract naive from aware. So
every input either fails to parse (naive strings) or fails to subtract
(aware strings). Use
`utc_iso_to_datetime(s).timestamp()` directly until this is fixed.

## For framework developers (internals)

### Design

```
  epoch seconds ──epoch_to_utc_iso()──────────► UTC ISO string (+00:00)
        ▲                                            │
        └──utc_iso_since_epoch() [BROKEN]────────────┤
                                                     │utc_iso_to_datetime()
  local "y-m-d h:m:s" ◄──utc_iso_to_local()──────────┤   (strptime, two
        ▲                                            ▼    fixed formats)
        └──local_iso_now()◄──datetime_now_utc_iso()  datetime (aware)
```

Pure functions over the standard `datetime` module — no external
dependencies, no state. The design choice worth knowing: parsing is done
with `strptime` against two hard-coded formats selected by *string
length* (`len == 25` → no microseconds), because at the time
`date.fromisoformat()` did not cope (see the commented-out line and the
"should work :(" lament). Python 3.11+ `datetime.fromisoformat()` now
parses all of these forms and is the natural replacement.

### CRC card

The module is purely functions; one row describes the module itself:

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `utc_iso8601` (module) | Produce UTC ISO 8601 timestamps (now / from epoch); convert UTC ISO strings to `datetime` and to local wall-clock strings | `datetime` (standard library); [Pipeline](../pipeline.md) (`local_iso_now()` in `share[]` diagnostics) |

## Current limitations and roadmap

The source has no `To Do` list. Known defects and gaps (all verified):

- `utc_iso_since_epoch()` is unusable: naive inputs fail `strptime`
  (the `%z` directive is unconditional), aware inputs fail the
  naive-epoch subtraction. Fix by making the epoch aware
  (`datetime(1970, 1, 1, tzinfo=timezone.utc)`) *and* accepting
  offset-less strings, or by delegating to `.timestamp()`
- `utc_iso_to_datetime()` / `utc_iso_to_local()` reject offset-less
  timestamps (e.g. `1970-01-01T00:00:01`), contradicting the module's
  own usage examples; the length-25 heuristic is fragile
- The usage header predates timezone-aware output — its expected values
  lack the `+00:00` suffix that is actually produced
- Consider replacing the whole parse path with
  `datetime.fromisoformat()` (Python 3.11+)
- No unit tests anywhere in the repository exercise this module —
  table-driven round-trip tests would have caught all of the above

## Related concepts

- [Pipeline](../pipeline.md) — stamps lifecycle/frame diagnostics with
  `local_iso_now()`
- [Recorder](../recorder.md) — timestamped event capture
- [System utility](system.md) — uptime and memory, the other
  "observability primitives" module
