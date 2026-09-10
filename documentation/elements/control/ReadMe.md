---
title: Control elements documentation
description: Index of OKF documents for the control-flow PipelineElements
  package — the Loop and CaptureLimit elements, with the factorial and the
  synthetic video example PipelineDefinitions
type: index
audience: [developers, end-users]
status: work-in-progress
ste: adapted
version: "0.8-dev"
last_updated: 2026-09-10
---

# Aiko Services: control elements

OKF documentation for `src/aiko_services/elements/control/` — the
PipelineElements that alter Pipeline graph control flow. One document per
source module, following the structure defined in the constitution's OKF
Concepts documentation template
(`constitution/t_00_OkfConceptTemplate.md`).

## Module documents

| Document | Source | One-line summary |
|----------|--------|------------------|
| [Control elements](elements.md) | `src/aiko_services/elements/control/elements.py` | The `Loop` element (`PipelineElementLoop`) — repeats a graph section until an S-expression condition over the Frame swag becomes false. The `CaptureLimit` element — stops a Stream after a frame count, a duration, a media run time or a condition |

The package `__init__.py` exports `CaptureLimit` and `Loop`:
`from aiko_services.elements.control import CaptureLimit, Loop`.

## Example PipelineDefinitions

| PipelineDefinition | Elements exercised |
|--------------------|--------------------|
| `pipelines/factorial_pipeline.json` (Pipeline `p_factorial`) | `Factorial` → [`Loop`](elements.md) (this package); `Tool_A` → `Mock` (`aiko_services.elements.media.elements`); `Inspect` → [`Inspect`](../observe/elements.md) (observe package). Computes 3! by looping `Tool_A` under boundary `Tool_A:Inspect`, then logs the result; `_create_stream_` / `_destroy_stream_exit_` make it a self-terminating run |

| `../media/pipelines/synthetic_pipeline_0.json` (Pipeline `p_synthetic_0`), `synthetic_pipeline_1.json` (`p_synthetic_1`) | `SyntheticVideoRead` ([synthetic_io](../media/synthetic_io.md)) → [`CaptureLimit`](elements.md) (this package) → display, or record to MP4. Bounded by `duration`, `frame_count`, `run_time` or `condition` |

```bash
cd src/aiko_services/elements/control
aiko_pipeline create pipelines/factorial_pipeline.json -ll debug_all -fd "()"

cd src/aiko_services/elements/media
aiko_pipeline create pipelines/synthetic_pipeline_0.json -s 1  \
  -p CaptureLimit.frame_count 45
```

## See also

- [Elements documentation index](../ReadMe.md)
- [Aiko Services concepts index](../../concepts/ReadMe.md) — in
  particular [PipelineElement](../../concepts/pipeline_element.md),
  [Parameters](../../concepts/parameters.md) and
  [Stream](../../concepts/stream.md)
