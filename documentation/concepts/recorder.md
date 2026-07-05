---
title: Recorder
description: A Service that subscribes to log topics, keeps recent records in
  per-topic ring buffers and republishes them as shared state for remote
  observation on the Dashboard
type: concept
audience: [architects, developers, end-users]
status: work-in-progress
source:
  - src/aiko_services/main/recorder.py
related: [design_overview, service, share, registrar, dashboard, message]
version: "0.6"
last_updated: 2026-07-05
---

# Recorder

## Overview

The **Recorder** is a small diagnostic [Service](service.md) that
subscribes to a wildcard MQTT topic filter — by default every process's
log topic, `{namespace}/+/+/+/log` — and keeps the most recent records in
per-topic ring buffers, held in an LRU cache so only the most recently
active topics are retained. Each record is also republished into the
Recorder's `ECProducer` shared state (see [Share](share.md)), which makes
the recent log activity of the whole deployment remotely observable — for
example, from the [Dashboard](dashboard.md) or any `ECConsumer`.

**Why you'd use it**: to watch recent log output from *every* Aiko
Services process in one place, without attaching to each process
individually:

```bash
mosquitto_sub -t '#' -v          # raw firehose, for comparison
aiko_registrar &
cd src/aiko_services/main
./recorder.py &                  # curated: recent logs per topic,
                                 # visible as shared state
```

## For application developers

### Command-line usage

There is no console script for this concept (no `aiko_recorder` entry
point in `pyproject.toml`); run the module directly:

```bash
cd src/aiko_services/main
./recorder.py [TOPIC_PATH_FILTER] &
```

`TOPIC_PATH_FILTER` defaults to `{namespace}/+/+/+/log` (e.g.
`aiko/+/+/+/log`) — the log topic of every Service process in the
namespace. Any MQTT topic filter is accepted, but only a single filter per
Recorder is supported (recording multiple different topic paths is on the
roadmap).

A typical session, following the source header:

```bash
mosquitto_sub -t '#' -v &        # observe everything (optional)
aiko_registrar &
./recorder.py &
aiko_dashboard                   # select the recorder Service and inspect
                                 # its "lru_cache.<topic>" shared state
```

### Public API

```python
class Recorder(Service):
    Interface.default("Recorder", "aiko_services.main.recorder.RecorderImpl")
```

The Recorder Interface currently declares no methods (a placeholder
`@abstractmethod` is commented out in the source) — the public surface is
its **shared state**, consumed via `ECConsumer` / the Dashboard:

| Share item | Meaning |
|------------|---------|
| `lifecycle`, `log_level`, `source_file` | Standard Service health items |
| `topic_path_filter` | The MQTT filter being recorded |
| `lru_cache_size`, `ring_buffer_size` | Configured capacities |
| `lru_cache.<topic>` | Most recent (sanitised) record seen on `<topic>` |

Service protocol: `.../recorder:0` (under `SERVICE_PROTOCOL_AIKO`).

**Wire behaviour.** Inbound, the Recorder is a passive subscriber to
`topic_path_filter`. Outbound, each received payload is republished
through the standard `ECProducer` update protocol as an update to
`lru_cache.<topic>`, after sanitisation so that arbitrary log text
survives S-expression parsing:

```
" "  (space)  →  " "  (Unicode U+00A0, no-break space)
"("           →  "{"
")"           →  "}"
```

Log messages with special characters are a known weakness of the parser
(`utilities/parser.py` `generate()` / `parse()`); the source suggests
Canonical S-expressions as the eventual fix — the character substitution
is the interim measure.

There is no request / response exchange, so no sequence diagram is
warranted.

## For framework developers (internals)

### Design

