---
title: DataSchemeRTSP
description: The rtsp URL DataScheme — a GStreamer-based RTSP client
  (implemented) and RTSP server (work-in-progress) plugged in beneath the
  VideoReadRTSP / VideoWriteRTSP PipelineElements
type: concept
audience: [developers, end-users]
status: work-in-progress
ste: adapted
source:
  - src/aiko_services/elements/gstreamer/scheme_rtsp.py
related: [scheme, data_source_target, pipeline_element, stream, parameters,
  rtsp_io, video_reader, utilities]
version: "0.6"
last_updated: 2026-08-01
---

# DataSchemeRTSP

## Overview

**`DataSchemeRTSP`** is the [DataScheme](../../concepts/scheme.md)
registered for the `rtsp` URL scheme. A
[DataSource or DataTarget](../../concepts/data_source_target.md) element
can receive a `data_sources` or `data_targets` URL that starts with
`rtsp://`. In practice that element is
[VideoReadRTSP or VideoWriteRTSP](rtsp_io.md). This class is then
instantiated per [Stream](../../concepts/stream.md), and it does the
GStreamer work: building the decode pipeline, pulling images off the
appsink through the legacy [VideoReader](video_reader.md) wrapper, and
feeding them to the Pipeline as Frames.

The *source* side (RTSP client) is **implemented**. The *target* side
(RTSP server, through GstRtspServer) is **work-in-progress and currently
broken** — most of its body is commented out (see Current limitations
and roadmap).

**Why to use it**: you do not use it directly — you write an ordinary
`rtsp://` URL and the scheme registry does the rest:

```bash
aiko_pipeline create pipelines/rtsp_pipeline_0.json -s 1 \
  -p VideoReadRTSP.data_sources rtsp://username:password@host:554/channel \
  -p VideoReadRTSP.frame_rate 25/1 -p VideoReadRTSP.resolution 640x480
```

## For application developers

### Command-line usage

DataSchemeRTSP has no CLI of its own. The URL scheme of the
`data_sources` or `data_targets` parameter selects it. That parameter
passes through `aiko_pipeline`, as shown above and in
[rtsp_io](rtsp_io.md). The module registers itself at import time:

```python
aiko.DataScheme.add_data_scheme("rtsp", DataSchemeRTSP)
```

so the scheme is available whenever `rtsp_io.py` (which imports it through
the package) is loaded as a PipelineElement module.

### Public API

URL forms — the `data_sources` / `data_targets` list "should only
contain a single entry":

```
(rtsp://hostname:port)
(rtsp://hostname:port/camera_channel)
(rtsp://username:password@hostname:port/camera_channel)
```

Parameters read from the owning
[PipelineElement](../../concepts/pipeline_element.md) through
`get_parameter()` (see [Parameters](../../concepts/parameters.md)):

| Parameter | Needed | Meaning |
|-----------|----------|---------|
| `frame_rate` | yes | GStreamer fraction, for example, `"30/1"`; missing → `StreamEvent.ERROR` with diagnostic `Must provide "frame_rate" parameter` |
| `resolution` | yes | `"1280x720"` string (or `(width, height)` tuple); missing → `StreamEvent.ERROR` |
| `format` | no | Appsink pixel format; default `get_format()` = `"RGB"` (see [utilities](utilities.md)) |
| `data_batch_size` | no | Read by the frame generator but **not yet honored** — always one image per Frame |

Stream lifecycle (the [DataScheme](../../concepts/scheme.md) contract):

| Operation | Status | Effect |
|-----------|--------|--------|
| `create_sources(stream, data_sources, frame_generator, use_create_frame=False)` | implemented | Build the GStreamer client pipeline, start a `VideoReader`, start `create_frames()` with this scheme's own `frame_generator` at `rate=0.0` |
| `frame_generator(stream, frame_id)` | implemented | Poll `VideoReader.read_frame(0.01)`; image → `OKAY, {"images": [image]}` plus `stream.variables["timestamps"]`; no image → `NO_FRAME`; terminated → `STOP` |
| `destroy_sources(stream)` | implemented | Set the terminate flag and `VideoReader.stop()` |
| `create_targets(stream, data_targets)` | **broken** | Parses parameters, then raises `NameError` (see roadmap) |
| `destroy_targets(stream)` | not implemented | Returns `StreamEvent.ERROR` with diagnostic `DataSchemeRTSP does not implement destroy_targets()` |

Frames delivered to the element's `process_frame()` carry `images`.
That is a list, currently always of length 1, of numpy `uint8`
height x width x 3 arrays. The frames also carry the capture Unix time
in `stream.variables["timestamps"]`, which is a one-element list.

## For framework developers (internals)

### Design

