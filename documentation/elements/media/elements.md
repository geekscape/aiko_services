---
title: General-purpose media elements
description: Mock and NoOp — minimal PipelineElements for scaffolding,
  wiring tests and placeholder graph nodes in any PipelineDefinition
type: concept
audience: [developers, end-users]
status: work-in-progress
source:
  - src/aiko_services/elements/media/elements.py
related: [pipeline_element, pipeline, parameters, stream, text_io]
version: "0.6"
last_updated: 2026-07-06
---

# General-purpose media elements

## Overview

`elements.py` provides the two smallest useful
[PipelineElements](../../concepts/pipeline_element.md) in
Aiko Services: **`Mock`** and **`NoOp`**. Both take no frame inputs, produce
no frame outputs, and always return `StreamEvent.OKAY` — their value is
structural. Use them to stand in for an element you have not written
yet, to keep a [Pipeline](../../concepts/pipeline.md) graph shape valid
while developing, or to verify that Frames flow through a graph at all.

`Mock` additionally logs its identity and an optional `label`
parameter at debug level, making it a cheap trace point; `NoOp` does
nothing whatsoever.

**Why you'd use it**: rough out a PipelineDefinition before the real
elements exist, and watch the Frames flow:

```json
{ "name":   "Mock",
  "parameters": {"label": "detector placeholder"},
  "input":  [],
  "output": [],
  "deploy": {
    "local": {"module": "aiko_services.elements.media.elements"}
  }
}
```

## For application developers

### Command-line usage

There is no committed PipelineDefinition dedicated to `Mock` / `NoOp` —
drop the JSON fragment above into any graph. The source header instead
records two shell one-liners for inspecting *any* PipelineDefinition,
useful when scaffolding:

```bash
grep -A14 graph example.json  # Show PipelineDefinition Graph
grep '{ "name"' example.json  # Show PipelineElements list
```

With `Mock` in a graph, watch it fire per Frame:

```bash
aiko_pipeline create my_pipeline.json -s 1 -ll debug
# ... DEBUG ... Mock<1:0> detector placeholder
```

### Public API

| Class | Kind | Inputs → Outputs | Parameters |
|-------|------|------------------|------------|
| `Mock` | placeholder | (none) → (none) | `label` (default `""`) — logged with `my_id()` at debug level each frame |
| `NoOp` | no-operation | (none) → (none) | (none) |

Service protocols: `mock:0`, `noop:0`.

Both elements return `StreamEvent.OKAY, {}` from `process_frame()` and
use the default `start_stream()` / `stop_stream()` — they are
Stream-lifecycle-neutral and safe anywhere in a graph. Because they
declare no inputs, the Pipeline passes them no frame data; because they
return an empty dict, the Frame's accumulated data (the swag) passes
through them unchanged for successor elements.

## For framework developers (internals)

### Design

These two classes are the *identity elements* of the PipelineElement
algebra — the least code that satisfies the
[PipelineElement](../../concepts/pipeline_element.md) contract:

```python
class NoOp(aiko.PipelineElement):
    def __init__(self, context):
        context.set_protocol("noop:0")
        context.call_init(self, "PipelineElement", context)

    def process_frame(self, stream) -> Tuple[aiko.StreamEvent, dict]:
        return aiko.StreamEvent.OKAY, {}
```

They double as the canonical demonstration of the constructor idiom
(`context.set_protocol()` then
`context.call_init(self, "PipelineElement", context)`) for new element
authors.

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `Mock` | Log `my_id()` and `label` per frame; hold a graph position | [PipelineElement](../../concepts/pipeline_element.md), [Parameters](../../concepts/parameters.md) |
| `NoOp` | Do nothing; hold a graph position | [PipelineElement](../../concepts/pipeline_element.md) |

## Current limitations and roadmap

From the source To Do list — **planned**, not implemented:

- Improve `Mock` towards `Code` and/or `LISP`: a `code` parameter such
  as `"{output} = {input} + {increment}"`, turning the placeholder into
  a small expression-evaluating element.

## Related concepts

- [PipelineElement](../../concepts/pipeline_element.md) — the contract
  these minimal elements demonstrate
- [Pipeline](../../concepts/pipeline.md) — graphs these placeholders
  keep valid during development
- [Parameters](../../concepts/parameters.md) — `Mock.label` resolution
- [Stream](../../concepts/stream.md) — StreamEvent semantics
- [text_io](text_io.md) — the next step up: the simplest *functional*
  element family
