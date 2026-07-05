---
title: LifeCycle
description: The LifeCycleManager / LifeCycleClient pair — one Actor creates,
  tracks and destroys a fleet of client Actors, with handshake and deletion
  Leases guarding every transition
type: concept
audience: [architects, developers, end-users]
status: work-in-progress
source:
  - src/aiko_services/main/lifecycle.py
related: [design_overview, process_manager, lease, share, actor, service,
  registrar, discovery, connection, hyperspace]
version: "0.6"
last_updated: 2026-07-05
---

# LifeCycle

## Overview

**LifeCycle** is the managed create-track-destroy relationship between one
**LifeCycleManager** and many **LifeCycleClients**. The manager creates
clients (typically as separate operating system processes via
[ProcessManager](process_manager.md)), each client *handshakes* back to its
manager once it is up and registered, and thereafter the manager observes
each client's shared state — its `lifecycle` variable — through an
`ECConsumer` (see [Share](share.md)). Every transition is guarded by a
[Lease](lease.md): a handshake Lease catches clients that never come up, and
a deletion Lease catches clients that refuse to die.

Both roles are **mixin Interfaces**, not standalone Actors: an
[Actor](actor.md) *incorporates* LifeCycleManager or LifeCycleClient
alongside its own behaviour. [HyperSpace](hyperspace.md) is designed as a
LifeCycleManager of Categories; the `LifeCycleManagerTest` /
`LifeCycleClientTest` Actors in the source demonstrate the pattern
end-to-end.

**Why you'd use it**: whenever one Actor must own a dynamic fleet of worker
Actors — spin up N workers, know reliably when each is ready (not merely
forked), watch each worker's state change, and clean up stragglers
automatically:

```bash
cd src/aiko_services/main
./lifecycle.py manager 4     # create manager, which spawns 4 clients
```

## For application developers

### Command-line usage

There is no console script for this concept; the CLI is a test harness for
exercising the manager / client pair. Run the module directly:

```bash
cd src/aiko_services/main

./lifecycle.py manager [CLIENT_COUNT]     # LifeCycleManager Actor
                                          # CLIENT_COUNT default: 1

./lifecycle.py client CLIENT_ID LIFECYCLE_MANAGER_TOPIC
                                          # LifeCycleClient Actor (normally
                                          # spawned by the manager, not you)
```

The manager waits for the [Registrar](registrar.md) connection, then uses
its embedded [ProcessManager](process_manager.md) to run
`./lifecycle.py client <id> <manager topic_path>` once per requested client.
Watch the fleet assemble on the [Dashboard](dashboard.md): the manager's
shared state shows `lifecycle_manager_clients_active` and one
`lifecycle_manager.<id>` entry per handshaken client.

Fine-grained logging is controlled by an environment variable:

```bash
AIKO_LOG_LEVEL_LIFECYCLE=DEBUG ./lifecycle.py manager 2
```

### Public API

Two public Interfaces, each paired with a private Interface that a concrete
implementation must fulfil:

```python
class LifeCycleManager(ServiceProtocolInterface):
    Interface.default("LifeCycleManager",
        "aiko_services.main.lifecycle.LifeCycleManagerImpl")

    @abstractmethod
    def lcm_create_client(self, parameters=None):  # bookkeeping + create
    @abstractmethod
    def lcm_delete_client(self, client_id):        # bookkeeping + delete

class LifeCycleClient(ServiceProtocolInterface):
    Interface.default("LifeCycleClient",
        "aiko_services.main.lifecycle.LifeCycleClientImpl")
```

`LifeCycleManagerImpl` handles all bookkeeping — client ids, handshake and
deletion Leases, per-client `ECConsumer`s, shared-state updates — and
delegates the *mechanism* of creation and deletion to private methods your
Actor provides (`LifeCycleManagerPrivate`):

| Private method | Your Actor implements |
|----------------|-----------------------|
| `_lcm_create_client(client_id, lifecycle_manager_topic, parameters)` | Actually create the client (e.g. `ProcessManager.create()`) |
| `_lcm_delete_client(client_id, force=False)` | Actually destroy the client (e.g. `ProcessManager.destroy()`) |

`LifeCycleManagerImpl` itself provides `_lcm_get_clients()`,
`_lcm_get_handshaking_clients()` (ids created but not yet handshaken) and
`_lcm_lookup_client_state(client_id, key)` (read a value from a client's
observed shared state).

Incorporating the manager into an Actor follows the standard composition
idiom (from `LifeCycleManagerTestImpl`):

