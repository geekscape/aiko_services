---
title: Process
description: The per-operating-system-process framework singleton — the
  aiko global, MQTT connection ownership, message dispatch onto the event
  loop, Service registration and Registrar tracking
type: concept
audience: [architects, developers, end-users]
status: work-in-progress
source:
  - src/aiko_services/main/process.py
related: [design_overview, event, connection, message, service, actor,
  registrar, discovery, share, process_manager]
version: "0.6"
last_updated: 2026-07-05
---

# Process

## Overview

**Process** provides the Aiko Services framework for one operating system
process. It is the singleton that everything else in a process hangs off:
it owns the [Message](message.md) connection (MQTT), pumps incoming
messages onto the [event loop](event.md), tracks the
[Registrar](registrar.md) via the bootstrap topic, holds the table of
[Services](service.md) hosted in this process (none, one or many), and
derives the process-level topic namespace
(`{namespace}/{host}/{pid}/…`). The module exports the `aiko` global —
`aiko.process`, `aiko.message`, `aiko.logger`, `aiko.connection` — that
every other Aiko Services module imports.

Do not confuse Process with [ProcessManager](process_manager.md):
ProcessManager creates and destroys *other* operating system processes;
Process is the framework runtime *inside* each one.

**Why you'd use it**: every Aiko Services program already does — the last
line of virtually every application, example and CLI tool is the blocking
call that hands control to the Process event loop:

```python
from aiko_services.main import *   # __init__.py: aiko.process = process_create()

event.add_timer_handler(timer_handler, 1.0)
aiko.process.run()                 # blocking: run the event loop
```

## For application developers

### Command-line usage

Process has no CLI of its own — it is the runtime every console script
(`aiko_registrar`, `aiko_pipeline`, `aiko_dashboard`, …) starts implicitly.
It is controlled through environment variables:

```bash
AIKO_LOG_LEVEL_MESSAGE=DEBUG   # show low-level incoming MQTT messages
AIKO_LOG_LEVEL_PROCESS=DEBUG   # show Connection locking, MQTT issues,
                               #   Registrar issues, Services locking
AIKO_LOG_MQTT=all|true|false   # route logging to MQTT (default: all)
```

MQTT server selection (`AIKO_MQTT_HOST`, `AIKO_MQTT_PORT`, namespace, TLS)
is resolved by [utilities/configuration](utilities/configuration.md).

### Public API

Process is deliberately **not** an Interface/Component — it is a plain
singleton created before the composition machinery can run (the
[ContextManager](utilities/context.md) holding `(aiko, message)` is set up
*by* `initialize()`). The public surface:

```python
aiko = ProcessData                    # class-level singleton data
aiko.process = process_create()       # ProcessImplementation singleton
aiko.message                          # Message instance (MQTT or Castaway)
aiko.logger(name, log_level=None, ...)  # AikoLogger factory (console + MQTT)
aiko.connection                       # Connection state ladder
aiko.registrar                        # {"topic_path", "version", "timestamp"} | None

aiko.process.run(loop_when_no_handlers=False, mqtt_connection_required=True)
aiko.process.initialize(mqtt_connection_required=True)   # idempotent
aiko.process.add_service(service)     # -> service_id (assigns topic_path)
aiko.process.remove_service(service_id)
aiko.process.add_message_handler(handler, topic, binary=False)
aiko.process.remove_message_handler(handler, topic)
aiko.process.set_last_will_and_testament(topic_lwt, payload_lwt, retain_lwt)
aiko.process.set_registrar_absent_terminate()
aiko.process.terminate(exit_status=0)
```

Key behaviours:

- `run(mqtt_connection_required=False)` lets a process run without an MQTT
  server — this is how unit tests run broker-free. When the connection is
  required but fails, `initialize()` raises `SystemExit`. Before (or
  without) an MQTT connection, `aiko.message` is a
  [Castaway](message.md) null implementation, so publishing never crashes.
- A message handler returning a truthy value **stops propagation** to the
  remaining handlers for that topic.
- Handlers for `binary=True` topics receive raw bytes; all other payloads
  are UTF-8 decoded.
- `terminate(exit_status)` stops the event loop; a non-zero status becomes
  `sys.exit(exit_status)` after `run()` unwinds.

