---
title: LLM example elements
description: PipelineElements that wrap a LangChain LLM chain — Ollama
  local models (or OpenAI) prompted as a robot-dog persona that answers
  only in S-Expressions, plus a hard-coded Detection stub
type: concept
audience: [developers, end-users]
status: draft
source:
  - src/aiko_services/examples/llm/elements.py
related: [pipeline_element, pipeline, message, parameters, text_io,
  speech_elements]
version: "0.6"
last_updated: 2026-07-06
---

# LLM example elements

## Overview

`elements.py` provides the **`LLM`**
[PipelineElement](../../concepts/pipeline_element.md): each text frame
is sent through a LangChain chain — `ChatPromptTemplate | llm |
StrOutputParser` — to a local **Ollama** model (default
`gemma4:latest`, temperature 0.0; a `llm_type` of `"openai"` selects
LangChain's `ChatOpenAI` instead). The system prompt casts the model
as "Oscar", an XGO-Mini 2 robot dog that replies **only in
S-Expressions** — `(action ...)`, `(get_temperature ...)`,
`(response ...)`, `(error ...)` — so replies can drive robot commands
directly. A `Detection` stub and a `PE_COQUI_TTS` pass-through
complete the module.

This is the `p_llm` Pipeline in the middle of the speech round trip:
the [speech example](../speech/ReadMe.md) transcribes microphone audio
and deploys its `PE_LLM` placeholder *remote* to this Pipeline, whose
reply can in turn be deployed remote to the `p_llm_output`
text-to-speech Pipeline.

**Why you'd use it**: chat with a local LLM from your terminal as an
Aiko Services [Pipeline](../../concepts/pipeline.md) (from the source
usage header):

```bash
ollama serve  # or systemctl start ollama
cd src/aiko_services/examples/llm
aiko_pipeline create llm_pipeline_1.json -s 1 -sr -gt 900
```

## For application developers

### Command-line usage

From the source usage header. Interactive terminal chat
(`llm_pipeline_1.json`, using
[text_io](../../elements/media/text_io.md) `tty://` elements):

```bash
ollama serve  # or systemctl start ollama

aiko_pipeline create llm_pipeline_1.json -s 1 -sr -gt 900
```

Headless service (`llm_pipeline_0.json`), fed a first frame from the
command line, with Metrics visible at debug level:

```bash
export AIKO_LOG_LEVEL=DEBUG  # Metrics
aiko_pipeline create llm_pipeline_0.json -s 1  \
  -fd "(texts: ('Tell me about yourself') detections: ())" -sr -gt 900
```

Further frames can be posted over MQTT (the
[Message](../../concepts/message.md) transport) — substitute your
Pipeline's actual topic path:

```bash
TOPIC_LLM=aiko/spike/3321189/1/in

MESSAGE="(process_frame (stream_id: 1) (texts: ('What are your interests ?') detections: ()))"
mosquitto_pub -t $TOPIC -m "$MESSAGE"

MESSAGE="(process_frame (stream_id: 1) (texts: ('What can you see ?') detections: (carrot octopus)))"
mosquitto_pub -t $TOPIC -m "$MESSAGE"
```

The header also records LangChain setup notes (`pip install langchain
langchain_community langchain-ollama`, optional `LANGCHAIN_*` /
`OPENAI_API_KEY` environment variables) and invocations of a
`./llm_chain.py` script that is **not present** in the package — a
historical reference only.

### Public API

| Class | Kind | Inputs → Outputs | Protocol |
|-------|------|------------------|----------|
| `LLM` | LLM chain invoker | `detections`, `texts` → `texts` | `llm:0` |
| `Detection` | detection stub | `texts` → `detections` | `detections:0` |
| `PE_COQUI_TTS` | pass-through stub | `text` → `text` | `text_to_speech:0` |

#### LLM

Per frame: takes `texts[0]`; a `"<silence>"` sentinel (from the
[speech elements](../speech/speech_elements.md)) is passed straight
through; otherwise `llm_chain("ollama", text, detections)` is invoked
and the response returned as `texts`. An Ollama connection failure
(`httpx.ConnectError`) yields the reply
`"#### Error: Can't connect to Ollama server ####"` instead of a
StreamEvent error.

The element also subscribes to the MQTT topic
`{namespace}/detections` and stores `(time.monotonic(), detections)`
on arrival — but the code that would merge those out-of-band
detections (with a 1-second freshness window) into the prompt is
commented out; only the `detections` frame input is used today.

Module knobs (constants, not yet
[Parameters](../../concepts/parameters.md)): `LLM_MODEL_NAME`
(`gemma4:latest`; commented alternatives include `deepseek-r1`,
`llama3.1/3.2/3.3`, `llama3.2-vision`, `llava-llama3`, `gpt-oss`) and
`LLM_TEMPERATURE` (0.0).

#### Detection

A stub that ignores its `texts` input and always returns
`{"detections": ["carrot, octopus"]}` (note: a single string, not two
items). It exists so `llm_pipeline_1.json` can exercise the `LLM`
element's two-input signature without a real detector.

#### PE_COQUI_TTS

A pass-through (`text` → `text`) bearing the same class name and
protocol as the *real* Coqui text-to-speech element in
[speech_elements](../speech/speech_elements.md) — here it only
reserves the graph position; `llm_pipeline_0.json`'s commented
alternative graph deploys the name *remote* to the `p_llm_output`
Pipeline, where the real implementation runs.

## For framework developers (internals)

### Design

```
llm_pipeline_1.json (p_llm, single process, terminal chat)

  TextReadTTY --> Detection --> LLM --> TextWriteTTY
  (tty:// in)     (stub)         |      (tty:// out)
                                 v
                   llm_chain(): ChatPromptTemplate
                                 | OllamaLLM(gemma4)
                                 | StrOutputParser

llm_pipeline_0.json (p_llm, service in the speech round trip)

  p_llm_input ==MQTT==> LLM --> Metrics
  (speech example)       |
                         +--[remote "#" option]--> PE_COQUI_TTS
                                                   in p_llm_output
```

Key design points:

- **The LLM is behind a plain function** — `llm_load(llm_type,
  model_name)` returns a LangChain LLM (`OllamaLLM` or `ChatOpenAI`)
  and `llm_chain(llm_type, text, detections)` builds and invokes the
  prompt chain. The PipelineElement is a thin frame adapter around
  them.
- **S-Expression-constrained output**: the system prompt enumerates
  the valid `(action ...)` commands (arm, crawl, pee, pitch, sniff,
  wag, ...), a `(get_temperature location)` function, `(response
  YOUR REPLY)` capped at 12 words and `(error diagnostic_message)` —
  aligning LLM output with the S-Expression convention used across
  Aiko Services, and appends `- see: {detections}` so the model can
  answer "What can you see ?".
- **Two deployment shapes for one Pipeline name** — both JSON files
  name the Pipeline `p_llm`, so the speech example's remote
  `service_filter` (`name: "p_llm"`) matches whichever is running.

### Implementation notes

- `llm_chain()` calls `llm_load()` on **every frame** — the LangChain
  LLM object is rebuilt per invocation rather than cached in the
  element (cheap for Ollama's HTTP client, but worth knowing).
- Two earlier system prompts remain in the source as dead code: an
  initial `SYSTEM_PROMPT` ("Keep all your responses brief and less
  than 10 words") is immediately overwritten by the S-Expression
  prompt, and `SYSTEM_PROMPT_OLD` (an earlier multi-robot
  select/action grammar) is built but never used.
- `OPENAI_API_KEY = "..."` inside `llm_load()` is a placeholder; the
  `"openai"` path relies on the environment variable instead.
- `LLM.__init__()` calls `context.call_init()` *before*
  `context.set_protocol()` — the reverse of the conventional order
  used elsewhere (e.g. the speech elements).

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `LLM` | Adapt text frames to `llm_chain()`; pass `"<silence>"` through; report Ollama connection errors; subscribe to out-of-band detections | [PipelineElement](../../concepts/pipeline_element.md), LangChain (`OllamaLLM` / `ChatOpenAI`), [Message](../../concepts/message.md) (MQTT `add_message_handler`) |
| `Detection` | Emit fixed placeholder detections | [PipelineElement](../../concepts/pipeline_element.md) |
| `PE_COQUI_TTS` | Reserve the text-to-speech graph position; remote-deploy target name | [speech_elements](../speech/speech_elements.md) (real implementation), [Pipeline](../../concepts/pipeline.md) remote deploy |

## Current limitations and roadmap

Implemented-versus-planned notes:

- The out-of-band MQTT detections path is wired up (subscription and
  handler) but its use in `process_frame()` is commented out.
- `Detection` is a stub; `PE_COQUI_TTS` here is a pass-through.
- Vision-capable models are listed but the image path
  (`describe image`) exists only as a commented line in
  `llm_chain()`.

From the source To Do list — **planned**, not implemented:

- Attach a CLI UI; move robot selection into it.
- Move the system prompt to a file specified by a CLI argument, and
  improve the prompt.
- An example using `test.mosquitto.org`, splitting the CLI UI and the
  LLM into separate Pipelines.
- Test using OpenAI ChatGPT-4o; set the LLM `seed` parameter.

## Related concepts

- [LLM example index](ReadMe.md) — the two PipelineDefinitions
- [Speech example](../speech/ReadMe.md) — the Pipelines that feed
  `p_llm` and speak its replies
- [speech_elements](../speech/speech_elements.md) — `PE_LLM`
  placeholder and the real `PE_COQUI_TTS`
- [PipelineElement](../../concepts/pipeline_element.md) — the element
  contract
- [Pipeline](../../concepts/pipeline.md) — remote deploys and
  `service_filter` matching
- [Message](../../concepts/message.md) — MQTT frames and the
  detections subscription
- [text_io](../../elements/media/text_io.md) — the `tty://` terminal
  elements in `llm_pipeline_1.json`
