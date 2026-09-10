---
title: Control elements
description: Control-flow PipelineElements — the Loop element repeats a
  section of the Pipeline graph until an S-expression condition over the
  Frame swag becomes false, and the CaptureLimit element stops a Stream
  after a frame count, a duration, a media run time or a condition
type: concept
audience: [developers, end-users]
status: work-in-progress
ste: adapted
source:
  - src/aiko_services/elements/control/elements.py
  - src/aiko_services/elements/control/pipelines/factorial_pipeline.json
  - src/aiko_services/elements/media/pipelines/synthetic_pipeline_0.json
  - src/aiko_services/elements/media/pipelines/synthetic_pipeline_1.json
related: [pipeline_element, pipeline, parameters, stream, synthetic_io]
version: "0.8-dev"
last_updated: 2026-09-10
---

# Control elements

## Overview

The control elements module gives
[PipelineElements](../../concepts/pipeline_element.md) that alter the
control flow of a [Pipeline](../../concepts/pipeline.md) graph. It
contains two elements. **Loop** implements the
`PipelineElementLoop` Interface. Loop executes the graph section between
itself and a named *boundary* element repeatedly, within a single Frame.
It stops when a condition evaluated against the Frame's swag becomes
false.

The `define`, `condition` and `expression`
[parameters](../../concepts/parameters.md) of Loop are S-expressions. The
expression helpers in the sibling
[utility elements](../utilities/elements.md) module evaluate them
(`evaluate_define()` and `evaluate_condition()`). Thus a Pipeline can
express simple iterative computation — initialize variables, test,
update —
without writing a new Python element.

**CaptureLimit** is a pass-through gate that stops the
[Stream](../../concepts/stream.md) when a bound is reached: a number of
Frames, a wall-clock duration, a media run time or an S-expression
condition. It is medium-neutral. It does not touch the Frame data, so it
works in an image, text or audio Pipeline. It is the standard way to
bound a run of the [Synthetic video source](../media/synthetic_io.md).

**Why to use it**: to repeat a tool or sub-graph until a data-driven
condition is met — retry-until-success, iterate-until-converged. The
committed example computes a factorial by looping over a mock tool
element:

```bash
cd src/aiko_services/elements/control
aiko_pipeline create pipelines/factorial_pipeline.json -ll debug_all -fd "()"
# ... Inspect: factorial: 6        (3! computed by looping)
```

And to bound a run: record exactly ten minutes of synthetic video, then
exit:

```bash
cd src/aiko_services/elements/media
aiko_pipeline create pipelines/synthetic_pipeline_1.json -s 1  \
  -p CaptureLimit.duration 10m
```

## For application developers

### Command-line usage

Control elements have no CLI of their own. They are hosted by the
`aiko_pipeline` CLI (see [Pipeline](../../concepts/pipeline.md)). From
the usage header of `elements.py`:

```bash
cd src/aiko_services/elements/control
aiko_pipeline create pipelines/factorial_pipeline.json -ll debug_all  \
                                                       -fd "()"
```

`factorial_pipeline.json` declares the `_create_stream_` and
`_destroy_stream_exit_` Pipeline parameters. Thus the Pipeline makes
Stream `"1"` at start-up, and the process exits when that Stream is
destroyed. The `-fd "()"` empty Frame triggers one run of the graph.

CaptureLimit is exercised by the two synthetic video pipelines in the
media package (run from `src/aiko_services/elements/media`):

```bash
# 10 seconds (the default), then exit
aiko_pipeline create pipelines/synthetic_pipeline_0.json -s 1

# Exactly 45 Frames
aiko_pipeline create pipelines/synthetic_pipeline_0.json -s 1  \
  -p CaptureLimit.frame_count 45

# Media run time of 2 minutes at the Pipeline "frame_rate"
aiko_pipeline create pipelines/synthetic_pipeline_1.json -s 1  \
  -p CaptureLimit.run_time 2m

# Continue while a condition over the swag and the counters holds
aiko_pipeline create pipelines/synthetic_pipeline_0.json -s 1  \
  -p CaptureLimit.condition "((elapsed<5))"
```

