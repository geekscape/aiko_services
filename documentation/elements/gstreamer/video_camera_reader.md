---
title: VideoCameraReader
description: Legacy GStreamer wrapper that reads video frames from a Linux
  V4L2 camera device via a parse_launch pipeline delegating to VideoReader
type: concept
audience: [developers, end-users]
status: work-in-progress
source:
  - src/aiko_services/elements/gstreamer/video_camera_reader.py
related: [video_reader, utilities, video_example, data_source_target,
  pipeline_element]
version: "0.6"
last_updated: 2026-07-06
---

# VideoCameraReader

## Overview

**`VideoCameraReader`** is a **legacy** (pre-PipelineElement) wrapper
that captures video from a local Linux camera device (`/dev/video*`,
via GStreamer `v4l2src`), delivering frames through the shared
[VideoReader](video_reader.md) queue contract. It is *not* a
[PipelineElement](../../concepts/pipeline_element.md) — the
current-style equivalent for cameras is `VideoReadWebcam` in
`src/aiko_services/elements/media/webcam_io.py` (OpenCV-based; a
`webcam://` [DataScheme](../../concepts/scheme.md) is on that module's
roadmap).

**Why you'd use it**: quick programmatic access to a V4L2 camera as
numpy frames when working in the legacy wrapper style:

```python
from aiko_services.elements.gstreamer import VideoCameraReader
reader = VideoCameraReader("/dev/video0", 640, 480)
frame = reader.read_frame(0.01)   # {"type": "image", "image": ndarray, ...}
```

The equivalent raw GStreamer sanity check (from the source notes):

```bash
gst-launch-1.0 v4l2src device=/dev/video0 ! videoconvert ! autovideosink
```

## For application developers

### Command-line usage

None — the class has no `__main__` block, and unlike the file/stream
wrappers it is not reachable from the [video_example](video_example.md)
CLI either (that tool only constructs file and network readers). Use it
from Python.

### Public API

```python
class VideoCameraReader:
    def __init__(self, input_devicepath, width, height): ...
    def queue_size(self): ...
    def read_frame(self, timeout=None): ...
```

- `__init__()` raises `ValueError` if `input_devicepath` does not exist,
  then builds `v4l2src device=… ! videoflip video-direction=horiz !
  videoconvert ! videorate ! appsink` with caps
  `video/x-raw, format=RGB, width=…, height=…, framerate=10/1`, and
  wraps it in a [VideoReader](video_reader.md).
- `read_frame(timeout)` / `queue_size()` delegate straight to the
  VideoReader queue: frame dicts are
  `{"type": "image", "id": n, "image": ndarray, "timestamp": unix_time}`
  and `{"type": "EOS"}`; `timeout=None` is non-blocking.

Fixed behaviour to be aware of (all hard-wired in the launch string):

- **Horizontal mirror** (`videoflip video-direction=horiz`) — selfie
  orientation, always on
- **Frame rate 10/1** — not a constructor parameter
- **Format `RGB`** from [utilities](utilities.md) `get_format()`

There is no `stop()` passthrough — callers wanting shutdown must reach
into `self.video_reader.stop()`.

## For framework developers (internals)

### Design

```
/dev/video0 ─► v4l2src ─► videoflip(horiz) ─► videoconvert ─► videorate
                                                                 │
              caps: RGB, width x height, 10/1 fps                ▼
                                                    appsink ─► VideoReader
                                                               Queue(30)
                                                                 │
                                                        read_frame() ─► caller
```

A thin Facade over [VideoReader](video_reader.md): the entire class is
pipeline construction; buffering, threading and bus handling are
inherited from the shared wrapper. It follows the same shape as
[VideoFileReader](video_file_reader.md) — validate the source path,
`parse_launch()` a source-specific pipeline, set appsink caps, delegate.

### Implementation notes

- The module uses the two-space indentation of the original legacy code
  and references `utilities.get_format()` via the package namespace —
  this works because `from aiko_services.elements.gstreamer import *`
  picks up the `utilities` submodule attribute bound by the package
  `__init__.py` imports (the package defines no `__all__`).
- `Gst` is obtained per-constructor via `gst_initialise()`, although
  importing the package has already initialised GStreamer (module-level
  call in `video_reader.py`).

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `VideoCameraReader` | Validate the V4L2 device path; build the camera capture pipeline (mirror, convert, rate) with RGB caps; expose `read_frame()` / `queue_size()` | [VideoReader](video_reader.md) (delegate), [utilities](utilities.md) (`gst_initialise()`, `get_format()`), `Gst` `parse_launch()` |

## Current limitations and roadmap

From the source To Do list:

- Support Mac OS X camera sources (`v4l2src` is Linux-only; Mac OS X
  would need `avfvideosrc`)

Additional observed gaps:

- Frame rate (10/1) and the horizontal flip are hard-wired — should be
  constructor parameters
- No `stop()` / release of the device
- Not integrated with the [video_example](video_example.md) CLI, and no
  test coverage
- Long-term, camera capture belongs behind a `webcam://` DataScheme so
  the current-style [DataSource](../../concepts/data_source_target.md)
  elements can use it — this wrapper would then be retired or absorbed

## Related concepts

- [video_reader](video_reader.md) — the shared appsink wrapper this
  class delegates to
- [utilities](utilities.md) — GStreamer initialisation and format
  helpers
- [video_file_reader](video_file_reader.md),
  [video_stream_reader](video_stream_reader.md) — sibling legacy readers
  with the same contract
- [DataSource / DataTarget](../../concepts/data_source_target.md) and
  [DataScheme](../../concepts/scheme.md) — the current-style design a
  camera source should eventually plug into
- [PipelineElement](../../concepts/pipeline_element.md) — the framework
  this wrapper predates
