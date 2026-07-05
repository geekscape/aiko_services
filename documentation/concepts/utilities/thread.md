---
title: Thread utility (ThreadManager)
description: A named-thread registry with a background "thread_tidy"
  janitor that prunes finished threads — written for ProcessManager, not
  yet wired into the framework
type: concept
audience: [developers]
status: work-in-progress
source:
  - src/aiko_services/main/utilities/thread.py
related: [design_overview, process_manager, event]
version: "0.6"
last_updated: 2026-07-05
---

# Thread utility (ThreadManager)

## Overview

`ThreadManager` is a registry of **named** `threading.Thread` instances:
create-and-start threads by unique name, look them up, list them with
liveness status, and let a background *thread_tidy* janitor prune
finished threads automatically.

**Status: implemented but not yet integrated.** The module is complete
and runnable, but it is *not* exported by `utilities/__init__.py` and no
framework code constructs a `ThreadManager` yet. Its intended customer
is [ProcessManager](../process_manager.md), whose source carries the
TODOs (`process_manager.py`):

```python
# * Aiko Dashboard plug-in support: Process CRUD et al plus ThreadManager view
self.thread.start()                           # TODO: Use ThreadManager
```

**Why you'd use it**: anywhere a component spawns worker threads ad hoc
and later cannot tell which are still alive:

```python
from aiko_services.main.utilities.thread import ThreadManager  # direct import

tm = ThreadManager(autoclean_interval=1.0)
tm.add_thread("frame_writer", writer_function, args=(queue,))
tm.list_threads()
# [{'name': 'thread_tidy', 'alive': True, 'ident': ...},
#  {'name': 'frame_writer', 'alive': True, 'ident': ...}]
```

## For application developers

### Command-line usage

There is no console script; running the module directly executes a
worked example — two workers plus the janitor, showing threads
disappearing from the tracking list as they finish:

```bash
cd src/aiko_services/main/utilities
python3 thread.py
```

### Public API

```python
class ThreadManager:
    THREAD_TIDY_NAME = "thread_tidy"

    def __init__(self, *, autoclean_interval: float = 1.0)
    def add_thread(name, target, args=None, kwargs=None, *,
                   daemon=True, start=True,
                   replace_finished=True) -> threading.Thread
    def get_thread(name) -> threading.Thread          # KeyError if missing
    def get_thread_count() -> int
    def list_threads(include_status=True) -> list     # dicts or just names
    def remove_thread(name, *, join=False, timeout=None)
    def cleanup() -> list[str]                        # names pruned now
    def shutdown(*, join_thread_tidy=True, timeout=None)
```

Behavioural contract:

- Names are unique. `add_thread()` raises `ValueError` if a **live**
  thread already holds the name; a *finished* thread with the name is
  replaced when `replace_finished=True` (the default), otherwise
  `ValueError`.
- The janitor thread is itself tracked under the reserved name
  `"thread_tidy"` — `add_thread("thread_tidy", ...)` raises
  `ValueError` and `remove_thread("thread_tidy")` raises
  `RuntimeError`; use `shutdown()` instead.
- `autoclean_interval=0` (or `None`) disables the janitor entirely; the
  registry then only prunes on API calls (every public method cleans
  first) or explicit `cleanup()`.
- `remove_thread()` only stops *tracking* — there is no way to
  force-stop a thread; pass `join=True` to wait for it.
- `shutdown()` stops and untracks the janitor only; worker threads are
  left untouched.

## For framework developers (internals)

### Design

```
   ThreadManager
   ┌───────────────────────────────────────────────┐
   │ _threads: {"thread_tidy": Thread,             │
   │            "frame_writer": Thread, ...}       │
   │ _lock: threading.Lock (guards _threads)       │
   │ _shutdown_event: Event (janitor stop signal)  │
   └───────────────┬───────────────────────────────┘
                   │ every autoclean_interval seconds
                   ▼
        _run_tidy(): prune not-alive threads
```

One lock guards the registry; every public method takes it and calls
`_cleanup_locked()` first, so callers always observe a pruned view. The
janitor is a daemon thread waiting on `_shutdown_event.wait(interval)`,
which doubles as both the periodic timer and the shutdown signal
(interval is clamped to a minimum of 0.05 s).

Note the contrast with the [Event](../event.md) system used throughout
Aiko Services: framework components generally run cooperative handlers
on the single event loop thread, while `ThreadManager` is for genuinely
concurrent OS threads (e.g. ProcessManager's per-process watchers).

### Implementation notes

- `thread.start()` in `add_thread()` happens *outside* the lock —
  deliberate, since `start()` can run arbitrary target code promptly.
- `_cleanup_locked()` does not special-case the janitor: after
  `shutdown()` the finished janitor thread is prunable like any other.
- All threads default to `daemon=True`; nothing here blocks process
  exit.

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `ThreadManager` | Registry of uniquely named threads; create/start/lookup/list/untrack; auto-prune finished threads via the reserved `thread_tidy` janitor; guarded by a single lock | `threading` (Thread, Lock, Event); [ProcessManager](../process_manager.md) (intended consumer, per its TODOs) |

## Current limitations and roadmap

The source `To Do` list is empty ("None, yet !"). Observed gaps:

- **Not exported**: `utilities/__init__.py` does not import this module,
  so `from aiko_services.main.utilities import *` will not provide
  `ThreadManager` — adding it is the obvious first step of integration
- **No consumers yet**: `process_manager.py` carries `TODO: Use
  ThreadManager` markers; the Aiko Services Dashboard "ThreadManager view" is
  also still a TODO there
- No cooperative-stop support (no per-thread stop event); `remove_thread`
  cannot terminate a runaway thread
- No unit tests anywhere in the repository exercise this module; the
  `__main__` demo is the only executable check

## Related concepts

- [ProcessManager](../process_manager.md) — the intended consumer
- [Event](../event.md) — the framework's event loop; use it for
  cooperative handlers, `ThreadManager` for real OS threads
- [Lock utility](lock.md) — named, diagnosable locks for the critical
  sections such threads will need
