---
title: "Self-Awareness Telemetry — HostMonitor protocol, the host.* EC key
  namespace and OpenTelemetry alignment"
description: Pre-RFC specification of self-awareness telemetry — the
  HostMonitor Actor and host.* EC keys for resource monitoring, and the
  OpenTelemetry model for logs, metrics and traces built on function calls
  over MQTT, the Recorder and the Dashboard
type: specification
audience: [architects, developers, implementers, ai-coding-agents]
status: draft-for-verification
ste: adapted
related: [p_00_DesignPrinciples, p_02_CandidatePrinciples,
  t_01_OkfRfcTemplate]
last_updated: 2026-08-01
---

# Self-Awareness Telemetry — HostMonitor protocol, the `host.*` EC key namespace and OpenTelemetry alignment

## 1. Abstract

This document specifies how an Aiko Services deployment observes its own hosts and itself.
Two halves, one model:

1. **Resource telemetry:** one **HostMonitor** Actor for each host. It publishes CPU,
   memory, GPU/VRAM, power, file-system, network, process and device state as
   eventually-consistent (EC) state, under the `host.*` key namespace. A bounded local
   history sits behind a **MetricsStore** seam.
2. **OpenTelemetry alignment:** Aiko Services adopts the OpenTelemetry data model for its
   three signals:
   - **Logs** — the existing per-service `/log` topics
   - **Metrics** — `host.*` and pipeline frame metrics, named per the OpenTelemetry
     semantic conventions
   - **Traces** — spans derived from the function calls that Aiko Services already makes
     as MQTT messages

   The bus stays the native transport and the ground truth (CP-I). A single **OTelBridge**
   export seam, built on the Recorder, carries the signals to the OpenTelemetry ecosystem
   (OTLP → Grafana/Jaeger/Prometheus and comparable tools).

Implementations of HostMonitor, consumers of `host.*` keys, and the bridge must conform.
Authored RFC-shaped per t_01_OkfRfcTemplate for later promotion into the AS-RFC series
(potential item 04). Until then it is pre-RFC prose with normative intent.

## 2. Terminology

Interpret the key words MUST, MUST NOT, REQUIRED, SHALL, SHOULD and MAY as described in
RFC 2119, when they appear in all capitals. "EC state" means the `share` dictionary of a
Service, published through an ECProducer and observable through an ECConsumer. "Collector"
means a
component that samples one resource class. "Cadence class" means a named sampling period.
"Signal" means an OpenTelemetry signal: log, metric or trace. "Span" and "trace context" are
as defined by OpenTelemetry and W3C Trace Context. "The bridge" means the OTelBridge Actor of
§7.4.

## 3. The HostMonitor Actor

**[REQ-1]** A HostMonitor is an Actor with protocol id ending `host_monitor:0`, exactly one
per participating host, discoverable through the Registrar like any Service (P5, P6).

**[REQ-2]** All telemetry publication MUST use `ec_producer.update()`. Direct writes to
`self.share` are non-conformant (they are invisible to remote observers).

**[REQ-3]** Collectors MUST run off the event-loop thread (or complete in bounded time within
a timer handler). A stalled collector MUST NOT stall the mailbox of the Actor (P2). The reference
pattern is the timer-handler design of `xgo_robot.py` `_monitor_battery()`, generalized.

**[REQ-4]** HostMonitor MUST set an MQTT Last Will and Testament so that host death is
observable as `(absent)` on its `/state` topic. Consumers MUST treat all `host.*` keys from an
absent HostMonitor as stale, not as zero.

**[REQ-5]** A HostMonitor SHOULD be launched and watched by ProcessManager, so a crashed
monitor restarts under the same supervision as any managed process.

## 4. The `host.*` key namespace

**[REQ-6]** All telemetry keys live under the top-level EC key `host`. They use the
two-level dotted form that ECProducer supports today (`host.cpu`, `host.memory`, …). Each
value is a dictionary of named fields. The field names below are normative. The units are fixed for each field.

