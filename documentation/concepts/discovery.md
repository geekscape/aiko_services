---
title: Discovery
description: Finding and invoking remote Services — ServiceDiscovery handlers
  over the ServicesCache, dynamic remote proxies, and the do_discovery /
  do_command / do_request one-shot idioms
type: concept
audience: [architects, developers, end-users]
status: work-in-progress
source:
  - src/aiko_services/main/discovery.py
related: [design_overview, registrar, service, actor, share, proxy,
  message, transport, pipeline, lifecycle]
version: "0.6"
last_updated: 2026-07-05
---

# Discovery

## Overview

**Discovery** is how Aiko Services code finds a running
[Service](service.md) matching a `ServiceFilter` and talks to it without
knowing in advance where (or whether) it is running. The module provides
three layers:

- **`ServiceDiscovery`** (and its aliases `ActorDiscovery`,
  `PipelineElementDiscovery`, `PipelineDiscovery`) — register a handler
  with a `ServiceFilter` against the process-wide `ServicesCache` (see
  [Share](share.md)), which is fed by the [Registrar](registrar.md), and
  be called back as matching Services come and go.
- **`get_service_proxy()`** — build a dynamic remote [proxy](proxy.md)
  for an Interface: calling a proxy method publishes an S-expression to
  the target's `topic_in`.
- **`do_discovery()` / `do_command()` / `do_request()`** — the one-shot
  idioms that combine the two: *discover a Service, hand me a proxy, run
  my command (and optionally gather a response, then terminate)*. These
  are the standard pattern behind nearly every Aiko Services CLI tool.

**Why you'd use it**: any time you want "call method X on whichever
Service matches this filter" — for example, the way the
[Category](category.md) CLI adds an entry to a running Category anywhere
on the network:

```python
do_command(Category,
    ServiceFilter(name=category_name, protocol=CATEGORY_PROTOCOL),
    lambda category: category.add(...), terminate=True)
aiko.process.run()
```

## For application developers

### Command-line usage

This concept has no console script of its own — it is a library that every
other CLI tool (`aiko_dashboard`, `aiko_hyperspace`, `aiko_pipeline`, the
Category and Storage CLIs, ...) uses to reach running Services. The module
does ship a self-contained test harness (an `Example` Actor plus three
exercisers), run directly:

```bash
cd src/aiko_services/main

AIKO_LOG_LEVEL=DEBUG ./discovery.py start &          # Example Actor
AIKO_LOG_LEVEL=DEBUG ./discovery.py test_discovery   # watch add / remove
#   Add:    name: topic_path
#   Remove: name: topic_path

AIKO_LOG_LEVEL=DEBUG ./discovery.py test_command [argument]
#   Command: argument            (printed by the "start" process)

AIKO_LOG_LEVEL=DEBUG ./discovery.py test_request [request]
#   Response: [('request', [])]  (printed by the test_request process)
```

(The To Do list plans renaming `start` to `run` and adding an `exit`
subcommand, for consistency with the other tools.)

### Public API

Exported names:

```python
__all__ = [
    "ServiceDiscovery", "ActorDiscovery",
    "PipelineElementDiscovery", "PipelineDiscovery",
    "do_command", "do_discovery", "do_request", "get_service_proxy"
]
```

**Continuous discovery** — track matching Services over time:

```python
service_discovery = ServiceDiscovery(aiko.process)
service_discovery.add_handler(service_change_handler, service_filter)
service_discovery.remove_handler(service_change_handler, service_filter)
```

The handler signature is `handler(command, service_details)` where
`command` is `"add"`, `"remove"` or `"sync"` (cache snapshot complete) and
`service_details` is the Service record
`[topic_path, name, protocol, transport, owner, tags]`.
`ActorDiscovery`, `PipelineElementDiscovery` and `PipelineDiscovery` are
currently empty subclasses — type aliases marking intent.

**One-shot idioms** — the workhorses:

```python
def do_discovery(service_interface, service_filter,
    discovery_add_handler=None, discovery_remove_handler=None)

def do_command(service_interface, service_filter,
    command_handler, terminate=False)

def do_request(service_interface, service_filter,
    request_handler, response_handler, response_topic, terminate=False)
```

