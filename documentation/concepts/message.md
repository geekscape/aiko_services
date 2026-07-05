---
title: Message
description: The publish/subscribe messaging abstraction — an abstract
  Message contract with an MQTT implementation (connection lifecycle,
  last-will-and-testament, topic subscription) and a Castaway null
  implementation for running without a server
type: concept
audience: [architects, developers, end-users]
status: work-in-progress
source:
  - src/aiko_services/main/message/__init__.py
  - src/aiko_services/main/message/message.py
  - src/aiko_services/main/message/mqtt.py
  - src/aiko_services/main/message/castaway.py
related: [design_overview, transport, connection, service, event, registrar]
version: "0.6"
last_updated: 2026-07-05
---

# Message

## Overview

**Message** is the lowest layer of the Aiko Services communication stack:
an abstract publish/subscribe contract (`Message`) with two
implementations — `MQTT`, which carries all distributed communication via
an MQTT server (broker) using the paho-mqtt client, and `Castaway`, a
null implementation used when no MQTT server is available so that a
process can still run standalone.

Everything above this layer — [Transport](transport.md) proxies,
[Service](service.md) remote invocation, [Registrar](registrar.md)
discovery, [Share](share.md) eventual consistency — reduces to
`aiko.message.publish(topic, payload)` and topic subscriptions. Each
process owns exactly **one** Message connection, created and managed by
the process event loop (see [Design](#design)); application code rarely
constructs a Message itself.

**Why you'd use it**: to send or receive raw payloads on an MQTT topic —
for example, a Service publishing to its output topic, exactly as
`test_mqtt.py` does:

```python
payload_out = f"(test {message})"
aiko.message.publish(self.topic_out, payload_out)
```

Incoming messages are handled by registering a topic handler with the
process (which subscribes on your behalf):

```python
aiko.process.add_message_handler(handler, topic)
```

## For application developers

### Command-line usage

Message has no CLI of its own — it is configured entirely through
environment variables and exercised by every Aiko Services tool
(`aiko_registrar`, `aiko_dashboard`, `aiko_pipeline`, ...).

Connection configuration (read by
`src/aiko_services/main/utilities/configuration.py`):

```bash
AIKO_NAMESPACE=aiko        # topic namespace prefix (default "aiko")
AIKO_MQTT_HOST=localhost   # tried first; falls back to "localhost"
AIKO_MQTT_PORT=1883        # or 1884 (websockets), 9883 (TLS), 9884 (WSS)
AIKO_MQTT_TRANSPORT=tcp    # or "websockets"
AIKO_MQTT_TLS=true         # if unset, TLS is enabled when AIKO_USERNAME is set
AIKO_USERNAME=username     # optional MQTT authentication ...
AIKO_PASSWORD=password     # ... setting a username enables TLS by default
```

Logging control — the MQTT module deliberately ignores `AIKO_LOG_LEVEL`
(so framework-wide `DEBUG` does not flood the console with low-level
MQTT records), and it cannot use the MQTT logging handler to diagnose
itself:

```bash
AIKO_LOG_LEVEL_MQTT=DEBUG some_application ...     # paho-level connect/subscribe
AIKO_LOG_LEVEL_MESSAGE=DEBUG some_application ...  # incoming messages (process.py)
```

A plain `mosquitto_sub -h $AIKO_MQTT_HOST -t '#' -v` is the standard way
to watch Message traffic from outside Aiko Services.

### Public API

The abstract contract (`src/aiko_services/main/message/message.py`):

```python
class MessageState:
    DISCONNECTED = "DISCONNECTED"
    CONNECTED = "CONNECTED"

class Message(abc.ABC):
    def __init__(self, message_handler=None, topics_subscribe=None,
        topic_lwt=None, payload_lwt=None, retain_lwt=False,
        mqtt_state_handler=None): ...
    def publish(self, topic, payload, retain=False, wait=False): ...
    def set_last_will_and_testament(self,
        topic_lwt=None, payload_lwt="(absent)", retain_lwt=False): ...
    def subscribe(self, topics): ...
    def unsubscribe(self, topics, remove=True): ...
```

| Operation | Effect |
|-----------|--------|
| `publish(topic, payload, retain, wait)` | Publish a payload; `retain=True` asks the server to keep it for future subscribers; `wait=True` blocks until the server confirms delivery |
| `subscribe(topics)` | Subscribe to one topic (`str`), several (`list`) or the keys of a `dict`; deferred automatically until connected |
| `unsubscribe(topics, remove)` | Unsubscribe; `remove=False` keeps the topics on the books for later re-subscription |
| `set_last_will_and_testament(...)` | Change the will registered with the MQTT server (see below) |

`topics_subscribe` accepts the same `str` / `list` / `dict` forms — the
process passes its message-handler dictionary directly, so its keys
become the subscriptions.

**You normally receive the Message ready-made.** The process event loop
creates the singleton connection during `aiko.process.initialize()` and
publishes it as `aiko.message` (`src/aiko_services/main/process.py`):

```python
aiko.message = Castaway()          # standalone and isolated :(
try:
    aiko.message = MQTT(
        self.on_message, self._message_handlers,
        aiko.topic_lwt, aiko.payload_lwt, False,
        self.on_mqtt_state_change)
except SystemError as system_error:
    ...   # fatal if mqtt_connection_required, else continue with Castaway
```

If no MQTT server can be reached, `MQTT()` raises `SystemError`. When
`aiko.process.run(mqtt_connection_required=False)` is used, the process
carries on with the `Castaway` null implementation — every publish and
subscribe silently does nothing, which lets purely local applications
(and tests) run without any server.

**Topic conventions.** Every process claims a topic subtree, and each
[Service](service.md) within it gets a `service_id` branch:

```
{namespace}/{hostname}/{process_id}/{service_id}/in     # remote invocation
{namespace}/{hostname}/{process_id}/{service_id}/out    # published results
{namespace}/{hostname}/{process_id}/{service_id}/log    # log records
{namespace}/{hostname}/{process_id}/0/state             # LWT: "(absent)"
{namespace}/service/registrar                           # Registrar boot topic
```

MQTT wildcard subscriptions are supported end-to-end: `topic/#` (match a
subtree) and `prefix/+/+/suffix` (match single levels).

**Connection and last will and testament (LWT).** The will is registered
with the MQTT server *at connect time*; if the process later dies without
a clean disconnect, the server itself publishes the will payload —
`(absent)` — on the process state topic. This is how the rest of Aiko
Services learns that a Service has vanished:

```
Process                    MQTT (Message)            MQTT server
   │ initialize()               │                        │
   │── MQTT(handler, topics, ──►│                        │
   │   topic_lwt, "(absent)")   │ probe host:port (up?)  │
   │                            │ will_set(topic_lwt,    │
   │                            │   "(absent)")          │
   │                            │── connect ────────────►│ stores will
   │                            │◄─ connected ───────────│
   │◄─ state: CONNECTED ────────│── subscribe(topics) ──►│
   │   (Connection → TRANSPORT) │                        │
   ⋮                            ⋮                        ⋮
   ✗ process dies (no clean disconnect)                  │
                                                         │ publishes
                                            "(absent)" ──┤ will to
                                                         │ topic_lwt
```

`set_last_will_and_testament()` changes the will *after* construction by
disconnecting and reconnecting (the MQTT protocol only accepts a will at
connect time). Note that a clean `disconnect()` does **not** cause the
server to send the will — only an ungraceful death does. The Registrar
uses this call when it takes over as primary.

## For framework developers (internals)

### Design

```
      application / framework code
              │ publish()                 ▲ handler(aiko, topic, payload)
              ▼                           │
   ┌─────────────────────────┐    ┌───────────────────────────┐
   │ aiko.message: Message   │    │ process event loop        │
   │  ├─ MQTT     (paho)     │    │  on_message() ─► queue ─► │
   │  └─ Castaway (no-op)    │    │  on_message_queue_handler │
   └───────────┬─────────────┘    └───────────▲───────────────┘
               │ paho network thread          │ event.queue_put()
               ▼        (loop_start)          │
   ┌─────────────────────────────────────────────────────────┐
   │                   MQTT server (broker)                  │
   └─────────────────────────────────────────────────────────┘
```

Key design points:

- **One connection per process** (singleton), owned by
  `ProcessImplementation` — Services share it rather than opening their
  own. The `Message` abstract class exists so other transports can be
  substituted; `Castaway` is the *Null Object* of the family (the file
  ends with the comment `# Wilson !`).
- **Two threads.** paho-mqtt's `loop_start()` runs the network I/O on a
  background thread. The process installs `on_message()` as the handler,
  which only does `event.queue_put(message, "message")` — actual message
  handling happens on the main event loop via
  `on_message_queue_handler()`. This keeps application handlers off the
  MQTT thread (blocking there would deadlock the client, see the
  roadmap).
- **Connection state flows upward.** `MQTT` reports
  `MessageState.CONNECTED / DISCONNECTED` through the
  `mqtt_state_handler` callback; the process maps this onto the
  [Connection](connection.md) state machine (`NONE → TRANSPORT`, and
  later `→ REGISTRAR` when the Registrar is discovered).
- **Server selection before connection.** `get_mqtt_configuration()`
  probes candidate `(host, port)` pairs with a raw TCP connect —
  `AIKO_MQTT_HOST` first, then a built-in host list, then `localhost` —
  and only then hands a known-up server to paho.

### Implementation notes

- **Deferred subscription.** `subscribe()` records topics in
  `self.topics_subscribe` and only issues the network subscribe when
  connected; `_on_connect()` replays the whole list, so subscriptions
  survive reconnection (paho reconnects automatically via its network
  loop).
- **`#` wildcard bookkeeping.** Subscribing to `#` unsubscribes all
  individual topics (kept on the books with `remove=False`) and sets
  `wildcard_topic` / `wildcard_subscribed` flags; unsubscribing from `#`
  restores the individual subscriptions. Used by tools that watch all
  traffic.
- **Busy-wait synchronisation.** `wait_connected()`,
  `wait_disconnected()` and `wait_published()` poll a flag in 1 ms steps
  for at most `_MAXIMUM_WAIT_TIME` (2000 steps ≈ 2 seconds), then log an
  error and *carry on* — they do not raise. `publish()` always calls
  `wait_connected()` first; `wait=True` additionally waits on a single
  shared `published` flag (not per-message, so concurrent publishers can
  race).
- **Never block on the MQTT thread.** If code running on the paho thread
  waits for a condition that depends on an *incoming* message (e.g.
  `set_last_will_and_testament()` → `wait_disconnected()`), the wait
  times out because that thread is the one that would process the
  message. The process-level message queue avoids this for ordinary
  handlers; framework code must not call the `wait_*` functions from a
  message callback that bypasses the queue.
- **TLS is implied by credentials.** With `AIKO_MQTT_TLS` unset, TLS is
  enabled exactly when `AIKO_USERNAME` is non-empty.
- A UDP bootstrap responder (`bootstrap_start()` in `configuration.py`)
  exists so devices without DNS/mDNS can broadcast `boot?` and learn the
  MQTT host, port and namespace.

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `Message` (abstract) | Declare the pub/sub contract: `publish()`, `subscribe()`, `unsubscribe()`, `set_last_will_and_testament()`; define `MessageState` | Implementations below; `ProcessImplementation` (owner) |
| `MQTT` | Select and connect to an MQTT server; register the LWT; defer/replay subscriptions across (re)connection; manage `#` wildcard mode; report state changes; `wait_*` synchronisation | paho-mqtt `Client` (network thread); `get_mqtt_configuration()` (server selection); [Connection](connection.md) via `mqtt_state_handler` |
| `Castaway` | Null Object: satisfy the Message contract with no-ops when no server is available | `ProcessImplementation` (fallback when MQTT construction fails) |
| `ProcessImplementation` (in `process.py`) | Own the singleton `aiko.message`; queue incoming messages onto the event loop; dispatch by topic (exact, `#`, `+` matching); map MessageState onto Connection state | `MQTT` / `Castaway`; [Event](event.md) loop; [Registrar](registrar.md) boot topic |

## Current limitations and roadmap

From the source `To Do` lists — highlights:

- **Known bug** (documented in `mqtt.py`): waiting on the MQTT thread for
  a condition driven by an incoming message times out — e.g. the
  Registrar handling `(primary absent)` then calling
  `set_last_will_and_testament()`. Proposed fix: queue *all* incoming
  MQTT messages onto the main event loop by default.
- Reconnect handling: implement explicit reconnection after
  disconnection (raise an exception on failure rather than exiting);
  rediscover the MQTT server on disconnection; `process.py` likewise
  plans automatic reconnection.
- `wait_connected()` / `wait_disconnected()` / `wait_published()`:
  refactor into a single condition-wait; on timeout, choose between
  carrying on and reconnecting instead of only logging an error.
- Track which subscriptions actually succeeded by matching
  `mqtt_client.subscribe()` message ids against `on_subscribe()`.
- `message.py`: implement `disconnect()` and `with`-statement support;
  add performance statistics.
- Allow `MQTT_HOST` / `MQTT_PORT` to be overridden by CLI parameters; a
  runtime message to change the MQTT logging level; a destructor.
- `configuration.py`: replace the hard-coded fallback host list with an
  environment variable; move discovery/bootstrap into
  `message/discovery.py`; implement discovery of the default MQTT host
  and namespace.
- `process.py`: multiple simultaneous message server connections (for
  Federation).
- There are no automated tests for this package; `configuration.py`
  lists the connection-failure scenarios that a test suite should cover.

## Related concepts

- [Design overview](design_overview.md)
- [Transport](transport.md) — remote Service invocation built on Message
- [Connection](connection.md) — the state machine fed by MessageState
- [Service](service.md) — topic conventions per Service (`in`/`out`/`log`)
- [Event](event.md) — the event loop that processes queued messages
- [Registrar](registrar.md) — discovered via the boot topic and LWT