| Key | Necessary fields (units) |
|-----|-------------------------|
| `host.info` | `hostname`, `platform`, `boot_utc` (ISO 8601), `monitor_version` |
| `host.cpu` | `percent` (0–100 overall), `per_cpu` (list), `load_1m/5m/15m`, `count` |
| `host.memory` | `total_b`, `available_b`, `used_percent`, `swap_used_percent` |
| `host.gpu` | per-GPU list: `name`, `utilization_percent`, `vram_total_b`, `vram_used_b`, `temperature_c`, `power_w` — key absent when no collector (see [REQ-10]) |
| `host.power` | `source` (`mains` \| `battery` \| `unknown`), `battery_percent`, `charging` (bool), `time_remaining_s` |
| `host.disk` | per-mount list: `mount`, `total_b`, `used_percent`; plus `io_read_bps`, `io_write_bps` |
| `host.network` | per-interface list: `name`, `kind` (`ethernet` \| `wifi` \| `wan` \| `loopback` \| `other`), `up` (bool), `rx_bps`, `tx_bps`; plus `wan_reachable` (bool, probed at slow cadence) |
| `host.processes` | `count`; `top` (top-N by CPU: `pid`, `name`, `cpu_percent`, `rss_b`); `managed` (one entry per ProcessManager-managed process, keyed by its uid) |
| `host.devices` | list of notable devices: `kind` (`camera` \| `serial` \| `usb` \| `other`), `id`, `present` (bool) |
| `host.monitor` | self-telemetry: `collect_ms` per collector, `overhead_cpu_percent`, `errors` |

**[REQ-7]** Byte quantities use the `_b` suffix and are integers. Percentages are floats
0–100. Rates use `_bps` (bytes/second). Durations use `_s` or `_ms`. Consumers MUST NOT infer
units from magnitude.

**[REQ-8]** Every collector samples at one of three cadence classes, each a HostMonitor
parameter: `fast` (default 2 s — cpu, memory), `normal` (default 10 s — gpu, disk, network,
processes), `slow` (default 60 s — power source, devices, `wan_reachable`, info). Defaults MAY
be tuned for each deployment. A HostMonitor MUST publish its active cadences under
`host.monitor`.

**[REQ-9]** Staleness: each `host.*` value carries a `sampled_utc` field. A consumer MUST
treat a value older than three cadence periods as stale. HostMonitor does not erase stale
keys. The absence semantics come from [REQ-4].

**[REQ-10]** Optional resources degrade by omission: where a collector is unavailable (no GPU,
no battery), its key is absent or its `source`/`present` field says so — never fabricated
zeros.

## 5. Collector architecture

**[REQ-11]** The core collectors (cpu, memory, disk, network, processes, battery) use psutil
only — no additional runtime dependencies (P9). GPU/VRAM (NVML), platform power extensions and
device probes are pluggable collector implementations, registered per P7 composition. Absence
of a plugin never fails the monitor.

**[REQ-12]** Overhead budget. Use the default cadences. Then the CPU usage of HostMonitor
in the steady state MUST NOT be more than 2% of one core on a Raspberry Pi 5. Also, its RSS
MUST NOT be more than 64 MiB.

The budget is verified at the telemetry milestone exit. It is
measured again by
the conformance trace, not assumed. `host.monitor` makes the monitor's own cost observable —
the observer is not exempt from observation (CP-I).

## 6. History — the MetricsStore seam

**[REQ-13]** Current values live only in EC state. History lives behind a `MetricsStore`
interface (the storage mirror of the e_03_FirstClassAgents MemoryStore pattern):
`append(key, value, sampled_utc)`, `query(key, window, aggregate, reply_topic)` — reply-to per
P3. The default implementation is local SQLite. Stored points carry the OpenTelemetry metric
data-model fields (§7.1) so history and export share one schema.

**[REQ-14]** History is bounded with a documented overflow policy (P9): per-key ring buffer,
default 24 h at cadence resolution, and the oldest rows drop first. The bounds are HostMonitor
parameters and are published under `host.monitor`.

**[REQ-15]** Windowed queries (`median`, `mean`, `min`, `max`, `p95` over a window) are
computed for each host, over local `sampled_utc` timestamps. No mechanism may compare clocks across
hosts (P4). Cross-host analysis is the consumer's job, over per-host aggregates.

The planned sandboxed predicate language consumes exactly this query
surface. `(window <key> <duration>)` resolves through MetricsStore. A live key reference
resolves through ECConsumer.

## 7. OpenTelemetry alignment — logs, metrics and traces

**Decision (project lead, 2026-07-08):** self-awareness uses OpenTelemetry as the model for
logs, metrics and traces. It is built on what Aiko Services already has: function calls as
MQTT messages, the Recorder and the Dashboard. The division of labor that keeps this honest
under P9 and CP-I: **signals are born on the bus in bus-native form. OpenTelemetry is the
schema they conform to and the border they are exported across.** No Service other than the
bridge takes an OpenTelemetry SDK dependency.

### 7.1 Metrics

**[REQ-17]** Every `host.*` field ([REQ-6]) and every pipeline frame metric
(`frame.metrics` element/pipeline times and memory) has a normative mapping to an
OpenTelemetry metric, per the OpenTelemetry semantic conventions. The instrument type and
the unit are declared. Representative mappings (the full table lives with the schema in the code
tree):

