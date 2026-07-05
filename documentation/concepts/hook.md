---
title: Hook
description: Named extension points created inside the Aiko Services
  framework that third-party developers attach handler functions to —
  observing framework internals without modifying them
type: concept
audience: [architects, developers, end-users]
status: work-in-progress
source:
  - src/aiko_services/main/hook.py
related: [design_overview, component, service, actor, pipeline]
version: "0.6"
last_updated: 2026-07-05
---

# Hook

## Overview

A **Hook** is a named extension point placed inside the Aiko Services
framework. The framework creates the Hook and invokes it at an interesting
moment; a third-party developer attaches one or more *hook handler*
functions to it and receives the moment's context — the component, its
logger and a dictionary of live variables — without modifying framework
source.

The division of labour:

- **Framework side** — a [component](component.md) composed with the
  `Hooks` Interface calls `self.add_hook(hook_name)` once, then
  `self.run_hook(hook_name, ...)` at the point of interest.
- **Developer side** — calls
  `add_hook_handler(hook_name, hook_function)`, providing
  `hook_function(hook_name, component, logger, variables, options)`.

Hooks are only supported within the component ([Service](service.md))
infrastructure. Built-in Hooks currently exist in
[Actor](actor.md) (`actor.message_call:0`, `actor.message_in:0` — every
message dispatched and received) and [Pipeline](pipeline.md)
(`pipeline.process_frame:0`, `pipeline.process_element:0` and its `_post`
variant — every frame and every element invocation).

**Why you'd use it**: trace exactly which messages an Actor processes,
with zero framework changes:

```python
def hook_function(hook_name, component, logger, variables, options):
    logger.debug(f"{hook_name} invoked for {component} with {variables}")

actor.add_hook_handler(ACTOR_HOOK_MESSAGE_IN + "0", hook_function)
```

A disabled Hook (no handlers) costs about 1 microsecond per `run_hook()`
call; one handler costs ~14 µs and two ~24 µs — cheap enough to leave
Hooks compiled into hot paths permanently.

## For application developers

### Command-line usage

Hooks have no CLI of their own; they are exercised through the components
that define them. The Pipeline CLI attaches diagnostic hook handlers when
log level is `DEBUG_ALL` (see `pipeline.py` main), and the unit test is
runnable directly:

```bash
pytest src/aiko_services/tests/unit/test_hook.py
```

### Public API

```python
class Hooks:
    Interface.default("Hooks", "aiko_services.main.hook.HooksImpl")
```

Every [Service](service.md) is currently composed with `Hooks`
(`class Service(ServiceProtocolInterface, Hooks)` — making it optional is
a TODO), so all Services, Actors and Pipelines expose these operations:

| Operation | Used by | Effect |
|-----------|---------|--------|
| `add_hook(hook_name)` | framework | Create the named Hook (no-op if it exists) |
| `run_hook(hook_name, variables=None)` | framework | Invoke all handlers of an *enabled* Hook |
| `add_hook_handler(hook_name, hook_function, hook_options=None)` | developer | Attach a handler; enables the Hook |
| `remove_hook_handler(hook_name, hook_function, hook_options=None)` | developer | Detach a handler; disables the Hook when none remain |
| `get_hook(hook_name)` / `get_hooks()` | either | Look up one Hook / the Hook registry |
| `remove_hook(hook_name)` | framework | Delete the Hook (`RuntimeError` if absent) |
| `set_hook_enabled(hook_name, enabled_flag)` | developer | Force a Hook on or off |

Hook names follow the convention `"component_name.hook_name:version"` —
bump the version whenever the variables passed to handlers change, e.g.
`ACTOR_HOOK_MESSAGE_IN = "actor.message_in:"` plus version `"0"`.

**Framework usage** (from the source header):

```python
NAME = "component.hook:version"

class HookTest(aiko.Actor):
    def __init__(self, context):
        self.add_hook(NAME)

    def method_with_a_hook(self):
        self.run_hook(NAME, lambda: {"variable": variable_value})
```

Passing `variables` as a *lambda* matters: `run_hook()` only calls it when
the Hook is enabled, so building the variables dictionary costs nothing
when nobody is listening.

**Developer usage**:

```python
component.add_hook_handler(NAME, hook_function)

def hook_function(hook_name, component, logger, variables, options):
    logger.debug(f"{hook_name}: {variables}")
```

Handlers receive the component instance itself, the component's `logger`
(or `None`), the variables dictionary and the per-handler `options`
dictionary given at `add_hook_handler()` time.

**`DEFAULT_HOOK`.** The module exports a ready-made logging handler,
`DEFAULT_HOOK`, which logs all variables at INFO level. Its `"show"`
option selects specific variables by dotted path (traversing dictionaries
and dataclasses):

