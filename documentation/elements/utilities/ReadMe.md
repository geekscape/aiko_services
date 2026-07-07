---
title: Utility elements documentation
description: Index of OKF documents for the utility PipelineElements
  package — the Expression element, the expression-evaluation helpers and
  their example PipelineDefinition
type: index
audience: [developers, end-users]
status: work-in-progress
version: "0.6"
last_updated: 2026-07-06
---

# Aiko Services: utility elements

OKF documentation for `src/aiko_services/elements/utilities/` — the
general-purpose PipelineElements and shared helpers used across the
element packages. One document per source module, following the
structure defined in the constitution's OKF Concepts documentation
template (`documentation/constitution/t_00_OkfConceptTemplate.md`).

## Module documents

| Document | Source | One-line summary |
|----------|--------|------------------|
| [Utility elements](elements.md) | `src/aiko_services/elements/utilities/elements.py` | The `Expression` element — define / delete / rename Frame swag values from S-expression parameters — plus the `evaluate*()` helpers (reused by the control package's `Loop`) and the `all_outputs()` pass-through helper |

Package exports (`__init__.py`): `all_outputs`, `evaluate`,
`evaluate_condition`, `evaluate_define`, `Expression` — imported from
`.elements`; its To Do list is currently empty ("None, yet !"). Note
that `elements.py`'s own `__all__` misspells `evaluate_condition`
(see the module document's limitations).

## Example PipelineDefinitions

| PipelineDefinition | Elements exercised |
|--------------------|--------------------|
| `pipelines/pipeline_expression.json` (Pipeline `p_expression`) | Graph `(Expression_0 Inspect_0 Expression_1 Inspect_1)`: [`Expression`](elements.md) twice — `Expression_0` defines `a: int`, `b: float`, `s: str`; `Expression_1` computes `a+1` / `b+1.0`, defines a dict and a list, deletes `s` and renames `b` to `c` — each followed by [`Inspect`](../observe/elements.md) (`"inspect": "(*)"`, observe package) to log the swag before and after |

```bash
cd src/aiko_services/elements/utilities
aiko_pipeline create pipelines/pipeline_expression.json -fd "()" -ll debug
```

## See also

- [Elements documentation index](../ReadMe.md)
- [Aiko Services concepts index](../../concepts/ReadMe.md) — in
  particular [PipelineElement](../../concepts/pipeline_element.md),
  [Parameters](../../concepts/parameters.md) and
  [Stream](../../concepts/stream.md)
