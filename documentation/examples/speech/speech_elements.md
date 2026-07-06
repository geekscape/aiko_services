---
title: Speech example elements
description: PipelineElements for the speech round trip — WhisperX
  speech-to-text, Coqui text-to-speech, audio sliding-window framing and
  the pass-through placeholders that link the speech Pipelines to the
  LLM Pipeline
type: concept
audience: [developers, end-users]
status: draft
source:
  - src/aiko_services/examples/speech/speech_elements.py
related: [pipeline_element, pipeline, stream, parameters, share,
  audio_io, elements]
version: "0.6"
last_updated: 2026-07-06
---

# Speech example elements

## Overview

`speech_elements.py` provides the
[PipelineElements](../../concepts/pipeline_element.md) for the speech
side of the speech-to-LLM round trip: **`PE_WhisperX`** (speech-to-text
via the WhisperX ML model), **`PE_COQUI_TTS`** (text-to-speech via the
Coqui TTS ML model), **`PE_AudioFraming`** (a sliding window over audio
chunks) and three small supporting elements — `PE_AudioWriteFile`,
`PE_SpeechFraming` and `PE_LLM`. Together with the microphone and
speaker elements from [audio_io](../../elements/media/audio_io.md) and
the [LLM example elements](../llm/elements.md), they form voice-driven
[Pipelines](../../concepts/pipeline.md): microphone audio in,
transcribed text to an LLM, and the LLM's reply spoken aloud.

The elements pass a `"<silence>"` sentinel down the graph when there is
nothing worth saying, so downstream stages (LLM, text-to-speech) can
skip work on empty frames.

**Why you'd use it**: transcribe your voice and hear it echoed back,
all as one Pipeline (from the source usage header):

```bash
cd src/aiko_services/examples/speech
T=0 aiko_pipeline create pipeline_transcription.json
```

## For application developers

### Command-line usage

The source usage header records two invocations:

```bash
T=0 aiko_pipeline create pipeline_transcription.json

W=0 AIKO_LOG_MQTT=true aiko_pipeline create pipeline_whisperx.json
```

Run them from `src/aiko_services/examples/speech/`, because the
PipelineDefinitions deploy these elements with
`"module": "speech_elements.py"` — a file path resolved relative to
the current directory. See the [speech example index](ReadMe.md) for
all eight PipelineDefinitions and their prerequisites — note that the
microphone / speaker Pipelines depend on `PE_Microphone*` /
`PE_Speaker`, which are currently **disabled** in
[audio_io](../../elements/media/audio_io.md).

Prerequisites for the ML elements: `pip install whisperx` (WhisperX
speech-to-text) and `pip install TTS` (Coqui text-to-speech), plus a
CUDA GPU — both models are loaded onto `"cuda"` with no CPU fallback.
Each import is guarded: if the package is missing, the module prints
and logs a warning and simply does not define `PE_WhisperX` /
`PE_COQUI_TTS`.

### Public API

| Class | Kind | Inputs → Outputs | Protocol |
|-------|------|------------------|----------|
| `PE_WhisperX` | speech-to-text | `audio` → `text` | `speech_to_text:0` |
| `PE_COQUI_TTS` | text-to-speech | `text` → `audio` | `text_to_speech:0` |
| `PE_AudioFraming` | sliding window | `audio` → `audio` | `audio_framing:0` |
| `PE_AudioWriteFile` | audio file writer (stub) | `audio` → `audio` | `audio_write_file:0` |
| `PE_SpeechFraming` | pass-through | `text` → `text` | `speech_framing:0` |
| `PE_LLM` | pass-through placeholder | `text` → `text` | `llm:0` |

#### PE_WhisperX

Defined only when the `whisperx` package imports. Loads the
`"large"` WhisperX model (1,550 M parameters, ~3,418 Mb VRAM — the
source lists the `tiny` / `base` / `small` / `medium` trade-offs as
comments) onto CUDA in `__init__()`, applying the documented
workaround for WhisperX issue 708 (`asr_options` with
`max_new_tokens`, `clip_timestamps` and
`hallucination_silence_threshold` set to `None`).

Per frame: squeezes the `audio` NumPy array (WhisperX expects
`np.float32` sampled at 16,000 Hz), transcribes with `language="en"`,
lower-cases and strips the first segment, then filters common Whisper
hallucinations (`"you"`, `"thank you."`, `"thanks for watching!"`).
A useful transcription is logged and returned as `text`; anything else
becomes `"<silence>"`. Saying **"terminate"** raises `SystemExit` —
a voice-controlled Pipeline shutdown. Transcriptions slower than 0.5
seconds are logged at debug level.