```python
class LifeCycleManagerTest(Actor, LifeCycleManager): ...

class LifeCycleManagerTestImpl(LifeCycleManagerTest):
    def __init__(self, context, client_count):
        context.call_init(self, "Actor", context)
        ...
        context.get_implementation("LifeCycleManager").__init__(self,
            self._lifecycle_client_change_handler, self.ec_producer)

    def _lcm_create_client(self, client_id, lifecycle_manager_topic,
        parameters):
        self.process_manager.create(
            parameters, ["client", str(client_id), lifecycle_manager_topic],
            client_id)

    def _lcm_delete_client(self, client_id, force=False):
        self.process_manager.destroy(client_id, kill=True)
```

The `lifecycle_client_change_handler(client_id, command, item_name,
item_value)` is invoked on every observed change to a client's shared
state (filtered by `client_state_consumer_filter`, default `"(lifecycle)"`),
and with `("update", "lifecycle", "absent")` when the Registrar reports the
client gone.

On the client side, `LifeCycleClientImpl.__init__(context, client_id,
lifecycle_manager_topic, ec_producer)` records the manager's topic in
shared state (`lifecycle_client.lifecycle_manager_topic`) and performs the
handshake automatically once the [Connection](connection.md) reaches the
Registrar state.

**Wire protocol.** The handshake is a single one-way message published by
the client to the manager's *control* topic:

```
{manager topic_path}/control  ◄─  (add_client CLIENT_TOPIC_PATH CLIENT_ID)
```

Everything else rides on existing protocols — Registrar discovery for
liveness, `ECProducer` / `ECConsumer` shared state for observation.

**Sequence** — creation, handshake and observation:

```
LifeCycleManager          ProcessManager        LifeCycleClient   Registrar
      │                        │                      │               │
      │ lcm_create_client()    │                      │               │
      │──create(id)───────────►│──spawn process──────►│               │
      │ start handshake Lease  │                      │               │
      │ (30 s default)         │                      │──(add ...)───►│
      │                        │            Registrar connected       │
      │◄─(add_client TOPIC_PATH ID)──────────────────│               │
      │ terminate Lease        │                      │               │
      │ ECConsumer ◄── observe {TOPIC_PATH}/control shared state      │
      │ do_discovery() ◄────── notified if client removed ───────────│
```

If the handshake Lease expires first, the manager calls
`_lcm_delete_client(client_id)` — a client that never announced itself is
reclaimed. Deletion mirrors this: `lcm_delete_client()` starts a deletion
Lease, and if the client's Service has not left the Registrar before the
Lease expires, `_lcm_delete_client(client_id, force=True)` is called.

Service protocols: `.../lifecycle_manager:0` and `.../lifecycle_client:0`
(under `SERVICE_PROTOCOL_AIKO`).

## For framework developers (internals)

### Design

```
  LifeCycleManager Actor
  ┌─────────────────────────────────────────────────────┐
  │ lcm_handshakes:       {client_id: Lease}   (30 s)   │
  │ lcm_deletion_leases:  {client_id: Lease}   (30 s)   │
  │ lcm_lifecycle_clients:{client_id:                   │
  │     LifeCycleClientDetails(client_id, topic_path,   │
  │                            ec_consumer)}            │
  │ shared state: lifecycle_manager.<id> = topic_path   │
  │               lifecycle_manager_clients_active = N  │
  └────────────┬────────────────────────────────────────┘
               │ creates via _lcm_create_client()
               ▼
  LifeCycleClient Actors (usually separate processes)
  each publishes (add_client ...) once Registrar-connected
```

Key design points:

- **Template method pattern**: the public `lcm_create_client()` /
  `lcm_delete_client()` own the bookkeeping and call down to the
  `_lcm_*` primitives that the incorporating Actor supplies. Creation
  mechanism (ProcessManager, in-process, Ray, ...) is a policy decision
  left to the implementation.
- **Leases make every transition self-healing**: no reply within the
  handshake window ⇒ reclaim; no Registrar removal within the deletion
  window ⇒ force-kill.
- **Observation, not polling**: after the handshake the manager consumes
  the client's `ECProducer` state (filter default `"(lifecycle)"`), so
  client state changes stream to the manager — and to the Dashboard.
- The design direction (per the source To Do) is to generalise this into
  "one manager Actor creates other client Actors and observes any chosen
  shared variables", and to refactor the handshake out as a reusable
  concept for [discovery](discovery.md).

