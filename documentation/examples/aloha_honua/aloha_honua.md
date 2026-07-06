---
title: AlohaHonua hello-world Actor tutorial
description: The graduated four-stage "hello world" tutorial — a minimal
  distributed Actor, remote discovery and invocation with do_command(),
  a combined start / call / stop CLI, and request / response round-trips
  with do_request()
type: concept
audience: [developers, end-users]
status: draft
source:
  - src/aiko_services/examples/aloha_honua/aloha_honua_0.py
  - src/aiko_services/examples/aloha_honua/aloha_honua_1.py
  - src/aiko_services/examples/aloha_honua/aloha_honua_2.py
  - src/aiko_services/examples/aloha_honua/aloha_honua_3.py
  - src/aiko_services/examples/aloha_honua/ReadMe.md
related: [actor, service, discovery, registrar, process, share, dashboard]
version: "0.6"
last_updated: 2026-07-06
---

# AlohaHonua hello-world Actor tutorial

## Overview

*Aloha honua* is Hawaiian for "hello world". This example package is the
Aiko Services equivalent of the traditional hello-world program — except
that even the smallest stage is a *distributed* Service: an
[Actor](../../concepts/actor.md) that registers with the
[Registrar](../../concepts/registrar.md), can be discovered from any
other process on the network, exposes a remotely callable method, logs
via distributed logging and appears live on the
[Dashboard](../../concepts/dashboard.md).

The tutorial is graduated across four source files, each building on
the last:

| Stage | File | Adds |
|-------|------|------|
| 0 | `aloha_honua_0.py` | The minimal `AlohaHonua` Actor: `aloha(name)` method, [Share](../../concepts/share.md) entries, MQTT topic printout |
| 1 | `aloha_honua_1.py` | A separate client: `click` argument parsing, [discovery](../../concepts/discovery.md) via `aiko.do_command()` and a `ServiceFilter`, remote fire-and-forget invocation |
| 2 | `aloha_honua_2.py` | Actor and client combined into one file as a `click` command group — `hoomaka` (start), `aloha` (call), `ku` (remote stop) |
| 3 | `aloha_honua_3.py` | `aiko.do_request()` — a remote call that returns a *response* on a caller-provided topic, plus the `AlohaHonuaResponse` response Interface |

The source directory also carries its own narrative
[ReadMe](../../../src/aiko_services/examples/aloha_honua/ReadMe.md)
(a line-by-line walk-through of stage 0 for absolute beginners), an
architecture diagram `aiko_diagram_0.png` and a Dashboard screenshot
`aiko_dashboard_0a.png`.

**Why you'd use it**: this is the first runnable code to try after
installing Aiko Services — three terminal sessions demonstrate the
whole distributed model in under a minute:

```bash
./scripts/system_start.sh   # terminal 1: mosquitto + Registrar
./aloha_honua_0.py          # terminal 2: MQTT topic: aiko/host/1234/1/in
./aloha_honua_1.py Pele     # terminal 3: remote call → "Aloha Pele !"
```

## For application developers

### Command-line usage

All stages assume the Core Services are running — from the repository
top level:

```bash
./scripts/system_start.sh   # Start mosquitto and the Registrar
# ... run the example stages (below) ...
./scripts/system_stop.sh    # Stop mosquitto and the Registrar
```

The scripts are invoked as executables from the source directory
`src/aiko_services/examples/aloha_honua/`.

**Stages 0 and 1** — Actor and client as separate programs:

```bash
# Terminal session 2
./aloha_honua_0.py          # Start AlohaHonua Actor
# MQTT topic: aiko/nomad.local/123/1/in

# Terminal session 3
./aloha_honua_1.py [Pele]   # Remote function call to say "hello"
# Terminal session 2 logs: ... Aloha Pele !
```

The `name` argument is optional and defaults to `hoaloha` ("friend").
The stage 0 usage header also notes that the same call can be made by
publishing a hand-crafted MQTT message to the Actor's `topic_in`
(the topic printed at start-up):

```bash
mosquitto_pub -t aiko/nomad.local/123/1/in -m "(aloha Pele)"
```

(The source comment leaves the topic as a `?` placeholder and plans to
replace this with an `aiko_dashboard` publish — see limitations.)

**Stage 2** — one file, three sub-commands:

```bash
./aloha_honua_2.py hoomaka       # Start AlohaHonua Actor
./aloha_honua_2.py aloha [Pele]  # Remote function call to say "hello"
./aloha_honua_2.py ku            # Remote function call to stop AlohaHonua
```

**Stage 3** — same sub-commands, but `aloha` now receives a reply:

```bash
./aloha_honua_3.py hoomaka       # Start AlohaHonua Actor
./aloha_honua_3.py aloha [Pele]  # Remote request, prints the response
# Response: Aloha Pele 👋
./aloha_honua_3.py ku            # Remote function call to stop AlohaHonua
```

