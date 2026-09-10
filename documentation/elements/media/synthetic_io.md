---
title: Synthetic video source
description: SyntheticVideoRead — a DataSource PipelineElement that
  produces synthesized numbered frames through the synth DataScheme, so a
  video Pipeline runs without a camera
type: concept
audience: [developers, end-users]
status: work-in-progress
ste: adapted
source:
  - src/aiko_services/elements/media/synthetic_io.py
  - src/aiko_services/elements/media/pipelines/synthetic_pipeline_0.json
  - src/aiko_services/elements/media/pipelines/synthetic_pipeline_1.json
related: [pipeline_element, data_source_target, scheme, stream, parameters,
  share, scheme_synth, webcam_io, video_io, image_io, elements]
version: "0.8-dev"
last_updated: 2026-09-10
---

# Synthetic video source

## Overview

**`SyntheticVideoRead`** is a camera-less
[DataSource](../../concepts/data_source_target.md)
[PipelineElement](../../concepts/pipeline_element.md). It emits the
standard `images: [image]` frame data. Thus everything downstream of a
webcam ([webcam_io](webcam_io.md)), a video file
([video_io](video_io.md)) or an image source ([image_io](image_io.md))
works identically on synthesized frames. The
[Synthetic DataScheme](scheme_synth.md) renders the frames: by default
the frame id and a timestamp as white text on black, at 1920x1080 and
15 frames per second.

The class name follows the `Synthetic<Type>Read` /
`Synthetic<Type>Write` pattern, where the type is Video, Image, Text or
Audio. Only `SyntheticVideoRead` exists now.

This element is unrelated to the `Mock` PipelineElement in
[elements](elements.md), which is a structural stand-in in the graph.

**Why to use it**: develop, demonstrate or regression test a video
Pipeline with no hardware. The number in each frame is the frame id, so
a dropped or reordered frame is visible:

```bash
cd src/aiko_services/elements/media

aiko_pipeline create pipelines/synthetic_pipeline_0.json -s 1  # view live
```

## For application developers

### Command-line usage

All commands run from `src/aiko_services/elements/media`. From the
`synthetic_io.py` usage header:

```bash
# Synthetic frames --> CaptureLimit --> resize --> display (10 s, or "x")
aiko_pipeline create pipelines/synthetic_pipeline_0.json -s 1

# Full size window, 30 seconds
aiko_pipeline create pipelines/synthetic_pipeline_0.json -s 1  \
  -p resolution 1920x1080 -p CaptureLimit.duration 30

# Smaller frames, frame id only, orange text
aiko_pipeline create pipelines/synthetic_pipeline_0.json -s 1  \
  -p SyntheticVideoRead.data_sources  \
     "(synth://video/plain?width=640&height=360&text=frame_id&color=orange)"

# Exactly 45 frames
aiko_pipeline create pipelines/synthetic_pipeline_0.json -s 1  \
  -p CaptureLimit.frame_count 45

# Synthetic frames --> CaptureLimit --> record to data_out/synthetic_0.mp4
aiko_pipeline create pipelines/synthetic_pipeline_1.json -s 1

# 30 frames per second: keep "rate" and "frame_rate" equal for playback
aiko_pipeline create pipelines/synthetic_pipeline_1.json -s 1  \
  -p rate 30 -p frame_rate 30
```

The [CaptureLimit](../control/elements.md) element bounds each run:
`duration` in seconds (or `10m`), `frame_count`, `run_time` or a
`condition`. The `VideoShow` window also ends the run when a person
presses `x`.

### Public API

| Class | Kind | Inputs → Outputs | Parameters |
|-------|------|------------------|------------|
| `SyntheticVideoRead` | DataSource | `images: [image]` → `images: [image]` | `data_sources` (`(synth://)` or `(synth://video/plain?width=W&height=H&text=...&color=...)`), `rate` (default 15.0 frames per second, 0 = unpaced), `media_type` (`numpy` \| `pil`) |

Service protocol: `synthetic_video_read:0`.

Live shared state: none yet. A `frame_id` progress item, as
`VideoReadWebcam` publishes, is on the roadmap.

**Stream lifecycle behavior:**

- `start_stream()` is the `DataSource` base method. It selects the
  [Synthetic DataScheme](scheme_synth.md) from the first `data_sources`
  URL, and the scheme starts `create_frames()` at `rate` frames per
  second. A missing `data_sources`, an unknown scheme or a bad URL
  returns `StreamEvent.ERROR` with a `diagnostic`.
- `process_frame()` applies the optional `media_type` conversion and
  passes the images through.
- `stop_stream()` calls the scheme's `destroy_sources()`, which stops
  the frame generator thread.

Note the PipelineDefinition declares `"input": [{"name": "images", ...}]`.
The frame generator of the scheme feeds the element's own
`process_frame()`, as with `VideoReadFile`.

## For framework developers (internals)

### Design

```
   SyntheticVideoRead (thin DataSource)
   ┌──────────────────────────────────────────────┐
   │ start_stream() ── DataScheme.LOOKUP["synth"] │
   │                        │                     │
   │                        ▼  per Stream         │
   │              DataSchemeSynthetic             │
   │              create_frames(rate) ── thread ──┼──► {"images": [image]}
   │                                              │         │
   │ process_frame(images) ◄──────────────────────┼─────────┘
   │   optional media_type conversion             │
   └──────────────────────────────────────────────┘
```

- **All state is in the scheme.** The element holds no per-Stream state.
  The frame size, the text options and the `stopped` flag live on the
  scheme instance, one per [Stream](../../concepts/stream.md).
- **Same shape as `VideoReadRTSP`.** A thin element plus a separate
  scheme module, the pattern of `rtsp_io.py` and `scheme_rtsp.py`.

### Implementation notes

- `synthetic_io.py` imports `scheme_synth` explicitly, so the `synth`
  registration does not depend on the import order in the package
  `__init__.py`.
- `convert_images` is imported from `image_io` directly, for the same
  reason.
- The frame size is not an element parameter. See the
  [Synthetic DataScheme](scheme_synth.md) for why `resolution` must stay
  free for `ImageResize` and `VideoWriteFile`.

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `SyntheticVideoRead` | Own the Stream lifecycle as a DataSource; optional `media_type` conversion of the generated images | [DataSource](../../concepts/data_source_target.md) (base), [Synthetic DataScheme](scheme_synth.md) (frame generation), [PipelineElement](../../concepts/pipeline_element.md), [Parameters](../../concepts/parameters.md) |

## Current limitations and roadmap

From the source To Do list:

- Publish `frame_id` progress in `self.share`, as `VideoReadWebcam` does
- `SyntheticVideoWrite`: a verifying DataTarget, see the
  [Synthetic DataScheme](scheme_synth.md) roadmap
- `SyntheticImageRead`, `SyntheticTextRead` and `SyntheticAudioRead`

## Related concepts

- [PipelineElement](../../concepts/pipeline_element.md) — the element
  contract and `create_frames()` pacing
- [DataSource / DataTarget](../../concepts/data_source_target.md) — the
  base class and the `data_sources` parameter
- [DataScheme](../../concepts/scheme.md) — how the URL selects the scheme
- [Synthetic DataScheme](scheme_synth.md) — the URL grammar and the
  renderer
- [Control elements](../control/elements.md) — `CaptureLimit`, used in
  both synthetic pipelines
- [video_io](video_io.md) — `VideoShow` and `VideoWriteFile`
- [image_io](image_io.md) — `ImageResize`
- [webcam_io](webcam_io.md) — the live camera equivalent
