---
title: Lease
description: A time-limited claim on a resource, built on event-loop
  timers, that expires unless extended — the framework's keep-alive and
  garbage-collection primitive
type: concept
audience: [architects, developers, end-users]
status: work-in-progress
source:
  - src/aiko_services/main/lease.py
related: [design_overview, event, share, lifecycle, pipeline, stream]
version: "0.6"
last_updated: 2026-07-05
---

# Lease

## Overview

A **Lease** is a time-limited claim that expires unless it is extended.
It is the Aiko Services answer to a hard distributed-systems problem:
remote parties disappear without saying goodbye. Rather than holding
resources for absent clients forever, the framework grants them for a
`lease_time` and requires periodic renewal — silence means release.

A Lease is a small in-process object built on [Event](event.md) timer
handlers. It is used throughout the framework:

- **[Share](share.md)**: an `ECProducer` holds an `ECLease` per remote
  consumer subscription, dropping the subscription when the consumer stops
  renewing; an `ECConsumer` holds one auto-extending Lease that re-sends
  its `(share ...)` request before the producer's lease lapses.
- **[Pipeline](pipeline.md)**: each [stream](stream.md) is guarded by a
  grace-time Lease whose expiry handler is `destroy_stream` — a stream
  that stops receiving frames is torn down automatically.
- **[LifeCycle](lifecycle.md)**: the LifeCycleManager wraps client
  creation handshakes and deletions in Leases, so a client that never
  responds is detected.