A commented-out integration posts the transcription to an "AIDE"
application server (`http://localhost:8080/welcome` and `/chat` via
`aide_http_request()`) and publishes the reply over MQTT to
`{namespace}/speech` — **dead code**, retained in the source.

#### PE_COQUI_TTS

Defined only when the Coqui `TTS` package imports. Loads
`tts_models/en/vctk/vits` (Coqui TTS 0.22.0, ~594 Mb VRAM) with
`gpu=True`; speaker `"p364"` (British, female; `"p226"` male
alternative in comments). Coqui produces audio as a Python list
sampled at 22,050 Hz.

Per frame: synthesises `text` to `audio`, or emits `audio = None` for
`"<silence>"`. Publishes two [share](../../concepts/share.md)
variables via `ec_producer`: `speech` (the spoken text, with spaces
replaced by Unicode U+00A0 no-break spaces so the value survives
S-Expression handling) and its own `frame_id` counter.

#### PE_AudioFraming

Maintains a sliding window of audio chunks in an `LRUCache`. Each
frame's `audio` input is a **WAV file path**: the file is loaded with
`whisperx.load_audio()` and then **deleted** (`os.remove`), the
waveform is cached keyed by `frame_id`, and the concatenation of all
cached waveforms is emitted as `audio`. Window arithmetic uses the
module literals `AUDIO_CHUNK_DURATION = 5.0` s,
`AUDIO_SAMPLE_DURATION = 5.0` s and `AUDIO_SAMPLE_RATE = 16000` Hz,
giving a cache size of 1 as committed. Frames that take longer than
0.5 seconds are logged. Not referenced by any committed
PipelineDefinition.

#### PE_AudioWriteFile

A stub: computes an output pathname from the template
`y_audio_{frame_id:06}.wav` and reads the `audio_channels`
[parameter](../../concepts/parameters.md) (default 1), but the actual
`soundfile` write is commented out. Its return value is buggy — see
Current limitations and roadmap. Not referenced by any committed
PipelineDefinition.

#### PE_SpeechFraming and PE_LLM

Identity pass-throughs (`text` → `text`), like
[`Mock` / `NoOp`](../../elements/media/elements.md) but with named
frame data. `PE_SpeechFraming` reserves the graph position where
utterance segmentation would go. `PE_LLM` is the **local placeholder
for the remote LLM Pipeline**: `pipeline_speech_llm_input.json`
declares it with a `"remote"` deploy whose `service_filter` matches a
Pipeline named `p_llm` — the [LLM example](../llm/ReadMe.md) — so the
class body here is only used when running it locally as a stub.

## For framework developers (internals)

### Design

The elements are the middle of a three-Pipeline round trip; the
microphone and speaker ends come from
[audio_io](../../elements/media/audio_io.md):

```
p_llm_input Pipeline                        p_llm Pipeline
+------------------------------------+     +---------------+
| PE_MicrophoneSD (audio_io)         |     | LLM (Ollama)  |
|   -> PE_WhisperX     (audio->text) | MQTT| (../llm/      |
|   -> PE_SpeechFraming(text ->text) |---->|  elements.py) |
|   -> PE_LLM [remote -> "p_llm"]    |     +-------+-------+
+------------------------------------+             | MQTT
                                                    v
                            p_llm_output Pipeline
                            +----------------------------------+
                            | PE_COQUI_TTS       (text->audio) |
                            |   -> PE_Speaker (audio_io)       |
                            +----------------------------------+
```

Key design points:

- **Sentinel-based flow control** — `"<silence>"` flows through the
  text stages instead of dropping frames, so every stage still sees a
  frame and the share variables stay live.
- **Remote deploys glue the Pipelines together** — `PE_LLM` (here) and
  `PE_COQUI_TTS` (declared remote in `llm_pipeline_0.json`) are proxied
  to other Pipelines by `service_filter` name matching, demonstrating
  [Pipeline](../../concepts/pipeline.md) composition over the network.
- **ML models load in `__init__()`** — the Pipeline is not "ready"
  until WhisperX and Coqui TTS have loaded; the source To Do list wants
  Pipeline lifecycle to depend on PipelineElement lifecycle for exactly
  this reason.