The loop behavior is configured entirely through element parameters in
the PipelineDefinition:

```json
{ "name": "Factorial", "input": [], "output": [],
  "parameters": { "boundary":   "Tool_A:Inspect",
                  "define":     "((n 3) (factorial 1))",
                  "condition":  "((n))",
                  "expression": "((factorial factorial*n) (n n-1))"},
  "deploy": { "local": {
      "class_name": "Loop",
      "module": "aiko_services.elements.control.elements" } } }
```

### Public API

```python
from aiko_services.elements.control import CaptureLimit, Loop
```

**`Loop(aiko.PipelineElementLoop)`** — protocol `loop:0`.

| Parameter | Default | Meaning |
|-----------|---------|---------|
| `boundary` | `""` | Name of the last graph element inside the loop body, written `LOOP_END_ELEMENT[:NEXT_ELEMENT]` — only the part before `:` is used (see limitations) |
| `define` | *(optional)* | S-expression `((name expression) ...)` — evaluated once per [Stream](../../concepts/stream.md), on the first `process_frame()`, to initialize swag entries |
| `condition` | **needed** | S-expression `((expression) ...)` — every expression must be truthy for the loop to continue; a missing parameter returns `StreamEvent.ERROR` |
| `expression` | *(optional)* | S-expression `((name expression) ...)` — evaluated on each iteration *while the condition holds*, updating swag entries |

Frame contract: `input: []` and `output: []`. Loop reads and writes the
Frame's swag directly (`stream.frames[stream.frame_id].swag`). It does
not use declared inputs and outputs. Thus any swag name is available to
its expressions.

`process_frame(stream)` behavior per invocation:

1. First call for a Stream (detected by
   `stream.variables["loop_boundary"]` being unset): record the
   `boundary` parameter into `stream.variables["loop_boundary"]` and
   evaluate `define` into the swag.
2. Evaluate `condition` against the swag:
   - **truthy** → evaluate `expression` (if given) into the swag and
     return `StreamEvent.OKAY, {}` — the Pipeline will run the loop body
     and come back;
   - **falsy** → return `StreamEvent.LOOP_END, {}` — the Pipeline
     resumes the graph *after* the boundary element.

Expression grammar (values, `+ - * /` and comparison operators over swag
names, numbers and strings) is documented with the evaluator in
[utility elements](../utilities/elements.md).

**`CaptureLimit(aiko.PipelineElement)`** — protocol `capture_limit:0`.

| Parameter | Default | Meaning |
|-----------|---------|---------|
| `frame_count` | *(optional)* | Stop after this number of Frames |
| `duration` | `10` when no bound is given | Wall-clock time since the first Frame: seconds, or a number with a unit suffix `s`, `m` or `h` (`10m`) |
| `run_time` | *(optional)* | Media time, `count / frame_rate`, for a source that is not real-time (unpaced synthetic frames, a file read). Needs the `frame_rate` parameter, which `VideoWriteFile` also reads at the Pipeline level. Same units as `duration` |
| `condition` | *(optional)* | S-expression list in Loop style, for example `((elapsed<600))`. The Stream continues while every expression is true. Evaluated over the Frame swag plus `frame_id`, `count`, `elapsed` and `run_time`. Write an expression without spaces |

Any configured bound that fires stops the Stream, the first one wins.
Parameters arrive as strings from the CLI: CaptureLimit coerces and
validates them, and a bad value returns `StreamEvent.ERROR`.

Frame contract: `input: []` and `output: []`. CaptureLimit leaves the
Frame swag untouched, so the downstream elements still get their
declared inputs. Declared outputs, if any, are forwarded unchanged
through `all_outputs()` from the
[utility elements](../utilities/elements.md). Note that `all_outputs()`
raises `KeyError` for a declared output that is not in the swag.

