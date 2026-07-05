---
title: VideoStreamReader
description: Legacy GStreamer wrapper that reads H.264 video from an RTSP
  camera or raw RTP/UDP stream through a hand-built (non parse_launch)
  pipeline delegating to VideoReader
type: concept
audience: [developers, end-users]
status: work-in-progress
source:
  - src/aiko_services/elements/gstreamer/video_stream_reader.py
related: [video_reader, video_stream_writer, video_example, utilities,
  scheme_rtsp, rtsp_io]
version: "0.6"
last_updated: 2026-07-06
---

# VideoStreamReader

## Overview

**`VideoStreamReader`** is a **legacy** (pre-PipelineElement) wrapper
that receives H.264 video from the network — either an **RTSP** source
(e.g. a security camera, via `rtspsrc`) or a raw **RTP over UDP** stream
(via `udpsrc`, pairing with [VideoStreamWriter](video_stream_writer.md))
— and delivers decoded numpy frames through the shared
[VideoReader](video_reader.md) queue contract.

It is the only module in the family that builds its GStreamer pipeline
**element-by-element** (`ElementFactory.make()` + explicit links,
including dynamic pad handling for `rtspsrc`) rather than
`Gst.parse_launch()` — the direction the writers' To Do lists point to.
The current-style RTSP path is [DataSchemeRTSP](scheme_rtsp.md) beneath
[VideoReadRTSP](rtsp_io.md).

**Why you'd use it**: legacy-style network capture, e.g. the input half
of a [video_example](video_example.md) run:

```python
from aiko_services.elements.gstreamer import VideoStreamReader
reader = VideoStreamReader("192.168.1.89", "554", 640, 480,
    framerate="25/1", rtp=False)          # RTSP camera
frame = reader.read_frame(0.01)
```

## For application developers

### Command-line usage

No `__main__` of its own — exercised via the
[video_example](video_example.md) CLI (`-is`, and `--RTP` to select raw
RTP):

```bash
CAMERA_IP=192.168.1.89:554
TARGET_IP=192.168.1.155:5000
./video_example.py -is $CAMERA_IP -os $TARGET_IP -r 640 480 -f 25/1 -cv
```

### Public API

```python
class VideoStreamReader:
    def __init__(self, input_hostname, input_port, width, height,
        framerate=None, rtp=False): ...
    def queue_size(self): ...
    def read_frame(self, timeout=None): ...
```

- `rtp=False` (default): RTSP client. The URL is built from the
  **module-level template** — as committed,
  `"rtsp://USERNAME:PASSWORD@%s:%s"` with *placeholder credentials that
  must be edited in the source* (a commented alternative shows the
  Periscope HD app form `rtsp://admin:admin@%s:%s/live.sdp`). `rtspsrc`
  is configured with `latency=10` ms (contrast
  [DataSchemeRTSP](scheme_rtsp.md)'s 500 ms).
- `rtp=True`: raw RTP receiver — `udpsrc` on `input_port` with caps
  `application/x-rtp, media=video, clock-rate=90000,
  encoding-name=H264` (`input_hostname` is unused in this mode).
- `framerate` (e.g. `"30/1"`, `"25/1"`, `"4/1"`) is optional; when given
  it is added to the appsink caps alongside `format=RGB`, `width`,
  `height`.
- `read_frame(timeout)` / `queue_size()` delegate to
  [VideoReader](video_reader.md): frame dicts
  `{"type": "image", "id": n, "image": ndarray, "timestamp": unix_time}`
  and `{"type": "EOS"}`; `timeout=None` is non-blocking.
- `GStreamerError` is raised if the pipeline cannot be created, linked
  or set playing.

## For framework developers (internals)

### Design

```
 rtp=False:  rtspsrc(location, latency=10) ──┐ dynamic "pad-added":
                                             │ link source → depay
 rtp=True:   udpsrc(port, x-rtp caps) ───────┤ static link
                                             ▼
   rtph264depay ─► h264parse ─► <get_h264_decoder()> ─► videoconvert
                                                            │
              appsink caps: RGB, w x h [, framerate]        ▼
                                            videorate ─► appsink
                                                            │
                                                     VideoReader Queue(30)
```

- **Hand-built pipeline.** Elements are created with
  `ElementFactory.make()`, added to a `Gst.Pipeline`, and linked via a
  `link_element()` helper. `rtspsrc` has dynamic source pads, so the
  source→depayloader link is deferred to a `pad-added` signal handler
  (`on_dynamic_pad()`); `udpsrc` links statically. This is the pattern
  the writers' "replace `parse_launch()`" To Dos aim for.
- Decode chain and caps mirror [DataSchemeRTSP](scheme_rtsp.md)'s
  launch string — the two implementations are siblings across the
  legacy/current boundary.

### Implementation notes

- **`link_element()` error path is broken**: on link failure it raises
  `GStreamerError` with a message formatted from `element1` /
  `element2`, names that do not exist (parameters are `source_name`,
  `source`, `target_name`, `target`) — so a real link failure raises
  `NameError` instead of the intended diagnostic.
- **`on_dynamic_pad()` failure path is also broken**: it calls
  `pipeline_link_error("source", "depay")`, which is not defined
  anywhere in the package — again a `NameError` if the RTSP pad link
  fails. (A commented line shows an older direct `pad.link()`
  approach.)
- `on_dynamic_pad()` links `self.source` to `self.depay` on *every*
  pad-added signal; an RTSP source offering audio + video pads would
  trigger a second (failing) link attempt.
- The intermediate elements (`parser`, `decoder`, `convert`,
  `videorate`, `sink`) are locals, while `source` / `depay` are
  attributes only because the dynamic-pad callback needs them.

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `VideoStreamReader` | Build the RTSP or RTP receive pipeline element-by-element; handle `rtspsrc` dynamic pads; set RGB/size/framerate appsink caps; expose `read_frame()` / `queue_size()` | [VideoReader](video_reader.md) (delegate), [utilities](utilities.md) (`gst_initialise()`, `get_format()`, `get_h264_decoder()`), `GStreamerError`; paired with [VideoStreamWriter](video_stream_writer.md) for RTP |

## Current limitations and roadmap

From the source To Do list:

- Constructor `Queue maxsize` parameter
- Ultimately, start "paused" and tell the video sender to start
- Should do `video_capture.release()` — needs thread termination first
- Optimisation: option to request BGR images directly, avoiding
  RGB→BGR conversion for OpenCV consumers

Additional observed gaps:

- **Hard-wired credential template** (`USERNAME:PASSWORD` in
  `url_template`) — RTSP authentication requires editing the source;
  URL/credentials should be constructor parameters (compare the full
  `rtsp://user:pass@host/...` URLs accepted by
  [scheme_rtsp](scheme_rtsp.md))
- Both link-failure paths raise `NameError` instead of
  `GStreamerError` (see Implementation notes)
- H.264 only; no stop/release passthrough (inherited from
  [VideoReader](video_reader.md)); no test coverage

## Related concepts

- [video_reader](video_reader.md) — the shared appsink wrapper this
  class delegates to
- [video_stream_writer](video_stream_writer.md) — the matching RTP/UDP
  sender
- [video_example](video_example.md) — the CLI that exercises it
  (`-is`, `--RTP`)
- [scheme_rtsp](scheme_rtsp.md) — the current-style RTSP client
  (DataScheme) that supersedes the RTSP mode
- [rtsp_io](rtsp_io.md) — the PipelineElements above that scheme
- [utilities](utilities.md) — GStreamer initialisation, decoder and
  format helpers
