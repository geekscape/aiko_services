---
title: VideoReadRTSP and VideoWriteRTSP
description: PipelineElements (current DataSource / DataTarget style) that
  read video frames from an RTSP network camera and — as a stub — write
  video frames out as an RTSP server
type: concept
audience: [developers, end-users]
status: work-in-progress
source:
  - src/aiko_services/elements/gstreamer/rtsp_io.py
  - src/aiko_services/elements/gstreamer/pipelines/rtsp_pipeline_0.json
  - src/aiko_services/elements/gstreamer/pipelines/rtsp_pipeline_1.json
related: [data_source_target, scheme, pipeline_element, pipeline, stream,
  parameters, scheme_rtsp, utilities, video_reader]
version: "0.6"
last_updated: 2026-07-06
---

# VideoReadRTSP and VideoWriteRTSP

## Overview

`rtsp_io.py` provides the RTSP PipelineElements in the **current**
Aiko Services style — subclasses of
[DataSource / DataTarget](../../concepts/data_source_target.md) whose
actual network I/O is delegated to the `rtsp:` /
[DataScheme](../../concepts/scheme.md) implemented by
[scheme_rtsp](scheme_rtsp.md):

- **`VideoReadRTSP`** — an RTSP *client* DataSource: connects to an RTSP
  server (typically a network camera), decodes H.264 video via GStreamer
  and emits one image per Frame into the
  [Pipeline](../../concepts/pipeline.md). Implemented and exercised by the
  two committed PipelineDefinitions (`rtsp_pipeline_0.json`,
  `rtsp_pipeline_1.json`).
- **`VideoWriteRTSP`** — an RTSP *server* DataTarget intended to serve
  frames produced by the Pipeline to RTSP clients. Currently a
  **non-functional stub** (see Current limitations and roadmap).

**Why you'd use it**: point a Pipeline at a security camera and process
its live video with ordinary
[PipelineElements](../../concepts/pipeline_element.md) — display, record,
infer — without any camera-specific code:

```bash
aiko_pipeline create pipelines/rtsp_pipeline_0.json -s 1 \
  -p VideoReadRTSP.data_sources rtsp://username:password@hostname:554/channel
```

## For application developers

### Command-line usage

These elements have no CLI of their own — they are hosted via
`aiko_pipeline` (see [Pipeline](../../concepts/pipeline.md)). From the
source usage header (run from
`src/aiko_services/elements/gstreamer/`):

```bash
aiko_pipeline create pipelines/rtsp_pipeline_0.json -s 1 -ll debug_all \
  -p VideoReadRTSP.data_sources rtsp://username:password@host:port \
  -p VideoReadRTSP.resolution 640x480  \
  -p VideoReadRTSP.format     RGB      \
  -p VideoReadRTSP.frame_rate 25/1
```

The two committed PipelineDefinitions:

- `pipelines/rtsp_pipeline_0.json` — `(VideoReadRTSP VideoShow)`: read a
  network camera and display it locally.
- `pipelines/rtsp_pipeline_1.json` —
  `(VideoReadRTSP VideoShow VideoWriteFiles Metrics)`: additionally record
  timestamped MP4 files (`VideoWriteFiles`, from
  `aiko_services.elements.media.video_io`) and report metrics.

Both definitions carry placeholder camera credentials
(`rtsp://admin:PASSWORD@192.168.0.230:554/...`) — override
`data_sources` on the command line or edit a copy.

### Public API

**`VideoReadRTSP(aiko.DataSource)`** — protocol `video_read_rtsp:0`.

Parameters (resolved via
[Parameters](../../concepts/parameters.md); most are consumed by
[DataSchemeRTSP](scheme_rtsp.md) during `start_stream()`):

| Parameter | Required | Meaning |
|-----------|----------|---------|
| `data_sources` | yes | RTSP server URL (single entry) — see URL forms below |
| `frame_rate` | yes | Frames per second as a GStreamer fraction, e.g. `"25/1"` |
| `resolution` | yes | `"WIDTHxHEIGHT"`, e.g. `"640x480"` |
| `format` | no | Pixel format, default `"RGB"` (from [utilities](utilities.md) `get_format()`) |
| `data_batch_size` | no | Accepted but not yet honoured — always one image per Frame (scheme To Do) |
| `media_type` | no | If set, `process_frame()` converts images via `convert_images()` (e.g. to PIL) |

URL forms (from the `scheme_rtsp.py` header — the `data_sources` list
should contain a single entry):

```
rtsp://hostname:port
rtsp://hostname:port/camera_channel
rtsp://username:password@hostname:port/camera_channel
```

Frame contract: the RTSP DataScheme's frame generator produces
`{"images": [image]}` (numpy `uint8` HxWx3 arrays) and sets the
per-[Stream](../../concepts/stream.md) variable
`stream.variables["timestamps"]` (a one-element list of Unix-time
floats). `VideoReadRTSP.process_frame(stream, images)` is then largely a
pass-through: it logs the timestamp, optionally converts the images per
`media_type`, and returns `StreamEvent.OKAY, {"images": images}`.