```python
component.add_hook_handler(NAME, DEFAULT_HOOK,
    {"show": ["stream.stream_id", "frame_data"]})
```

There is no wire protocol: Hooks are an in-process mechanism; handlers run
synchronously on the thread that calls `run_hook()` (normally the event
loop thread).

## For framework developers (internals)

### Design

```
   HooksImpl.hooks  (class variable — one registry per process)
   ┌───────────────────────────────────────────────────────┐
   │ "actor.message_in:0" ─► Hook(enabled, invoked,        │
   │                              handlers: OrderedDict    │
   │                                hash ─► HookHandler(   │
   │                                  function, options))  │
   │ "pipeline.process_frame:0" ─► Hook(...)               │
   └───────────────────────────────────────────────────────┘
              ▲ add_hook / run_hook          ▲ add_hook_handler
         framework component            third-party developer
```

Key design points:

- **Process-wide registry.** `HooksImpl.hooks` is a *class* variable, so
  all components in a process share one Hook namespace — attaching a
  handler through any component instance affects every instance that runs
  that Hook. The `component` argument passed to handlers identifies which
  instance actually fired.
- **Enable/disable is automatic**: a Hook is enabled exactly when it has
  handlers (`hook.enabled = len(hook.handlers) > 0` on both add and
  remove); `set_hook_enabled()` can override. A disabled Hook makes
  `run_hook()` a near-free early return — the basis of the ~1 µs figure.
- **Handler identity** is `hash(function) + hash(repr(options))`, stored
  as the `OrderedDict` key — the same function may be attached twice with
  different options, and removal requires the same function *and* options.
- **Lazy variables**: `run_hook()` accepts a dict or a callable returning
  one; each Hook counts invocations in `Hook.invoked`.

### Implementation notes

- `Hook` and `HookHandler` are dataclasses; `HookHandler.__post_init__`
  computes the hash. Handler insertion order is preserved (`OrderedDict`),
  so handlers fire in the order they were added.
- `run_hook()` resolves `logger` as `self.logger` if present — components
  outside the Service hierarchy would pass `logger=None` to handlers.
- The Interface declares `run_hook(self, hook_name)` and
  `remove_hook_handler(self, hook_name, hook_function)`, while the
  implementation accepts extra parameters (`variables`, `hook_options`) —
  the abstract signatures lag the implementation.
- The source-header developer example shows a four-argument
  `hook_function(hook_name, component, logger, variables)`; the actual
  call passes five arguments (adds `options`).
- `DEFAULT_HOOK`'s `"show"` traversal stores each result under the *last*
  path segment (`show[name] = value`), so two paths ending in the same
  leaf name overwrite each other.

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `Hooks` (Interface) | Declare the extension-point contract: `add_hook()`, `run_hook()`, `add_hook_handler()`, `remove_hook_handler()`, `get_hook()`, `get_hooks()`, `remove_hook()`, `set_hook_enabled()` | Composed into [Service](service.md) |
| `HooksImpl` | Maintain the process-wide `hooks` registry; auto-enable/disable; evaluate lazy variables; dispatch to handlers in order | `Hook`, `HookHandler` |
| `Hook` (dataclass) | One named extension point: enabled flag, ordered handlers, invocation count | `HookHandler` |
| `HookHandler` (dataclass) | One attached function plus options; identity hash | — |
| `hook_function` / `DEFAULT_HOOK` | Ready-made logging handler with `"show"` dotted-path filtering | component `logger` |

## Current limitations and roadmap

- From the source `To Do` list: refactor Metrics to use Hooks for
  capturing CPU time "and beyond"
- Hooks are baked into every Service (`Service(ServiceProtocolInterface,
  Hooks)`); the stated intent (service.py TODO) is that Service Hooks
  become optional whilst Actor Hooks stay baked in
- No remote (wire-protocol) management of Hooks yet — handlers can only be
  attached in-process
- Abstract Interface signatures for `run_hook()` and
  `remove_hook_handler()` need updating to match the implementation
- Unit test coverage exists (`src/aiko_services/tests/unit/test_hook.py`
  covers the full add / run / remove lifecycle); `hook_options` and
  `DEFAULT_HOOK` filtering are untested

## Related concepts

- [Design overview](design_overview.md)
- [Component](component.md) — the composition machinery that mixes
  `Hooks` into Services
- [Service](service.md) — every Service currently is-a `Hooks`
- [Actor](actor.md) — built-in message-call / message-in Hooks
- [Pipeline](pipeline.md) — built-in per-frame and per-element Hooks
