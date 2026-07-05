---
title: Service
description: The distributed component primitive — a discoverable,
  message-addressable unit that runs within a Process and is described by
  its topic path, name, protocol, transport, owner and tags
type: concept
audience: [architects, developers, end-users]
status: work-in-progress
source:
  - src/aiko_services/main/service.py
  - src/aiko_services/main/process.py
related: [design_overview, actor, component, context, hook, registrar,
  discovery, share, message, transport]
version: "0.6"
last_updated: 2026-07-05
---

# Service

## Overview

A **Service** is the distributed component primitive of Aiko Services: a
unit of functionality that can be **discovered** via the
[Registrar](registrar.md) and **processes messages** delivered over the
[message transport](message.md) (MQTT). Every other distributed concept
builds on it — an [Actor](actor.md) is-a Service that serializes messages
through a mailbox, a Pipeline is-an Actor, and so on.

A Service always lives inside a **Process** (see
`src/aiko_services/main/process.py`): one operating-system process hosts
none, one or many Services, and the Process owns the MQTT connection, the
event loop and the Registrar handshake on behalf of all of them. When a
Service is added to its Process it is assigned a `service_id` and a
**topic path** — `namespace/hostname/process_id/service_id` — which is its
unique address in the distributed system.

Alongside the Service itself, `service.py` defines the descriptive data
structures used throughout Aiko Services: `ServiceFields` (what a Service
*is*), `ServiceFilter` (what a Service *matches*), `ServiceProtocol`,
`ServiceTags`, `ServiceTopicPath` and the `Services` collection (used by
the Registrar and the [Share](share.md) ServicesCache).

**Why you'd use it**: you implement a Service (or more commonly its
subclass Actor) whenever you want functionality that any process on the
network can find by *what it is* — name, protocol, tags — rather than by
*where it is*:

```python
from abc import abstractmethod
from aiko_services.main import *

class ServiceTest(Service):
    Interface.default("ServiceTest", "__main__.ServiceTestImpl")

    @abstractmethod
    def test(self):
        pass

class ServiceTestImpl(ServiceTest):
    def __init__(self, context):
        context.call_init(self, "Service", context)

    def test(self):
        print("ServiceTestImpl.test() invoked")

protocol = f"{SERVICE_PROTOCOL_AIKO}/service_test:0"
init_args = service_args("service_test", protocol)
service_test = compose_instance(ServiceTestImpl, init_args)
service_test.test()
aiko.process.run()
```

## For application developers

### Command-line usage

Service has no command-line tool of its own — it is a framework primitive
exercised through the tools built on it: `aiko_registrar` (which registers
and tracks Services), `aiko_dashboard` (which browses running Services),
the `share.py` test commands (see [Share](share.md)) and the
`src/aiko_services/examples/aloha_honua/` examples.

### Public API

**The Service Interface.** `Service` extends `ServiceProtocolInterface`
and [Hooks](hook.md):

```python
class Service(ServiceProtocolInterface, Hooks):
    Interface.default("Service", "aiko_services.main.service.ServiceImpl")
```

| Operation | Effect |
|-----------|--------|
| `add_message_handler(handler, topic, binary=False)` | Subscribe `handler` to an MQTT `topic` (delegates to the Process) |
| `remove_message_handler(handler, topic)` | Unsubscribe a handler |
| `set_registrar_handler(handler)` | Register a callback for Registrar `found` / `absent` transitions |
| `registrar_handler_call(action, registrar)` | Invoked by the Process when the Registrar state changes |
| `run()` | Run the Service — `ServiceImpl` raises `SystemExit` ("currently only supported by Actor") |
| `stop()` | Terminate the owning Process (`aiko.process.terminate()`) |
| `add_tags(tags)` / `add_tags_string("a=1,b=2")` / `get_tags_string()` | Manage the Service's tags |

**Construction.** Services are composed via the
[Context](context.md) / [Component](component.md) machinery:

```python
init_args = service_args(name, implementations=None,
    parameters=None, protocol=None, tags=None, transport=None)
service = compose_instance(ServiceTestImpl, init_args)
```

Registration happens in `ServiceImpl.__init__()`: unless
`register_service=False`, the Service is added to `aiko.process`, which
assigns `service_id` and `topic_path`. A Service with `protocol=None` is
*not* announced to the Registrar — it stays private to its Process.

**Topic conventions.** From the assigned topic path, five conventional
topics are derived:

```
namespace/hostname/process_id/service_id            # topic_path
├── .../control     # framework control-plane (e.g. ECProducer commands)
├── .../in          # application commands in
├── .../out         # application responses / events out
├── .../log         # log records
└── .../state       # shared state changes (ECProducer publishes here)
```

**The descriptive data structures:**

