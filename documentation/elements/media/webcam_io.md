---
title: Webcam I/O elements
description: VideoReadWebcam — a live-camera DataSource PipelineElement
  with hot-swappable camera path, color/flip controls and paced frames
type: concept
audience: [developers, end-users]
status: work-in-progress
ste: adapted
source:
  - src/aiko_services/elements/media/webcam_io.py
  - src/aiko_services/elements/media/pipelines/webcam_pipeline_0.json
  - src/aiko_services/elements/media/pipelines/webcam_pipeline_1.json
  - src/aiko_services/elements/media/pipelines/webcam_pipeline_2.json
  - src/aiko_services/elements/media/pipelines/webcam_pipeline_3.json
  - src/aiko_services/elements/media/pipelines/webcam_zmq_pipeline_0.json
related: [pipeline_element, data_source_target, scheme, stream, parameters,
  share, video_io, image_io, scheme_zmq]
version: "0.6"
last_updated: 2026-08-01
---

# Webcam I/O elements

## Overview

**`VideoReadWebcam`** is the live-camera
[DataSource](../../concepts/data_source_target.md)
[PipelineElement](../../concepts/pipeline_element.md). It opens a camera
with `open_video_capture()` (from [video_io](video_io.md)). It reads
frames at a configurable rate, and emits the standard `images: [image]`
frame data. Thus everything downstream of a video file
([video_io](video_io.md)) or an image source ([image_io](image_io.md))
works identically on a live camera.

The file-based sources use a `data_sources` URL. But a `path`
*parameter* selects this camera. That parameter is a device index such
as `0`, or a Linux device path such as `/dev/video2`. A `webcam://`
[DataScheme](../../concepts/scheme.md) is planned, but not yet
implemented. The camera path, color mode and flip mode are live
[shared state](../../concepts/share.md): update `path` from the
Dashboard or an `ECConsumer` and the element hot-swaps cameras
mid-Stream.

**Why to use it**: point a Pipeline at a camera and view, record or
stream it across the network with no code:

```bash
cd src/aiko_services/elements/media

aiko_pipeline create pipelines/webcam_pipeline_1.json -s 1  # view live
```

## For application developers

### Command-line usage

All commands run from `src/aiko_services/elements/media`. From the
`webcam_io.py` usage header:

```bash
# Camera --> resize --> display --> record to MP4
aiko_pipeline create pipelines/webcam_pipeline_0.json -s 1 -ll debug

# Select a different camera device (Linux)
aiko_pipeline create pipelines/webcam_pipeline_0.json -s 1  \
  -p VideoReadWebcam.path /dev/video2

# Camera --> resize --> display (press "x" in the window to exit)
aiko_pipeline create pipelines/webcam_pipeline_1.json -s 1
```

Other committed webcam pipelines:

```bash
# Camera --> resize --> JPEG files
aiko_pipeline create pipelines/webcam_pipeline_2.json -s 1

# Camera --> resize --> display --> rolling timestamped MP4 files
aiko_pipeline create pipelines/webcam_pipeline_3.json -s 1
```

Stream a camera between hosts over ZeroMQ — start the receiver
(`image_zmq_pipeline_0.json`, see [image_io](image_io.md)) first:

```bash
aiko_pipeline create pipelines/image_zmq_pipeline_0.json  -s 1 -sr -gt 10
aiko_pipeline create pipelines/image_zmq_pipeline_0.json  -s 1 -sr  \
           -p ImageReadZMQ.data_sources zmq://0.0.0.0:6502

aiko_pipeline create pipelines/webcam_zmq_pipeline_0.json -s 1 -sr \
           -p VideoReadWebcam.rate 2.0 \
           -p ImageWriteZMQ.data_targets zmq://192.168.0.1:6502
```

Installation note from the source: Ultralytics' `av` package clashes
with `cv2.imshow()` — `pip uninstall av` (or reinstall with
`pip install av --no-binary av`).

### Public API

| Class | Kind | Inputs → Outputs | Parameters |
|-------|------|------------------|------------|
| `VideoReadWebcam` | DataSource | `images: [image]` → `images: [image]` | `path` (default `0`; device index or pathname), `rate` (default 10.0 frames/second), `media_type` (`numpy` \| `pil`) |

Service protocol: `webcam:0`.

Live shared state (observable and updatable through the Aiko Services
Dashboard / `ECProducer` — see [Share](../../concepts/share.md)):

| Share item | Default | Meaning |
|------------|---------|---------|
| `path` | `0` | Camera device; updating it hot-swaps the camera (string digits are coerced to `int`) |
| `color` | `true` | `true`: RGB images; `false`: grayscale |
| `flip` | `"none"` | `"horizontal"`, `"vertical"` or `"both"` mirror the image |
| `frame_id` | `-1` | Progress indicator, republished every 10th frame |

**Stream lifecycle behavior:**

- `start_stream()` reads `path` and `rate` with
  `self_share_priority=False` (definition/stream parameters win over
  live share values at start-up), opens the camera and starts
  `create_frames()` at `rate` Hz. It does **not** call the DataSource
  base `start_stream()` — no `data_sources` URL is involved (yet).