Stream lifecycle is entirely inherited from
[DataSource](../../concepts/data_source_target.md): `start_stream()`
selects `DataSchemeRTSP` from the URL scheme and calls
`create_sources()`; `stop_stream()` calls `destroy_sources()`.

**`VideoWriteRTSP(aiko.DataTarget)`** — protocol `video_write_rtsp:0`;
parameter `data_targets` names the RTSP server details. **Stub only**:
`process_frame(stream, images)` serialises each image with
`image_to_bytes()` but the actual send is commented out — and
`image_to_bytes` is not imported by this module (see roadmap), so the
method would raise `NameError` if invoked. `VideoWriteRTSP` is also
excluded from the module's `__all__` and from the package
`__init__.py` exports.

## For framework developers (internals)

### Design

```
 RTSP camera                Pipeline "p_rtsp_video_0"
 ────────────               ─────────────────────────────────────────
 rtsp://host ──► DataSchemeRTSP ──► VideoReadRTSP ──► VideoShow ──► …
                 (GStreamer client,  process_frame():   display
                  frame generator    media_type convert,
                  thread)            {"images": […]}
```

- **Thin element, fat scheme.** All GStreamer work — pipeline
  construction, H.264 decode, pacing, timestamps — lives in
  [DataSchemeRTSP](scheme_rtsp.md); the element contributes only the
  optional `media_type` conversion. This is the intended division of
  labour of the [DataSource / DataTarget](../../concepts/data_source_target.md)
  design (element = what the data means, scheme = how to reach it).
- **Timestamps as Stream variables.** Frame capture times travel in
  `stream.variables["timestamps"]` rather than in the swag, so downstream
  recorders (e.g. `VideoWriteFiles`) can name files by capture time.
  `process_frame()` uses negative sentinel values (`-3.0` missing,
  `-4.0` falsy) when no timestamp is available.
- The header comments note both classes "only support Streams with"
  their respective URL parameter — there is no parameter-less default.

### Implementation notes

- `process_frame()` contains a commented-out
  `print_memory_used(...)` probe — RTSP streams are long-running and
  memory growth has evidently been watched here; see the
  `buffer.map()` leak note in [video_reader](video_reader.md).
- `VideoWriteRTSP.process_frame()` hard-codes `media_type = "image"`
  with a TODO considering `"image/zip"`, and a commented
  `"image:length:content"` record framing; the commented send targets
  `stream.variables["target_zmq_socket"]` — a leftover from the ZMQ
  DataScheme this stub was adapted from.

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `VideoReadRTSP` | DataSource PipelineElement: declare protocol `video_read_rtsp:0`; optionally convert images per `media_type`; forward `{"images": …}`; surface capture timestamps from Stream variables | [DataSource](../../concepts/data_source_target.md) (lifecycle), [DataSchemeRTSP](scheme_rtsp.md) (I/O), [Stream](../../concepts/stream.md) (`variables["timestamps"]`), `convert_images` (`aiko_services.elements.media`) |
| `VideoWriteRTSP` (stub) | DataTarget PipelineElement intended to push frames to an RTSP server; currently serialise-and-drop | [DataTarget](../../concepts/data_source_target.md), [DataSchemeRTSP](scheme_rtsp.md) (`create_targets()` — also incomplete) |

## Current limitations and roadmap

From the source To Do list and the state of the code:

- **`VideoWriteRTSP` is not functional**: the send is commented out;
  `image_to_bytes` is used but not imported (would `NameError`); the
  class is not exported via `__all__` or the package `__init__.py`; and
  the scheme side (`DataSchemeRTSP.create_targets()`) is itself broken —
  see [scheme_rtsp](scheme_rtsp.md).
- Planned: a device-discovery PipelineElement using avahi-browse /
  zeroconf feeding a Device Registrar — static configuration for device
  types (ESP32, Host, Robot), dynamically created Actors per device,
  starting with network cameras (Dahua, HikVision).
- Design question recorded in the header: should a "VideoRTSPStore"
  (RTSP in, video files out) be a DataSource in its own right?
- `data_batch_size` accepted but not honoured (one image per Frame).

## Related concepts

- [DataSource / DataTarget](../../concepts/data_source_target.md) — the
  base classes these elements extend
- [DataScheme](../../concepts/scheme.md) — the plug-in mechanism that
  routes `rtsp:` URLs to [scheme_rtsp](scheme_rtsp.md)
- [scheme_rtsp](scheme_rtsp.md) — the GStreamer client/server behind
  these elements
- [PipelineElement](../../concepts/pipeline_element.md) — the element
  contract (`process_frame()`, StreamEvents)
- [Pipeline](../../concepts/pipeline.md) — hosts the elements;
  `aiko_pipeline` CLI
- [Stream](../../concepts/stream.md) — lifecycle and per-Stream variables
- [Parameters](../../concepts/parameters.md) — how `data_sources`,
  `resolution` etc. are supplied
- [utilities](utilities.md) — GStreamer initialisation and codec
  selection helpers
- [video_reader](video_reader.md) — the legacy `VideoReader` reused by
  the RTSP DataScheme
