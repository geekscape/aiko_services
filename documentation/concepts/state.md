---
title: State
description: A finite state machine wrapper (StateMachineOld) over the
  Python "transitions" package, providing logged, fail-fast state
  transitions for framework components such as the Registrar
type: concept
audience: [architects, developers, end-users]
status: work-in-progress
source:
  - src/aiko_services/main/state.py
related: [design_overview, registrar, lifecycle, event]
version: "0.6"
last_updated: 2026-07-05
---

# State

## Overview

The **State** module provides `StateMachineOld`, a thin wrapper around the
third-party [`transitions`](https://github.com/pytransitions/transitions)
package. It gives a framework component a simple operational finite state
machine (FSM): the component supplies a *model* object declaring `states`
and `transitions`, and drives it with `transition(action, parameters)`
calls that are logged and fail-fast — any transition failure terminates
the process.

The naming convention recommended by the module: name machine states with
descriptive adjectives that correspond to the transition operations —
i.e. the past tense of each transitive verb — e.g. `pending`, `running`,
`success`, `error`.

Its one current production user is the [Registrar](registrar.md), whose
primary/secondary election FSM moves through `start → primary_search →
primary | secondary` as MQTT retained messages reveal (or fail to reveal)
an existing primary Registrar.

**Why you'd use it**: give a component an explicit, observable lifecycle
instead of scattered boolean flags:

```python
from aiko_services.main import StateMachineOld

class StateMachineModel:
    states = ["start", "running"]
    transitions = [
        {"source": "start", "trigger": "initialize", "dest": "running"}
    ]

model = StateMachineModel()
state_machine = StateMachineOld(model)
state_machine.transition("initialize", None)
state_machine.get_state()  # "running"
```

The trailing "Old" is deliberate: this wrapper is legacy, retained until a
replacement `state_machine.py` design lands (see roadmap), and the module
header suggests investigating Behaviour Trees as a longer-term direction.

## For application developers

### Command-line usage

The State module has no CLI of its own. It is exercised by running
`aiko_registrar` and watching the Registrar's `lifecycle` shared-state
value move through `primary_search`, `secondary` and `primary` in the
[Dashboard](dashboard.md). Fine-grained transition logging is controlled
by an environment variable:

```bash
AIKO_LOG_LEVEL_STATE=DEBUG aiko_registrar
```

### Public API

`StateMachineOld` is a plain class — not an Aiko Services Interface — with
a two-method surface:

| Operation | Effect |
|-----------|--------|
| `StateMachineOld(model)` | Build a `transitions.Machine` from `model.states` and `model.transitions`, initial state `"start"`, `send_event=True` |
| `transition(action, parameters)` | Dispatch the trigger named `action`; `parameters` is delivered to state-entry callbacks via `event_data.kwargs` |
| `get_state()` | Return the model's current state name |

The model object supplies the FSM declaration and receives callbacks:

- `model.states` — list of state names (the initial state `"start"` must
  be included).
- `model.transitions` — list of `transitions`-package dictionaries:
  `{"source": ..., "trigger": ..., "dest": ...}`.
- `on_enter_<state>(event_data)` methods — invoked on entry; retrieve the
  parameters with `event_data.kwargs.get("parameters", {})` (the machine
  is constructed with `send_event=True`).

Failure semantics are deliberately fatal — a state machine in an undefined
condition is unrecoverable, so `transition()` catches and logs, then
raises `SystemExit`:

| Failure | Log output |
|---------|-----------|
| Unknown trigger name | `unknown action: <action>` (CRITICAL) |
| Trigger valid but not from the current state | the `MachineError` (CRITICAL) |
| Exception inside a callback | full traceback (CRITICAL) |
| any of the above | then `SystemExit("Fatal error: StateMachineOld: state=..., action=...")` |

There is no wire protocol: the FSM is in-process. Components typically
mirror the current state into ECProducer shared state (the Registrar
updates `share["lifecycle"]` in each `on_enter_*` callback), which is how
the state becomes remotely observable.

## For framework developers (internals)

### Design

```
   Component (e.g. RegistrarImpl)
   ┌──────────────────────────────────────────────────────┐
   │ model = StateMachineModel(self)                      │
   │   states       = [start, primary_search,             │
   │                   secondary, primary]                │
   │   transitions  = [initialize, primary_found,         │
   │                   primary_promotion, primary_failed] │
   │   on_enter_*() = side-effects (timers, MQTT publish, │
   │                  shared-state update)                │
   │                                                      │
   │ state_machine = StateMachineOld(model)               │
   │        │ wraps                                       │
   │        ▼                                             │
   │ transitions.Machine(model=model, initial="start",    │
   │                     send_event=True)                 │
   └──────────────────────────────────────────────────────┘
```

Key design points:

- **Model owns behaviour, wrapper owns policy.** All states, transitions
  and entry actions live in the component's model class; `StateMachineOld`
  contributes only logging, exception discipline and the fail-fast exit.
- **The current state is stored on the model** (`self.model.state`, set by
  the `transitions` package) — the wrapper holds no state of its own.
- **Interplay with the [Event](event.md) loop**: entry callbacks commonly
  add timer handlers (the Registrar's `primary_search` timeout), and timer
  handlers in turn call `transition()` — the FSM advances entirely on the
  event-loop thread.
- **Fail-fast**: `SystemExit` rather than recovery, on the grounds that a
  component whose FSM is broken should be restarted by its process
  manager.

### Implementation notes

- `AIKO_LOG_LEVEL_STATE` (default `INFO`) controls the module logger;
  DEBUG shows each transition's before/after state.
- `transition()` distinguishes an unknown action from a callback bug by
  searching `model.transitions` for the trigger after catching
  `AttributeError` — the `transitions` package raises `AttributeError`
  for undefined triggers.
- Because the wrapper uses `Machine.dispatch(action, parameters=...)`,
  callbacks must accept `event_data` (the `send_event=True` calling
  convention) — not plain positional arguments.

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `StateMachineOld` | Construct the `transitions.Machine`; dispatch triggers with logging; classify failures and terminate fatally; report current state | `transitions.Machine` / `MachineError`; the model object supplied by a component |
| model classes (e.g. Registrar `StateMachineModel`) | Declare `states` and `transitions`; implement `on_enter_*` side-effects | [Registrar](registrar.md); [Event](event.md) timers; ECProducer shared state ([Share](share.md)) |

## Current limitations and roadmap

- The class name `StateMachineOld` marks it as legacy: the
  [Registrar](registrar.md) source carries the TODO "Implement protocol.py
  and state_machine.py !" — a redesigned state machine module is planned
  but not yet written
- The module header proposes investigating **Behaviour Trees** as an
  alternative to flat FSMs
- The initial state is hard-coded to `"start"`; models cannot choose
  another
- Failure handling is all-or-nothing (`SystemExit`) — there is no
  recoverable-error path for callers that could handle a rejected
  transition
- Only one production user (the Registrar); the planned
  [LifeCycle](lifecycle.md) work is a natural second consumer
- No unit tests exist for this module (nothing under
  `src/aiko_services/tests/` covers it)

## Related concepts

- [Design overview](design_overview.md)
- [Registrar](registrar.md) — the primary/secondary election FSM, the
  module's sole production user
- [LifeCycle](lifecycle.md) — component lifecycle states that this
  mechanism should eventually serve
- [Event](event.md) — timers that drive time-based transitions
