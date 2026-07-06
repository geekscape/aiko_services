---
title: Multitude Pipeline examples index
description: Index of the multitude stress / scale examples — chains of
  Pipelines joined by remote PipelineElement proxies (small a/b/c and
  large 000..090 patterns) with driver shell scripts that launch them
  and publish Frames over MQTT
type: index
audience: [developers, end-users]
status: draft
source:
  - src/aiko_services/examples/pipeline/multitude
related: [pipeline, pipeline_element, stream, elements]
version: "0.6"
last_updated: 2026-07-06
---

# Multitude Pipeline examples index

The multitude examples stress-test distributed
[Pipelines](../../../concepts/pipeline.md): many Pipeline Processes
chained head-to-tail through **remote PipelineElement proxies**, all
doing trivial [`PE_Add`](../elements.md) arithmetic so that the
measurable cost is the framework itself — MQTT round-trips, Frame
routing and per-element overhead, reported by the
[Metrics](../../../elements/observe/elements.md) element that ends
every graph.

Navigation: [pipeline examples index](../ReadMe.md) ·
[concepts guide](../../../concepts/ReadMe.md)

## Module documents

| Document | Summary |
|----------|---------|
| [elements](elements.md) | `PE_A0` / `PE_B0` / `PE_C0` and `PE_000` .. `PE_090` — empty `PE_Add` subclasses required by the remote deployments |

## The chained-Pipeline patterns

Every PipelineDefinition sets `parameters`
`{ "constant": 1, "delay": 0 }`, so each `PE_Add` node adds 1 to the
Frame value `i` and the end-to-end result counts the elements
traversed.

### Small: three Pipelines, a → b → c

`pipeline_small_a.json`, `pipeline_small_b.json` and
`pipeline_small_c.json` (Pipelines `p_small_a` / `_b` / `_c`) each run
two local `PE_Add` nodes and — except the terminal `c` — one remote
proxy *in the middle* of the graph, so the downstream Pipeline is
called mid-Frame and its result flows back before the local tail node
runs:

```
p_small_a: (PE_A0  PE_B0*           PE_A1  Metrics)
                     |          ^
                     v          |
p_small_b:         (PE_B0  PE_C0*  PE_B1  Metrics)
                              |  ^
                              v  |
p_small_c:                  (PE_C0  PE_C1  Metrics)

* = remote proxy, resolved by service_filter name
```

Six `PE_Add` executions in total: publish `(i: 0)` into `p_small_a`
and the Frame completes with `i = 6`.

### Large: ten Pipelines, 000 → 010 → ... → 090

`pipeline_large_000.json` .. `pipeline_large_090.json` (steps of 10)
follow one pattern: Pipeline `p_large_0N0` runs ten local `PE_Add`
nodes `PE_0N0` .. `PE_0N9`, with a remote proxy to the next Pipeline
(`PE_0(N+1)0` → `p_large_0(N+1)0`) spliced in after the fifth local
node — except the terminal `p_large_090`, which is all-local:

```
p_large_000 graph:
(PE_000 PE_001 PE_002 PE_003 PE_004  PE_010*  PE_005 ... PE_009 Metrics)
                                       |   ^
                                       v   |
p_large_010: five local adds, PE_020*, five local adds, Metrics
    ...                          (recursing down to)
p_large_090: (PE_090 PE_091 ... PE_099 Metrics)   -- no remote proxy
```

Ten nested Pipelines, 100 `PE_Add` executions: publish `(i: 0)` into
`p_large_000` and the Frame completes with `i = 100`.

### Tiny: two Pipelines, a → b (work-in-progress)

`pipeline_tiny_a.json` / `pipeline_tiny_b.json` and `run_tiny.sh`
shrink the small pattern to a single remote hop (three `PE_Add`
executions). These files are present in the working tree but not yet
committed to git.

## Driver scripts

| Script | What it runs |
|--------|--------------|
| `run_small.sh` | Launches the three `pipeline_small_*.json` Pipelines with `aiko_pipeline create ... --windows` as background Processes, derives each Pipeline's `.../1/in` topic from its process id, sends `(create_stream 1 () 10)` to `p_small_a`, then publishes `(process_frame (stream_id: 1 frame_id: N) (i: 0))` every `frame_delay` seconds. First Ctrl-C stops frame generation; second Ctrl-C kills the Pipelines |
| `run_large.sh` | Same structure for the ten `pipeline_large_*.json` Pipelines (waits 5 seconds for start-up); `USE_PIPELINE=000` selects which Pipeline receives the Stream and Frames |
| `run_publish.sh` | Frame publisher only — no Pipelines. Publishes `process_frame` messages to the fixed topic `aiko/test` at `frame_delay` intervals and, on Ctrl-C, prints total time and achieved frame rate. Useful for measuring raw `mosquitto_pub` throughput |
| `run_tiny.sh` | As `run_small.sh` for the two tiny Pipelines (work-in-progress, uncommitted) |

`run_small.sh`, `run_large.sh` and `run_tiny.sh` share a common
usage:

```bash
./run_small.sh [WARNING|INFO|DEBUG] [true|false] [frame_delay]
./run_small.sh WARNING true 0.02  # max frame rate before falling behind
```

- argument 1 → `AIKO_LOG_LEVEL` (default `WARNING`; `DEBUG` shows
  Metrics measurements)
- argument 2 → `AIKO_LOG_MQTT` (usage comment says `true` = MQTT
  logging, `false` = console; the script default is `all`)
- argument 3 → seconds between Frames (default `1.0`)

## Current limitations and roadmap

From the scripts' To Do lists — **planned**, not implemented:

- Determine what limits the maximum frame rate to about 50 Hz
- Support multiple concurrent Streams
- Support an unlimited number of Pipelines (loop-generated, rather
  than one hand-written PipelineDefinition per Pipeline)

## Related documentation

- [Multitude alias elements](elements.md) — why `PE_B0`, `PE_010`
  etc. must exist as Python classes
- [Pipeline example elements](../elements.md) — `PE_Add`, the single
  element behaviour used throughout
- [Pipeline examples index](../ReadMe.md) — the single-Pipeline
  teaching examples these scale up
- [Pipeline](../../../concepts/pipeline.md) — remote deployment and
  the PipelineDefinition format
- [Stream](../../../concepts/stream.md) — the `create_stream` /
  `process_frame` messages the scripts publish
- [Observe elements](../../../elements/observe/elements.md) — the
  `Metrics` element ending every multitude graph
