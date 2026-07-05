---
title: System utility
description: Host and process introspection helpers — path splitting
  (dir_base_name), process and virtual memory usage, and system uptime
  across Linux, macOS and Windows
type: concept
audience: [developers]
status: work-in-progress
source:
  - src/aiko_services/main/utilities/system.py
related: [design_overview, hyperspace, metrics]
version: "0.6"
last_updated: 2026-07-05
---

# System utility

## Overview

The system utility is a small grab-bag of host and process introspection
helpers with no Aiko Services dependencies: a combined
dirname/basename path splitter, process (RSS/VMS) and host virtual-memory
usage readings, and cross-platform system uptime. All functions are
exported via `utilities/__init__.py`.

**Why you'd use it**: quick diagnostics without reaching for `psutil`
directly, and normalised path splitting for HyperSpace-style paths:

```python
from aiko_services.main.utilities import *

dir_base_name("a/b//c/")     # ("a/b", "c")
print_memory_used("Frame 42: ")
# Frame 42: Memory RSS used: 58.3 Mbyte, VMS used: 400.1 Mbyte
```

## For application developers

### Command-line usage

There is no console script; running the module directly prints uptime and
both memory readings:

```bash
cd src/aiko_services/main/utilities
./system.py
# System uptime: 6 days, 3:14:15
# Memory RSS used: 15.2 Mbyte, VMS used: 400.5 Mbyte
# Virtual Memory used: 20.1 Gbyte, available: 11.9 Gbyte
```

### Public API

```python
__all__ = [
    "dir_base_name",
    "get_memory_used", "get_virtual_memory",
    "print_memory_used", "print_virtual_memory",
    "get_uptime"
]
```

**`dir_base_name(path)`** — like `dirname` and `basename` combined,
returning `(directory, name)`. It collapses repeated `/`, strips a
trailing `/`, and handles the edge cases explicitly:

```python
dir_base_name(None)        # (".", "")
dir_base_name("name")      # (".", "name")
dir_base_name("/name")     # ("/", "name")
dir_base_name("a/b/name")  # ("a/b", "name")
```

Written for and used by [HyperSpace](../hyperspace.md):

```python
# src/aiko_services/main/hyperspace.py
from aiko_services.main.utilities import dir_base_name, get_hostname
```

**Memory functions** — each accepts a unit (`"Kb"`, `"Mb"`, `"Gb"`,
`"Tb"`, binary powers of two; any other value raises `ValueError`) and
runs `gc.collect()` first so readings reflect reachable memory:

```python
rss, vms, unit = get_memory_used()          # this process, default "Mb"
available, used, unit = get_virtual_memory() # whole host, default "Gb"
print_memory_used("label: ")                 # formatted one-liner
print_virtual_memory("label: ")
```

**`get_uptime()`** — system uptime as a `H:MM:SS`-style string
(`str(timedelta(...))`). Implemented per platform: `/proc/uptime`
(Linux), `sysctl kern.boottime` (macOS), `GetTickCount64` (Windows).
Any failure is caught and returned as an `"Error: ..."` string rather
than raised.

## For framework developers (internals)

### Design

```
   dir_base_name()      pure string manipulation (no os.path)
   get_memory_used()  ─► psutil.Process().memory_info()   (RSS, VMS)
   get_virtual_memory()► psutil.virtual_memory()          (host-wide)
   get_uptime()       ─► platform dispatch: /proc | sysctl | kernel32
```

Deliberately dependency-light: only `psutil`, `platform`, `subprocess`
and the standard library, so it can be imported very early. The
`print_*` functions are thin formatting wrappers over the `get_*` pairs
— prefer the `get_*` forms when feeding metrics elsewhere.

### Implementation notes

- `_get_scale(unit)` is the shared unit table; it returns
  `(scale, spelled_out_unit)` — the same table the broken
  [metrics](metrics.md) module duplicates.
- `dir_base_name()` is by-hand rather than `os.path.split()` so
  behaviour is identical across platforms and matches HyperSpace path
  semantics (e.g. `("/", "name")` for `"/name"`).
- `get_uptime()` on macOS shells out twice (`sysctl`, `date`); it is not
  suitable for tight loops.

### CRC card

The module is purely functions; one row describes the module itself:

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `system` (module) | Split paths into `(dir, base)`; report process RSS/VMS and host virtual memory in a chosen unit; report system uptime across Linux/macOS/Windows | `psutil` (memory); [HyperSpace](../hyperspace.md) (`dir_base_name`); [metrics](metrics.md) (intended future consumer) |

## Current limitations and roadmap

The source `To Do` list is empty ("None, yet !"). Observed limitations:

- `get_uptime()` swallows all exceptions into an `"Error: ..."` return
  value — callers cannot distinguish failure programmatically
- Memory readings only; no CPU, disk or per-thread statistics — the
  [metrics](metrics.md) roadmap is the intended home for richer
  telemetry
- No unit tests anywhere in the repository exercise this module
  (`dir_base_name()` in particular deserves table-driven tests)

## Related concepts

- [HyperSpace](../hyperspace.md) — uses `dir_base_name()` for path
  addressing
- [Metrics utility](metrics.md) — the (currently placeholder) module
  intended to build on these readings
- [Configuration utility](configuration.md) — the other host-identity
  helper (hostname, username, PID)
