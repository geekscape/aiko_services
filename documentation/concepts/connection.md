---
title: Connection
description: A per-process ladder of connectivity states — from no network
  up to Registrar available — with handlers notified on every change, so
  components can defer work until the infrastructure they need exists
type: concept
audience: [architects, developers, end-users]
status: work-in-progress
source:
  - src/aiko_services/main/connection.py
related: [design_overview, process, registrar, message, transport, share,
  lifecycle]
version: "0.6"
last_updated: 2026-07-05
---

# Connection

## Overview

A **Connection** tracks how connected an Aiko Services process currently
is, as a ladder of `ConnectionState` values:

```
NONE ─► NETWORK ─► BOOTSTRAP ─► TRANSPORT ─► REGISTRAR
        Wi-Fi or   MQTT          MQTT (Ray,   Registrar
        Ethernet   configuration ROS2, ...)   available
        available  found         connected    for use
```

Every process owns exactly one Connection instance
(`aiko.connection`, created as `ProcessData.connection =
Connection("process")`). As the [transport](transport.md) connects or
drops and the [Registrar](registrar.md) is discovered or lost, the process
moves the state up and down the ladder, and every registered handler is
notified of each change.

This solves a start-up ordering problem that pervades distributed
systems: components are constructed before the MQTT server is connected or
the Registrar found, so anything needing those facilities must *wait for a
state, not a moment*. The Connection is deliberately a low-level mechanism
with no static dependencies on the rest of the framework (only the `Lock`
utility).

**Why you'd use it**: defer work until the Registrar is available —
exactly what the [Share](share.md) `ECConsumer` does:

```python
def _connection_state_handler(self, connection, connection_state):
    if connection.is_connected(ConnectionState.REGISTRAR):
        ...  # safe to issue (share ...) requests now

aiko.connection.add_handler(self._connection_state_handler)
```

## For application developers

### Command-line usage

Connection has no CLI of its own; every Aiko Services process embeds one.
Observe it in practice by starting any tool without an MQTT server or
Registrar running — e.g. `aiko_dashboard` or an example such as
`src/aiko_services/examples/aloha_honua/aloha_honua_0.py` — which waits at
`ConnectionState.NONE` / `TRANSPORT` until the infrastructure appears.
State-change logging is visible via the process logger:

```bash
AIKO_LOG_LEVEL_PROCESS=DEBUG aiko_dashboard
# Connection state: NONE --> TRANSPORT
# Connection state: TRANSPORT --> REGISTRAR
```

### Public API

Two plain classes (not Aiko Services Interfaces):

```python
class ConnectionState:
    NONE = "NONE"
    NETWORK = "NETWORK"      # Wi-Fi or Ethernet available
    BOOTSTRAP = "BOOTSTRAP"  # MQTT configuration found
    TRANSPORT = "TRANSPORT"  # MQTT, Ray, ROS2, ZeroMQ, etc
    REGISTRAR = "REGISTRAR"  # Registrar available for use

    states = [NONE, NETWORK, TRANSPORT, REGISTRAR]  # order matters
```

| Operation | Effect |
|-----------|--------|
| `Connection(id)` | New tracker at `ConnectionState.NONE`, with its own `Lock` |
| `add_handler(handler)` | Register `handler(connection, connection_state)`; **called immediately** with the current state, then on every change |
| `remove_handler(handler)` | Deregister |
| `get_state()` | Current `ConnectionState` |
| `is_connected(connection_state)` | `True` if the current state is *at or above* the given rung (raises `ValueError` for a state missing from `states`) |
| `update_state(connection_state, logger=None)` | Set the state and notify all handlers |
| `lock_acquire(location)` / `lock_release()` | Guard compound check-then-update sequences across threads |

The immediate callback from `add_handler()` matters: a component
registering *after* the Registrar was found still learns the current state
right away — no change event is ever "missed".

Because states are ordered, handlers test with `is_connected()` (at least
this rung) rather than equality — robust to future intermediate rungs.

Compound state changes must hold the Connection's lock (the module's own
usage pattern), because the main thread and the MQTT thread can update
concurrently:

```python
try:
    connection.lock_acquire("function_name()")
    ## Critical code ##
finally:
    connection.lock_release()
```

`update_state()` supports this discipline: when given a `logger`, it logs
an error if invoked while the lock is not held, and logs each state change
at DEBUG.

There is no wire protocol: Connection is in-process state. Its *inputs*
arrive over the wire, however — the transport's connect/disconnect
callbacks and the Registrar's retained
`(primary found ...)` / `(primary absent)` boot messages (see
[Registrar](registrar.md)).