While a client waits for discovery it prints a reminder every half
second (from `do_command()`): `Waiting for <service filter summary>`.

Standard Aiko Services environment variables apply, as the source
ReadMe demonstrates for stage 0:

```bash
AIKO_LOG_LEVEL=DEBUG ./aloha_honua_0.py   # initial log level
AIKO_LOG_MQTT=false  ./aloha_honua_0.py   # log to console, not MQTT
```

### Public API

**The AlohaHonua Actor** (all stages) — a plain
[Actor](../../concepts/actor.md) whose public methods *are* the remote
contract:

| Method | Stage | Behaviour |
|--------|-------|-----------|
| `aloha(name)` | 0-3 | Log `Aloha {name} !` at info level |
| `ku()` | 2-3 | Log a farewell, then `raise SystemExit()` — stops the Actor process |
| `request(topic_path_response, request)` | 3 | Reply on `topic_path_response` via a Service proxy: `item_count(1)` then `response(f"Aloha {request} 👋")` |

Stage 0 additionally publishes two extra
[Share](../../concepts/share.md) entries beside those inherited from
Actor — `aiko_id` (the framework version id) and `source_file` — which
are visible on the Dashboard.

**Construction** (stages 0, 2, 3) is the standard Actor idiom:

```python
init_args = aiko.actor_args("aloha_honua")
aloha_honua = aiko.compose_instance(AlohaHonua, init_args)
aiko.process.run()
```

**Remote invocation** (stages 1-3) is the discovery idiom — find the
first Service whose *name* is `aloha_honua`, call it, terminate:

```python
aiko.do_command(
    AlohaHonua,
    aiko.ServiceFilter("*", "aloha_honua", "*", "*", "*", "*"),
    lambda aloha_honua: aloha_honua.aloha(name),
    terminate=True)
aiko.process.run()
```

The `ServiceFilter` positional fields are `topic_paths, name, protocol,
transport, owner, tags` — here everything but the name is a wildcard.

**Request / response** (stage 3) replaces `do_command()` with
`do_request()`, passing a response handler and the caller's own
`topic_in` as the response topic:

```python
_RESPONSE_TOPIC = aiko.aiko.topic_in

aiko.do_request(
    AlohaHonua,
    aiko.ServiceFilter("*", "aloha_honua", "*", "*", "*", "*"),
    lambda aloha_honua: aloha_honua.request(_RESPONSE_TOPIC, name),
    response_handler, _RESPONSE_TOPIC, terminate=True)
aiko.process.run(loop_when_no_handlers=True)  # Keep event loop running
```

Stage 3 also defines the response contract as an Interface with
abstract methods — the Actor-side proxy is built against it:

```python
class AlohaHonuaResponse(aiko.Actor):
    @abstractmethod
    def item_count(self, count): pass

    @abstractmethod
    def response(self, payload): pass
```

**Wire protocol** — every remote call is an S-expression published to
the target Actor's `topic_in`:

```
(aloha Pele)                     # stage 1/2 fire-and-forget command
(ku)                             # stage 2/3 remote stop
(request aiko/host/pid/sid/in Pele)   # stage 3 request
```

The stage 3 reply arrives on the response topic as two messages:
`(item_count 1)` announcing the item count, then one `(response ...)`
per item. The client's `response_handler(response)` receives a list of
argument lists — the example prints `response[0][0]`, the first
argument of the first item.

Request / response sequence (stage 3 `aloha` sub-command):

```
 aloha client            Registrar            AlohaHonua Actor
      |                      |                        |
      |-- discover(filter) ->|                        |
      |<- match: topic_path -|                        |
      |                                               |
      |-- (request <client topic_in> Pele) ---------->|
      |                                               |
      |<------------- (item_count 1) -----------------|
      |<------------- (response "Aloha Pele ...") ----|
      |                                               |
 response_handler() prints, then process terminates
```

## For framework developers (internals)

### Design

The tutorial is deliberately a *minimal slice* through the framework's
runtime structure — one [Process](../../concepts/process.md) per
terminal session, all glued together by MQTT and the Registrar:

```
+---------------------+        +----------------------+
| Process: client     |        | Process: AlohaHonua  |
| (aloha_honua_1/2/3) |        | (aloha_honua_0/2/3)  |
|                     |        |                      |
|  ServiceDiscovery   |        |  AlohaHonua Actor    |
|  + Service proxy    |        |  topic_in: .../in    |
+---------+-----------+        +-----------+----------+
          |                                |
          +---------------+----------------+
                          |
                 +--------+--------+       +-----------+
                 |  MQTT (broker)  |<----->| Registrar |
                 +-----------------+       +-----------+
```

Key design points, in the order the stages introduce them:

