---
title: Share (Eventual Consistency)
description: Eventually-consistent shared state between Services —
  ECProducer publishes a dictionary of live state that any number of
  ECConsumers replicate and watch, plus the ServicesCache replica of the
  Registrar
type: concept
audience: [architects, developers, end-users]
status: work-in-progress
source:
  - src/aiko_services/main/share.py
related: [design_overview, service, actor, registrar, lease, connection,
  dashboard]
version: "0.6"
last_updated: 2026-07-05
---

# Share (Eventual Consistency)

## Overview

**Share** is the Aiko Services mechanism for distributed state: a
[Service](service.md) owns a dictionary (its *share*), an **ECProducer**
publishes every change to it, and any number of **ECConsumers** — in the
[Dashboard](dashboard.md), in other Services, on other hosts — hold a
local replica (*cache*) that converges on the producer's state. "EC"
stands for *Eventual Consistency*: consumers synchronize with a snapshot,
then apply incremental add/update/remove messages, protected by a
[Lease](lease.md) that is automatically extended while the consumer is
alive.

Every [Actor](actor.md) gets a share and an ECProducer automatically
(`self.share`, `self.ec_producer`), which is why an Actor's `lifecycle`,
`log_level` and any application state appear live in the Dashboard with
no extra code. [Category](category.md) stores its entries in the share;
the [Registrar](registrar.md) is observed through the related
**ServicesCache**, also defined in `share.py`.

**Why you'd use it**: to observe — or remotely change — a Service's live
state without polling and without writing any protocol code:

```python
# Producer side (any Service; Actors get this for free)
self.share = {"lifecycle": "ready", "temperature": 25}
self.ec_producer = ECProducer(self, self.share)

# Consumer side (any Service, anywhere on the network)
self.cache = {}
self.ec_consumer = ECConsumer(
    self, 0, self.cache, producer_topic_control, filter="*")
self.ec_consumer.add_handler(self.change_handler)
```

## For application developers

### Command-line usage

There is no `aiko_share` console script; `share.py` provides two built-in
test commands (run the module directly):

```bash
aiko_registrar                              # prerequisite, in another shell
cd src/aiko_services/main

./share.py sc_test                          # ServicesCache test
./share.py ec_test                          # start an ECProducer test Service
./share.py ec_test PRODUCER_PID [EC_PRODUCER_SID] [FILTER]
                                            # start an ECConsumer against it
```

`ec_test` without arguments creates a producer whose share contains
`lifecycle`, `log_level`, `source_file` and a nested `items` dictionary;
with the producer's process id it creates a consumer that replicates and
logs every change.

Because the wire protocol is plain S-expressions over MQTT, a producer
can be exercised directly with the mosquitto tools (from the source
usage header):

```bash
NAMESPACE=aiko; HOST=localhost
PRODUCER_PID=`ps ax | grep python | grep share.py | xargs | cut -d" " -f1`
TOPIC_PATH=$NAMESPACE/$HOST/$PRODUCER_PID/1

mosquitto_sub -t '#' -v                     # watch everything

mosquitto_pub -t $TOPIC_PATH/control -m "(add count 0)"
mosquitto_pub -t $TOPIC_PATH/control -m "(update count 1)"
mosquitto_pub -t $TOPIC_PATH/control -m "(remove count)"
mosquitto_pub -t $TOPIC_PATH/control -m "(share topic 0 *)"
mosquitto_pub -t $TOPIC_PATH/control -m "(share topic 0 (lifecycle x))"
```

Logging detail is controlled with `AIKO_LOG_LEVEL_SHARE`
(`ERROR`, `WARNING`, `INFO`, `DEBUG`).

### Public API

**ECProducer** — wraps a Service's share dictionary:

| Operation | Effect |
|-----------|--------|
| `ECProducer(service, share, topic_in=None, topic_out=None)` | Listen for commands on `topic_in` (default: the Service's `topic_control`), publish changes on `topic_out` (default: `topic_state`); adds the `ec=true` tag to the Service |
| `get(item_name)` | Read an item (dotted path), `None` if absent |
| `update(item_name, item_value)` | Set an item (creating the path) and notify handlers and lease-holding consumers |
| `remove(item_name)` | Delete an item and notify |
| `add_handler(handler)` / `remove_handler(handler)` | Local change callbacks `handler(command, item_name, item_value)`; on registration the handler is replayed an `"add"` for every existing item |

**ECConsumer** — replicates a producer's share into a local cache:

| Operation | Effect |
|-----------|--------|
| `ECConsumer(service, ec_consumer_id, cache, ec_producer_topic_control, filter="*")` | Subscribe a private response topic and, once the Registrar is connected, request the share under a 300-second auto-extending lease |
| `add_handler(handler)` / `remove_handler(handler)` | Change callbacks `handler(ec_consumer_id, command, item_name, item_value)`; replayed with `"add"` for existing cache items |
| `cache_state` | `"empty"` until the initial snapshot completes, then `"ready"` |
| `terminate()` | Unsubscribe, clear the cache and cancel the lease (`lease_time=0` share request) |

Item names use a dotted path with a **maximum depth of two**
(`services.test` is valid, `a.b.c` raises `ValueError`).

**Wire protocol.** Commands *to* the producer (on its `topic_control`):

```
(add ITEM_NAME ITEM_VALUE)                  # create (or update) an item
(update ITEM_NAME ITEM_VALUE)               # update (or create) an item
(remove ITEM_NAME)                          # delete an item
(share RESPONSE_TOPIC LEASE_TIME FILTER)    # snapshot + subscription lease
```

`FILTER` is `*` or a list of item-name prefixes, e.g. `(lifecycle
services)` — an item matches if its name equals a filter entry or starts
with `ENTRY.`. `LEASE_TIME 0` means either "one-shot snapshot, no lease"
(if no lease exists for that response topic) or "cancel my lease" (if one
does); a positive lease time creates or extends the lease.

Messages *from* the producer:

```
RESPONSE_TOPIC   (item_count N)             # snapshot begins
                 (add ITEM_NAME ITEM_VALUE) # repeated N times
RESPONSE_TOPIC   (add|update ITEM_NAME ITEM_VALUE)
                 (remove ITEM_NAME)         # incremental, while leased
topic_state      (add|update|remove ...)    # echo of accepted commands
                 (sync RESPONSE_TOPIC)      # snapshot for that consumer done
```

**The synchronization round-trip** (the ECConsumer's private response
topic is `CONSUMER_TOPIC_PATH/PRODUCER_TOPIC_CONTROL/ID/in`):

```
ECConsumer                                     ECProducer
     │                                              │
     │  Registrar connected (ConnectionState)       │
     │──(share RESPONSE_TOPIC 300 *)──────────────► │  topic_control
     │                                              │  filter share,
     │                                              │  create 300 s lease
     │ ◄─(item_count N)─────────────────────────────│  RESPONSE_TOPIC
     │ ◄─(add ITEM_NAME ITEM_VALUE)  × N ───────────│  RESPONSE_TOPIC
     │  cache_state = "ready"                       │
     │                                       (sync RESPONSE_TOPIC)
     │                                              │  on topic_state
     │       ... producer state changes ...         │
     │ ◄─(update ITEM_NAME ITEM_VALUE)──────────────│  while lease valid
     │                                              │
     │──(share RESPONSE_TOPIC 300 *)──────────────► │  automatic lease
     │                                              │  extension
```

If the lease expires (consumer gone), the producer silently drops it and
stops publishing to that response topic.

**ServicesCache** — a local, continuously updated replica of the
[Registrar](registrar.md)'s Services, used by the Dashboard and
[Discovery](discovery.md):

```python
services_cache = services_cache_create_singleton(
    aiko.process, event_loop_start=True, history_limit=4)
services_cache.wait_ready()
services = services_cache.get_services()    # a service.py Services collection
history = services_cache.get_history()      # recently removed Services
services_cache.add_handler(service_change_handler, service_filter)
```

The handler receives `("sync", None)` once loaded, then
`("add"|"remove", service_details)` as Services come and go. Cache states
progress `empty → history → share → loaded → ready` (the `history` state
only occurs when `history_limit > 0`).

## For framework developers (internals)

### Design

```
   Producer Service                        Consumer Services
   ┌───────────────────────┐    lease      ┌──────────────────┐
   │ share {…}             │◄──(share …)───│ cache {…} replica│
   │ ECProducer            │               │ ECConsumer       │
   │  ├─ leases: topic --> │──snapshot────►│  handlers        │
   │  │        ECLease     │──increments──►│                  │
   │  └─ handlers (local)  │               └──────────────────┘
   └───────────────────────┘               ┌──────────────────┐
        topic_control ▲                    │ Dashboard, etc   │
        topic_state   │ echoes + (sync …)  └──────────────────┘
```

Key design points:

- **Producer-authoritative, consumer-converging.** The share dictionary
  is the single source of truth; consumers converge via
  snapshot-then-increments. There is no conflict resolution because only
  the producer mutates its share (remote writers go *through* the
  producer's command topic).
- **Leases bound fan-out.** Every consumer subscription is an
  [ECLease](lease.md) (a Lease plus the consumer's filter); expired
  leases are dropped, so a producer never publishes forever to dead
  consumers. The consumer holds its own auto-extending 300-second Lease
  that re-sends the share request.
- **Filters cut traffic.** Both the snapshot (`_filter_share()`) and
  incremental updates (`_filter_compare()` per lease) honour the
  consumer's item-name filter.
- **Connection-driven startup.** The consumer only issues its share
  request once the [Connection](connection.md) state reaches
  `REGISTRAR`, so shares work reliably across late starts — though see
  the roadmap for degradation handling.
- ServicesCache predates ECProducer/ECConsumer and duplicates the same
  snapshot-plus-updates pattern against the Registrar's own wire
  protocol; the stated direction is to reimplement it (and the Registrar)
  on the EC classes.

### Implementation notes

- **Item paths**: `_ec_parse_item_path()` splits on `.` and enforces the
  two-level depth limit; `_ec_modify_item()` walks/creates nested
  dictionaries and applies an update or remove closure;
  `_flatten_dictionary()` produces `("a.b", value)` pairs for replay and
  snapshots. Improving the share to work recursively beyond two levels
  is on the To Do list.
- **`ECProducer._producer_handler()`** accepts `add` and `update` as
  synonyms (both upsert). Accepted mutations are echoed verbatim on
  `topic_out` *and* fanned out per-lease; local `update()`/`remove()`
  calls notify handlers and leases but do **not** echo on `topic_out`.
- **Payload generation**: `_update_consumers()` formats
  `({command} {item_name} {item_value})` with an f-string — a To Do notes
  it should use `generate()`; complex `item_value`s (spaces, nested
  structures) may not round-trip through `parse()` cleanly.
- **`ECConsumer` cache values are parsed S-expression fragments** —
  strings and lists — not rich Python objects; consumers needing typed
  values must convert (`parse_int()` etc.).
- **Response-topic construction**: the consumer's `topic_share_in`
  embeds the producer's full control topic beneath the consumer's own
  topic path, so one consumer Service can hold distinct response topics
  for many producers and consumer ids.
- **ServicesCache startup sequence**: on Registrar connection it
  subscribes to the Registrar's `out` topic and its own
  `registrar_share` response topic, requests `(history ...)` if a
  history limit is set, then `(share RESPONSE_TOPIC * * * * *)`;
  `registrar_share_handler()` counts down `item_count`, then live
  add/remove flows through `registrar_out_handler()`; `"ready"` is only
  entered after the Registrar's `(sync ...)` confirmation. On Registrar
  loss the cache resets to `empty` and the departed Registrar is pushed
  onto the history ring buffer (4096 entries).
- `services_cache_create_singleton()` starts the cache's `run()` on a
  separate `Thread`; only the instance that started the event loop
  terminates it.

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `ECProducer` | Own the share's wire interface: apply add/update/remove commands, answer `(share ...)` snapshots, manage per-consumer ECLeases, notify local handlers and leased consumers | [Service](service.md) (topics, tags), `ECLease`, `aiko.message` |
| `ECLease` | A [Lease](lease.md) that also remembers the consumer's filter | `ECProducer` |
| `ECConsumer` | Request and replicate a producer's share into a local cache; maintain its own auto-extending Lease; notify handlers; track `cache_state` | [Service](service.md), [Lease](lease.md), [Connection](connection.md) |
| `ServicesCache` | Replicate the [Registrar](registrar.md)'s Services (and optional history) into a `Services` collection; drive filtered add/remove/sync handlers; own the state machine empty→…→ready | [Registrar](registrar.md) wire protocol, `Services` from [Service](service.md), [Connection](connection.md) |
| `ECProducerTest` / `ECConsumerTest` | CLI test Services for `ec_test` | `ECProducer`, `ECConsumer` |

## Current limitations and roadmap

From the source `To Do` lists — highlights:

- **BUG?**: ECProducer and ECConsumer handling of remotely expired
  leases is suspect (flagged in the source)
- **BUG**: ServicesCache (and EC generally) should handle network
  degradation (ConnectionState changes) and lease expiry
- **BUG** (noted in `service.py`): `ServicesCache.add_handler()` calls
  the handler with `("sync", None)` without providing *filtered*
  Services
- An `ECProducerCore` minimal implementation (answers every `(share ...)`
  with `(item_count 0)`, ignores the rest), with `ECProducer` extending it
- Multiple Actors per Process each wanting their own ECProducer — the
  constructor should optionally take the Service name to disambiguate
- **Provide unit tests** — the source asks for them explicitly, and no
  tests for `share.py` exist under `src/aiko_services/tests/`
- Reimplement ServicesCache using ECProducer/ECConsumer; the Registrar
  should share identical code; `services_cache_delete()` should become a
  class method
- Handle the Registrar being unavailable, stopping and restarting
- Allow an ECConsumer to change its filter with or without an existing
  lease; catch `ValueError` from `_ec_remove_item()`/`_ec_update_item()`
  in the consumer (currently uncaught)
- Work recursively beyond the two-level dictionary depth; when a
  subscribed-to dictionary is removed, emit remove messages for its
  components (currently not sent)
- Use `generate()` for incremental update payloads (values with spaces
  or structure currently rely on f-string formatting)

## Related concepts

- [Design overview](design_overview.md)
- [Service](service.md) — provides the topics, tags and Services collection Share builds on
- [Actor](actor.md) — every Actor embeds a share and ECProducer
- [Registrar](registrar.md) — observed via ServicesCache; shares the same snapshot idiom
- [Lease](lease.md) — bounds every consumer subscription
- [Connection](connection.md) — gates when consumers issue share requests
- [Dashboard](dashboard.md) — the largest ECConsumer user