```
create_sources():
  rtspsrc location=rtsp://… latency=500 ! rtph264depay ! h264parse !
  <get_h264_decoder()> ! videoconvert ! videorate ! appsink name=sink
        │  caps: video/x-raw, format=…, width=…, height=…, framerate=…
        ▼
  VideoReader(gst_pipeline, sink)        (legacy wrapper, own thread,
        │        Queue(maxsize=30)        frame dicts w/ Unix timestamp)
        ▼
  create_frames(stream, frame_generator, rate=0.0)
        │  poll read_frame(0.01) ─ NO_FRAME when queue empty
        ▼
  VideoReadRTSP.process_frame(stream, images)
```

Key design points:

- **Legacy reuse.** The current-style DataScheme deliberately reuses the
  legacy [VideoReader](video_reader.md) wrapper rather than reimplement
  appsink handling — the two styles meet here.
- **Real-time bias.** `RTSP_LATENCY = 500` ms (GStreamer's default is
  2,000 ms), and the appsink is configured `drop=True`,
  `max-buffers=1`, `sync=False` — prefer fresh frames over completeness.
  Frames are additionally rate-limited by the sink caps
  (`videorate` + `framerate=`), so `frame_rate` is enforced by
  GStreamer, not by the frame generator.
- **Per-Stream instance.** As with every DataScheme, an instance is
  created per Stream by the owning element's `start_stream()`. Instance
  state (`video_reader`, `terminate`) is therefore per-Stream.

### Implementation notes

- `create_sources()` overrides the base signature with
  `use_create_frame=False` as its default (the base class default is
  `True`) and ignores both `frame_generator` and `use_create_frame`,
  always installing its own generator through `create_frames(..., rate=0.0)`.
  Note the known framework issue with `rate=0` compared with `rate=None`
  (see [PipelineElement](../../concepts/pipeline_element.md) roadmap).
- `self.queue = queue.Queue()` is created in `create_sources()` but
  never used — buffering happens inside `VideoReader`. Likewise
  `from threading import Thread` is only needed by the commented-out
  server code.
- `frame_generator()` computes a normalized local `timestamp`
  (`-1.0` missing, `-2.0` non-float) but then stores the *raw*
  `frame["timestamp"]` into `stream.variables["timestamps"]` — the
  normalized value is dead code. The sentinel handling actually applied
  downstream is the one in `VideoReadRTSP.process_frame()`.
- `create_targets()` sets `self.share["rtsp_url"]` (as does
  `create_sources()`), making the URL observable in the element's
  shared state.

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `DataSchemeRTSP` | Register for `rtsp:`; build the GStreamer RTSP client pipeline and caps from parameters; generate `{"images": …}` Frames with capture timestamps; tear down on `destroy_sources()`; (planned) run a GstRtspServer for targets | [DataScheme](../../concepts/scheme.md) (base contract, registry), [DataSource / DataTarget](../../concepts/data_source_target.md) through [rtsp_io](rtsp_io.md) (owning elements), [VideoReader](video_reader.md) (appsink wrapper), [utilities](utilities.md) (`gst_initialise()`, `get_format()`, `get_h264_decoder()`), [Stream](../../concepts/stream.md) (`variables`) |

## Current limitations and roadmap

From the source To Do list:

- Enable GStreamer appsink properties to be set through `get_parameter()`
- Support `data_batch_size`, so a Frame may contain multiple images

State of the code (honest digest):

- **`create_targets()` is broken as written**: it references `port`,
  `fps_n`, `fps_d` and `fps_float`, whose computations are commented out
  (a stray `rtsp_port = 9554` is assigned but unused), so it raises
  `NameError` before it constructs the server. Most of the intended
  implementation exists only inside two large triple-quoted string
  literals in the class body. That code covers the `RTSPMediaFactory`
  media-configure wiring, the appsrc push thread, the frame consumer,
  and the matching `destroy_targets()` clean-up. Treat RTSP *serving* as
  design-stage.
- `destroy_targets()` deliberately returns `StreamEvent.ERROR`
  ("does not implement").
- Only one URL per `data_sources` list is used (`data_sources[0]`).
- H.264 only (`rtph264depay ! h264parse`). No H.265/AAC paths.
- The `format` parameter is documented in the header as
  "TODO: document other options" — only `"RGB"` is exercised.

## Related concepts

- [DataScheme](../../concepts/scheme.md) — the registry and per-Stream
  contract this class implements
- [DataSource / DataTarget](../../concepts/data_source_target.md) — the
  element base classes that instantiate it
- [rtsp_io](rtsp_io.md) — `VideoReadRTSP` / `VideoWriteRTSP`, the
  elements above this scheme
- [video_reader](video_reader.md) — the legacy appsink wrapper reused
  for the client side
- [utilities](utilities.md) — `gst_initialise()` (including the
  GstRtspServer variant) and codec selection
- [PipelineElement](../../concepts/pipeline_element.md) —
  `create_frames()` and frame-generator semantics
- [Stream](../../concepts/stream.md) — per-Stream scheme instances and
  variables
- [Parameters](../../concepts/parameters.md) — `frame_rate`,
  `resolution`, `format` resolution order