```python
topic_path = ServiceTopicPath("namespace", "host", "process_id", "service_id")

service_fields = ServiceFields(
    "topic_path", "name",
    ServiceProtocol(SERVICE_PROTOCOL_AIKO, "test", "0"),
    "transport", "owner", "tags")
```

- `ServiceFields` — the six facts describing one Service: `topic_path`,
  `name`, `protocol`, `transport`, `owner`, `tags` (all
  property-accessible, validation planned).
- `ServiceFilter` — the same fields as *match criteria*, each defaulting
  to `"*"` (match anything). `ServiceFilter.with_topic_path()` builds a
  filter for a single known topic path. Note:
  `ServiceFilter(name=None, ...)` substitutes the local hostname for the
  null name.
- `ServiceProtocol` — `url_prefix/name:version`, e.g.
  `github.com/geekscape/aiko_services/protocol/service_test:0`.
- `ServiceTags` — helpers over `key=value` string lists:
  `parse_tags()`, `get_tag_value()`, `match_tags()`.
- `ServiceTopicPath` — parse/compose topic paths;
  `topic_path_process` drops the service id, `terse` abbreviates for
  display.
- `Services` — a two-level `OrderedDict` collection (Process topic path
  → per-Process Services), iterable across all Services, with
  `add_service()`, `remove_service()`, `get_service()`,
  `filter_services(filter)` and `copy()`. Registrar entries are kept
  first in iteration order.

**Remote operation — the discovery idiom.** Application code rarely
addresses a topic path directly. Instead it discovers a Service matching
a `ServiceFilter` and calls Interface methods on a proxy
(see [Discovery](discovery.md)):

```python
do_command(ServiceTest,
    ServiceFilter("*", "service_test", "*", "*", "*", "*"),
    lambda service_test: service_test.test(), terminate=True)
aiko.process.run()
```

For request/response exchanges, `do_request()` additionally subscribes a
response handler and gathers `(item_count N)` / `(response ...)` records
— see [Category](category.md) for a worked sequence diagram of that
protocol.

**Wire protocol.** Remote method invocation is an S-expression payload
published to the target's `topic_in`:

```
(method_name argument ...)        # e.g. (test) or (aloha Pele)
```

The Process↔Registrar exchange (performed automatically by
`process.py`) uses:

```
namespace/service/registrar   (primary found TOPIC_PATH VERSION TIMESTAMP)
                              (primary absent)
REGISTRAR/in                  (add TOPIC_PATH NAME PROTOCOL TRANSPORT
                                   OWNER (TAGS))
                              (remove TOPIC_PATH)
```

Each Process also sets an MQTT Last Will and Testament of `(absent)` on
its `.../state` topic, so the Registrar can drop its Services if the
Process dies.

## For framework developers (internals)

### Design

```
   Process (one per operating-system process)
   ┌─────────────────────────────────────────────────────┐
   │ MQTT connection · event loop · Registrar handshake  │
   │ message_handlers: topic --> [handler, ...]          │
   │                                                     │
   │ services:                                           │
   │   1 ─► Service  namespace/host/pid/1  (protocol A)  │
   │   2 ─► Service  namespace/host/pid/2  (protocol B)  │
   │   3 ─► Service  namespace/host/pid/3  (private)     │
   └─────────────────────────────────────────────────────┘
              ▲ discovers / registers via
   ┌──────────┴──────────┐
   │ Registrar (Service) │  tracks ServiceFields for every Service
   └─────────────────────┘
```

Key design points:

- **Separation of Process and Service.** The Process
  (`ProcessImplementation`, singleton per operating-system process,
  accessed as `aiko.process`) owns all shared infrastructure: the MQTT
  connection, the message-handler routing table (with `#`/`+` wildcard
  matching), the [event](event.md) loop and the Registrar
  [connection](connection.md) state machine. A Service is deliberately
  thin — description plus message handling — so that many can share one
  Process cheaply.
- **Identity is a topic path.** `service_id` is a monotonically
  increasing integer per Process; the topic path composes namespace,
  hostname, process id and service id into a globally unique,
  transport-level address.
- **Description over location.** `ServiceFields` / `ServiceFilter` embody
  the design direction that Services are found by matching descriptive
  fields, not by configuration of endpoints.
- **Hooks are baked in (for now).** `Service` inherits
  [Hooks](hook.md), giving every Service instrumentation points; the
  To Do list intends Service Hooks to become optional whilst Actor Hooks
  remain built in.

### Implementation notes

- `ServiceImpl.__init__()` records `time_started = time.monotonic()` and
  copies `name`, `protocol`, `tags`, `transport` from the construction
  Context; a To Do notes these should consolidate into `ServiceFields`.