- `do_discovery()` wraps a `ServiceDiscovery`: on each `"add"` it builds a
  proxy for `service_interface` bound to `{topic_path}/in` and calls
  `discovery_add_handler(service_details, service)`; on `"remove"` it
  calls `discovery_remove_handler(service_details)`.
- `do_command()` waits for the first match (printing
  `Waiting for {filter summary}` after 0.5 seconds if none found yet),
  invokes `command_handler(service_proxy)`, and terminates the process if
  `terminate=True`. Fire-and-forget: there is no reply.
- `do_request()` is `do_command()` plus a response collector: it
  subscribes to `response_topic` (conventionally your own
  `aiko.topic_in`), and the `request_handler` should invoke a remote
  method that publishes the item-count grammar back to that topic. When
  all items arrive, `response_handler(response)` is called with a list of
  the response payloads.

**Remote proxies.** `get_service_proxy(service_topic, protocol_class)`
reflects over the *public* methods of `protocol_class` (non-underscore
functions; raises `ValueError` for a string or a class with no public
methods) and returns an object whose methods publish to `service_topic`:

```python
service = get_service_proxy(f"{topic_path}/in", Example)
service.command("hello")     # publishes "(command hello)" to topic_path/in
```

Proxies also provide `is_local()` returning `False`. Keyword arguments are
supported with the convention `[args[0], kwargs]` — first positional
argument, then the kwargs dictionary.

**Wire protocol.** A proxy method call is one S-expression message:

```
{target topic_path}/in  ◄─  (METHOD_NAME ARGUMENT ...)
```

Responses (for `do_request()`) use the standard grammar on the requester's
response topic:

```
(item_count N)
(response PAYLOAD ...)       # repeated N times
```

The `DiscoveryResponse` Actor Interface (`item_count(count)` /
`response(payload)`) names this contract, and the responding side can use
a proxy of it — as `ExampleImpl.request()` does:

```python
def request(self, topic_path_response, request):
    service = get_service_proxy(topic_path_response, DiscoveryResponse)
    service.item_count(1)
    service.response(request)
```