| Aiko Services field | OpenTelemetry metric (semconv) | Instrument, unit |
|---------------------|--------------------------------|------------------|
| `host.cpu.percent` | `system.cpu.utilization` | gauge, `1` (0–1 rescaled) |
| `host.memory.available_b` | `system.memory.usage{state=free}` | updowncounter, `By` |
| `host.disk.io_read_bps` | `system.disk.io` (rate derived) | counter, `By` |
| `host.network.rx_bps` | `system.network.io{direction=receive}` | counter, `By` |
| `host.gpu.*` | `hw.gpu.*` (hardware semconv) | gauge |
| `host.processes.managed[*].cpu_percent` | `process.cpu.utilization` | gauge, `1` |
| `frame.metrics` `<element>_time` | `aiko.pipeline.element.duration` | histogram, `s` |

**[REQ-18]** OpenTelemetry resource attributes identify the producer: `host.name`,
`service.name` (the Aiko Services service name), `service.instance.id` (the
`namespace/host/pid/sid` topic path — stable-identity work in potential item 07 refines
this), `service.version` (`aiko.id`). Aiko Services-specific metrics use the `aiko.` prefix.
resource-class metrics reuse the standard `system.`/`hw.`/`process.` conventions rather than
inventing parallel names.

### 7.2 Traces — function calls over MQTT are the spans

Aiko Services' remote method invocation *is* a traceable call graph: every `(command …)`
message on a `/in` topic is a function call, every Pipeline frame is a causal chain of
element invocations across processes and hosts. Tracing formalizes what the bus already
shows.

**[REQ-19]** Trace derivation lands first, with zero wire change. The bridge MUST be able
to construct spans from observed bus traffic alone. The sources are:

- Span name — from the service + command
  (`aiko.message.call: <service_name>.<command>`)
- Span start/end — from Hook-emitted timing, where it is available
  (ACTOR_HOOK_MESSAGE_IN/CALL, PIPELINE_HOOK_PROCESS_FRAME/ELEMENT — the existing AOP seam)
- Resource attributes — per [REQ-18]
- Frame causality — from the stream id + frame id. There is one trace for each frame, and
  one span for each element invocation. The parent is the graph predecessor.

**[REQ-20]** Trace propagation (lands second, wire-visible): messages SHOULD carry W3C Trace
Context (`traceparent`, optional `tracestate`) so causality is explicit rather than derived —
an Actor that handles a message continues the incoming context. `create_frame` and
`process_frame` propagate it along the graph. Hooks inject and extract it, so element code
never touches it. The
exact wire encoding (an optional metadata element alongside the existing
positional-args-or-trailing-dict convention) is fixed in the AS-RFC series (item 04,
AS-RFC-1 territory) — this specification needs the capability and the semantics, not the
byte layout. Non-participating Services MUST be able to ignore the context unharmed (CP-G
tolerant reader).

**[REQ-21]** Span timing uses each host's monotonic clock for durations and local wall-clock
only as metadata. Cross-host span order relies on causality (parent/child from
propagation or derivation). It never compares wall clocks across hosts (P4, the same rule
as the trace format of potential item 14).

### 7.3 Logs

**[REQ-22]** Every record already published to the `/log` topic of a service maps to an
OpenTelemetry LogRecord. The severity comes from the log level, the body from the message,
and the resource attributes per [REQ-18]. When a log is emitted inside a handled message or
frame, the record also carries the active trace/span ids from §7.2.

Thus the logs, the metrics and the
traces correlate by construction.
The `/log` topic stays the transport. No second logging path is introduced.

### 7.4 The OTelBridge — one export seam, built on the Recorder

**[REQ-23]** A single **OTelBridge** Actor per deployment (or per site) subscribes to bus
traffic exactly as the Recorder does. It is the export face of Recorder v2 (the planned
record/replay capture design and this bridge share the tap).

Also,
converts: `/log` records → LogRecords, `host.*`/frame metrics → OTLP metrics, derived or
propagated call/frame causality → spans.

It exports OTLP (gRPC or HTTP) to a configured
endpoint: an OpenTelemetry Collector, a Grafana stack, Jaeger, Prometheus through the
Collector,
or a file exporter for air-gapped sites.

**[REQ-24]** The OpenTelemetry SDK dependency is confined to the bridge (P9): HostMonitor,
Pipelines, Actors and the Dashboard neither import it nor need it. A deployment without a
bridge loses nothing on-bus — EC state, `/log` topics, Recorder traces and the Dashboard are
unchanged (CP-I: the bus is ground truth, and OTLP is a projection of it).