### Implementation notes

- `_lcm_topic_control_handler()` is registered on the manager's
  `topic_control` and only understands `add_client`. An `add_client` for an
  unknown (never-created or already-expired) `client_id` is logged and
  ignored.
- On handshake completion the manager calls `do_discovery()` with a
  `NullClass` interface purely to receive the *remove* callback — proxy
  creation is irrelevant, only Registrar removal notification is wanted.
- `_lcm_service_remove_handler()` terminates the client's `ECConsumer`,
  cancels any pending deletion Lease, deletes the
  `LifeCycleClientDetails`, updates shared state, and notifies the change
  handler with `(client_id, "update", "lifecycle", "absent")`.
- The per-client shared-state entry
  `lifecycle_manager.<client_id> = topic_path` is flagged in the source as
  a significant performance problem at large client counts.
- `LifeCycleClientImpl` guards with `lcc_added_to_lcm` so the handshake is
  published only once, even if the Connection handler fires again.
- `_lcc_lifecycle_manager_change_handler()` is currently a no-op (`pass`):
  a client does *not* yet react when its manager disappears.

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `LifeCycleManager` (Interface) | Declare the public contract: `lcm_create_client()`, `lcm_delete_client()` | `ServiceProtocolInterface` (parent) |
| `LifeCycleManagerPrivate` (Interface) | Declare the primitives an implementation supplies: `_lcm_create_client()`, `_lcm_delete_client()`, `_lcm_get_clients()`, `_lcm_get_handshaking_clients()`, `_lcm_lookup_client_state()` | `Interface` (parent) |
| `LifeCycleManagerImpl` | Bookkeeping: client ids, handshake / deletion [Leases](lease.md), per-client `ECConsumer`s, shared-state fleet view, change-handler notifications | `Lease`, `ECConsumer` / `ECProducer` ([Share](share.md)), `do_discovery()` ([Discovery](discovery.md)) |
| `LifeCycleClient` / `LifeCycleClientPrivate` (Interfaces) | Declare the client contract and its private handlers | `ServiceProtocolInterface`, `Interface` (parents) |
| `LifeCycleClientImpl` | Record manager topic in shared state; publish `(add_client ...)` handshake once Registrar-connected; watch for manager removal | `ECProducer`, [Connection](connection.md), `do_discovery()` |
| `LifeCycleClientDetails` | Value object: `client_id`, `topic_path`, `ec_consumer` | — |
| `LifeCycleManagerTest[Impl]` / `LifeCycleClientTest[Impl]` | End-to-end demonstration Actors used by the CLI; manager spawns clients via ProcessManager | `Actor`, [ProcessManager](process_manager.md) |

## Current limitations and roadmap

From the source `To Do` lists — highlights:

- **CRITICAL** (source's own marking): check MQTT message volume — every
  LifeCycleClient currently uses ActorDiscovery / ServicesCache and so
  receives notifications about *every other* Service on the Registrar
  `/out` topic; the Registrar should support server-side filtering
- **Bugs noted in the source**: `event.py` `remove_timer_handler()` may
  remove the wrong handler when several timers share one function; neither
  manager nor client yet handles network degradation
  (ConnectionState changes) or lease expiry gracefully — should the
  manager recreate or terminate clients?
- `lifecycle_manager.destroy(lifecycle_client_id)` unimplemented; a
  client does not yet exit when its manager exits (change handler is a
  no-op `pass`)
- Performance: LifeCycleClient creation appears delayed / "chunky" on the
  Dashboard; per-client shared-state updates are costly at scale
- Support creating clients in the same process (not only as separate
  processes); use ProcessManager's `process_exit_handler` to detect
  unexpected client process death
- Generalise: any manager Actor observing any chosen shared variables (not
  just `lifecycle`); refactor Handshake into a standalone reusable concept;
  refactor ProcessManager to provide functionality without being an Actor

## Related concepts

- [Design overview](design_overview.md)
- [ProcessManager](process_manager.md) — the usual client-creation mechanism
- [Lease](lease.md) — guards the handshake and deletion windows
- [Share](share.md) — ECProducer / ECConsumer state observation
- [Actor](actor.md) / [Service](service.md) — what managers and clients are
- [Registrar](registrar.md) — liveness source of truth
- [Discovery](discovery.md) — `do_discovery()` removal notifications
- [Connection](connection.md) — the handshake fires on Registrar connection
- [HyperSpace](hyperspace.md) — designed as a LifeCycleManager of Categories
