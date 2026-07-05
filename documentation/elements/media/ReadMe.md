---
title: Media PipelineElements index
description: Index of the media PipelineElement concept documents — text,
  image, video, webcam and audio element families, the file / tty / zmq
  DataSchemes — and the committed example PipelineDefinitions
type: index
audience: [developers, end-users]
status: work-in-progress
source:
  - src/aiko_services/elements/media
related: [pipeline_element, data_source_target, scheme, pipeline]
version: "0.6"
last_updated: 2026-07-06
---

# Media PipelineElements index

One concept document per Python module in
`src/aiko_services/elements/media/` — the standard media
[PipelineElement](../../concepts/pipeline_element.md) families built on
the [DataSource / DataTarget](../../concepts/data_source_target.md) and
[DataScheme](../../concepts/scheme.md) design.

Navigation: [elements index](../ReadMe.md) ·
[concepts guide](../../concepts/ReadMe.md)

## Module documents

| Document | Summary |
|----------|---------|
| [audio_io](audio_io.md) | Audio elements — working `AudioOutput`, an `AudioReadFile` scaffold, and a disabled legacy microphone / FFT / speaker suite |
| [elements](elements.md) | `Mock` and `NoOp` — minimal placeholder elements for scaffolding and wiring tests |
| [image_io](image_io.md) | Image sources, transforms (convert / resize / crop / overlay) and targets — files or ZeroMQ, PIL or NumPy |
| [images_to_video](images_to_video.md) | Legacy Pipeline_2020 script for images → video; superseded by `images_to_video_pipeline.json` |
| [scheme_file](scheme_file.md) | `file:` DataScheme — files, directories and `{}` glob/format templates; the default scheme |
| [scheme_tty](scheme_tty.md) | `tty://` DataScheme — line-oriented interactive terminal input/output |
| [scheme_zmq](scheme_zmq.md) | `zmq://` DataScheme — out-of-band record transport over ZeroMQ PUSH/PULL |
| [text_io](text_io.md) | Text sources, transforms and targets — files, terminal REPL or ZeroMQ; the exemplar element family |
| [video_example](video_example.md) | Legacy Pipeline_2020 branching-video demonstration with a StateMachine; dormant |
| [video_io](video_io.md) | Video file decode / sample / display / encode elements, plus `open_video_capture()` |
| [webcam_io](webcam_io.md) | `VideoReadWebcam` — live camera DataSource with hot-swappable device and live share controls |

## Example PipelineDefinitions

The twenty git-committed PipelineDefinitions under
`src/aiko_services/elements/media/pipelines/` — each module document's
Command-line usage section shows `aiko_pipeline create` invocations for
the pipelines it covers.

| PipelineDefinition | Module document(s) | Purpose |
|--------------------|--------------------|---------|
| `image_pipeline_0.json` | [image_io](image_io.md) | Read JPEGs (glob template) → resize → write JPEGs |
| `image_pipeline_1.json` | [image_io](image_io.md), [video_io](video_io.md) | Read JPEGs → display in a `VideoShow` window |
| `image_zmq_pipeline_0.json` | [image_io](image_io.md), [scheme_zmq](scheme_zmq.md), [video_io](video_io.md) | ZeroMQ server: receive image records → resize → display |
| `image_zmq_pipeline_1.json` | [image_io](image_io.md), [scheme_zmq](scheme_zmq.md) | ZeroMQ client: read JPEGs → resize → send image records |
| `images_to_video_pipeline.json` | [image_io](image_io.md), [video_io](video_io.md), [images_to_video](images_to_video.md) | Assemble JPEG frames into an MP4 (MP4V, 30 fps) |
| `text_pipeline_0.json` | [text_io](text_io.md), [scheme_file](scheme_file.md) | Read text files → case transform → write text files |
| `text_pipeline_1.json` | [text_io](text_io.md) | Drop-frame test: `TextSample` keeps every 2nd frame (local) |
| `text_pipeline_2.json` | [text_io](text_io.md) | Drop-frame test with `TextSample` deployed **remote** (pairs with `text_pipeline_3.json`) |
| `text_pipeline_3.json` | [text_io](text_io.md) | The remote `TextSample` Pipeline serving `text_pipeline_2.json` |
| `text_tty_pipeline_0.json` | [text_io](text_io.md), [scheme_tty](scheme_tty.md) | Interactive terminal REPL: type lines → transform → print with prompt/history |
| `text_zmq_pipeline_0.json` | [text_io](text_io.md), [scheme_zmq](scheme_zmq.md) | ZeroMQ server: receive text records → write to file |
| `text_zmq_pipeline_1.json` | [text_io](text_io.md), [scheme_zmq](scheme_zmq.md) | ZeroMQ client: read text files → send text records |
| `video_pipeline_0.json` | [video_io](video_io.md), [image_io](image_io.md) | Decode video → resize → display → re-encode (+ optional Metrics) |
| `video_pipeline_1.json` | [video_io](video_io.md) | Drop-frame test: `VideoSample` keeps every 10th frame → display |
| `video_to_images_pipeline.json` | [video_io](video_io.md), [image_io](image_io.md) | Explode a video into numbered JPEG frames (rate 0.0 = flat out) |
| `webcam_pipeline_0.json` | [webcam_io](webcam_io.md), [image_io](image_io.md), [video_io](video_io.md) | Camera → resize → display → record MP4 |
| `webcam_pipeline_1.json` | [webcam_io](webcam_io.md), [image_io](image_io.md), [video_io](video_io.md) | Camera → resize → display (press `x` to exit) |
| `webcam_pipeline_2.json` | [webcam_io](webcam_io.md), [image_io](image_io.md) | Camera → resize → write JPEG files |
| `webcam_pipeline_3.json` | [webcam_io](webcam_io.md), [image_io](image_io.md), [video_io](video_io.md) | Camera → resize → display → rolling timestamped MP4 files (`VideoWriteFiles`) |
| `webcam_zmq_pipeline_0.json` | [webcam_io](webcam_io.md), [image_io](image_io.md), [scheme_zmq](scheme_zmq.md) | Camera → resize → send image records over ZeroMQ |

## Suggested reading order

1. [text_io](text_io.md) with [scheme_file](scheme_file.md) — the
   complete, dependency-free exemplar of the element-family design
2. [scheme_tty](scheme_tty.md) and [scheme_zmq](scheme_zmq.md) — how a
   URL swaps the transport
3. [image_io](image_io.md) → [video_io](video_io.md) →
   [webcam_io](webcam_io.md) — the media families proper
4. [elements](elements.md), [audio_io](audio_io.md),
   [images_to_video](images_to_video.md),
   [video_example](video_example.md) — placeholders, work-in-progress
   and legacy
