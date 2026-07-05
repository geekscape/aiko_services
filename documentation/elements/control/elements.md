---
title: Control elements
description: Control-flow PipelineElements — the Loop element repeats a
  section of the Pipeline graph until an S-expression condition over the
  Frame swag becomes false
type: concept
audience: [developers, end-users]
status: work-in-progress
source:
  - src/aiko_services/elements/control/elements.py
  - src/aiko_services/elements/control/pipelines/factorial_pipeline.json
related: [pipeline_element, pipeline, parameters, stream]
version: "0.6"
last_updated: 2026-07-06
---

# Control elements

## Overview

The control elements module provides
[PipelineElements](../../concepts/pipeline_element.md) that alter the
control flow of a [Pipeline](../../concepts/pipeline.md) graph. It
currently contains one element, **Loop**, which implements the
`PipelineElementLoop` Interface: the graph section between the Loop
element and a named *boundary* element is executed repeatedly — within a
single Frame — until a condition evaluated against the Frame's swag
becomes false.

Loop's `define`, `condition` and `expression`
[parameters](../../concepts/parameters.md) are S-expressions evaluated by
the expression helpers in the sibling
[utility elements](../utilities/elements.md) module
(`evaluate_define()` / `evaluate_condition()`), so a Pipeline can express
simple iterative computation — initialise variables, test, update —
without writing a new Python element.

**Why you'd use it**: to repeat a tool or sub-graph until a data-driven
condition is met — retry-until-success, iterate-until-converged. The
committed example computes a factorial by looping over a mock tool
element:

```bash
cd src/aiko_services/elements/control
aiko_pipeline create pipelines/factorial_pipeline.json -ll debug_all -fd "()"
# ... Inspect: factorial: 6        (3! computed by looping)
```

## For application developers

### Command-line usage

Control elements have no CLI of their own; they are hosted by the
`aiko_pipeline` CLI (see [Pipeline](../../concepts/pipeline.md)). From
the usage header of `elements.py`:

```bash
cd src/aiko_services/elements/control
aiko_pipeline create pipelines/factorial_pipeline.json -ll debug_all  \
                                                       -fd "()"
```

`factorial_pipeline.json` declares `_create_stream_` and
`_destroy_stream_exit_` Pipeline parameters, so the Pipeline creates
Stream `"1"` at start-up and the process exits when that Stream is
destroyed — the `-fd "()"` empty Frame triggers one run of the graph.

The loop behaviour is configured entirely through element parameters in
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
from aiko_services.elements.control.elements import Loop   # __all__
```

**`Loop(aiko.PipelineElementLoop)`** — protocol `loop:0`.

| Parameter | Default | Meaning |
|-----------|---------|---------|
| `boundary` | `""` | Name of the last graph element inside the loop body, written `LOOP_END_ELEMENT[:NEXT_ELEMENT]` — only the part before `:` is used (see limitations) |
| `define` | *(optional)* | S-expression `((name expression) ...)` — evaluated once per [Stream](../../concepts/stream.md), on the first `process_frame()`, to initialise swag entries |
| `condition` | **required** | S-expression `((expression) ...)` — every expression must be truthy for the loop to continue; a missing parameter returns `StreamEvent.ERROR` |
| `expression` | *(optional)* | S-expression `((name expression) ...)` — evaluated on each iteration *while the condition holds*, updating swag entries |

Frame contract: `input: []` / `output: []` — Loop reads and writes the
Frame's swag directly (`stream.frames[stream.frame_id].swag`) rather
than through declared inputs and outputs, so any swag name is available
to its expressions.

`process_frame(stream)` behaviour per invocation:

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

### Implementation notes

- `stream.variables["loop_boundary"]` doubles as the "first invocation"
  guard for evaluating `define` — even the default empty-string boundary
  is recorded, so `define` runs exactly once per Stream.
- Parameters are parsed with
  `aiko_services.main.utilities.parse(..., car_cdr=False)` on every
  invocation; `condition` is re-parsed and re-evaluated each iteration
  (the parsed structure is mutated in place by the evaluators, so
  re-parsing is required).
- Case sensitivity is asymmetric in the Pipeline machinery: the
  boundary-element comparison during looping lowercases the boundary
  (element Actor names are lowercased by the framework), but the
  `LOOP_END` path passes the boundary verbatim to
  `pipeline_graph.iterate_after()`, which matches graph node names in
  their original definition case. In practice the `boundary` parameter
  must be written exactly as the element name appears in the
  PipelineDefinition.

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `Loop` | Initialise loop state per [Stream](../../concepts/stream.md) (`loop_boundary`, `define`); evaluate `condition` / `expression` [parameters](../../concepts/parameters.md) against the Frame swag; return `StreamEvent.OKAY` (continue) or `StreamEvent.LOOP_END` (finish) | `PipelineElementLoop` ([PipelineElement](../../concepts/pipeline_element.md) Interface marker); `PipelineImpl` loop re-queueing ([Pipeline](../../concepts/pipeline.md)); `evaluate_condition()` / `evaluate_define()` ([utility elements](../utilities/elements.md)); `parse()` (S-expression parser) |

## Current limitations and roadmap

From the source To Do list:

- Log debug output for the `define`, `condition` and `expression`
  parameter evaluations.

Additional observed limitations (implemented behaviour, not yet in the
To Do list):

- Only the first `:`-separated component of `boundary` is used by the
  Pipeline loop machinery; the `NEXT_ELEMENT` part (e.g. `:Inspect` in
  `factorial_pipeline.json`) is documentation only.
- One loop per Stream: `loop_boundary`, `loop_node` and `loop_graph` are
  single slots in `stream.variables`, so nested or multiple sequential
  Loop elements in one Stream would overwrite each other's state.
- The expression evaluator has known operator gaps (`>` and `<=` — see
  [utility elements](../utilities/elements.md), limitations), which
  constrain the conditions Loop can express.
- The package has no `__init__.py` (it imports as an implicit namespace
  package) and no unit tests cover Loop or the Pipeline loop machinery.

## Related concepts

- [PipelineElement](../../concepts/pipeline_element.md) — the contract
  Loop implements; `PipelineElementLoop` and `StreamEvent.LOOP_END`
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
