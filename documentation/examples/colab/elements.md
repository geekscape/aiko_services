---
title: Google Colab example PipelineElements
description: The colab example element family — audio pass-through,
  speech-to-text (faster-whisper), text-to-speech (coqui-tts), YOLO
  detection-to-chat conversion, ChatServer publishing and the
  VideoReadColab DataSource
type: concept
audience: [developers, end-users]
status: draft
source:
  - src/aiko_services/examples/colab/elements.py
related: [pipeline_element, pipeline, actor, data_source_target,
  parameters, stream, colab_io, scheme_colab]
version: "0.6"
last_updated: 2026-07-06
---

# Google Colab example PipelineElements

## Overview

`elements.py` provides the [PipelineElements](../../concepts/pipeline_element.md)
used by the Google Colab example
[PipelineDefinitions](ReadMe.md): a browser-audio loopback, a local
speech-to-text / text-to-speech pair (faster-whisper and coqui-tts), a
YOLO-detections-to-text converter, an element that publishes messages
to a discovered chat server, and a DataSource for the browser web
camera. Together with [colab_io](colab_io.md) (the notebook glue) and
[scheme_colab](scheme_colab.md) (the `colab://` DataScheme) they form
the Google Colab integration example.

**Why you'd use it**: assemble a voice assistant on a Google Colab
GPU — browser microphone in, transcription published to a chat
channel, synthesised speech back to the browser speaker — from
off-the-shelf elements:

```
(SpeechToText Expression MQTTPublish TextToSpeech)
```

The package `__init__.py` exports `AudioPassThrough`,
`ConvertDetections`, `ChatServer`, `MQTTPublish` and `VideoReadColab`.
`SpeechToText` and `TextToSpeech` are in the module's `__all__` but are
*not* re-exported by the package — deploy them via the module path
`aiko_services.examples.colab.elements`, which keeps the heavy
faster-whisper / coqui-tts imports out of the package import.

## For application developers

### Command-line usage

From the source usage header:

```bash
aiko_pipeline create pipelines/colab_pipeline_1.json -ll debug_all

aiko_chat
# > :change_change yolo
```

`aiko_chat` is the Aiko Chat application (a separate Git repository)
that implements the `chat_server` Service which `MQTTPublish`
discovers; the `:change_change yolo` command in the comment switches
the chat channel (the command name in the comment may be stale —
verify against the Aiko Chat repository).

The audio elements are exercised by the three
`colab_audio_pipeline_*.json` PipelineDefinitions, driven from a
Google Colab notebook via [colab_io](colab_io.md) rather than from a
terminal — see the [package ReadMe](ReadMe.md) for the mapping.

### Public API

| Class | Protocol | Inputs -> Outputs | Parameters |
|-------|----------|-------------------|------------|
| `AudioPassThrough` | `audio_pass_through:0` | `audio`, `mime_type` -> same | (none) — logs length and MIME type at debug level |
| `ConvertDetections` | `convert_detections:0` | `overlay` -> `message` | (none) — joins `overlay["objects"][*]["name"]` into a comma-separated string |
| `MQTTPublish` | `mqtt_publish:0` | `message` -> declared outputs (forwarded from the swag via `all_outputs()`) | `chat_channel` (default `"yolo"`), `username` (default `<env_var>` = `$USER`), `service_filter` (`name`, `protocol` of the chat server) |
| `SpeechToText` | `speech_to_text:0` | `audio`, `mime_type` -> `audio`, `mime_type`, `text` | `stt_model` (default `"small"`), `device` (default `"cuda"`, falls back to `"cpu"`), `compute_type` (default `"int8_float16"`), `stt_sample_rate` (default 16000), `language`, `task` (default `"transcribe"`), `vad_filter` (default true) |
| `TextToSpeech` | `text_to_speech:0` | `text`, `mime_type` -> `audio`, `mime_type`, `text` (text cleared) | `tts_model` (default `"tts_models/en/ljspeech/tacotron2-DDC"`), `tts_gpu` (default true) |
| `VideoReadColab` | `colab:0` | `images` -> `images` | `data_sources` (must be `"(colab://)"`), `media_type` (optional conversion via `convert_images()`) |

