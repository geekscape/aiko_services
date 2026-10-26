---
title: Recorder
description: A Service that subscribes to log topics, keeps recent records in
  per-topic ring buffers and republishes them as shared state for remote
  observation on the Dashboard
type: concept
audience: [architects, developers, end-users]
status: work-in-progress
ste: adapted
source:
  - src/aiko_services/main/recorder.py
related: [design_overview, service, share, registrar, dashboard, message]
version: "0.6"
last_updated: 2026-10-23
---

# Recorder

## Overview

Source code: [`src/aiko_services/main/recorder.py`](../../src/aiko_services/main/recorder.py)

The **Recorder** is a small diagnostic [Service](service.md). It
subscribes to a wildcard MQTT topic filter, by default every process's
log topic, `{namespace}/+/+/+/log`. It keeps the most recent records in
per-topic ring buffers. An LRU cache holds those buffers, so the
Recorder retains only the most recently active topics. Each record is
also republished into the Recorder's `ECProducer` shared state (see
[Share](share.md)). Thus the recent log activity of the whole deployment
is remotely observable, for example from the [Dashboard](dashboard.md)
or any `ECConsumer`.

**Why to use it**: to watch recent log output from *every* Aiko
Services process in one place, without attaching to each process
individually:

```bash
mosquitto_sub -t '#' -v          # raw firehose, for comparison
aiko_registrar &
aiko_recorder &                  # curated: recent logs per topic,
                                 # visible as shared state
```

## For application developers

### Command-line usage

The console script is `aiko_recorder`:

```bash
aiko_recorder [--lru_cache_size N] [--ring_buffer_size N] [TOPIC_PATH_FILTER] &
```

`TOPIC_PATH_FILTER` defaults to `{namespace}/+/+/+/log` (for example
`aiko/+/+/+/log`) — the log topic of every Service process in the
namespace. Any MQTT topic filter is accepted, but only a single filter per
Recorder is supported (recording multiple different topic paths is on the
roadmap).

A typical session, following the source header:

```bash
mosquitto_sub -t '#' -v &        # observe everything (optional)
aiko_registrar &
aiko_recorder &
aiko_dashboard                   # select the recorder Service and inspect
                                 # its "lru_cache.<topic>" shared state
```

Both sizes are shared variables as well as options, so the Dashboard
changes them while the Recorder runs. The default of each one is 128,
which is what the source always intended. A smaller LRU cache evicts the
least recently used topics at once, and a smaller ring buffer keeps the
newest records. A value out of range leaves the one in force alone, and
the Recorder publishes it again and says so in its log.

The shared state carries `metrics.records`, `metrics.topics` and
`metrics.evicted`, so a client sees how much the Recorder holds and how
much it has let go.

A log record is stored and published as it arrived. The parser gives a
length prefix to a value that holds a space, a parenthesis, a quote, a
newline or a non-breaking space. It then returns that value exactly, so
the Recorder changes nothing. Before 2026-10-23 it turned each
parenthesis into a brace, which reported a log record that nobody wrote.

### The Dashboard page

`aiko_dashboard` has a page for each Recorder. Select the Service, then
press `S`. The page needs no `--plugin` flag, because
`ide/tui/dashboard/plugins.py` is the default module and registers it.

The page shows each recorded topic, how many records the shared state
holds for it, and the newest one. `Enter` on a topic shows those records.
The title bar carries the count of topics, records and evictions. Below
the topics are the filters, both sizes and the metrics.

The keys are `r` to record a filter, `R` to stop one, `L` for the log
level and `H` for help. Each of those functions is one the Recorder
allows in every posture, so this page has no posture to explain, which
the ProcessManager's page does.

A `lru_cache.<topic>` item is either the newest record, as a string, or
every record the ring buffer holds, as a list. The page reads both, so it
needs no change when that question is settled.

### Public API

```python
class Recorder(Actor):
    Interface.default("Recorder", "aiko_services.main.recorder.RecorderImpl")

    record(topic_path_filter)       # record these topics as well
    record_stop(topic_path_filter)  # stop, and forget what it recorded
```

An Actor since 2026-10-23, which is what `s_02_InterfaceComposition`
asks for. The spike refined `Service`, so a filter could be given only
at construction. A client adds one while it runs:

```bash
mosquitto_pub -t <topic_path>/in -m "(record_start aiko/+/+/+/out)"
```

The filter is the identity of a recording, so recording one twice
changes nothing. `record_stop` is not `stop(recording_id)`, which
`s_02` asks for and which cannot be written: `stop` is the framework's
control verb and takes no argument. ADR-025 decision 1 resolved the same
clash for the Display Actor's `exit`.

