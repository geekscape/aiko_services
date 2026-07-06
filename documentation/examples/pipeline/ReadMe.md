---
title: Pipeline examples index
description: Index of the Pipeline example package — the teaching
  PipelineElements and the committed PipelineDefinitions demonstrating
  local and remote deployment, Graph Paths, frame generation and data
  encoding — plus the multitude stress-test sub-package
type: index
audience: [developers, end-users]
status: draft
source:
  - src/aiko_services/examples/pipeline
related: [pipeline, pipeline_element, stream, parameters]
version: "0.6"
last_updated: 2026-07-06
---

# Pipeline examples index

The canonical worked examples for the
[Pipeline](../../concepts/pipeline.md) concept, in
`src/aiko_services/examples/pipeline/`. One Python module of small
teaching [PipelineElements](../../concepts/pipeline_element.md) and
eight committed PipelineDefinitions that exercise local versus remote
deployment, fan-out / fan-in graphs, multiple Graph Paths,
self-generating [Streams](../../concepts/stream.md) and binary data
encoding.

Navigation: [concepts guide](../../concepts/ReadMe.md) ·
[elements index](../../elements/ReadMe.md) ·
[multitude sub-package](multitude/ReadMe.md)

## Module documents

| Document | Summary |
|----------|---------|
| [elements](elements.md) | The example PipelineElements — `PE_Add`, `PE_Event`, `PE_RandomIntegers`, the `PE_0`..`PE_4` diamond, the `PE_IN` / `PE_TEXT` / `PE_OUT` Graph Path trio, `PE_DataEncode` / `PE_DataDecode` |
| [multitude/ReadMe](multitude/ReadMe.md) | Stress / scale examples: chains of Pipelines linked by remote PipelineElement proxies, with driver shell scripts |

## Example PipelineDefinitions

All element behaviour is documented in [elements](elements.md);
`Inspect` and `Metrics` in the
[observe elements](../../elements/observe/elements.md); `Expression`
in the [utility elements](../../elements/utilities/elements.md).

| PipelineDefinition | Pipeline name | Demonstrates |
|--------------------|---------------|--------------|
| `pipeline_local.json` | `p_local` | All elements in one Process; diamond fan-out / fan-in `(PE_1 (PE_2 PE_4) (PE_3 PE_4) Inspect Metrics)`; Pipeline and element parameters; `class_name` reuse (`PE_5` reuses `PE_4`, defined but not in the graph) |
| `pipeline_remote.json` | `p_remote` | Distributed Pipeline: local `PE_0`, then a **remote** proxy element whose contract is satisfied by the whole `p_local` Pipeline; run `pipeline_local.json` first |
| `pipeline_example.json` | `p_example` | Self-generating Stream: `PE_RandomIntegers` creates its own Frames; `_create_stream_` / `_destroy_stream_exit_` Pipeline parameters; watch `random` in the [Dashboard](../../concepts/dashboard.md). A fuller graph adding `PE_Add` (with the `(random: i)` remap) and `PE_Event` is present but commented out |
| `pipeline_paths.json` | `p_paths` | Four Graph Paths (`PE_IN_0`..`PE_IN_3` head nodes) over shared `PE_IN` / `PE_TEXT` / `PE_OUT` classes via `class_name` aliasing; path selection with `-gp` or `(create_stream 1 PE_IN_1)` |
| `pipeline_decode.json` | `p_decode` | The serving half of the encode / decode pair: a lone local `PE_DataDecode` |
| `pipeline_encode.json` | `p_encode` | Local `PE_DataEncode` chained to a **remote** `PE_DataDecode` served by `p_decode` — binary (NumPy) payloads over the text transport |
| `pipeline_mic_fft.json` | `p_mic_fft` | (dormant) Microphone → FFT → resampler audio chain |
| `pipeline_mic_fft_graph.json` | `p_mic_fft_graph` | (dormant) As above plus audio filter and XY graph display |

**Dormant**: the two `pipeline_mic_fft*.json` definitions deploy their
elements from `"module": "audio_io.py"` — a filename, not a Python
module path — and the `PE_Microphone` / `PE_FFT` / `PE_AudioResampler`
/ `PE_AudioFilter` / `PE_GraphXY` classes belong to the disabled
legacy suite described in
[audio_io](../../elements/media/audio_io.md). They are kept as design
references and do not run as committed.

## Command-line usage

From `src/aiko_services/examples/pipeline` (per the usage header in
`elements.py`); `$TOPIC` is the Pipeline Stream topic
`$NAMESPACE/$HOST/$PID/$SID/in`:

```bash
aiko_pipeline create pipeline_local.json -ll debug  \
  -p Inspect.enable true -p Inspect.target log -p Metrics.enable true
mosquitto_pub -h $HOST -t $TOPIC -m "(process_frame (stream_id: 1) (b: 0))"

aiko_pipeline create pipeline_remote.json    # requires p_local running
mosquitto_pub -h $HOST -t $TOPIC -m "(process_frame (stream_id: 1) (a: 0))"

aiko_pipeline create pipeline_example.json -s 1 -p limit 1000 -p rate 1
aiko_dashboard  # select "PE_RandomIntegers" and watch "random" update

aiko_pipeline create pipeline_paths.json -gp PE_IN_0 -fd "(in_a: x)"
```

Explicit Stream lifecycle over MQTT:

```bash
mosquitto_pub -h $HOST -t $TOPIC -m "(create_stream 1)"
mosquitto_pub -h $HOST -t $TOPIC -m "(process_frame (stream_id: 1) (a: 0))"
mosquitto_pub -h $HOST -t $TOPIC -m "(destroy_stream 1)"
```

## Related documentation

- [Pipeline](../../concepts/pipeline.md) — PipelineDefinition format,
  graphs, deployment and Graph Paths
- [PipelineElement](../../concepts/pipeline_element.md) — the element
  contract these examples teach
- [Stream](../../concepts/stream.md) — create / process / destroy
  lifecycle driven here over MQTT
- [Parameters](../../concepts/parameters.md) — the `-p`, Pipeline and
  element parameter precedence exercised throughout
- [Observe elements](../../elements/observe/elements.md) — `Inspect`
  and `Metrics`, present in most of these graphs
- [Utility elements](../../elements/utilities/elements.md) —
  `Expression`, declared in `pipeline_example.json`
- [Media elements index](../../elements/media/ReadMe.md) — the
  production element families and their PipelineDefinitions
- [multitude/ReadMe](multitude/ReadMe.md) — scaling these ideas to
  chains of ten Pipelines