- **Audio currently crosses element boundaries as WAV files**
  (`PE_AudioFraming` reads and deletes a file per frame) — the To Do
  list plans to stop using files and match the microphone output data
  type to WhisperX's NumPy input directly.

### Implementation notes

- `PE_AudioFraming` is defined unconditionally but calls
  `whisperx.load_audio()`; if the `whisperx` import failed, calling it
  raises `NameError` at frame time rather than failing fast.
- Module-level literals `AUDIO_CHUNK_DURATION`,
  `AUDIO_SAMPLE_DURATION`, `AUDIO_SAMPLE_RATE`, `AUDIO_CHANNELS`,
  `COQUI_MODEL_NAME`, `COQUI_SPEAKER_ID`, `WHISPERX_MODEL_SIZE` and
  `CUDA_DEVICE` are candidates for
  [Parameters](../../concepts/parameters.md) / share variables (per
  the source TODO comments).
- `aide_http_request()` and the imports it needs (`requests`, plus
  `generate` / `get_namespace` and `Thread`) are live code serving
  only the commented-out AIDE integration in
  `PE_WhisperX.process_frame()`.

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `PE_WhisperX` | Transcribe audio frames; filter hallucinations; emit text or `"<silence>"`; voice-terminate | [PipelineElement](../../concepts/pipeline_element.md), WhisperX ML model, [Stream](../../concepts/stream.md) |
| `PE_COQUI_TTS` | Synthesise speech from text; publish `speech` / `frame_id` share variables | [PipelineElement](../../concepts/pipeline_element.md), Coqui TTS ML model, `ECProducer` ([Share](../../concepts/share.md)) |
| `PE_AudioFraming` | Slide a window of audio chunks; load and delete per-frame WAV files | `LRUCache`, WhisperX (`load_audio`), [Stream](../../concepts/stream.md) |
| `PE_AudioWriteFile` | (Stub) name and write per-frame WAV files | [Parameters](../../concepts/parameters.md) |
| `PE_SpeechFraming` | Hold the utterance-segmentation graph position | [PipelineElement](../../concepts/pipeline_element.md) |
| `PE_LLM` | Stand in locally for the remote LLM Pipeline | [Pipeline](../../concepts/pipeline.md) remote deploy, [LLM elements](../llm/elements.md) |

## Current limitations and roadmap

Bugs and stubs in the committed source:

- `PE_AudioWriteFile.process_frame()` returns
  `{"audio", audio_pathname}` — a Python **set**, not a dict — and its
  `soundfile` write code is commented out (referencing an undefined
  `indata` and an unimported `sf`). The element is a non-functional
  stub.
- `aide_http_request()` builds its error reply from a plain string
  containing `{response.status_code}` — missing the `f` prefix, so the
  placeholder is never interpolated (dead code path today, since the
  AIDE integration is commented out).
- Both ML elements hard-code CUDA (`gpu=True`, `CUDA_DEVICE =
  "cuda"`); there is no CPU fallback.

From the source To Do list — **planned**, not implemented:

- Match microphone audio output to WhisperX's input data type and stop
  passing audio through files.
- Pipeline "lifecycle" should depend on all PipelineElement
  lifecycles — wait until the WhisperX model is loaded before the
  Pipeline is "ready".
- Move `AUDIO_CHUNK_DURATION` / `AUDIO_SAMPLE_DURATION` into
  `self.share[]`.
- `PE_MicrophoneFile` (does not exist yet) to carve off exact sample
  chunk sizes.
- More precise timing in `PE_WhisperX`; FFT-based amplitude / silence
  detection; proper WhisperX VAD (Voice Activity Detection).

## Related concepts

- [Speech example index](ReadMe.md) — the eight PipelineDefinitions
  that wire these elements together
- [LLM example elements](../llm/elements.md) — the `p_llm` Pipeline
  these speech Pipelines feed
- [PipelineElement](../../concepts/pipeline_element.md) — the contract
  every class here implements
- [Pipeline](../../concepts/pipeline.md) — local and remote element
  deployment
- [audio_io](../../elements/media/audio_io.md) — the microphone /
  speaker elements the PipelineDefinitions expect (currently disabled)
- [Share](../../concepts/share.md) — `PE_COQUI_TTS`'s `speech` /
  `frame_id` variables
- [Parameters](../../concepts/parameters.md) — `audio_channels` and
  the literals destined to become parameters
- [Stream](../../concepts/stream.md) — frame identity and StreamEvent
  semantics