`ChatServer` is not a PipelineElement: it is an abstract
[Actor](../../concepts/actor.md) Interface declaring one operation,
`send_message(username, recipients, message)`. It exists so
`MQTTPublish` can pass it to `aiko.do_discovery()` and obtain a remote
proxy for whatever Service matches the `service_filter` — by
convention the Aiko Chat server, protocol
`github.com/geekscape/aiko_services/protocol/chat_server:0`.

**`MQTTPublish` behaviour** (the name is aspirational — see roadmap):
on `start_stream()` it resolves its
[parameters](../../concepts/parameters.md) and starts
[discovery](../../concepts/discovery.md) for the chat server; on each
frame with a non-empty `message` it prefixes `username:` and calls
`chat_server.send_message()` on the discovered proxy. Direct MQTT
topic publishing is present in the source but commented out.

**`SpeechToText` / `TextToSpeech`** load their models lazily in
`start_stream()` (with a defensive re-load in `process_frame()` if the
model is missing), decode / encode audio entirely in memory through
`ffmpeg` subprocess pipes, and preserve the browser's audio format:
`TextToSpeech` maps the incoming `mime_type` to a strict
container / codec pair (`webm`/`opus`, `ogg`/`opus`, `mp4`/`aac`,
`wav`/`pcm_s16le`) and returns `StreamEvent.ERROR` for anything else.
An empty `text` synthesises one second of silence.

**`VideoReadColab`** is a
[DataSource](../../concepts/data_source_target.md) whose
`data_sources` URL selects the [`colab://`](scheme_colab.md)
DataScheme; its `process_frame()` optionally converts the images'
`media_type`. It only supports Streams that carry a `data_sources`
parameter.

## For framework developers (internals)

### Design

Two independent data paths share this module:

```
Audio path (Google Colab notebook, push-style frames)
  browser mic --> [colab_io] --> SpeechToText --> Expression
      --> MQTTPublish --> TextToSpeech --> [colab_io] --> speaker
                     |
                     v  send_message()
              chat_server Actor (Aiko Chat, discovered)

Video path
  browser camera --> VideoReadColab (colab:// DataScheme)
      --> YoloDetector --> ConvertDetections --> MQTTPublish
                     \--> ImageOverlay --> browser canvas
```

- The module-level helpers `_ffmpeg_decode_to_pcm_f32_mono()`,
  `_wav_bytes_from_pcm_mono()`,
  `_parse_audio_mime_strict()` (returning the frozen dataclass
  `AudioFormat`) and `_ffmpeg_transcode_wav_bytes_to_format_strict()`
  deliberately avoid temporary files — audio moves through `ffmpeg`
  via stdin / stdout pipes (contrast `encode_silence()` in
  [colab_io](colab_io.md), which still uses temporary files).
- `MQTTPublish` uses `all_outputs(self, stream)` (from the
  [utility elements](../../elements/utilities/elements.md)) so the
  same class can be a pass-through (declared outputs
  `audio` / `mime_type` / `text` in `colab_audio_pipeline_1.json`) or
  a sink (no outputs in `colab_audio_pipeline_2.json`).
- GPU use degrades gracefully: both model elements probe
  `torch.cuda.is_available()` and fall back to CPU (with
  `compute_type="int8"` for faster-whisper).

### Implementation notes

- `ConvertDetections.process_frame()` uses a nested-quote f-string,
  `f"{delimiter}{object["name"]}"` (`elements.py:53`) — this is valid
  only on Python 3.12+ (PEP 701) and is a syntax error on older
  interpreters; it also shadows the `object` builtin.
- `MQTTPublish.start_stream()` keeps the `aiko.do_discovery()` return
  values only in local variables; the discovery handlers keep working,
  but there is no handle to cancel discovery on `stop_stream()`.
