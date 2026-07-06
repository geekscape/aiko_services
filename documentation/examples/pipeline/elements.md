---
title: Pipeline example elements
description: The teaching PipelineElements — PE_Add, PE_Event,
  PE_RandomIntegers, the PE_0..PE_4 diamond, the PE_IN / PE_TEXT /
  PE_OUT Graph Path trio and the PE_DataEncode / PE_DataDecode pair —
  behind the committed example PipelineDefinitions
type: concept
audience: [developers, end-users]
status: draft
source:
  - src/aiko_services/examples/pipeline/elements.py
related: [pipeline_element, pipeline, stream, parameters, share,
  elements]
version: "0.6"
last_updated: 2026-07-06
---

# Pipeline example elements

## Overview

`examples/pipeline/elements.py` is the teaching companion to the
[Pipeline](../../concepts/pipeline.md) and
[PipelineElement](../../concepts/pipeline_element.md) concepts. Where
the media element families do real work, these elements do arithmetic
and string tagging — just enough behaviour to make Frame flow,
[Parameters](../../concepts/parameters.md) resolution, fan-out /
fan-in, remote deployment and Graph Path selection visible in the log.

Every committed PipelineDefinition in this package (see the
[package index](ReadMe.md)) is built from these classes:

- **`PE_Add`** — add a constant to `i`, with an optional per-frame
  delay; the workhorse of the [multitude](multitude/ReadMe.md)
  stress-test Pipelines
- **`PE_Event`** — parameter-driven StreamEvent demonstration
  (work-in-progress; see limitations)
- **`PE_RandomIntegers`** — a self-clocking frame generator that
  publishes each value to its [Share](../../concepts/share.md)d state
- **`PE_0` .. `PE_4`** — increment-and-sum elements forming a diamond
  graph (fan-out then fan-in)
- **`PE_IN`, `PE_TEXT`, `PE_OUT`** — string-tagging elements reused
  under several node names to demonstrate multiple Graph Paths
- **`PE_DataEncode`, `PE_DataDecode`** — base64 / NumPy serialisation
  for moving binary data between Pipelines as text

**Why you'd use it**: watch a two-element Pipeline generate and
transform Frames without any hardware, files or data preparation:

```bash
aiko_pipeline create pipeline_example.json -s 1 -p limit 1000 -p rate 1
aiko_dashboard  # select "PE_RandomIntegers" and watch "random" update
```

## For application developers

### Command-line usage

All commands run from `src/aiko_services/examples/pipeline` (the
source header says `cd ../examples/pipeline`). `$HOST` is the MQTT
server and `$TOPIC` is the Pipeline's `.../in` topic, i.e.
`$NAMESPACE/$HOST/$PID/$SID/in`.

Single-Process diamond graph (`PE_1 .. PE_4` plus `Inspect` and
`Metrics`):

```bash
aiko_pipeline create pipeline_local.json -ll debug  \
  -p Inspect.enable true -p Inspect.target log -p Metrics.enable true
mosquitto_pub -h $HOST -t $TOPIC -m "(process_frame (stream_id: 1) (b: 0))"
```

Distributed Pipeline: `pipeline_remote.json` runs `PE_0` locally, then
hands the Frame to the *whole* `p_local` Pipeline via a remote proxy
element (start `pipeline_local.json` first):

```bash
aiko_pipeline create pipeline_remote.json
mosquitto_pub -h $HOST -t $TOPIC -m "(process_frame (stream_id: 1) (a: 0))"
```

Self-generating stream — `PE_RandomIntegers` creates its own Frames,
so only `create_stream` is needed (here via `-s 1` plus parameter
overrides):

```bash
aiko_pipeline create pipeline_example.json -s 1 -p limit 1000 -p rate 1
aiko_dashboard  # select "PE_RandomIntegers" and watch "random" update
```

Graph Path selection — choose which of the four paths in
`pipeline_paths.json` handles the Stream, either for the Pipeline via
`-gp` or per-Stream via `create_stream`:

```bash
aiko_pipeline create pipeline_paths.json -gp PE_IN_0 -fd "(in_a: x)"
aiko_pipeline create pipeline_paths.json -gp PE_IN_1 -fd "(in_a: x)"

mosquitto_pub -t $TOPIC_PATH/in -m "(create_stream 1 PE_IN_1)"
mosquitto_pub -t $TOPIC_PATH/in -m "(process_frame (stream_id: 1) (in_a: x))"
mosquitto_pub -t $TOPIC_PATH/in -m "(destroy_stream 1)"
```

Explicit Stream lifecycle over MQTT for any of these Pipelines:

```bash
TOPIC=$NAMESPACE/$HOST/$PID/$SID/in
mosquitto_pub -h $HOST -t $TOPIC -m "(create_stream 1)"
mosquitto_pub -h $HOST -t $TOPIC -m "(process_frame (stream_id: 1) (a: 0))"
mosquitto_pub -h $HOST -t $TOPIC -m "(destroy_stream 1)"
```

