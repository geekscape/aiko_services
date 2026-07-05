---
title: Observe elements
description: Observability PipelineElements — Inspect writes selected
  Frame swag values to log, file or stdout; Metrics reports per-element
  and whole-Pipeline timing and memory figures
type: concept
audience: [developers, end-users]
status: work-in-progress
source:
  - src/aiko_services/elements/observe/elements.py
  - src/aiko_services/elements/observe/pipelines/pipeline_observe.json
related: [pipeline_element, pipeline, parameters, stream, dashboard]
version: "0.6"
last_updated: 2026-07-06
---

# Observe elements

## Overview

The observe elements module provides two
[PipelineElements](../../concepts/pipeline_element.md) for watching a
running [Pipeline](../../concepts/pipeline.md) from inside the graph:

- **Inspect** — prints selected (or all) values from the Frame's swag to
  the log, a file or stdout; the in-graph equivalent of a debugger watch
  window.
- **Metrics** — reports the per-element `*_time` / `*_memory` figures and
  whole-Pipeline timing collected in each Frame's `metrics` dictionary
  (see [Stream](../../concepts/stream.md)); conventionally placed at the
  end of a graph, where it also forwards declared outputs so child
  Pipeline responses reach the parent Pipeline.

Both are pure observers: they never modify the swag, and both pass
through the values named in their `output` definition (via the
`all_outputs()` helper from
[utility elements](../utilities/elements.md)).

**Why you'd use it**: to see what a Pipeline is actually doing — values
flowing between elements and where the time goes — without adding print
statements to element code:

```bash
cd src/aiko_services/elements/observe
aiko_pipeline create pipelines/pipeline_observe.json -ll debug -fd "(b: 0)"
# ... inspect<*:0> b: 0            (every swag name, via "inspect": "(*)")
# ... metrics<*:0> PE_1_time      : 0.…  ms
# ... metrics<*:0> Pipeline time  : 0.…  ms
```

## For application developers

### Command-line usage

Observe elements have no CLI of their own; they are hosted and
parameterised through the `aiko_pipeline` CLI. From the usage header of
`elements.py`:

```bash
cd src/aiko_services/elements/observe
aiko_pipeline create pipelines/pipeline_observe.json -ll debug -fd "(b: 0)"
```

Both elements log at `debug` level, so run with `-ll debug` (or
`-ll debug_all`) to see their output. Parameters can be supplied or
overridden from the command line (see
[Parameters](../../concepts/parameters.md)):

```bash
# Enable/target Inspect and enable Metrics on any Pipeline that hosts them
aiko_pipeline create pipeline_local.json -ll debug \
    -p Inspect.enable true -p Inspect.target log -p Metrics.enable true

# Send Inspect output to a file instead
aiko_pipeline update p_inspect_metrics -fd "(b: 0)" \
    -p Inspect.target file:inspect_out.txt
```

### Public API

```python
from aiko_services.elements.observe import Inspect, Metrics
```

**`Inspect(aiko.PipelineElement)`** — protocol `inspect:0`.

| Parameter | Default | Meaning |
|-----------|---------|---------|
| `enable` | `True` | Truthy → inspect this Frame; falsy → pass through only |
| `inspect` | *(all swag names)* | S-expression list of swag names to show, e.g. `(factorial)`; `(*)` (or omitting the parameter) means every name in the swag |
| `target` | `"log"` | `log` (logger, info level), `print` (stdout) or `file:PATH` (append to PATH); anything else returns `StreamEvent.ERROR` |

- Frame contract: `input: []`; `output` declares any swag names to
  forward (commonly `[]`). Missing swag names are shown as `None`.
- Output line format: `NAME<stream_id:frame_id> name: value` (one line
  per name, via `my_id()`).
- Stream lifecycle: for `file:` targets the file handle is opened once
  per Stream (kept in `stream.variables["inspect_file"]`, append mode,
  flushed each Frame) and closed by `stop_stream()`.

**`Metrics(aiko.PipelineElement)`** — protocol `metrics:0`.

| Parameter | Default | Meaning |
|-----------|---------|---------|
| `enable` | `True` | Truthy → report; falsy → pass through only |
| `rate` | `1` | Report every `rate`-th Frame (`frame_id % rate == 0`) |

- Frame contract: `input: []`; `output` may name any value produced
  earlier in the graph — the source comments note that Metrics typically
  appears at the end of a Pipeline graph so that child Pipeline
  responses can be returned to the parent Pipeline, e.g.
  `"output": [{ "name": "i", "type": "int" }]`.
