---
title: Context utility (process-global context)
description: A minimal process-global holder for the (aiko, message)
  pair, set once at process start and readable from anywhere
type: concept
audience: [developers]
status: work-in-progress
ste: adapted
source:
  - src/aiko_services/main/utilities/context.py
related: [design_overview, context]
version: "0.6"
last_updated: 2026-08-01
---

# Context utility (process-global context)

## Overview

Source code: [`src/aiko_services/main/utilities/context.py`](../../../src/aiko_services/main/utilities/context.py)

The context utility gives `ContextManager`, a tiny holder. It makes the
current process's core framework objects available globally through
`get_context()`. Those objects are the `aiko` process data and the
`message` (MQTT) instance.

**Do not confuse this with `src/aiko_services/main/context.py`.** That is
a different module. It holds the interface-composition `Context` and
`ContextService` machinery that `compose_instance()` uses, documented
separately as [Context (interface composition)](../context.md). This
utility is a *service locator* for two process-wide singletons. The other
is the constructor-argument dataclass system.

**Why to use it**: code deep inside a library that needs to publish an
MQTT message without threading `aiko` / `message` references through every
call signature:

```python
from aiko_services.main.utilities import get_context

context = get_context()
context.message.publish(topic, payload)
```

## For application developers

### Command-line usage

There is no CLI. Every Aiko Services process exercises the module —
`process.py` activates the context during `initialize()`.

### Public API

```python
class ContextManager:
    def __init__(self, aiko=None, message=None)   # stores and activates
    def activate(self) -> "ContextManager"        # set as the global context
    # also usable as a "with" context manager

def get_context() -> ContextManager               # the current global context
```

The one real call site — the framework sets the context once MQTT is up:

```python
# src/aiko_services/main/process.py (initialize)
context = ContextManager(aiko, aiko.message)
```

Usage patterns from the source header:

```python
with ContextManager({}) as context:
    print(context.aiko, context.message)

context = ContextManager({})
context.aiko["a"] = 1

context = get_context()
print(context.aiko)
```

Note that `__init__()` already calls `activate()`, so the `with` form is
cosmetic. To enter the block does not scope anything. To exit it does
**not** restore any previously active context.

## For framework developers (internals)

### Design

```
   process.py initialize()
        │  ContextManager(aiko, aiko.message)
        ▼
   ┌───────────────────┐
   │ module _CONTEXT   │◄── get_context()  (any code, any thread)
   │  .aiko  .message  │
   └───────────────────┘
```

A single module-level `_CONTEXT` variable — last `activate()` wins. There
is exactly one context per process. It is not thread-local (a thread-local
variant is on the To Do list).

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `ContextManager` | Hold `(aiko, message)`; install itself as the process-global context on construction or `activate()` | `process.py` (sole creator); `aiko` / `message` singletons |
| *function* `get_context()` | Return the currently active `ContextManager` (or `None` before initialization) | Any framework or application code |

## Current limitations and roadmap

- `get_context()` returns `None` if called before
  `aiko.process.initialize()` / `run()` — callers must cope
- `__exit__()` is a no-op: no restoration of a previous context, so nested
  `with ContextManager(...)` blocks do not behave like a stack
- Not thread-local. The source To Do lists a thread-local context example
- `get_context()` currently has no callers in the code base — the global
  is written by `process.py` but nothing reads it yet
- No unit tests (`tests/unit/test_context.py` tests the *other* context
  module, `main/context.py`)

## Related concepts

- [Context (interface composition)](../context.md) — the different
  `main/context.py` module: `ContextService`, `actor_args()`,
  `compose_instance()`
- [Design overview](../design_overview.md) — process start-up sequence
