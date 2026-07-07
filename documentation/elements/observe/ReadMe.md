---
title: Observe elements documentation
description: Index of OKF documents for the observability PipelineElements
  package — Inspect and Metrics, and their example PipelineDefinition
type: index
audience: [developers, end-users]
status: work-in-progress
version: "0.6"
last_updated: 2026-07-06
---

# Aiko Services: observe elements

OKF documentation for `src/aiko_services/elements/observe/` — the
PipelineElements that provide observability from inside a Pipeline
graph. One document per source module, following the structure defined
in the constitution's OKF Concepts documentation template
(`documentation/constitution/t_00_OkfConceptTemplate.md`).

## Module documents

| Document | Source | One-line summary |
|----------|--------|------------------|
| [Observe elements](elements.md) | `src/aiko_services/elements/observe/elements.py` | `Inspect` writes selected Frame swag values to log, file or stdout; `Metrics` reports per-element and whole-Pipeline timing and memory figures |

Package exports (`__init__.py`): `Inspect`, `Metrics` — imported from
`.elements`; its To Do list is currently empty ("None, yet !").

## Example PipelineDefinitions

| PipelineDefinition | Elements exercised |
|--------------------|--------------------|
| `pipelines/pipeline_observe.json` (Pipeline `p_inspect_metrics`) | Graph `(PE_1 PE_2 Inspect Metrics)`: `PE_1` / `PE_2` (`aiko_services.examples.pipeline.elements`) increment an integer `b → c → d`; [`Inspect`](elements.md) with `"inspect": "(*)"` logs every swag value; [`Metrics`](elements.md) (`rate: 1`) logs timing each Frame and redeclares output `d` to forward it |

```bash
cd src/aiko_services/elements/observe
aiko_pipeline create pipelines/pipeline_observe.json -ll debug -fd "(b: 0)"
```

## See also

- [Elements documentation index](../ReadMe.md)
- [Aiko Services concepts index](../../concepts/ReadMe.md) — in
  particular [PipelineElement](../../concepts/pipeline_element.md),
  [Parameters](../../concepts/parameters.md) and
  [Stream](../../concepts/stream.md)