- Reported per Frame, at debug level, from `frame.metrics`:
  `ELEMENT_time` (milliseconds) and `ELEMENT_memory` (Mb, when the
  Pipeline runs with memory tracing) for each element, then
  `pipeline_time`, `pipeline_memory` and the process-level
  `pipeline_start_memory`.
- Both elements return `StreamEvent.OKAY` with
  `all_outputs(self, stream)` on every path except Inspect's unknown
  `target` error.

## For framework developers (internals)

### Design

```
   graph: (PE_1 ──► PE_2 ──► Inspect ──► Metrics)
                              │            │
                              ▼            ▼
                    swag {b, c, d}   frame.metrics
                    → log/file/print  {PE_1_time, …,
                                       pipeline_time, …}
```

- Both elements read Pipeline-internal per-Frame structures directly —
  `stream.frames[stream.frame_id]` for the swag (Inspect) and
  `frame.metrics` (Metrics) — rather than declared inputs. This is what
  lets one Inspect definition observe *any* graph without editing its
  `input` list, at the cost of bypassing the declared data contract.
- Per-Stream state (the Inspect output file handle) lives in
  `stream.variables`, per the PipelineElement rule that one instance
  serves every concurrent Stream.
- Metrics is a consumer of the timing/memory capture performed by
  `PipelineImpl` (`_process_metrics_start()` /
  `_process_metrics_capture()`); it adds no instrumentation of its own.

### Implementation notes

- Parameter coercion: `enable` is used as a raw truthy value. A CLI or
  MQTT override arrives as a *string*, and the string `"false"` is
  truthy — so `-p Inspect.enable false` does **not** disable Inspect;
  only a definition-level `"enable": false` (JSON boolean) does.
  Similarly `rate` is used directly in `frame_id % rate`: a string value
  raises `TypeError` and `rate = 0` raises `ZeroDivisionError`.
- Inspect validates `target` inside the per-name loop, so with an
  invalid target it returns `StreamEvent.ERROR` on the first name after
  doing no output; the diagnostic text says `'file'` where the accepted
  form is the `file:PATH` prefix.
- `Inspect.stop_stream()` closes the file handle but does not remove it
  from `stream.variables`; harmless today because the Stream is being
  destroyed.

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `Inspect` | Resolve `enable` / `inspect` / `target` [parameters](../../concepts/parameters.md); write selected swag name/value lines to log, file or stdout; manage the per-Stream file handle (`stream.variables`, closed in `stop_stream()`); forward declared outputs | [PipelineElement](../../concepts/pipeline_element.md) (contract); [Stream](../../concepts/stream.md) `Frame.swag` / `variables`; `parse()` (S-expression name list); `all_outputs()` ([utility elements](../utilities/elements.md)) |
| `Metrics` | Resolve `enable` / `rate` parameters; log per-element and Pipeline time/memory figures from `Frame.metrics`; forward declared outputs so parent Pipelines receive responses | [PipelineElement](../../concepts/pipeline_element.md) (contract); [Pipeline](../../concepts/pipeline.md) metrics capture; [Stream](../../concepts/stream.md) `Frame.metrics`; `all_outputs()` ([utility elements](../utilities/elements.md)) |

## Current limitations and roadmap

From the source To Do list (all Metrics):

- Make Metrics visible to the Aiko Services Dashboard via `self.share[]`
  (see [Dashboard](../../concepts/dashboard.md))
- Store Metrics to file (JSON, CSV), SQLite, InfluxDB
- Add run-time average calculation

Additional observed limitations:

- No type coercion of CLI/MQTT parameter overrides: string `"false"`
  does not disable `enable`; string or zero `rate` values raise
  exceptions (see Implementation notes).
- Metrics output is debug-level logging only — nothing is retained,
  shared or aggregated yet (hence the To Do list above).
- No unit tests cover Inspect or Metrics.

## Related concepts

- [PipelineElement](../../concepts/pipeline_element.md) — the contract
  both elements implement
- [Pipeline](../../concepts/pipeline.md) — collects the metrics that
  Metrics reports
- [Parameters](../../concepts/parameters.md) — declaration, CLI override
  and resolution of `enable` / `inspect` / `target` / `rate`
- [Stream](../../concepts/stream.md) — `Frame.swag`, `Frame.metrics` and
  `stream.variables`
- [Dashboard](../../concepts/dashboard.md) — planned destination for
  shared Metrics state
- [Utility elements](../utilities/elements.md) — `all_outputs()` helper;
  the Expression element pairs naturally with Inspect
- [Control elements](../control/elements.md) — the factorial example
  uses Inspect after its loop