- `Services.add_service()` orders entries so that Processes hosting a
  Registrar sort first (`move_to_end(..., last=protocol !=
  REGISTRAR_PROTOCOL)`), so iteration meets Registrars before ordinary
  Services. `service_details` may be either a list/tuple (wire order:
  `topic_path, name, protocol, transport, owner, tags`) or a dict — a
  To Do calls for consolidating into one `ServiceDetails` structure.
- `Services.count` is maintained incrementally because
  `len(self._services)` counts *Processes*, not Services (the source
  carries a To Do questioning this).
- `Services.filter_services()` applies `filter_by_topic_paths()` then
  `filter_by_attributes()`; the attribute comparison is exact-match per
  field (no patterns) except tags, which use `ServiceTags.match_tags()`
  (subset semantics). The source notes this code is copied from the
  Registrar and should be unified with `share.py:_filter_compare()`.
- The Process holds `_services` under a `Lock` and re-announces every
  registered Service when a Registrar (re)appears (`on_registrar()`), then
  invokes each Service's `registrar_handler_call()`.

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `Service` (Interface) | Declare the contract: message handlers, Registrar handler, tags, `run()`/`stop()` | `ServiceProtocolInterface`, [Hooks](hook.md) (parent Interfaces) |
| `ServiceImpl` | Hold name/protocol/tags/transport; register with the Process to obtain `service_id` and `topic_path`; derive control/in/out/log/state topics; delegate messaging to `aiko.process` | `ProcessImplementation` (via `aiko.process`); [Registrar](registrar.md) (indirectly) |
| `ServiceFields` | Describe one Service: topic_path, name, protocol, transport, owner, tags | [Registrar](registrar.md), [Dashboard](dashboard.md) |
| `ServiceFilter` | Match criteria over the same fields (default `"*"`) | [Discovery](discovery.md), [Share](share.md) ServicesCache, [Category](category.md) |
| `ServiceProtocol` | Structured `url_prefix/name:version` protocol identifier | All Service definitions |
| `ServiceTags` | Parse and match `key=value` tag lists | `ServiceImpl`, `Services` |
| `ServiceTopicPath` | Parse/compose `namespace/host/pid/sid`; terse display form | `Services`, [Message](message.md) topic conventions |
| `Services` | Two-level ordered collection of Service details, keyed by Process then Service topic path; filtering and iteration | [Registrar](registrar.md), `ServicesCache` in [Share](share.md) |
| `ProcessImplementation` (in `process.py`) | Own MQTT connection, event loop, message routing, Service registry and Registrar handshake for the whole process | [Message](message.md), [Event](event.md), [Connection](connection.md), [Registrar](registrar.md) |

## Current limitations and roadmap

From the source `To Do` lists — highlights:

- **BUG**: `ServicesCache.add_handler()` should provide *filtered*
  Services to the `service_change_handler` (noted at the top of
  `service.py`, lives in `share.py`)
- `ServiceImpl.run()` is unimplemented — only Actor provides `run()`
- Services created after the Registrar is found, or terminated while
  running, need guaranteed add/remove with the Registrar (currently
  handled by the Process re-announce path only)
- Consolidate name/protocol/tags/transport into `ServiceFields`; consider
  `@dataclass`; possibly merge `ServiceFields` and `ServiceFilter`
- Parsers, generators and setter validation for `ServiceFields`,
  `ServiceTags`, `ServiceTopicPath`; a generator for `ServiceFilter`
- A default `topic_in_handler()` ("message → function call") on Service
  itself, plus the reverse remote proxy ("function call → message") —
  today both live in Actor and Discovery
- Every Service should define its own static `ServiceProtocol`
- Make `Hooks` optional for plain Services
- Consolidate the Services eventual-consistency cache and the Registrar's
  ServicesCache; longer term, turn `Services` into a tree ordered by
  topic-path fields and share subtrees via Eventual Consistency
  ("like GraphQL")
- Move `ServiceImpl2` (referenced in To Do; not present in the source) to
  tutorials or examples
- No unit tests exist for `service.py` (the repository's
  `src/aiko_services/tests/unit/` does not cover Service, Services or the
  filter classes)

## Related concepts

- [Design overview](design_overview.md)
- [Actor](actor.md) — a Service with a mailbox that serializes message handling
- [Component](component.md) and [Context](context.md) — the Interface /
  `compose_instance()` machinery Services are built with
- [Hook](hook.md) — instrumentation points every Service inherits
- [Registrar](registrar.md) — where Services are registered and looked up
- [Discovery](discovery.md) — `do_command()` / `do_request()` and Service proxies
- [Share](share.md) — eventually-consistent state and the ServicesCache
- [Message](message.md) and [Transport](transport.md) — how payloads reach a Service's topics
