---
title: Actor
description: A Service following the Actor Model — incoming messages and
  local method calls are posted to mailboxes and invoked one at a time on
  the event-loop thread, eliminating shared-state locking
type: concept
audience: [architects, developers, end-users]
status: work-in-progress
source:
  - src/aiko_services/main/actor.py
related: [design_overview, service, event, share, hook, proxy, lifecycle,
  pipeline]
version: "0.6"
last_updated: 2026-07-05
---

# Actor

## Overview

An **Actor** is a [Service](service.md) that follows the
[Actor Model](https://en.wikipedia.org/wiki/Actor_model): instead of
handling MQTT messages (or local calls) on whatever thread they arrive,
every command is wrapped as a `Message` and posted to a **mailbox**; the
[event](event.md) loop drains the mailboxes and invokes each message
**one at a time**. State inside an Actor therefore never needs locking —
serialization is the concurrency model.

Actor is the workhorse base class of Aiko Services: Category, HyperSpace,
[Pipeline](pipeline.md), ProcessManager, the LifeCycleManager and most
examples are Actors. Where a plain Service gives you discovery and
message topics, Actor adds the mailbox discipline, built-in
[shared state](share.md) (`self.share` with an ECProducer), a per-Actor
logger with remotely adjustable log level, and message
[Hooks](hook.md) for instrumentation.

**Why you'd use it**: any component that owns mutable state and must be
operable both locally and remotely. Define the Interface, implement it,
and every public method becomes remotely callable by publishing an
S-expression to the Actor's `topic_in`:

```python
from abc import abstractmethod
from aiko_services.main import *

class ActorTest(Actor):
    Interface.default("ActorTest", "__main__.ActorTestImpl")

    @abstractmethod
    def test(self):
        pass

class ActorTestImpl(ActorTest):
    def __init__(self, context):
        context.call_init(self, "Actor", context)

    def test(self):
        print("ActorTestImpl.test() invoked")

protocol = f"{SERVICE_PROTOCOL_AIKO}/actor_test:0"
init_args = actor_args("actor_test", protocol=protocol)
actor_test = compose_instance(ActorTestImpl, init_args)
actor_test.test()
aiko.process.run()
```

Note that even the local `actor_test.test()` call above runs via the
mailbox — nothing happens until `aiko.process.run()` starts the event
loop.

## For application developers

### Command-line usage

Actor has no command-line tool of its own — it is exercised by every
Actor-based tool (`aiko_dashboard`, `aiko_pipeline`, `aiko_registrar`,
`aiko_hyperspace`) and most directly by the hello-world examples in
`src/aiko_services/examples/aloha_honua/`:

```bash
scripts/system_start.sh        # start mosquitto and the Registrar
cd src/aiko_services/examples/aloha_honua
./aloha_honua_0.py             # start the AlohaHonua Actor
./aloha_honua_1.py Pele        # discover it and call aloha("Pele") remotely
```

Fine-grained logging is controlled with the `AIKO_LOG_LEVEL_ACTOR`
environment variable (`ERROR`, `WARNING`, `INFO`, `DEBUG`) — `DEBUG`
shows low-level `Message.invoke()` diagnostics.

### Public API

```python
class Actor(Service):
    Interface.default("Actor", "aiko_services.main.actor.ActorImpl")

    @abstractmethod
    def run(self, mqtt_connection_required=True):
        pass

    @abstractmethod
    def set_log_level(self, level):
        pass
```

| Operation | Effect |
|-----------|--------|
| `run(mqtt_connection_required=True)` | Set `share["running"]`, then run the Process event loop (blocking) |
| `set_log_level(level)` | Update `share["log_level"]` via the ECProducer, which adjusts the Actor's logger — works remotely |
| `is_running()` | Return `share["running"]` |
| `_post_message(topic, command, args, delay=None, target_function=None)` | Post a `Message` to the Actor's own mailbox (protected; used by subclasses, e.g. to defer work or schedule delayed commands) |
| `ActorImpl.proxy_post_message(...)` (classmethod) | Proxy hook that turns a method call into a mailbox post — see below |

**Construction** uses `actor_args()` (identical signature to
`service_args()`) and `compose_instance()`, as in the Overview example.
Every Actor automatically gets:

- `self.share = {"lifecycle": "ready", "log_level": ..., "running": False}`
  published by an `ECProducer` — subclasses extend it with
  `self.share.update({...})` *before* further `ec_producer.update()` calls
  (see [Share](share.md))
- `self.logger` — an Aiko Services logger named after the Actor
- Two mailboxes (`control` and `in`) and a subscription of
  `_topic_in_handler` to the Actor's `topic_in`

**Remote invocation and the wire protocol.** Any S-expression published
to the Actor's `topic_in` is parsed and posted to the `in` mailbox as a
command:

```
namespace/host/pid/sid/in       (method_name argument ...)
```

The event loop then invokes `self.method_name(*arguments)`. There is no
reply unless the method itself publishes one — one-way messaging is the
default; request/response idioms (`do_request()`, `(item_count N)` /
`(response ...)`) are layered on top by [Discovery](discovery.md) and
its users.

Local calls take exactly the same path when made through a
[proxy](proxy.md): `ActorImpl.proxy_post_message()` converts a method
call into `_post_message()`, routing commands whose names start with
`control_` to the priority `control` topic and everything else to `in`:

```
 remote:  MQTT (test 1) ──► _topic_in_handler ──► _post_message(IN, ...)
 local :  actor.test(1) ──► proxy_post_message ─► _post_message(IN, ...)
                                                        │
                                             mailbox "name/sid/in"
                                                        │
                                        event loop (single thread)
                                                        │
                                              Message.invoke()
                                                        │
                                                 self.test(1)
```

**Delayed messages.** `_post_message(..., delay=seconds)` queues the
message and posts it to the mailbox after the delay via an event-loop
timer (see Implementation notes for current precision limits).

**Hooks.** Two built-in [Hook](hook.md) points fire around the message
path — `ACTOR_HOOK_MESSAGE_IN` (`actor.message_in:0`) when a message is
posted, and `ACTOR_HOOK_MESSAGE_CALL` (`actor.message_call:0`) when the
mailbox handler is about to invoke it.

## For framework developers (internals)

### Design

```
                       Actor (is-a Service)
   ┌───────────────────────────────────────────────────────┐
   │  share {lifecycle, log_level, running} ── ECProducer  │
   │  logger (remotely adjustable)                         │
   │                                                       │
   │  mailboxes (per Actor, named "name/service_id/topic") │
   │    "control"  ◄── priority: always drained first      │
   │    "in"       ◄── application commands                │
   │  delayed_message_queue ── timer ──► mailbox           │
   └───────────────────────────────────────────────────────┘

   Message ──► Actor ──► Mailbox ──► Event loop ──► Message (optional)
   StateChange external ──► Message ──► Actor ──► Mailbox ──► Event loop
   StateChange internal ──► Priority Mailbox ──► Event loop
```

Key design points:

- **Single-threaded invocation.** All message handling happens on the
  event-loop thread; an Actor's state is only ever touched by one message
  at a time. This is the framework's alternative to locks.
- **Two mailboxes, one priority.** The first mailbox added to the event
  loop gets priority handling — `ActorImpl` registers `control` before
  `in`, so framework/control commands (method names prefixed
  `control_`) preempt queued application work.
- **Uniform local/remote calls.** The same mailbox path serves MQTT
  payload parsing (`_topic_in_handler`) and proxied local calls
  (`proxy_post_message`), so behaviour does not depend on where the
  caller lives.
- **Observable by construction.** `share` + ECProducer means every Actor
  exposes lifecycle, log level and any subclass-added state to the
  [Dashboard](dashboard.md) and other consumers without extra code.
- The design notes describe an Actor as "is a LifeCycleClient (can be
  standalone)" with `[Leases]` and an ordered, priority MailBox — the
  [lease](lease.md)-on-message aspect is still an open design question
  (see roadmap).