**[REQ-25]** The Dashboard remains bus-native. Timeline/flow visualization of traces is the
planned Dashboard tracing plugin, which reads the shared trace format. Rich
OpenTelemetry-ecosystem visualization (Grafana/Jaeger) is reached through the bridge. Both
views render the same underlying events — one mechanism, two renderers (P10).

**[REQ-26]** The bridge is observe-only. It holds no authority, it accepts no inbound OTLP,
and it mutates nothing (the sole-authority-gate posture). An *importer* of external telemetry, if it is ever
wanted, is a
separate concern gated like any external surface). Its own health is EC state
(`otel_bridge.*`: export queue depth — bounded per P9, endpoint status, dropped-signal
counts. Drops are counted, never silent).

## 8. Correlation summary

**[REQ-16]** The correlation identifiers across all self-awareness data are the
OpenTelemetry ones:

- `trace_id`/`span_id` join the logs, the metrics exemplars and the spans
- The resource attributes ([REQ-18]) join everything to a host and a service
- The stream id + frame id stay the bus-native keys. Frame traces are derived from them
  ([REQ-19])

MetricsStore rows carry
`sampled_utc` plus the resource attributes. The join tooling (comparison, replay,
visualization) belongs to potential item 14 and action 9. This specification guarantees the
identifiers
exist and agree.

## 9. Security Considerations

The bus is (today) unauthenticated: anyone on the broker can read `host.*` state, which
reveals host names, process names and load patterns — reconnaissance-grade information. Until
potential item 08 (CP-C) lands, deployments MUST treat telemetry as trusted-LAN only.
HostMonitor accepts no command that executes anything. Its wire surface is parameter updates
(cadences, bounds) through the ordinary EC control path. CP-E applies: the parameters are
coerced and validated data, and are never evaluated.

A forged HostMonitor could publish false telemetry and steer any automated consumer of it.
The mitigations are capability security (item 08) and
protected invariants at the consuming gate, which bound what one false signal can cause.

The **bridge widens the audience**. An OTLP endpoint receives the operational picture of
the deployment. Thus the endpoint and its transport credentials are part of the trust
boundary. A deployment MUST give the export destination the same care as broker access, and
the bridge MUST support TLS OTLP. Trace context ([REQ-20]) is metadata,
never code, and MUST NOT influence dispatch (a message is handled identically with or
without it). MetricsStore files inherit the host file-system permissions. They contain
operational metadata, not payload data.

## 10. Registry Considerations

Adds to the protocol registry: `host_monitor:0`, `otel_bridge:0`. Adds the reserved EC key
prefixes `host.` and `otel_bridge.`, the field/unit vocabulary of §4, and the
metric-mapping table of [REQ-17] (extended per CP-G — new collectors add mappings, never
silently change existing semantics). Reserves the `aiko.` OpenTelemetry namespace for
Aiko Services-specific instruments and attributes. The trace-context wire element is
registered by the AS-RFC that fixes its encoding ([REQ-20]).

## 11. References

**Normative:** p_00_DesignPrinciples (P2–P7, P9).
t_01_OkfRfcTemplate (form). W3C Trace Context. The OpenTelemetry
specification — data model, semantic conventions (system/hardware/process) and OTLP.
**Informative:** p_02_CandidatePrinciples (CP-E, CP-F, CP-G,
CP-I). `src/aiko_services/examples/xgo_robot/xgo_robot.py`
(the `_monitor_battery` pattern). `src/aiko_services/main/process_manager.py` ("Use Open
Telemetry schema" To Do — the source tree already points here).
`src/aiko_services/main/recorder.py` (the tap that the bridge builds on).
`src/aiko_services/main/hook.py` (the instrumentation seam).
`src/aiko_services/elements/observe/elements.py` (the `Metrics` element — the frame-level
counterpart).

## Appendix: Conformance traces (stubs — recorded at the telemetry milestone exit)

1. **Telemetry-key trace:** do a HostMonitor cold start on a reference host. Assert that
   every [REQ-6] necessary key appears with the correct field names, units and cadence.
   Assert that `host.monitor` reports within the [REQ-12] budget.
2. **Absence trace:** stop the HostMonitor process. Assert the `(absent)` LWT and the
   consumer staleness behavior per [REQ-4]/[REQ-9].
3. **History trace:** let a bounded MetricsStore fill past its ring limit. Assert the
   overflow
   policy per [REQ-14] and windowed-query results per [REQ-15].
4. **Signals trace:** observe one Pipeline frame across two processes, plus one Actor
   method call, at the bridge. Assert the derived spans per [REQ-19] (names, parentage and
   resource attributes). Assert the metric mappings per [REQ-17]. Assert the
   `/log` → LogRecord correlation per
   [REQ-22]. Validate the exported OTLP against an OpenTelemetry Collector.
