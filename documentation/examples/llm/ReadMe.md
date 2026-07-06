---
title: LLM example index
description: Index of the LLM example — the LangChain / Ollama LLM
  PipelineElement and the two PipelineDefinitions for terminal chat and
  for serving the speech-to-LLM round trip
type: index
audience: [developers, end-users]
status: draft
source:
  - src/aiko_services/examples/llm
related: [pipeline, pipeline_element, text_io, speech_elements]
version: "0.6"
last_updated: 2026-07-06
---

# LLM example index

The LLM example under `src/aiko_services/examples/llm/` runs a local
LLM — **Ollama** (default model `gemma4:latest`) via LangChain, with
an OpenAI option — as the `p_llm` Aiko Services
[Pipeline](../../concepts/pipeline.md), prompted as a robot-dog
persona that replies only in S-Expressions.

Navigation: [concepts guide](../../concepts/ReadMe.md) ·
[media elements](../../elements/media/ReadMe.md) ·
[speech example](../speech/ReadMe.md)

## Module documents

| Document | Summary |
|----------|---------|
| [elements](elements.md) | `LLM` (LangChain chain to Ollama / OpenAI), `Detection` stub and a `PE_COQUI_TTS` pass-through |

## Example PipelineDefinitions

| PipelineDefinition | Pipeline | Demonstrates |
|--------------------|----------|--------------|
| `llm_pipeline_0.json` | `p_llm` | Headless LLM service: `(LLM Metrics)` — fed by `-fd` frame data, MQTT messages, or remotely by the speech example. A `"#"` comment graph `(LLM PE_COQUI_TTS Metrics)` adds `PE_COQUI_TTS` deployed *remote* to the `p_llm_output` Pipeline, closing the voice loop |
| `llm_pipeline_1.json` | `p_llm` | Self-contained terminal chat: `(TextReadTTY Detection LLM TextWriteTTY)` — `tty://` [text_io](../../elements/media/text_io.md) elements for the REPL, `Detection` stub supplying the second `LLM` input |

`Metrics` comes from the
[observe elements](../../elements/observe/elements.md). Both files
name the Pipeline `p_llm`, so the speech example's remote
`service_filter` (`name: "p_llm"`) matches whichever one is running.

### Command-line usage

From the `elements.py` usage header — run from
`src/aiko_services/examples/llm/`:

```bash
ollama serve  # or systemctl start ollama

aiko_pipeline create llm_pipeline_1.json -s 1 -sr -gt 900

export AIKO_LOG_LEVEL=DEBUG  # Metrics
aiko_pipeline create llm_pipeline_0.json -s 1  \
  -fd "(texts: ('Tell me about yourself') detections: ())" -sr -gt 900
```

Posting frames over MQTT (substitute your Pipeline's topic path):

```bash
TOPIC_LLM=aiko/spike/3321189/1/in

MESSAGE="(process_frame (stream_id: 1) (texts: ('What are your interests ?') detections: ()))"
mosquitto_pub -t $TOPIC -m "$MESSAGE"
```

## Connecting with the speech Pipelines

The [speech example](../speech/ReadMe.md) splits a voice conversation
across three Pipelines, with `p_llm` in the middle:

```
p_llm_input                  p_llm                 p_llm_output
microphone -> WhisperX  ==>  LLM (Ollama)  ==>  Coqui TTS -> speaker
(pipeline_speech_            (llm_pipeline_     (pipeline_speech_
 llm_input.json)              0.json)            llm_output.json)
```

`pipeline_speech_llm_input.json` deploys its `PE_LLM` element remote
to `p_llm`; enabling `llm_pipeline_0.json`'s `"#"` graph deploys
`PE_COQUI_TTS` remote to `p_llm_output`, which speaks the reply.

## Related documentation

- [Speech example](../speech/ReadMe.md) — microphone, speech-to-text
  and text-to-speech Pipelines around `p_llm`
- [elements](elements.md) — the LLM element concept document
- [Pipeline](../../concepts/pipeline.md) — graphs, `"#"` comment keys,
  remote deploys
- [PipelineElement](../../concepts/pipeline_element.md) — the element
  contract
- [text_io](../../elements/media/text_io.md) — the `tty://` REPL
  elements
- [observe elements](../../elements/observe/elements.md) — `Metrics`