**Topic namespace.** ProcessData derives, never configures (see
[Service](service.md) for the full scheme):

```
{namespace}/{host}/{pid}            topic_path_process
{namespace}/{host}/{pid}/0          topic_path   (process-level Service id 0)
…/0/in  …/0/out  …/0/log            command / response / logging topics
…/0/state                           last-will-and-testament topic
{namespace}/service/registrar       TOPIC_REGISTRAR_BOOT (well-known)
```

**Registrar wire protocol.** Process subscribes to the bootstrap topic and
reacts to the Registrar's announcements; when Services are registered it
publishes to the Registrar's `in` topic:

```
(primary found REGISTRAR_TOPIC_PATH VERSION TIMESTAMP)   # Registrar present
(primary absent)                                         # Registrar gone

(add TOPIC_PATH NAME PROTOCOL TRANSPORT OWNER (TAGS))    # register Service
(remove TOPIC_PATH)                                      # deregister Service
```

Startup and registration sequence:

```
MQTT thread            Process (event loop)              Registrar
    │                        │                               │
    │  connect + LWT "(absent)" on …/0/state                 │
    │──on_mqtt_state_change─►│ Connection: NONE → TRANSPORT  │
    │                        │                               │
    │◄─(primary found …) retained on {namespace}/service/registrar
    │──queue_put("message")─►│ on_registrar():               │
    │                        │  Connection: TRANSPORT → REGISTRAR
    │                        │──(add topic name protocol …)─►│  every hosted
    │                        │                               │  Service
    │                        │  registrar_handler_call() per Service
```

If the Registrar later announces `(primary absent)`, Connection drops back
to TRANSPORT, every Service's registrar handler is notified, and — when
`set_registrar_absent_terminate()` was called (used by tools that cannot
usefully outlive the Registrar) — the Process terminates with exit status 1.

## For framework developers (internals)

### Design

```
   OS process
   ┌─────────────────────────────────────────────────────────────┐
   │  aiko (ProcessData, class-level singleton)                  │
   │    topic_path_process = namespace/host/pid                  │
   │    connection · message · registrar · logger                │
   │                                                             │
   │  ProcessImplementation (aiko.process)                       │
   │    _services      {service_id → Service}   (+ Lock)         │
   │    _message_handlers {topic → [handler]}                    │
   │       + binary-topic dict + wildcard-topic list             │
   │                                                             │
   │  MQTT thread ──queue_put("message")──► event loop thread    │
   │                          │                                  │
   │                          ├─ on_message_queue_handler()      │
   │                          │    topic_matcher() → handlers    │
   │                          ├─ on_registrar()                  │
   │                          └─ Service mailboxes, timers, …    │
   └─────────────────────────────────────────────────────────────┘
```

Design points:

- **One Process per OS process, many Services within it.** `add_service()`
  hands out ascending `service_id`s and derives each Service's topic path
  from the process path — Services are addressable the moment they exist.
- **The MQTT thread never runs application code.** `on_message()` only does
  `event.queue_put(message, "message")`; parsing, matching and handler
  dispatch all happen in `on_message_queue_handler()` on the event-loop
  thread. This is the boundary that makes the single-threaded
  [Actor](actor.md) model work.
- **Connection is a ladder, not a flag.** MQTT connect lifts
  [Connection](connection.md) to TRANSPORT; Registrar discovery lifts it to
  REGISTRAR; components defer work until the rung they need exists.
- **Logging works before the framework does.** `AikoLogger` is usable
  before `ProcessImplementation` exists, and routes records to the console
  and/or the process `…/0/log` topic (see [Recorder](recorder.md)).

### Implementation notes

- `initialize()` is idempotent and is called by `run()`; it installs the
  `"message"` queue handler, subscribes `on_registrar()` to the bootstrap
  topic, constructs the MQTT connection (falling back to Castaway), and
  creates the `ContextManager(aiko, aiko.message)` global.