`process_frame()` behavior per Frame:

1. **Before the bound**: `StreamEvent.OKAY`, the Frame continues.
2. **The bounding Frame**: `StreamEvent.STOP` with the outputs and a
   `diagnostic`. STOP does not skip the remaining elements of the current
   Frame, so a writer after CaptureLimit still writes this Frame. The
   Pipeline posts a graceful `destroy_stream()`.
3. **Later Frames**: `StreamEvent.DROP_FRAME`. Queued Frames still arrive
   until the destroy lands, and DROP_FRAME skips the remaining elements
   for each of them, so nothing more is written.

The time bounds only tick when a Frame arrives. A source that makes one
Frame with `create_frame()` must use `frame_count`. Place CaptureLimit
before any writer in the graph.

Worked example — `factorial_pipeline.json`, graph
`(Factorial Tool_A Inspect)` with boundary `Tool_A:Inspect`:

```
Frame ()                     swag
  Factorial: define          n=3 factorial=1
             (n) truthy      factorial=3  n=2      → OKAY
  Tool_A     (loop body)
  Factorial: (n) truthy      factorial=6  n=1      → OKAY
  Tool_A
  Factorial: (n) truthy      factorial=6  n=0      → OKAY
  Tool_A
  Factorial: (n) falsy                             → LOOP_END
  Inspect:   factorial: 6    (runs once, after the loop)
```

## For framework developers (internals)

### Design

```
   graph: (Factorial ──► Tool_A ──► Inspect)
              ▲             │
              └── loop ─────┘   boundary = "Tool_A:…"

   Loop element                 PipelineImpl frame loop
   ├ returns OKAY          ──►  saves loop_node + remaining loop_graph;
   │                            after the boundary element completes,
   │                            re-queues from the Loop element
   └ returns LOOP_END      ──►  graph_node_list = iterate_after(boundary)
```

- Loop is deliberately thin: the *iteration machinery* lives in
  `PipelineImpl._process_frame_common()` (see
  [PipelineElement](../../concepts/pipeline_element.md), Design), keyed
  off the `PipelineElementLoop` Interface marker and the
  `loop_boundary` / `loop_node` / `loop_graph` Stream variables. The
  element itself only decides *continue or end* and maintains the swag.
- All loop state is per-Stream (`stream.variables`), never on `self` —
  one Loop instance serves every concurrent Stream.
- The whole loop executes within a single Frame: no new Frames are
  created per iteration, so per-iteration state accumulates in the one
  swag dictionary.

CaptureLimit timeline, `frame_count` 3, with a paced frame generator:

```
Frame 0   CaptureLimit OKAY        ─► writer writes
Frame 1   CaptureLimit OKAY        ─► writer writes
Frame 2   CaptureLimit STOP        ─► writer writes, destroy_stream() posted
Frame 3   CaptureLimit DROP_FRAME  ─► writer skipped   (queued in flight)
          destroy_stream() lands   ─► stop_stream() on every element
```

- CaptureLimit is per-Stream too: `capture_limit_count`,
  `capture_limit_start` and `capture_limit_stopped` live in
  `stream.variables`.

### Implementation notes

- `stream.variables["loop_boundary"]` doubles as the "first invocation"
  guard for evaluating `define` — even the default empty-string boundary
  is recorded, so `define` runs exactly once per Stream.
- Parameters are parsed with
  `aiko_services.main.utilities.parse(..., car_cdr=False)` on every
  invocation. `condition` is re-parsed and re-evaluated each iteration
  (the parsed structure is mutated in place by the evaluators, so
  re-parsing is needed).