- The lazy-load fallback in `SpeechToText.process_frame()` calls
  `stream.get("stream_id", ...)`, treating the Stream as a dict.
- `TextToSpeech` contains leftover LLM-citation artifacts
  (`:contentReference[oaicite:N]{index=N}`) in its docstring and
  comments (`elements.py:309`, `:321`, `:328`) and a commented-out
  `/tmp/out.webm` debugging dump (`elements.py:384`).

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `AudioPassThrough` | Forward audio bytes and MIME type unchanged; log per frame | [PipelineElement](../../concepts/pipeline_element.md) |
| `ConvertDetections` | Flatten YOLO overlay objects to a comma-separated name string | [PipelineElement](../../concepts/pipeline_element.md); YoloDetector (`aiko_services.examples.yolo.yolo`) upstream |
| `ChatServer` (Interface) | Declare the contract: `send_message(username, recipients, message)` | [Actor](../../concepts/actor.md); implemented by the Aiko Chat server (separate repository) |
| `MQTTPublish` | Discover the chat server; publish `username:message` per frame; forward declared outputs | `ChatServer` proxy; [discovery](../../concepts/discovery.md) (`aiko.do_discovery`, `aiko.ServiceFilter`); [Share](../../concepts/share.md) (`chat_channel`, `username`); `all_outputs()` ([utility elements](../../elements/utilities/elements.md)) |
| `SpeechToText` | Decode browser audio to 16 kHz mono PCM; transcribe with faster-whisper; emit `text` | `_ffmpeg_decode_to_pcm_f32_mono()`; `faster_whisper.WhisperModel`; torch (GPU probe) |
| `TextToSpeech` | Synthesise `text` with coqui-tts; transcode to the caller's strict container / codec | `_wav_bytes_from_pcm_mono()`; `AudioFormat` / `_parse_audio_mime_strict()`; `_ffmpeg_transcode_wav_bytes_to_format_strict()`; `TTS.api.TTS` |
| `VideoReadColab` | DataSource for the browser web camera; optional image `media_type` conversion | [DataSource](../../concepts/data_source_target.md); [DataSchemeColab](scheme_colab.md); `convert_images()` ([image_io](../../elements/media/image_io.md)) |

## Current limitations and roadmap

The source To Do list is empty ("None, yet !"), but several gaps are
visible in the code:

- **`MQTTPublish` does not publish to MQTT** — the
  `aiko.process.message.publish(...)` path is commented out
  (`elements.py:112-113`); today it only calls the discovered
  ChatServer Actor. Messages are silently dropped when no chat server
  has been discovered.
- `ConvertDetections` requires Python 3.12+ (see Implementation
  notes), narrower than the Python versions Aiko Services otherwise
  supports.
- `ConvertDetections` ignores `object["confidence"]` (noted in a
  trailing comment) — no confidence threshold or display.
- `SpeechToText` / `TextToSpeech` depend on packages listed in the
  package `requirements.txt` (faster-whisper, coqui-tts, torch) that
  are not Aiko Services dependencies; import failures surface as
  `RuntimeError` at `start_stream()`.
- No `stop_stream()` cleanup: models stay resident and discovery is
  never cancelled.

## Related concepts

- [PipelineElement](../../concepts/pipeline_element.md) — the contract
  all six elements implement
- [Pipeline](../../concepts/pipeline.md) — the graphs in
  `pipelines/*.json` that compose them
- [Actor](../../concepts/actor.md) — `ChatServer` is a remote Actor
  Interface
- [Discovery](../../concepts/discovery.md) — how `MQTTPublish` finds
  the chat server
- [DataSource / DataTarget](../../concepts/data_source_target.md) —
  `VideoReadColab` is a DataSource
- [colab_io](colab_io.md) — the notebook glue that feeds the audio
  elements
- [scheme_colab](scheme_colab.md) — the `colab://` DataScheme behind
  `VideoReadColab`
- [Utility elements](../../elements/utilities/elements.md) —
  `Expression` and `all_outputs()` used alongside these elements