- `topic_matcher()` intentionally supports literal topics, a trailing `#`,
  and `+` wildcards — but its semantics are narrower than MQTT's:
  the `#` branch matches exactly one extra level (`tokens[:-1] ==
  wildcard_tokens[:-1]` requires equal depth), and the `+` branch compares
  only the first and last tokens, so `a/+/c` also matches `a/x/y/c`.
  Subscriptions are made with the real MQTT semantics, so mismatches
  surface as unmatched (dropped) or over-matched deliveries.
- **Suspected bug — `remove_message_handler()`**: when the last handler for
  a topic is removed, the binary-topic branch deletes from
  `_message_handlers_wildcard_topics` (a *list*) instead of
  `_message_handlers_binary_topics`, and `del list[topic]` raises
  `TypeError`; the wildcard branch has the same list-vs-dict problem
  (should be `.remove(topic)`).
- **Suspected bug — Service id reuse**: `remove_service()` decrements
  `service_count`, which `add_service()` uses to mint ids — after
  add, add, remove, the next add reuses a live Service's id and topic path.
- Exceptions in message handlers are caught, printed and republished to
  `topic_log` (marked `# REVIEW` in source); a raising handler cannot
  crash the Process — nor can it be noticed by supervision (an exception
  policy per Service or per Process is a To Do).
- The source acknowledges: `AikoLogger.logger()` uses Service id 0 rather
  than the actual Service id (BUG in the To Do list), and there is no MQTT
  auto-reconnection after disconnection yet.

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `ProcessData` (the `aiko` global) | Hold the singleton state: topic paths derived from namespace/host/pid, `connection`, `message`, `registrar`, `logger`; well-known Registrar bootstrap topic | [utilities/configuration](utilities/configuration.md) (namespace, hostname, pid); [Connection](connection.md) |
| `AikoLogger` | Logger factory usable before the Process exists; console and/or MQTT transport per `AIKO_LOG_MQTT` | [utilities/logger](utilities/logger.md); [Message](message.md) (LoggingHandlerMQTT) |
| `ProcessImplementation` | Own the MQTT connection and last-will-and-testament; pump MQTT messages onto the event loop; topic-match and dispatch to handlers; track hosted Services and (de)register them with the Registrar; track Registrar presence; terminate with exit status | [Event](event.md) (queue, loop, terminate); [Message](message.md) (MQTT / Castaway); [Registrar](registrar.md) (boot protocol, add/remove); [Service](service.md) (hosted table, `registrar_handler_call`); [utilities/lock](utilities/lock.md); [utilities/context](utilities/context.md) (ContextManager) |
| `process_create()` | Create-once accessor for the `ProcessImplementation` singleton (invoked from `main/__init__.py`) | `ProcessData` |

## Current limitations and roadmap

From the source `To Do` list — highlights:

- Watchdog monitoring of framework processes, including detecting
  superfluous duplicate core processes
- Automatic MQTT reconnection after disconnection; multiple message server
  connections (Federation)
- Fix `AikoLogger` Service id (always 0 today); improve console/MQTT
  logging to carry the correct Service id (ContextManager?)
- Ensure `add_service()` / `remove_service()` always update the Registrar;
  consider moving Registrar-related functions into the Registrar
- Optional policy when a Service's event/message handler raises: terminate
  the Service or the whole Process
- Replace global Event functions with a Handler class instance; review
  event queues for latency and bandwidth (MQTT `on_message()` →
  application handler)
- Load testing: one Process with 1,000–10,000+ Services; 1,000+ Processes
  — find the limits
- Rename `ProcessData` to `ProcessInfo` (naming To Do)
- No unit tests exist for process.py (message dispatch, topic matching and
  Service registration are all pure-logic test candidates)

## Related concepts

- [Event](event.md) — the loop `run()` blocks on; queues and timers
- [Message](message.md) — the MQTT/Castaway connection Process owns
- [Connection](connection.md) — the NONE → TRANSPORT → REGISTRAR ladder
- [Service](service.md) / [Actor](actor.md) — what a Process hosts
- [Registrar](registrar.md) — discovered via the bootstrap topic;
  Services are registered there
- [Discovery](discovery.md) — builds on the Registrar tracking Process
  maintains
- [Share (Eventual Consistency)](share.md) — per-Service state published
  over the topics Process derives
- [ProcessManager](process_manager.md) — creates and destroys OS processes
  (each containing a Process)