Deny by default (P12, ADR-023): the Recorder accepts `record`,
`record_stop`, `set_log_level` and `stop`, and denies every other
function. `recorder_handler` is the subscription callback, which no
client calls, so it is not on the list.

The rest of the surface is its **shared state**, consumed through
`ECConsumer` or the Dashboard:

| Share item | Meaning |
|------------|---------|
| `lifecycle`, `log_level`, `source_file` | Standard Actor health items |
| `filters` | Each MQTT filter being recorded |
| `lru_cache_size`, `ring_buffer_size` | The capacities in force |
| `lru_cache.<topic>` | The newest record seen on `<topic>` |
| `metrics.records` | Log records recorded |
| `metrics.topics` | Topics held, which is the LRU cache length |
| `metrics.evicted` | Topics evicted, each one losing its records |

Service protocol: `.../recorder:0` (under `SERVICE_PROTOCOL_AIKO`).

**Wire behavior.** Inbound, the Recorder subscribes to each filter, and
accepts the four functions above on its `in` topic. Outbound, each
received payload is republished through the standard `ECProducer` update
protocol, as an update to `lru_cache.<topic>`, exactly as it arrived:

```
" "  (space)  →  " "  (Unicode U+00A0, no-break space)
"("           →  "{"
")"           →  "}"
```

Log messages with special characters are a known weakness of the parser
(`utilities/parser.py` `generate()` / `parse()`). The source suggests
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
- **Observation through shared state**, not a bespoke query protocol.
  The Recorder reuses the `ECProducer` machinery, so any existing
  consumer (Dashboard, `ECConsumer`) works unchanged. The source marks
  the `lru_cache` share entry as a HACK: only the *latest* record per
  topic is exposed as shared state, while the ring buffers hold slightly
  more history locally.
- Both capacities are currently hard-coded to **2** (`_LRU_CACHE_SIZE`,
  `_RING_BUFFER_SIZE`). The `# 128` comments show the intended
  production values, so these are debugging-sized settings. On-the-fly
  configuration of both is on the roadmap.

### Implementation notes

- `recorder_handler(aiko, topic, payload_in)` looks up the ring buffer
  for `topic`, or lazily makes it. It then appends the sanitized record
  and publishes the `ECProducer` update. When the `LRUCache` evicts its
  oldest topic, the related shared-state entry is *not* yet removed. The
  To Do notes that an eviction (`popitem()`) handler must call
  `ECProducer.remove(topic)`, so that ECConsumers stay consistent.
- A source note observes that `ECConsumer._consumer_handler()`
  (`share.py`) must handle list and dict values correctly. `(add ...)`
  appears to fail where `(update ...)` works, although the Dashboard
  ends up correct.
- The standard `log_level` change handler is wired through
  `_ec_producer_change_handler()`, so the Recorder's own logging is
  remotely adjustable like any other Service.
- The source header asks why a Python MQTT client
  `subscribe("+/+/+/+/log")` (leading wildcard, no namespace) does not
  work. That is why the filter defaults to the explicit namespace prefix.

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `Recorder` (Interface) | Declare `record_start` and `record_stop` | `Actor` (parent Interface) |
| `RecorderImpl` | Subscribe to each filter; hold an LRU cache of per-topic ring buffers; remove an evicted topic's shared state; republish the newest record of each topic | `LRUCache` (utilities); `collections.deque`; `ECProducer` ([Share](share.md)); `FunctionGate` |

## Current limitations and roadmap

From the source `To Do` list and inline notes:

- Replay, which `s_02_InterfaceComposition` says lands here
- A recording identity of its own, instead of the filter
- The shared state carries the newest record of each topic, and not the
  whole ring buffer. A depth of 128 is about 8 KB for each record
  published, to each attached consumer. Thus this waits on a design that
  sends no large message for each log record
- LRU eviction does not remove the evicted topic's shared-state entry
  (needs a `popitem()` handler plus `ECProducer.remove(topic)`)
- Statistics: LRU cache length, total and per-second message rates
- Parser robustness for log payloads with special characters — the
  space / parenthesis substitution is an interim HACK. Canonical
  S-expressions are the suggested fix
- No remote method API yet — the Interface is an empty placeholder

## Related concepts

- [Design overview](design_overview.md)
- [Service](service.md) — the Recorder is a plain Service
- [Share](share.md) — ECProducer shared state is the Recorder's output
- [Registrar](registrar.md) — must be running for the Recorder to appear
- [Dashboard](dashboard.md) — the usual way to view recorded logs
- [Message](message.md) — MQTT subscription with wildcard topic filters