The source header also mentions
`aiko_pipeline create pipeline_test.json` — that file is not committed
in this directory (a `pipeline_test.json` exists only under the
work-in-progress `distributed/` sub-directory).

### Public API

All elements return `StreamEvent.OKAY` from `process_frame()` and use
the default `start_stream()` / `stop_stream()` unless noted.

#### PE_Add

| Protocol | Inputs → Outputs | Parameters |
|----------|------------------|------------|
| `add:0` | `i` (int) → `i` (int) | `constant` (default 1), `delay` (default 0, seconds) |

Adds `constant` to `i`, logs `i in / out` at info level, then sleeps
`delay` seconds when non-zero — the delay makes Pipeline back-pressure
and `Metrics` timing observable in the
[multitude](multitude/ReadMe.md) stress tests.

#### PE_Event

| Protocol | Inputs → Outputs | Parameters |
|----------|------------------|------------|
| `event:0` | (none) → `diagnostic` | `condition` (no default), `event` (default `"STOP"`, upper-cased), `diagnostic` (default `"Return StreamEvent.<event>"`) |

Intended to end or fail a Stream from inside the graph, driven by a
`condition` typically defined by the upstream
[Expression](../../elements/utilities/elements.md) element. **As
implemented it always returns `StreamEvent.OKAY`** with the
`diagnostic` value — evaluating `condition` and returning the named
`StreamEvent.STOP` / `StreamEvent.ERROR` is work-in-progress (see
limitations).

#### PE_RandomIntegers

| Protocol | Inputs → Outputs | Parameters |
|----------|------------------|------------|
| `random_integers:0` | `random` (int) → `random` (int) | `rate` (default 1.0 frames/second), `limit` (required — no default) |

A minimal self-clocking frame generator, structured like a
[DataSource](../../concepts/data_source_target.md) (the source comments
its protocol with `data_source:0`). `start_stream()` registers
`frame_generator` via `create_frames(stream, self.frame_generator,
rate=...)`; the generator emits `{"random": randint(0, 9)}` until
`frame_id` reaches `limit`, then returns `StreamEvent.STOP` with the
diagnostic `"Frame limit reached"`. Each `process_frame()` call also
publishes the value with `self.ec_producer.update("random", random)`,
so the [Dashboard](../../concepts/dashboard.md) shows it live via
[Share](../../concepts/share.md). Commented-out code in
`frame_generator` sketches two planned variations: returning several
frames at once (a list of frame-data dicts) and extending the Stream
[Lease](../../concepts/lease.md).

The `limit` parameter has no default: if it is not supplied by the
PipelineDefinition or the command line, `int(limit)` raises
`TypeError`.

#### PE_0 .. PE_4 — the diamond graph

| Class | Protocol | Inputs → Outputs | Behaviour |
|-------|----------|------------------|-----------|
| `PE_0` | `increment:0` | `a` → `b` | `b = a + pe_0_inc` (parameter, default 1) |
| `PE_1` | `increment:0` | `b` → `c` | `c = b + pe_1_inc` (parameter, default 1); also reads Pipeline parameter `p_1` |
| `PE_2` | `increment:0` | `c` → `d` | `d = c + 1` |
| `PE_3` | `increment:0` | `c` → `e` | `e = c + 1` |
| `PE_4` | `sum:0` | `d`, `e` → `f` | `f = d + e` — fan-in of two inputs |

`pipeline_local.json` wires them as
`(PE_1 (PE_2 PE_4) (PE_3 PE_4) Inspect Metrics)` — fan-out from `PE_1`
to `PE_2` and `PE_3`, fan-in at `PE_4`. `pipeline_remote.json` runs
`PE_0` locally and deploys "`PE_1`" as a **remote proxy for the entire
`p_local` Pipeline**, demonstrating that a remote PipelineElement's
contract (`b` in, `f` out) can be satisfied by another Pipeline.

#### PE_IN, PE_TEXT, PE_OUT — Graph Path trio

| Class | Protocol | Inputs → Outputs | Behaviour |
|-------|----------|------------------|-----------|
| `PE_IN` | `in:0` | `in_a` → `text_b` | `text_b = "<in_a>:in"` |
| `PE_TEXT` | `text_to_text:0` | `text_b` → `text_b` | appends `":text"` |
| `PE_OUT` | `out:0` | `text_b` → `out_c` | appends `":out"` |

Each element tags the string with its own name, so the final `out_c`
value (e.g. `x:in:text:out`) records exactly which path the Frame
took. `pipeline_paths.json` instantiates them under multiple node
names (`PE_IN_0` .. `PE_IN_3`, `PE_OUT_0`, `PE_OUT_1`) using the
`deploy.local.class_name` field, giving four selectable Graph Paths.