### Implementation notes

- **`Message`** captures `(target_object, command, arguments,
  target_function)`. `invoke()` resolves the command name with
  `__getattribute__` unless an explicit `target_function` was supplied
  (the proxy path supplies one, skipping re-resolution). Invocation
  failures are logged with a stack trace but *swallowed* — the source
  notes the `except Exception` used to be `except TypeError` only, and
  that catching everything hides bugs in the target function.
- **Mailbox naming**: `_actor_mailbox_name(topic)` returns
  `f"{self.name}/{self.service_id}/{topic}"` — unique per Actor within
  the Process, supporting multiple Actors per Process.
- **Delayed delivery is approximate.** `_post_message(delay=...)` puts
  `(deadline, topic, message)` on `delayed_message_queue` and starts a
  timer only when the queue transitions from empty (size 1). When the
  timer fires, `_post_delayed_message_handler()` drains the *entire*
  queue to the mailboxes regardless of each entry's deadline — later
  entries with longer delays are delivered early, and entries added
  while a longer timer is pending wait for it. Treat `delay` as
  "at least roughly, not before other work" rather than precise
  scheduling.
- **`ec_producer_change_handler`** watches `share` changes and applies
  `log_level` updates to the Actor's logger (invalid levels are ignored).
- **`ActorImpl.run()`** sets `self.share["running"]` by direct dictionary
  assignment (not `ec_producer.update()`), so remote consumers are *not*
  notified of the running-state change; exceptions from the event loop
  are logged with a traceback and re-raised.
