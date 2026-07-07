---
title: Control elements documentation
description: Index of OKF documents for the control-flow PipelineElements
  package — the Loop element and its factorial example PipelineDefinition
type: index
audience: [developers, end-users]
status: work-in-progress
version: "0.6"
last_updated: 2026-07-06
---

# Aiko Services: control elements

OKF documentation for `src/aiko_services/elements/control/` — the
PipelineElements that alter Pipeline graph control flow. One document per
source module, following the structure defined in the constitution's OKF
Concepts documentation template
(`documentation/constitution/t_00_OkfConceptTemplate.md`).

## Module documents

| Document | Source | One-line summary |
|----------|--------|------------------|
| [Control elements](elements.md) | `src/aiko_services/elements/control/elements.py` | The `Loop` element (`PipelineElementLoop`) — repeats a graph section until an S-expression condition over the Frame swag becomes false |

Note: the package currently has no `__init__.py`, so there are no
package-level exports; `elements.py` declares `__all__ = ["Loop"]`.

## Example PipelineDefinitions

| PipelineDefinition | Elements exercised |
|--------------------|--------------------|
| `pipelines/factorial_pipeline.json` (Pipeline `p_factorial`) | `Factorial` → [`Loop`](elements.md) (this package); `Tool_A` → `Mock` (`aiko_services.elements.media.elements`); `Inspect` → [`Inspect`](../observe/elements.md) (observe package). Computes 3! by looping `Tool_A` under boundary `Tool_A:Inspect`, then logs the result; `_create_stream_` / `_destroy_stream_exit_` make it a self-terminating run |

```bash
cd src/aiko_services/elements/control
aiko_pipeline create pipelines/factorial_pipeline.json -ll debug_all -fd "()"
```

## See also

- [Elements documentation index](../ReadMe.md)
- [Aiko Services concepts index](../../concepts/ReadMe.md) — in
  particular [PipelineElement](../../concepts/pipeline_element.md),
  [Parameters](../../concepts/parameters.md) and
  [Stream](../../concepts/stream.md)