#### PE_DataEncode and PE_DataDecode

| Class | Inputs → Outputs | Behaviour |
|-------|------------------|-----------|
| `PE_DataEncode` | `data` → `data` | `str` → UTF-8 bytes; `numpy.ndarray` → `np.save()` bytes; then base64-encode to a text string |
| `PE_DataDecode` | `data` → `data` | base64-decode, then `np.load(..., allow_pickle=True)` back to an ndarray |

The pair shows how binary payloads (NumPy arrays) can cross the
text-based [Transport](../../concepts/transport.md) between local and
remote Pipeline halves (`pipeline_encode.json` /
`pipeline_decode.json`). Neither class calls
`context.set_protocol()` — unlike every other element in the file —
so they advertise the default PipelineElement protocol.

## For framework developers (internals)

### Design

The file is a graded sequence of PipelineElement idioms, each class
introducing exactly one more mechanism than the last:

```
PE_Add ................. get_parameter() with defaults, logging
PE_Event ............... parameter-driven StreamEvent (WIP)
PE_RandomIntegers ...... start_stream() + create_frames() generator,
                         self.share / ec_producer live state
PE_0 .. PE_4 ........... multi-node graphs: fan-out, fan-in,
                         Pipeline vs element Parameters
PE_IN / PE_TEXT / PE_OUT class_name aliasing, Graph Paths
PE_DataEncode / Decode . binary payloads over a text transport
```

All follow the standard constructor idiom —
`context.set_protocol(...)` then
`context.call_init(self, "PipelineElement", context)` — as documented
in [PipelineElement](../../concepts/pipeline_element.md). Because the
elements are trivial, the interesting design lives in the companion
PipelineDefinitions (deployment topology, Graph Paths, remote
proxies); see the [package index](ReadMe.md).

### Implementation notes

- Frame values arrive as strings when published via `mosquitto_pub`,
  so every arithmetic element coerces with `int(...)` before use.
- `PE_1` reads Pipeline-level parameter `p_1` purely to demonstrate
  Pipeline-scope parameter resolution; the value is not used. The
  local variable `increment = 1` in `PE_1.process_frame()` is also
  unused.
- `PE_DataDecode` passes `allow_pickle=True` to `np.load()` — do not
  feed it untrusted input.

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `PE_Add` | Add `constant` to `i`; optional per-frame `delay` | [PipelineElement](../../concepts/pipeline_element.md), [Parameters](../../concepts/parameters.md) |
| `PE_Event` | (WIP) Return a parameter-selected StreamEvent | [Stream](../../concepts/stream.md), [Expression](../../elements/utilities/elements.md) |
| `PE_RandomIntegers` | Generate random-integer Frames at `rate` up to `limit`; publish `random` to shared state | [Stream](../../concepts/stream.md), [Share](../../concepts/share.md), [Pipeline](../../concepts/pipeline.md) |
| `PE_0` .. `PE_3` | Increment one value, rename the output | [PipelineElement](../../concepts/pipeline_element.md) |
| `PE_4` | Sum two inputs — fan-in | [PipelineElement](../../concepts/pipeline_element.md) |
| `PE_IN` / `PE_TEXT` / `PE_OUT` | Tag a string with the path taken | [Pipeline](../../concepts/pipeline.md) Graph Paths |
| `PE_DataEncode` / `PE_DataDecode` | base64 / NumPy (de)serialisation of `data` | [Transport](../../concepts/transport.md) |

## Current limitations and roadmap

- **`PE_Event` does not yet act on its parameters**: it reads
  `condition` and `event`, but always returns `StreamEvent.OKAY` —
  the diagnostic string is produced, the event itself is not.
- `PE_RandomIntegers.limit` has no default and fails with `TypeError`
  when omitted; multi-frame generation and Stream-Lease extension are
  present only as commented-out sketches.
- From the source To Do list — **planned**: rework `PE_DataDecode` /
  `PE_DataEncode` to use `kwargs` for flexible choices of data type
  transferred via function parameters.
- The header's `aiko_pipeline create pipeline_test.json` refers to a
  PipelineDefinition that is not committed alongside this module.

## Related concepts

- [Pipeline](../../concepts/pipeline.md) — the graphs these elements
  populate; Graph Paths and remote deployment
- [PipelineElement](../../concepts/pipeline_element.md) — the contract
  every class here implements
- [Stream](../../concepts/stream.md) — StreamEvent semantics and the
  create / process / destroy lifecycle used in the examples
- [Parameters](../../concepts/parameters.md) — element, Pipeline and
  command-line parameter resolution demonstrated throughout
- [Share](../../concepts/share.md) — how `PE_RandomIntegers.random`
  reaches the Dashboard
- [Media elements](../../elements/media/elements.md) — `Mock` and
  `NoOp`, the even smaller structural placeholders
