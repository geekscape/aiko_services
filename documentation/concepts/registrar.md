---
title: Registrar
description: The Service discovery hub — maintains the live directory of all
  Services, streams add / remove updates, answers share and history queries,
  and elects a primary via a bootstrap topic
type: concept
audience: [architects, developers, end-users]
status: work-in-progress
source:
  - src/aiko_services/main/registrar.py
related: [design_overview, process, service, discovery, share, connection,
  state, event, message, transport, dashboard, lifecycle]
version: "0.6"
last_updated: 2026-07-05
---

# Registrar

## Overview

The **Registrar** is the discovery hub of an Aiko Services deployment: a
[Service](service.md) that maintains the live directory of every other
Service — its topic path, name, protocol, transport, owner and tags — and
streams (filtered) updates to anyone who asks. Every process finds the
primary Registrar through a single retained MQTT bootstrap topic, registers
its Services there, and learns about all other Services from it. All
higher-level [discovery](discovery.md) — `do_command()`, `do_request()`,
the `ServicesCache`, the [Dashboard](dashboard.md) — is built on the
Registrar's wire protocol.

A deployment runs exactly one *primary* Registrar per namespace; additional
Registrars become *secondaries* and promote themselves if the primary
disappears (work-in-progress — see the roadmap).

**Why you'd use it**: nothing else works without it — it is the first thing
started in every Aiko Services system:

```bash
aiko_registrar &
aiko_dashboard        # everything the Dashboard shows comes via the Registrar
```

## For application developers

### Command-line usage

The console script is `aiko_registrar` (defined in `pyproject.toml`); the
module fallback is `src/aiko_services/main/registrar.py`:

```bash
aiko_registrar          # run a Registrar Service (foreground)
aiko_registrar &        # ... or in the background
```

There are no options yet — `--primary` (force take-over of the primary
role), `show [registrar_filter]` and `kill service_filter` appear in the
source To Do list but are **not implemented**.