(`DiscoveryResponse` is marked in the source as provisional — "improve and
make part of the API ?".)

**Sequence** — `do_request()` round trip:

```
 Requester process                Registrar              Target Service
      │                               │                        │
      │ ServicesCache share/sync ────►│                        │
      │◄── (add TARGET ...) ──────────│                        │
      │ build proxy, call             │                        │
      │ request_handler(proxy)        │                        │
      │──(request MY_TOPIC_IN ...)───────────────────────────►│
      │                               │     gather results     │
      │◄─(item_count N)───────────────────────────────────────│
      │◄─(response PAYLOAD) × N ──────────────────────────────│
      │ response_handler(response)    │                        │
      │ terminate (if requested)      │                        │
```

## For framework developers (internals)

### Design

```
                    Registrar /out and (share ...) replies
                                   │
                                   ▼
                     ServicesCache (process singleton)
                                   │  add / remove / sync
                                   ▼
                       ServiceDiscovery.add_handler()
                     ┌─────────────┴──────────────┐
                     ▼                            ▼
               do_discovery()              application handlers
              "add" → get_service_proxy(topic_in, Interface)
                     │
                     ▼
               do_command()  ── first match → command_handler(proxy)
                     │
                     ▼
               do_request()  ── + response collector on response_topic
```

Key design points:

- **Layered convenience**: each function is a thin closure over the layer
  below — `do_request()` → `do_command()` → `do_discovery()` →
  `ServiceDiscovery` → `ServicesCache`. All state (item counts, gathered
  responses) lives in closure variables, not classes.
- **Duck-typed proxies**: a proxy is built from the *Interface's* public
  method names, so the caller programs against the same contract locally
  and remotely; the transport is a single one-way MQTT publish per call
  (no return values — responses are an explicit, separate pattern).
- The design direction (per the To Do list) is to refactor
  `ServiceDiscovery` into a proper Interface / Implementation, support
  multiple simultaneous ServiceFilters, unify with `proxy.py` (used by
  `actor.py`), and cache remote proxies (LRUCache).

### Implementation notes

- `ServiceDiscovery.__init__()` calls
  `services_cache_create_singleton(service)` — one cache per process,
  started on its own thread; handlers added while the cache is already
  `loaded` / `ready` receive an immediate `"sync"` callback.
- `_make_service_proxy()` uses a closure-per-method
  (`_proxy_send_message`) and `generate(method_name, arguments)` from the
  [parser utilities](message.md) to build payloads.
- `do_command()`'s waiting timer is self-removing; it prints at most one
  `Waiting for ...` line. Note that the discovery handler is *not*
  removed after the first match — with `terminate=False` the
  `command_handler` will run again for every further matching Service
  that appears.
- `do_request()` resets its collector state whenever a new
  `(item_count N)` arrives, and calls `response_handler` when
  `items_received == item_count` — including immediately, for `N == 0`.
- CLI processes that only run `do_command()` / `do_request()` must keep
  the event loop alive with
  `aiko.process.run(loop_when_no_handlers=True)`.

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `ServiceDiscovery` | Bind (handler, ServiceFilter) pairs to the process `ServicesCache` singleton | `ServicesCache` ([Share](share.md)), fed by the [Registrar](registrar.md) |
| `ActorDiscovery` / `PipelineElementDiscovery` / `PipelineDiscovery` | Type aliases (empty subclasses) for [Actor](actor.md) and [Pipeline](pipeline.md) discovery | `ServiceDiscovery` (parent) |
| `ServiceRemoteProxy` (built by `get_service_proxy()`) | One publish per method call to the target's `topic_in`; `is_local() == False` | `aiko.message` ([Message](message.md)); parser `generate()` |
| `do_discovery` / `do_command` / `do_request` (functions) | The one-shot discover-invoke(-collect)(-terminate) idioms | `ServiceDiscovery`, `get_service_proxy()`, `event` timers, `aiko.process` |
| `DiscoveryResponse` (Interface, provisional) | Name the response contract: `item_count()`, `response()` | `Actor` (parent Interface) |
| `Example` / `ExampleImpl` | CLI test harness Actor: `command()` prints, `request()` responds via a `DiscoveryResponse` proxy | `Actor`, `get_service_proxy()` |

## Current limitations and roadmap

From the source `To Do` list — highlights:

- **Timeouts are not implemented**: `do_command()` / `do_request()` wait
  forever for discovery, and `do_request()` waits forever for a response
- `do_request()` used before the Registrar connection is up may need to
  wait on `ConnectionState.REGISTRAR` (marked "Fix" in the source)
- Promote `DiscoveryResponse` into the public API; handle multiple
  response items better; replace message-payload parsing with remote
  function calls on a `DiscoveryResponse` implementation
- Consolidate `proxy.py` (used by `actor.py`) with
  `get_service_proxy()`; make `get_actor_mqtt()` / `make_proxy_mqtt()`
  reusable without re-reflecting public methods (the old
  `get_actor_mqtt()` path in `ServiceDiscovery` is commented out and
  marked broken)
- Refactor `ServiceDiscovery` into Interface + Implementation; support
  multiple simultaneous ServiceFilters; add an LRU cache of remote
  proxies
- Rename the `start` subcommand to `run` and implement `exit`; design
  a pattern for creating Actors of different transport types (MQTT,
  ROS2, Ray); replace the `actor=name` tag with proper Service protocol
  matching once implemented

## Related concepts

- [Design overview](design_overview.md)
- [Registrar](registrar.md) — the source of truth discovery consumes
- [Share](share.md) — `ServicesCache`, the eventually-consistent directory
- [Service](service.md) — `ServiceFilter`, `ServiceFields`, topic paths
- [Proxy](proxy.md) — the local counterpart (`proxy.py`) to be unified
  with `get_service_proxy()`
- [Actor](actor.md) — discovered targets are usually Actors
- [Message](message.md) / [Transport](transport.md) — payload generation
  and MQTT publishing underneath proxies
- [Pipeline](pipeline.md) — `PipelineDiscovery` / `PipelineElementDiscovery`
- [LifeCycle](lifecycle.md) — uses `do_discovery()` for removal tracking