```
   {namespace}/+/+/+/log  (or custom filter)
              │ every matching message
              ▼
   ┌───────────────────────────────────────────┐
   │ RecorderImpl (Service)                    │
   │                                           │
   │ lru_cache: LRUCache(size 2)               │
   │   topic_a ─► deque(maxlen=2)  ring buffer │
   │   topic_b ─► deque(maxlen=2)  ring buffer │
   │                                           │
   │ ECProducer: lru_cache.<topic> = record    │
   └──────────────────┬────────────────────────┘
                      ▼
        ECConsumer / Dashboard (remote observers)
```

Key design points:

- **Bounded memory by construction**: an LRU cache of topics, each with a
  fixed-size ring buffer (`collections.deque(maxlen=...)`) — a noisy
  deployment cannot grow the Recorder without limit.
- **Observation via shared state**, not a bespoke query protocol: the
  Recorder reuses the `ECProducer` machinery, so any existing consumer
  (Dashboard, `ECConsumer`) works unchanged. The source marks the
  `lru_cache` share entry as a HACK — only the *latest* record per topic
  is exposed as shared state, while the ring buffers hold slightly more
  history locally.
- Both capacities are currently hard-coded to **2** (`_LRU_CACHE_SIZE`,
  `_RING_BUFFER_SIZE`), with `# 128` comments indicating the intended
  production values — debugging-sized settings, and on-the-fly
  configuration of both is on the roadmap.

### Implementation notes

- `recorder_handler(aiko, topic, payload_in)` looks up (or lazily
  creates) the ring buffer for `topic`, appends the sanitised record and
  publishes the `ECProducer` update. When the `LRUCache` evicts its
  oldest topic, the corresponding shared-state entry is *not* yet removed
  — the To Do notes an eviction (`popitem()`) handler should call
  `ECProducer.remove(topic)` so ECConsumers stay consistent.
- A source note observes that `ECConsumer._consumer_handler()`
  (`share.py`) needs to handle list and dict values properly — `(add ...)`
  appears to fail where `(update ...)` works, though the Dashboard ends
  up correct.
- The standard `log_level` change handler is wired through
  `_ec_producer_change_handler()`, so the Recorder's own logging is
  remotely adjustable like any other Service.
- The source header asks: why doesn't a Python MQTT client
  `subscribe("+/+/+/+/log")` (leading wildcard, no namespace) work? —
  hence the filter defaults to the explicit namespace prefix.

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `Recorder` (Interface) | Declare the Recorder Service type (no methods yet) | `Service` (parent Interface) |
| `RecorderImpl` | Subscribe to `topic_path_filter`; maintain LRU cache of per-topic ring buffers; sanitise records; republish latest record per topic as shared state | `LRUCache` (utilities); `collections.deque`; `ECProducer` ([Share](share.md)); `aiko.message` ([Message](message.md)) |

## Current limitations and roadmap

From the source `To Do` list and inline notes:

- Only one `topic_path_filter` per Recorder — improve the CLI to record
  multiple different topic paths
- On-the-fly configuration updates: `_RING_BUFFER_SIZE`,
  `_TOPIC_LRU_CACHE_SIZE`, and changing `topic_path_filter` should
  unsubscribe / resubscribe accordingly
- Capacities are hard-coded at debug size (2) rather than the intended
  128
- LRU eviction does not remove the evicted topic's shared-state entry
  (needs a `popitem()` handler plus `ECProducer.remove(topic)`)
- Statistics: LRU cache length, total and per-second message rates
- Parser robustness for log payloads with special characters — the
  space / parenthesis substitution is an interim HACK; Canonical
  S-expressions are the suggested fix
- No remote method API yet — the Interface is an empty placeholder

## Related concepts

- [Design overview](design_overview.md)
- [Service](service.md) — the Recorder is a plain Service
- [Share](share.md) — ECProducer shared state is the Recorder's output
- [Registrar](registrar.md) — must be running for the Recorder to appear
- [Dashboard](dashboard.md) — the usual way to view recorded logs
- [Message](message.md) — MQTT subscription with wildcard topic filters