- Why STOP then DROP_FRAME. A STOP from a mid-graph element is not
  sticky: the OKAY of the next element resets the Stream state to RUN
  (`stream.py` `set_state()`), so the frame generator continues until the
  graceful `destroy_stream()` is dequeued. DROP_FRAME can not be used for
  the bounding Frame, because it never posts `destroy_stream()`. And the
  outputs can not be blanked, because a missing declared input is a fatal
  Pipeline error (`_process_map_in()`).
- The `condition` parameter is re-parsed on each Frame, as Loop does,
  because the evaluator mutates the parsed structure in place. The
  evaluation arguments are a copy of the swag, so the counters are not
  written into the Frame data.
- Case sensitivity is asymmetric in the Pipeline machinery. During
  looping, the boundary-element comparison lowercases the boundary,
  because the framework lowercases element Actor names. But the
  `LOOP_END` path passes the boundary verbatim to
  `pipeline_graph.iterate_after()`, which matches graph node names in
  their original definition case. In practice the `boundary` parameter
  must be written exactly as the element name appears in the
  PipelineDefinition.

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `Loop` | Initialize loop state per [Stream](../../concepts/stream.md) (`loop_boundary`, `define`); evaluate `condition` / `expression` [parameters](../../concepts/parameters.md) against the Frame swag; return `StreamEvent.OKAY` (continue) or `StreamEvent.LOOP_END` (finish) | `PipelineElementLoop` ([PipelineElement](../../concepts/pipeline_element.md) Interface marker); `PipelineImpl` loop re-queueing ([Pipeline](../../concepts/pipeline.md)); `evaluate_condition()` / `evaluate_define()` ([utility elements](../utilities/elements.md)); `parse()` (S-expression parser) |
| `CaptureLimit` | Count Frames and elapsed time per [Stream](../../concepts/stream.md); test the `frame_count`, `duration`, `run_time` and `condition` bounds; return OKAY, then STOP with the outputs on the bounding Frame, then DROP_FRAME | `all_outputs()` and `evaluate_condition()` ([utility elements](../utilities/elements.md)); `parse()`; [Stream](../../concepts/stream.md) variables; the Pipeline graceful `destroy_stream()` ([Pipeline](../../concepts/pipeline.md)) |

## Current limitations and roadmap

From the source To Do list:

- Log debug output for the `define`, `condition` and `expression`
  parameter evaluations.

Additional observed limitations (implemented behavior, not yet in the
To Do list):

- Only the first `:`-separated component of `boundary` is used by the
  Pipeline loop machinery. The `NEXT_ELEMENT` part (for example, `:Inspect` in
  `factorial_pipeline.json`) is documentation only.
- One loop per Stream: `loop_boundary`, `loop_node` and `loop_graph` are
  single slots in `stream.variables`, so nested or multiple sequential
  Loop elements in one Stream would overwrite each other's state.
- The expression evaluator has known operator gaps (`>` and `<=` — see
  [utility elements](../utilities/elements.md), limitations), which
  constrain the conditions Loop can express.
- No unit tests cover Loop or the Pipeline loop machinery.
  `tests/unit/test_capture_limit.py` covers the four CaptureLimit bounds
  in an in-process Pipeline, without a broker.
- CaptureLimit To Do: a timer, so that the `duration` bound also fires
  when no Frame arrives.

## Related concepts

- [PipelineElement](../../concepts/pipeline_element.md) — the contract
  Loop implements. `PipelineElementLoop` and `StreamEvent.LOOP_END`
- [Pipeline](../../concepts/pipeline.md) — hosts the loop re-queueing
  machinery
- [Parameters](../../concepts/parameters.md) — how `boundary` / `define`
  / `condition` / `expression` are declared and resolved
- [Stream](../../concepts/stream.md) — `stream.variables` loop state and
  the Frame swag
- [Utility elements](../utilities/elements.md) — the expression
  evaluator Loop depends on
- [Observe elements](../observe/elements.md) — Inspect, used after the
  loop in the factorial example
- [Synthetic video source](../media/synthetic_io.md) — the camera-less
  DataSource that the CaptureLimit examples bound
