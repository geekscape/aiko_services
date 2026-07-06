---
title: Google Colab notebook glue (colab_io)
description: Notebook-side bridge between browser JavaScript (web camera
  and microphone) and an Aiko Services Pipeline running in the Google
  Colab kernel — callbacks, frame injection and the interactive widget
type: concept
audience: [developers, end-users]
status: draft
source:
  - src/aiko_services/examples/colab/colab_io.py
related: [pipeline, pipeline_element, stream, elements, scheme_colab]
version: "0.6"
last_updated: 2026-07-06
---

# Google Colab notebook glue (colab_io)

## Overview

`colab_io.py` is the notebook-side glue that connects a web browser —
camera, microphone and speaker, driven by JavaScript — to an
Aiko Services [Pipeline](../../concepts/pipeline.md) running inside the
Google Colab kernel. The browser cannot talk to the Pipeline directly:
Google Colab only allows JavaScript to call registered Python kernel
callbacks. This module registers those callbacks
(`notebook.do_print`, `notebook.handle_audio_frame`,
`notebook.handle_image_frame`), injects the JavaScript user interface
widget (`do_start_stream()`), and converts browser media payloads into
Pipeline Frames via `pipeline.create_frame()`.

It is designed to be imported in a notebook cell alongside the
[colab example PipelineElements](elements.md); the Pipeline itself is
defined by the `pipelines/*.json` PipelineDefinitions indexed in the
[package ReadMe](ReadMe.md).

**Why you'd use it**: run a speech Pipeline on a free Google Colab GPU
and talk to it from your laptop's browser:

```python
# Notebook cell (after creating the Pipeline and a response queue)
import aiko_services.examples.colab.colab_io as colab_io
colab_io.common.pipeline = pipeline           # the Pipeline instance
colab_io.common.queue_response = my_queue     # Pipeline output queue
colab_io.do_start_stream()                    # render camera+audio UI
```

The module degrades gracefully outside Google Colab: when
`google.colab` cannot be imported, the callbacks are simply not
registered, so the module can be imported (for example by tests) on any
host.

## For application developers

### Command-line usage

This module is notebook-hosted — there is no console script. The usage
comment at the top of the source reads:

```bash
aiko_pipeline create pipelines/webcam_pipeline_0.json -s 1 -ll debug
```

Note: `webcam_pipeline_0.json` is *not* part of this package (it lives
in `src/aiko_services/elements/media/pipelines/`) — the comment appears
to be stale. In practice the Pipeline is created inside the notebook
(or with `aiko_pipeline create` against one of the
[colab PipelineDefinitions](ReadMe.md)), then this module is imported
and wired up as shown above.

### Public API

```python
__all__ = [
    "ColabCommon", "common",
    "do_create_audio_frame", "do_create_image_frame", "do_print",
    "do_start_stream", "encode_silence",
    "handle_audio_frame", "handle_image_frame"
]
```

**`ColabCommon`** and the module singleton **`common`** hold the shared
notebook state: `pipeline` (the Pipeline instance), `queue_response`
(a queue the notebook must fill with Pipeline output), `stream_id`
(fixed `"1"`) and a monotonically increasing `frame_id`. The notebook
**must** assign `common.pipeline` and `common.queue_response` before
any audio frame is processed — both default to `None`.

| Function | Role |
|----------|------|
| `do_start_stream()` | Display the JavaScript widget: side-by-side input / output canvases, audio record / send / cancel buttons, volume and frame-interval sliders, pause and stop buttons |
| `handle_audio_frame(payload)` | Kernel callback (`notebook.handle_audio_frame`): base64-decode browser audio, run it through the Pipeline, return base64 audio + MIME type + `<stream_id:frame_id>` as JSON; errors are returned as `{"error": ...}` |
| `handle_image_frame(data_url)` | Kernel callback (`notebook.handle_image_frame`): decode a JPEG data URL to PIL, process, re-encode to a JPEG data URL |
| `do_create_audio_frame(audio, mime_type)` | Build `stream` / `frame_data` dicts, call `common.pipeline.create_frame()`, then **block** on `common.queue_response.get()` for the Pipeline result |
| `do_create_image_frame(image_pil)` | **Stub**: returns `("Loopback", image)` unchanged — image frames do not yet reach the Pipeline (see roadmap) |
| `encode_silence(mime_type, ...)` | Encode one second of silence (48 kHz mono float32 by default) via an `ffmpeg` subprocess, honouring the requested container / codec (webm / ogg + opus, or wav) — used when an audio frame arrives empty |
| `do_print(message)` | Kernel callback (`notebook.do_print`): JavaScript-side logging into the notebook output |

The audio round-trip is the genuine multi-party exchange:

```
Browser (JavaScript)          Colab kernel (Python)      Pipeline
     |                              |                       |
     | MediaRecorder stop           |                       |
     |----------------------------->|                       |
     |  invokeFunction(             |                       |
     |   notebook.handle_audio_frame| create_frame(stream,  |
     |   {mime, b64})               |   {audio, mime_type}) |
     |                              |---------------------->|
     |                              |                       | process
     |                              |  queue_response.get() | frames
     |                              |<----------------------|
     |  JSON {mime, b64,            |  (stream, frame_data) |
     |   stream_frame_ids}          |                       |
     |<-----------------------------|                       |
     | play audio via <audio>       |                       |
```