**Why you'd use it**: track claims that must vanish when their owner does
(the module's own usage example):

```python
from aiko_services.main import *

def lease_expired(lease_uuid):
    if lease_uuid in leases:
        del leases[lease_uuid]

leases = {}
lease_time = 10  # seconds
lease_uuid = "1"
lease = Lease(lease_time, lease_uuid,
    lease_expired_handler=lease_expired, automatic_extend=True)
leases[lease_uuid] = lease
event.loop()
```

## For application developers

### Command-line usage

Lease has no CLI of its own; it is exercised by anything that uses shared
state or streams — for example `aiko_dashboard` (whose ECConsumers hold
auto-extending Leases against every Service they monitor) or a Pipeline
processing a stream. Fine-grained logging of Lease activity:

```bash
AIKO_LOG_LEVEL_LEASE=DEBUG aiko_dashboard
```

### Public API

`Lease` is a plain class — not an Aiko Services Interface:

| Operation | Effect |
|-----------|--------|
| `Lease(lease_time, lease_uuid, lease_expired_handler=None, lease_extend_handler=None, automatic_extend=False)` | Start the expiry timer immediately; with `automatic_extend`, also start a renewal timer at 0.8 × `lease_time` |
| `extend(lease_time=None)` | Restart the expiry timer (optionally with a new duration) and call `lease_extend_handler(lease_time, lease_uuid)` if set |
| `terminate()` | Cancel the timers without calling any handler — normal, deliberate release |

Handler signatures:

```python
def lease_expired_handler(lease_uuid): ...            # lease lapsed
def lease_extend_handler(lease_time, lease_uuid): ... # renewal side-effect
```

The two sides of a keep-alive pairing use the same class differently:

- **Grantor** (e.g. `ECProducer`): creates a plain Lease per client with a
  `lease_expired_handler` that releases the resource; calls `extend()`
  whenever the client renews; calls `terminate()` when the client
  explicitly releases (lease time `0` in the share protocol).
- **Holder** (e.g. `ECConsumer`): creates one Lease with
  `automatic_extend=True` and a `lease_extend_handler` that transmits the
  renewal request — the Lease becomes a self-driving heartbeat.

There is no wire protocol in this module itself — lease times travel
inside the protocols of its users, notably the [Share](share.md) request
`(share response_topic lease_time filter)`. The resulting keep-alive
exchange is a genuine two-party loop:

```
ECConsumer process                          ECProducer process
      │                                            │
      │ Lease(automatic_extend=True)               │
      │──(share topic_out lease_time filter)──────►│ ECLease(lease_time)
      │◄─(item_count N) (response items …)─────────│
      │                                            │
      │  … 0.8 × lease_time elapses …              │
      │  extend() fires lease_extend_handler       │
      │──(share topic_out lease_time filter)──────►│ extend(lease_time)
      │                    …repeats…               │
      │                                            │
      │  (consumer dies silently)                  │
      │                          lease_time passes │ lease_expired_handler:
      │                                            │ drop the subscription
```

## For framework developers (internals)

### Design

```
   Lease(lease_time, lease_uuid)
   ┌────────────────────────────────────────────────────┐
   │ expiry timer   ── fires at lease_time ──►          │
   │                   _lease_expired_timer():          │
   │                     remove timer,                  │
   │                     lease_expired_handler(uuid)    │
   │                                                    │
   │ renewal timer  ── fires at 0.8 × lease_time ──►    │  (only when
   │  (periodic)       extend(): restart expiry timer,  │   automatic_
   │                   lease_extend_handler(time, uuid) │   extend=True)
   └────────────────────────────────────────────────────┘
              both timers run on the event-loop thread
```

Key design points:

- **A Lease is two [Event](event.md) timers** and nothing more — no
  threads, no wall-clock bookkeeping. Expiry is a one-shot timer that
  removes itself; renewal (when enabled) is periodic at
  `_LEASE_EXTEND_TIME_FACTOR = 0.8` of the lease time, leaving a 20 %
  margin for the renewal message to arrive before the far side expires.
- **Handlers are optional**: a Lease with no handlers is a pure timeout.
- **Expiry is silent by design on `terminate()`**: deliberate release must
  not trigger the same cleanup as failure.
- **Subclassing for context**: `share.py` defines
  `ECLease(Lease)` adding only a `filter` attribute — the pattern for
  attaching per-lease context is a small subclass (the Pipeline instead
  attaches `stream_lease.stream = Stream(...)` dynamically).

### Implementation notes

- Timer identity is the *bound method* `self._lease_expired_timer`, unique
  per Lease instance — which is what makes
  `event.remove_timer_handler()` safe despite its match-by-handler
  limitation (see [Event](event.md) internals).
- `extend()` restarts the expiry timer by remove-then-add; the elapsed
  fraction of the old period is discarded, so the new expiry is a full
  `lease_time` from the moment of extension.
- With `automatic_extend`, the renewal timer's period is fixed at
  construction (0.8 × the *original* `lease_time`); a later
  `extend(new_lease_time)` changes the expiry duration but not the renewal
  cadence.
- `extend` doubles as the renewal timer handler — timer handlers are
  invoked with no arguments, relying on the `lease_time=None` default.
- `AIKO_LOG_LEVEL_LEASE` (default `INFO`) controls the module logger;
  DEBUG traces create / extend / expire / terminate per `lease_uuid`.

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `Lease` | Hold `lease_time` / `lease_uuid`; run the expiry timer; optionally self-renew at 0.8 × lease time; notify expiry and extension handlers; cancel cleanly on `terminate()` | [Event](event.md) (timer handlers); handler callables supplied by the owner |
| `ECLease(Lease)` (in share.py) | Carry the consumer's share `filter` alongside the lease | [Share](share.md) `ECProducer` |

## Current limitations and roadmap

From the source `To Do` list:

- Consider changing `lease_time: seconds` to
  `lease: {start: UTC, duration: seconds}` — absolute start times rather
  than relative durations
- Lease request *rejection* responses for grantors, e.g.
  `(lease_rejected maximum_time 60)` and
  `(lease_rejected no_resource memory)` — currently a grantor has no
  protocol for declining a lease

Additional observations:

- The renewal cadence does not track lease-time changes made via
  `extend(new_lease_time)` when `automatic_extend` is in use
- There is no unit test for Lease (nothing under
  `src/aiko_services/tests/` covers it); timer-based behaviour would suit
  a virtual-clock test harness

## Related concepts

- [Design overview](design_overview.md)
- [Event](event.md) — the timer machinery a Lease is built from
- [Share](share.md) — producer- and consumer-side leases keeping
  eventually-consistent state subscriptions alive
- [Stream](stream.md) / [Pipeline](pipeline.md) — stream grace-time
  leases that garbage-collect idle streams
- [LifeCycle](lifecycle.md) — handshake and deletion leases around
  managed clients