## For framework developers (internals)

### Design

```
   MQTT thread                         main / event-loop thread
       │                                        │
       │ on_mqtt_state()                        │ on_registrar()
       ▼                                        ▼
   ┌───────────────────────────────────────────────────────┐
   │ aiko.connection = Connection("process")   [singleton] │
   │   lock ─ serialises check-then-update sequences       │
   │   connection_state:  NONE → TRANSPORT → REGISTRAR     │
   │   connection_state_handlers: [ ... ]                  │
   └───────────────────────────────────────────────────────┘
                          │ update_state() → notify all
          ┌───────────────┼──────────────────┐
          ▼               ▼                  ▼
     ECConsumer      ECProducer       LifeCycleClient
     (share.py)      (share.py)       (lifecycle.py)
```

Key design points:

- **One Connection per process**, class-level on `ProcessData`
  (`aiko.connection`), shared by all Services in the process.
- **Ladder, not a set of flags**: ordering lets `is_connected()` express
  "at least this much connectivity", and lets the process degrade
  gracefully (losing the Registrar drops `REGISTRAR → TRANSPORT`; losing
  MQTT drops to `NONE`).
- **Callers own the transitions**: Connection stores and notifies, but the
  rules for *when* to move rungs live in [Process](process.md)
  (`on_mqtt_state()`, `on_registrar()`), which is also why the lock is
  exposed rather than internalised — the critical section spans the
  caller's check *and* the update.
- **Framework-independent by design**: the module must not acquire static
  dependencies on the framework, so it can underpin bootstrap code.

### Implementation notes

- `update_state()` notifies handlers synchronously on the calling thread —
  which may be the MQTT thread, not the event-loop thread. Handlers must
  therefore be thread-aware; the roadmap direction is to route updates
  through [Event](event.md) loop events instead.
- `add_handler()` ignores duplicate registrations; `remove_handler()` of
  an unknown handler is a no-op.
- `ConnectionState.states` deliberately omits `BOOTSTRAP` — no code sets
  it yet — with the consequence that
  `is_connected(ConnectionState.BOOTSTRAP)` raises `ValueError`.
  `NETWORK` is listed but nothing currently sets it either: in practice
  processes move only through `NONE`, `TRANSPORT` and `REGISTRAR`.
- `process.py` is the only writer: `on_mqtt_state()` sets
  `NONE`/`TRANSPORT` from the transport callback, and `on_registrar()`
  raises to `REGISTRAR` on `(primary found ...)` and lowers to
  `TRANSPORT` on `(primary absent)` — each within
  `lock_acquire()` / `lock_release()`.

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `ConnectionState` | Name the connectivity rungs; define their order; map state → index for comparisons | `Connection` |
| `Connection` | Hold the current state; register/notify handlers (immediately on add, then per change); answer `is_connected()` threshold queries; provide the lock for compound updates; log undisciplined updates | `Lock` (utility); Process (`on_mqtt_state()` / `on_registrar()` writers); [Share](share.md), [LifeCycle](lifecycle.md) and [Dashboard](dashboard.md) handlers (readers) |

## Current limitations and roadmap

- From the source `To Do` list: ensure all updates occur via events
  (handlers, messages and timers) managed by the [Event](event.md) loop
  and executed solely by the event-loop thread — today handlers run on
  whichever thread calls `update_state()`
- `BOOTSTRAP` is defined but absent from `ConnectionState.states`, and
  `NETWORK` is never set — the lower rungs of the ladder are declared
  intent, not implemented behaviour; querying `is_connected(BOOTSTRAP)`
  raises `ValueError`
- Handler notification has no error isolation: one handler raising
  prevents later handlers from seeing the change
- The lock discipline is advisory — `update_state()` only *logs* when
  called unlocked (and only if a logger is passed)
- No unit tests exist for this module (nothing under
  `src/aiko_services/tests/` covers it)

## Related concepts

- [Design overview](design_overview.md)
- [Process](process.md) — owns `aiko.connection` and drives every transition
- [Message](message.md) / [Transport](transport.md) — whose connect and
  disconnect events drive the `TRANSPORT` rung
- [Registrar](registrar.md) — whose discovery and loss drive the
  `REGISTRAR` rung
- [Share](share.md) — ECProducer/ECConsumer wait for `REGISTRAR` before
  issuing share requests
- [LifeCycle](lifecycle.md) — LifeCycleClients defer joining until
  connected
