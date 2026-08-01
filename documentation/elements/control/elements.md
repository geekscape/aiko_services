---
title: Control elements
description: Control-flow PipelineElements — the Loop element repeats a
  section of the Pipeline graph until an S-expression condition over the
  Frame swag becomes false
type: concept
audience: [developers, end-users]
status: work-in-progress
ste: adapted
source:
  - src/aiko_services/elements/control/elements.py
  - src/aiko_services/elements/control/pipelines/factorial_pipeline.json
related: [pipeline_element, pipeline, parameters, stream]
version: "0.6"
last_updated: 2026-08-01
---

# Control elements

## Overview

The control elements module gives
[PipelineElements](../../concepts/pipeline_element.md) that alter the
control flow of a [Pipeline](../../concepts/pipeline.md) graph. It
currently contains one element, **Loop**, which implements the
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

**Why to use it**: to repeat a tool or sub-graph until a data-driven
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
from aiko_services.elements.control.elements import Loop   # __all__
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
  invocation. `condition` is re-parsed and re-evaluated each iteration
  (the parsed structure is mutated in place by the evaluators, so
  re-parsing is needed).
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
- The package has no `__init__.py` (it imports as an implicit namespace
  package) and no unit tests cover Loop or the Pipeline loop machinery.

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