Because the wire protocol is plain S-expressions over MQTT, `mosquitto_pub`
/ `mosquitto_sub` work as a diagnostic CLI (from the source header, where
`TOPIC_PATH=$NAMESPACE/$HOST/$PID/$SID` is the Registrar's own topic path):

```bash
mosquitto_pub -t $TOPIC_PATH/in -m  \
    "(add topic_prefix name protocol transport owner $TAGS)"
mosquitto_pub -t $TOPIC_PATH/in -m "(remove topic_prefix)"
mosquitto_pub -t $TOPIC_PATH/in -m "(share response * * * * $TAGS)"
```

Observing the whole conversation is the single most useful Aiko Services
debugging technique:

```bash
mosquitto_sub -t '#' -v
```

### Public API

```python
class Registrar(Service):
    Interface.default("Registrar", "aiko_services.main.registrar.RegistrarImpl")
```

The Registrar Interface currently declares no Python methods — defining the
public API on the Interface is the first item on the source To Do list. The
public contract *is* the wire protocol (currently version 2,
`REGISTRAR_VERSION`), which application code normally reaches through
`do_discovery()` / `do_command()` / `do_request()` and the `ServicesCache`
(see [Discovery](discovery.md) and [Share](share.md)) rather than directly.

**Bootstrap topic.** The primary announces itself on the retained topic
`{namespace}/service/registrar` (`aiko.TOPIC_REGISTRAR_BOOT`):

```
(primary found TOPIC_PATH VERSION TIME_STARTED)   # retained
(primary absent)                                  # retained; also the LWT
```

`(primary absent)` is also installed as the primary's MQTT Last Will and
Testament, so a crashed Registrar is announced automatically by the MQTT
server. Every process subscribes to this topic at start-up; "found" moves
its [Connection](connection.md) state to `REGISTRAR` and triggers
registration of all its Services.

**Topics the Registrar subscribes to:**

```
{namespace}/service/registrar   (primary found ...) | (primary absent)
{registrar topic_path}/in       (add ...) (remove ...) (share ...) (history ...)
{namespace}/+/+/+/state         (absent)      ← Service/Process LWT death notices
```

**Registration** (published by `aiko.process` for every Service that has a
protocol):

```
(add TOPIC_PATH NAME PROTOCOL TRANSPORT OWNER (TAG ...))
(remove TOPIC_PATH)
```

Every accepted `add` / `remove` is re-broadcast verbatim on the Registrar's
`topic_out` — subscribing to `{registrar topic_path}/out` is how caches
stay current without polling.

**Queries.** `share` returns the current directory filtered by
ServiceFilter fields (`*` matches anything); `history` returns recently
*removed* Services (count `*` means the default limit, 16):

```
(share   RESPONSE_TOPIC NAME PROTOCOL TRANSPORT OWNER TAGS)
(history RESPONSE_TOPIC COUNT|*)
```

Responses use the standard item-count grammar on `RESPONSE_TOPIC`:

```
(item_count N)
(add TOPIC_PATH NAME PROTOCOL TRANSPORT OWNER (TAG ...))              × N
      # history records append two fields: TIME_ADD TIME_REMOVE
```

After a `share` response, the Registrar publishes `(sync RESPONSE_TOPIC)`
on its `topic_out` — the marker a `ServicesCache` uses to know its initial
snapshot is complete and the live `add` / `remove` stream is now
authoritative.

**Sequence** — a Service starts, registers and is discovered:

```
 Process (new Service)         MQTT retained topic          Registrar
      │                              │                          │
      │◄─(primary found T V TS)──────│      (published at primary
      │  Connection → REGISTRAR      │       promotion, retained)
      │                              │                          │
      │──(add TOPIC NAME PROTO ...)──────────────────────────► /in
      │                              │      store; service_count++
      │◄─────────────────────(add TOPIC NAME PROTO ...)─────── /out
      │                              │                          │
   Discovering client               │                          │
      │──(share MY_TOPIC * * * * *)──────────────────────────► /in
      │◄─(item_count N)──────────────────────────── to MY_TOPIC │
      │◄─(add ...) × N ───────────────────────────── to MY_TOPIC│
      │◄─(sync MY_TOPIC)────────────────────────────────────── /out
      │  then track live (add ...) / (remove ...) on /out       │
```

**Death notices.** When a process dies, its MQTT LWT publishes `(absent)`
on `{topic_path}/state` (see [State](state.md)); the Registrar removes the
Service, stamps `time_remove`, pushes the record onto its history ring
buffer (4096 entries) and broadcasts `(remove TOPIC_PATH)`. A state topic
with service id `0` means the whole *process* terminated, and all of that
process's Services are removed together.

**Shared state** (visible on the Dashboard via `ECProducer`): `aiko_id`,
`lifecycle` (the election state: `start` → `primary_search` → `secondary` |
`primary`), `log_level`, `source_file`, `service_count`.

## For framework developers (internals)

### Design

```
              ┌────────────────────────────────────────────┐
              │ RegistrarImpl (Service)                    │
              │                                            │
   /in ──────►│ _topic_in_handler: add/remove/share/history│
   +/+/+/state│ _service_state_handler: (absent) → remove  │
   boot topic►│ _registrar_handler: found/absent           │
              │                                            │
              │ services: Services()   (live directory,    │
              │   nested dict: process → service → details)│
              │ history: deque(maxlen=4096) (removed)      │
              │                                            │
              │ StateMachine:                              │
              │  start ─initialize─► primary_search        │
              │   primary_search ─primary_found─► secondary│
              │   primary_search ─primary_promotion─►      │
              │                              primary       │
              │   primary|secondary ─primary_failed─►      │
              │                              primary_search│
              └────────────────────────────────────────────┘
```

Key design points:

- The Registrar is a plain **Service**, not an Actor — commands arrive as
  raw payloads on `topic_in` handled by `_topic_in_handler()`, not as
  remote method calls (whether it should become an Actor, and indeed a
  sub-class of [Category](category.md), is an open To Do).
- **Election by retained message**: on `initialize` the state machine
  enters `primary_search` and starts a 2-second timer
  (`_PRIMARY_SEARCH_TIMEOUT`). If the bootstrap topic delivers
  `(primary found ...)` first, this Registrar becomes a *secondary*;
  otherwise the timer fires `primary_promotion`. On promotion the new
  primary clears the retained topic, installs the `(primary absent)` LWT,
  then publishes the retained `(primary found ...)` announcement. If the
  primary fails (`(primary absent)` observed), survivors drop their
  directory and re-enter `primary_search`.
- **State lives in one place**: the primary's in-memory `Services`
  directory plus the history ring buffer. Secondaries currently hold
  nothing (acquiring the primary's state is on the roadmap); clients keep
  eventually-consistent copies via `ServicesCache`.
- The directory is ordered so that the Registrar's own entry sorts first
  (`Services.add_service()` special-cases `REGISTRAR_PROTOCOL`), which
  keeps the Registrar at the top of Dashboard listings.

### Implementation notes

- `StateMachineModel` drives `StateMachineOld` (see [State](state.md));
  each `on_enter_*` callback updates the shared `lifecycle` value so the
  election is observable remotely.
- `on_enter_primary()` wraps LWT installation in `try/except SystemError`
  — if the MQTT server is unavailable the transition rolls back via
  `primary_failed`.
- `_service_add()` ignores duplicate `add`s for a known `topic_path`, and
  re-publishes the *original inbound payload* on `topic_out` rather than
  regenerating it.
- Timestamps (`time_add`, `time_remove`, and the boot announcement's
  `TIME_STARTED`) use `time.monotonic()` — meaningful for ordering within
  a host, not wall-clock time.
- The client-side counterparts live elsewhere and are worth reading
  together with this file: `process.py` (`on_registrar()`,
  `_add_service_to_registrar()`) and `share.py` (`ServicesCache`
  history → share → loaded → ready start-up sequence).

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `Registrar` (Interface) | Declare the Registrar Service type (no Python methods yet — the contract is the wire protocol) | `Service` (parent Interface) |
| `RegistrarImpl` | Maintain the `Services` directory and removal history; handle `add` / `remove` / `share` / `history`; re-broadcast changes on `topic_out`; watch `+/+/+/state` for deaths; run the primary election | `Services` / `ServiceTopicPath` ([Service](service.md)); `ECProducer` ([Share](share.md)); `StateMachineOld` ([State](state.md)); `event` timers ([Event](event.md)); `aiko.message` ([Message](message.md)) |
| `StateMachineModel` | Define states / transitions; on promotion publish the retained announcement and install the `(primary absent)` LWT | `StateMachineOld`, `ECProducer`, `aiko.message` |

## Current limitations and roadmap

From the source `To Do` list — highlights (the source marks several as
**BUG**):

- **BUG**: a stale retained `(primary found ...)` on the bootstrap topic
  (e.g. after a system crash where no LWT fired) prevents a fresh
  Registrar from ever becoming primary
- **BUG**: with multiple secondaries, when the primary fails *all*
  secondaries promote themselves to primary
- **BUG** (noted at `_service_remove()`): process-level removal of all of
  a process's Services needs review; also `service_count` should be
  coerced with `int()` when updated via ECProducer
- `--primary` (forced take-over), `show`, `kill` CLI commands are
  planned, not implemented
- Secondaries should acquire the primary's history / directory, announce
  themselves on the bootstrap topic, and the Dashboard should surface
  primary / secondary health
- Define the public API as methods on the Registrar Interface; consider
  Registrar as an Actor and as a sub-class of Category; reimplement
  ServicesCache using ECProducer / ECConsumer
- Proper protocol matching (interface-style, with inheritance) instead of
  exact string comparison; allow Services to update their details (e.g.
  tags) on the fly
- Robustness: handle MQTT server restart or migration to another host;
  real consensus (the source cites Raft and CRDTs) for
  primary / secondary replication

## Related concepts

- [Design overview](design_overview.md)
- [Process](process.md) — performs the boot handshake and (re)registers its
  hosted Services
- [Service](service.md) — what is registered; `Services`, topic paths, tags
- [Discovery](discovery.md) — `do_discovery()` et al. build on the Registrar
- [Share](share.md) — `ServicesCache` consumes the share / history protocol
- [Connection](connection.md) — the `REGISTRAR` connection state
- [State](state.md) — the election state machine; `(absent)` death notices
- [Message](message.md) / [Transport](transport.md) — MQTT, retained
  messages and Last Will and Testament
- [Dashboard](dashboard.md) — the human view of the Registrar's directory
- [LifeCycle](lifecycle.md) — relies on Registrar liveness notifications