- **Stage 0 — Actor as Service.** The composition idiom
  (`actor_args()` → `compose_instance()` → `aiko.process.run()`)
  demonstrates the framework's Inversion of Control and
  design-by-composition approach: `context.call_init(self, "Actor",
  context)` is the only boilerplate, and the resulting instance is
  automatically registered, shareable and remotely callable.
- **Stage 1 — proxy-based remoting.** `do_command()` wraps
  `do_discovery()`: when the Registrar reports a Service matching the
  `ServiceFilter`, `get_service_proxy()` manufactures a proxy object
  whose method calls serialise to S-expressions published on the
  target's `topic_in`. The client code reads like a local call —
  `aloha_honua.aloha(name)`.
- **Stage 2 — symmetric roles.** One file can be *either* the Actor or
  a client depending on the `click` sub-command, showing that there is
  no structural difference between "server" and "client" processes.
- **Stage 3 — responses without a server socket.** A "request" is a
  command that carries a reply-to topic. The Actor builds its *own*
  proxy toward the caller (`get_service_proxy(topic_path_response,
  AlohaHonuaResponse)`), so both directions use the same one-way
  message mechanism. The `item_count` / `response` pair frames
  multi-item replies.

### Implementation notes

- `_RESPONSE_TOPIC = aiko.aiko.topic_in` (aloha_honua_3.py) is
  evaluated at import time — it is the *client process's own* incoming
  topic, reused as the reply-to address.
- Stage 3's `aloha` sub-command must run the event loop with
  `aiko.process.run(loop_when_no_handlers=True)`; otherwise the
  process would exit before the asynchronous response arrives.
- `AlohaHonuaResponse` mirrors the framework's internal
  `DiscoveryResponse` class (`src/aiko_services/main/discovery.py`),
  which is marked "TODO: Improve and make part of the API". The
  client side of `do_request()` currently parses response payloads
  directly rather than implementing this Interface.
- `aloha_honua_1.py` does `from aloha_honua_0 import AlohaHonua`, so
  it must be run from the source directory (Python adds the script's
  directory to `sys.path`); it is not importable as a package module.
- `ku()` stops the Actor by raising `SystemExit` from within the
  message-handling path — the simplest possible remote shutdown, not
  a graceful [lifecycle](../../concepts/lifecycle.md) transition.

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `AlohaHonua` (stages 0-3) | Register as a discoverable Service; log greetings on `aloha(name)`; stop on `ku()`; reply via a response proxy on `request()` (stage 3) | [Actor](../../concepts/actor.md), [Process](../../concepts/process.md), [Registrar](../../concepts/registrar.md), [Share](../../concepts/share.md) |
| `AlohaHonuaResponse` (Interface, stage 3) | Declare the reply contract: `item_count(count)`, `response(payload)` | [Actor](../../concepts/actor.md), `get_service_proxy()` ([Discovery](../../concepts/discovery.md)) |
| `main` click group (stages 2-3) | Map sub-commands `hoomaka` / `aloha` / `ku` onto Actor start-up or `do_command()` / `do_request()` invocations | `click`, [Discovery](../../concepts/discovery.md) |

## Current limitations and roadmap

The four source To Do lists all read "None, yet !" — the example code
itself is complete for its purpose. Remaining rough edges:

- The stage 0 usage header's raw-MQTT example is a placeholder
  (`mosquitto_pub -m "(aloha Pele)" -t ?`) with a note to replace it
  with an `aiko_dashboard` publish — **planned**, not yet written.
- The source
  [ReadMe](../../../src/aiko_services/examples/aloha_honua/ReadMe.md)
  has several *[TBC]* sections (installation guide, remote MQTT
  server, Dashboard log page, MQTT publish walk-through) and its
  transcribed stage 0 listing has drifted slightly from
  `aloha_honua_0.py` (import style, log message text, the Share
  entries).
- The framework `do_request()` client side parses payloads instead of
  implementing the response Interface (framework TODO in
  `src/aiko_services/main/discovery.py`) — when that lands, stage 3's
  `response_handler` idiom may change.

## Related concepts

- [Actor](../../concepts/actor.md) — the class every stage subclasses
- [Service](../../concepts/service.md) — what an Actor is to the rest
  of the system; defines `ServiceFilter` fields
- [Discovery](../../concepts/discovery.md) — `do_command()`,
  `do_request()` and `get_service_proxy()` used by stages 1-3
- [Registrar](../../concepts/registrar.md) — the Core Service that
  makes discovery work; started by `system_start.sh`
- [Process](../../concepts/process.md) — `aiko.process.run()` event
  loop hosting each stage
- [Share](../../concepts/share.md) — the `self.share` entries stage 0
  publishes for the Dashboard
- [Dashboard](../../concepts/dashboard.md) — monitor the running
  AlohaHonua Actor (see `aiko_dashboard_0a.png` in the source
  directory)
