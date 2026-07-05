---
title: Lock utility
description: A named, diagnosable wrapper around threading.Lock that
  records who holds it — turn on AIKO_LOG_LEVEL_LOCK=DEBUG to watch
  contention live
type: concept
audience: [developers]
status: work-in-progress
source:
  - src/aiko_services/main/utilities/lock.py
related: [design_overview, logger]
version: "0.6"
last_updated: 2026-07-05
---

# Lock utility

## Overview

The lock utility wraps Python's `threading.Lock` with two additions: a
*name* for the lock and a *location* string recorded on every acquire, so
that deadlocks and contention can be diagnosed by log inspection instead
of debugger archaeology. The Aiko Services event loop, process Service
table, stream state and connection state are all guarded by these Locks.

**Why you'd use it**: protect shared state that is mutated from more than
one thread, while keeping a breadcrumb trail:

```python
from aiko_services.main.utilities import Lock

lock_test = Lock(f"{__name__}.test", aiko.logger(__name__))
try:
    lock_test.acquire("add_service()")
    # critical section
finally:
    lock_test.release()
```

Then, when something hangs:

```bash
export AIKO_LOG_LEVEL_LOCK=DEBUG   # log every acquire / release / wait
```

## For application developers

### Command-line usage

There is no CLI; the module is exercised by every Aiko Services process —
the event loop, `process.py`, `stream.py` and `connection.py` all take
these Locks (and `AIKO_LOG_LEVEL_LOCK=DEBUG` applies to any of them).

### Public API

```python
class Lock:
    Lock(name, logger=None)
    acquire(location)    # location: human-readable caller identity
    release()
    in_use()             # location currently holding the lock, or None
```

Real call sites:

```python
# src/aiko_services/main/event.py
event_loop_lock = Lock(f"{__name__}.loop")

# src/aiko_services/main/process.py
self._services_lock = Lock(f"{__name__}._services", _LOGGER_PROCESS)

# src/aiko_services/main/stream.py
self.lock = Lock(f"{__name__}_{self.stream_id}")
```

Always pair `acquire()` with `release()` in a `try` / `finally` — the
class does not (yet) support `with` blocks.

## For framework developers (internals)

### Design

```
   Lock("event.loop")
   ┌───────────────────────────────┐
   │ _lock:   threading.Lock       │
   │ _in_use: "add_timer_handler()"│ ◄─ set on acquire, cleared on release
   └───────────────────────────────┘
        DEBUG log: '"event.loop" acquired by add_timer_handler()'
```

Before blocking, `acquire()` logs (at DEBUG) that the lock is already
held and by whom — that pre-check is inherently racy and is diagnostic
only; correctness comes solely from the underlying `threading.Lock`.

### Implementation notes

- Logging goes through the module-level logger created with
  `AIKO_LOG_LEVEL_LOCK` (default INFO), *not* through the `logger`
  argument — `self._logger` is stored but never used.
- `in_use()` returns the location string, doubling as a truthy "is
  locked" test.

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `Lock` | Serialise access to a critical section; record and report the holding location; emit DEBUG diagnostics on acquire/release/contention | `threading.Lock` (delegate); [Logger](logger.md) (diagnostics); `event.py`, `process.py`, `stream.py`, `connection.py` (users) |

## Current limitations and roadmap

From the source `To Do` list:

- Keep a process-wide registry of all Locks that can be displayed
- Longer term, *remove* most Locks entirely: route all state updates
  through events (handlers, messages, timers) executed solely by the
  event-loop thread
- Not re-entrant, no timeout, no context-manager (`with`) support
- The `logger` constructor argument is dead code (see Implementation
  notes)
- No direct unit tests; `tests/unit/test_stream_lock.py` tests Pipeline
  *stream* locking behaviour built on top of this class

## Related concepts

- [Logger](logger.md) — supplies `get_logger()` and the `DEBUG` level
  constant used for lock diagnostics
- [Design overview](../design_overview.md) — the event-loop-centric
  design that the roadmap says should eventually replace these Locks