- **`ActorTest` / `ActorTestImpl`** are a self-exercising example
  (overriding `_mailbox_handler` to trace deliveries) that the source
  flags for relocation to `examples/`; `__test__ = False` stops PyTest
  collecting it.
- When subclassing, initialize with
  `context.call_init(self, "Actor", context)` first, and remember every
  public method is remotely invokable — validate arguments accordingly.

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `Actor` (Interface) | Declare the contract: `run()`, `set_log_level()`; is-a Service | [Service](service.md) (parent Interface) |
| `ActorImpl` | Create mailboxes and subscribe `topic_in`; wrap commands as Messages and post them (`_post_message`, `proxy_post_message`); drain via `_mailbox_handler`; manage `share`/ECProducer, logger and delayed messages; run the event loop | [Event](event.md) (mailboxes, timers), `ECProducer` in [Share](share.md), [Hooks](hook.md), `aiko.process` |
| `Message` | Carry one deferred invocation; resolve and call the target, logging failures | `ActorImpl` (poster and invoker) |
| `ActorTopic` | Name the mailbox/topic categories: `control`, `state`, `in`, `out` | `ActorImpl`, [Proxy](proxy.md) routing |
| `ActorTest` / `ActorTestImpl` | Built-in demonstration Actor (slated to move to examples) | `ActorImpl` |

## Current limitations and roadmap

From the source `To Do` list — highlights:

- Generalize `pipeline.py:is_local()` into Actor — or better, into
  `Service.is_local()` (see also the Discovery ServiceRemoteProxy)
- A lightweight `ActorCoreImpl` if the default `ActorImpl` proves too
  heavy
- A true **priority mailbox for internal needs**, e.g. posting
  `(raise_exception ...)` when initialization fails (today priority is
  only "first mailbox drained first")
- **Multiple Actors per Process** as a first-class feature: framework
  generated unique names (fully-qualified `(actortype
  namespace/host/pid/sid)` and short forms), and shared ECConsumer
  instances across Actors in one Process (required for
  Pipeline → PipelineElements)
- **State machine**: consolidate `share["lifecycle"]` and
  `share["running"]` into `share["state"]`; `is_running()` becomes
  `get_state()`; stop via a state change, hard-terminate separately
- Optional [Leases](lease.md) attached to Messages (semantics still an
  open question in the source), function-tracing wrappers
  (enter count / exit time), and remote-Actor function-call round-trips
- Rename "function" vs "method" consistently; consider a `uuid` suffix on
  Actor names for non-singletons
- Distributed transports beyond MQTT (single process, pyro5, Ray);
  distributed logging collection (Kafka?); multithreading support
- Narrow `Message.invoke()` exception handling back to argument
  `TypeError`s only (current broad catch hides target-function bugs)
- Move `ActorTest` / `ActorTestImpl` into `examples/`
- No unit tests exist for `actor.py` (nothing under
  `src/aiko_services/tests/` covers Message, mailbox posting or delayed
  delivery)

## Related concepts

- [Design overview](design_overview.md)
- [Service](service.md) — what an Actor is, before the mailbox is added
- [Event](event.md) — the loop, mailboxes and timers that drive invocation
- [Share](share.md) — `self.share` / ECProducer built into every Actor
- [Hook](hook.md) — the message_in / message_call instrumentation points
- [Proxy](proxy.md) — how local method calls become mailbox posts
- [Lifecycle](lifecycle.md) — LifeCycleManager/Client, themselves Actors
- [Pipeline](pipeline.md) — the largest Actor subclass family