The notebook is responsible for the return path: a final
PipelineElement (or a Pipeline response handler defined in the
notebook) must `put()` `(stream, frame_data)` tuples onto
`common.queue_response` — no committed element in this package does
so.

## For framework developers (internals)

### Design

The module is three layers in one file:

```
+---------------------------------------------------------------+
| Browser iframe (JavaScript emitted by do_start_stream())      |
|   camera -> canvas -> JPEG data URL     mic -> MediaRecorder  |
+------------------------|---------------------------|----------+
                         v invokeFunction             v
+---------------------------------------------------------------+
| Kernel callbacks: handle_image_frame   handle_audio_frame     |
|                        |                        |             |
|            do_create_image_frame     do_create_audio_frame    |
|              (loopback stub)          (create_frame + queue)  |
+------------------------|---------------------------|----------+
                         x (not connected)            v
+---------------------------------------------------------------+
| Aiko Services Pipeline (PipelineDefinition from pipelines/)   |
+---------------------------------------------------------------+
```

Key points:

- **Registration is conditional**: each `output.register_callback()`
  call is guarded by `if output:`, so importing the module outside
  Google Colab is safe.
- **One stream, kernel-driven frames**: unlike a
  [DataScheme](../../concepts/scheme.md)-based DataSource, frames are
  created *push-style* by the kernel callback each time the browser
  sends media; `common.frame_id` is incremented per call.
- **Synchronous by construction**: `do_create_audio_frame()` blocks
  the kernel callback until the Pipeline responds, which in turn
  blocks the browser's `await invokeFunction(...)`. Throughput is
  therefore bounded by end-to-end Pipeline latency, and the JavaScript
  frame-interval slider (250 ms – 2000 ms, default 500 ms) exists to
  keep the request rate below it.

### Implementation notes

- Both `handle_audio_frame()` and `handle_image_frame()` contain an
  `if False:` toggle to short-circuit the Pipeline and echo the input
  (audio) or vertically flip the image — flip it to `True` to test the
  browser / kernel path in isolation.
- `encode_silence()` writes two `NamedTemporaryFile`s with
  `delete=False` and never removes them; each silent frame leaks two
  files in the kernel's temporary directory.
- `common.queue_response.get()` has no timeout: if the Pipeline drops
  the frame (or the notebook never wires the response queue), the
  kernel callback — and the browser widget — hang indefinitely.
- The JavaScript widget selects the first `MediaRecorder` MIME type the
  browser supports from `audio/webm;codecs=opus`, `audio/webm`,
  `audio/ogg;codecs=opus`, `audio/ogg`; the resulting MIME type is
  carried end-to-end so [TextToSpeech](elements.md) can reply in the
  same container / codec.

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `ColabCommon` | Hold shared notebook state: Pipeline reference, response queue, stream and frame identifiers | [Pipeline](../../concepts/pipeline.md); notebook code that assigns `pipeline` / `queue_response` |
| *(module functions)* | Register kernel callbacks; inject the JavaScript widget; convert browser payloads to Frames and back; encode silence via `ffmpeg` | `google.colab.output`; `IPython.display`; [Pipeline](../../concepts/pipeline.md) `create_frame()`; [colab elements](elements.md) |

## Current limitations and roadmap

From the source To Do list — **planned**, not implemented:

- Cache the `encode_silence()` result (saves about 40 ms per silent
  frame).
- Consider an `mqtt://` DataScheme that creates its own MQTT
  connection.
- A plain web server / browser combination that works *outside*
  Google Colab.

Additional implemented-versus-planned gaps observed in the source:

- **Image frames bypass the Pipeline**: `do_create_image_frame()` is a
  loopback stub, so the video half of the widget displays the camera
  input unprocessed. Only the audio path is wired through
  `create_frame()`. (The [scheme_colab](scheme_colab.md) DataScheme is
  a parallel, also-incomplete attempt at the image path.)
- The response-queue producer is left to the notebook; there is no
  committed PipelineElement that fills `common.queue_response`.
- The stale `webcam_pipeline_0.json` usage comment (see Command-line
  usage above).

## Related concepts

- [Pipeline](../../concepts/pipeline.md) — `create_frame()` is the
  injection point for browser media
- [Stream](../../concepts/stream.md) — stream / frame identifier
  semantics echoed back to the browser
- [colab elements](elements.md) — the PipelineElements these frames
  flow through (AudioPassThrough, SpeechToText, TextToSpeech, ...)
- [scheme_colab](scheme_colab.md) — the DataScheme approach to the
  same browser camera, pull-style rather than push-style
- [DataSource / DataTarget](../../concepts/data_source_target.md) —
  the design this module sidesteps by calling `create_frame()`
  directly