- `frame_generator()` reads one camera frame, converts BGR→RGB (or
  grayscale), applies `flip`, and returns
  `{"images": [image]}`. When the camera is closed, or when a read
  fails, it returns `StreamEvent.OKAY` with `None` frame data, and emits
  no frame. It does not stop the Stream. Thus the Stream survives a
  camera
  swap.
- `process_frame()` sets `stream.variables["timestamps"]` (hard-coded
  25 fps clock) and applies optional `media_type` conversion.
- `stop_stream()` closes the camera.

Note the PipelineDefinition still declares
`"input": [{"name": "images", ...}]` — the element's generator feeds
its own `process_frame()`, as with `VideoReadFile`.

## For framework developers (internals)

### Design

```
        VideoReadWebcam (one camera per element instance)
        ┌───────────────────────────────────────────────┐
 share: │ path ── _ec_producer_change_handler ─┐        │
        │ color, flip, frame_id                │        │
        │                                      ▼        │
 self:  │ video_capture ◄── _open_camera / _close_camera│
        │ path_current, stream_started                  │
        └──────────────┬────────────────────────────────┘
                       │ frame_generator (rate Hz)
                       ▼
              {"images": [image_rgb]}
```

- **Camera state is per-element, not per-Stream.** `video_capture`,
  `path_current` and `stream_started` live on `self` — one physical
  camera per element instance, shared by whatever Streams run. This is
  a deliberate departure from the per-Stream state rule of the other
  DataSources. `stream_started` counts Streams so `_open_camera()`
  only acts while at least one Stream is active.
- **Hot-swap through shared state.** `_ec_producer_change_handler()`
  watches `path` (and `color`). A changed `path` closes the current
  camera and opens the new one without touching the Stream — frames
  simply pause while no camera is open.
- **Parameter-selected device.** Until the planned `webcam://` scheme
  exists, the element bypasses the
  [DataScheme](../../concepts/scheme.md) machinery entirely.

### Implementation notes

- On a failed read, `frame_generator()` returns `(OKAY, None)`. This
  relies on the frame-creation loop, which treats `None` frame data as
  "no frame". A commented-out `StreamEvent.STOP` (`"Camera stopped"`)
  is marked "TODO: Test this".
- `stop_stream()` calls `_close_camera()` unconditionally — with
  `self.video_capture` already `None` (camera never opened or already
  swapped away) `_close_camera()` raises `AttributeError` on
  `.release()`. It also does not terminate the frame-generator thread
  (the `create_frames_terminate()` call is commented out).
- `frame_id` is published to shared state only every 10th frame to
  limit MQTT traffic.

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `VideoReadWebcam` | Open/close/hot-swap the camera; generate paced RGB/grayscale image frames with flip; expose `path`/`color`/`flip`/`frame_id` as live shared state; optional `media_type` conversion | [DataSource](../../concepts/data_source_target.md) (base, largely bypassed), [PipelineElement](../../concepts/pipeline_element.md) (`create_frames()`), `open_video_capture()` ([video_io](video_io.md)), `ECProducer` ([Share](../../concepts/share.md)), [Stream](../../concepts/stream.md), [Parameters](../../concepts/parameters.md) |

## Current limitations and roadmap

From the source To Do list — **planned**, not implemented:

- Fix: as a DataSource, PipelineDefinitions should assign the
  `data_sources` parameter properly — implement a
  `webcam://0` / `webcam://dev/video0` DataScheme (also noted on the
  [DataScheme](../../concepts/scheme.md) roadmap)
- Fix: make `frame_rate` configurable and correct for `timestamps`
  (shared issue with [video_io](video_io.md))
- Implement `data_batch_size` in `frame_generator()`
- Use `rate` to control camera FPS at the driver level
  (`CAP_PROP_FRAME_WIDTH/HEIGHT` get/set), and list available camera
  pathnames (for example, `/dev/video[02...]`)
- Move the guarded `import cv2` into a shared `source_target.py`
  helper

Known sharp edges (see Implementation notes): unguarded
`_close_camera()` in `stop_stream()`, and the untested camera-stop
`STOP` event.

## Related concepts

- [PipelineElement](../../concepts/pipeline_element.md) — the element
  contract, `create_frames()` pacing
- [DataSource / DataTarget](../../concepts/data_source_target.md) —
  nominal base class. The `data_sources` integration is on the roadmap
- [DataScheme](../../concepts/scheme.md) — where the planned
  `webcam://` scheme will plug in
- [Share (Eventual Consistency)](../../concepts/share.md) — live
  `path` / `color` / `flip` controls
- [Stream](../../concepts/stream.md) — lifecycle. Camera state
  deliberately outlives Streams
- [Parameters](../../concepts/parameters.md) — `path`, `rate`,
  `media_type` resolution (`self_share_priority`)
- [video_io](video_io.md) — `open_video_capture()`, `VideoShow`,
  `VideoWriteFile(s)` used in every webcam pipeline
- [image_io](image_io.md) — `ImageResize` / `ImageWriteZMQ` used in the
  webcam pipelines
