---
title: VideoFileReader
description: Legacy GStreamer wrapper that reads H.264 video frames from an
  MP4/QuickTime file via a parse_launch pipeline delegating to VideoReader
type: concept
audience: [developers, end-users]
status: work-in-progress
source:
  - src/aiko_services/elements/gstreamer/video_file_reader.py
related: [video_reader, video_file_writer, video_example, utilities,
  data_source_target, scheme]
version: "0.6"
last_updated: 2026-07-06
---

# VideoFileReader

## Overview

**`VideoFileReader`** is a **legacy** (pre-PipelineElement) wrapper that
decodes an H.264 video file (MP4/QuickTime container, via GStreamer
`qtdemux`) into numpy image frames, delivered through the shared
[VideoReader](video_reader.md) queue contract. The current-style
equivalent is `VideoReadFile` in
`src/aiko_services/elements/media/video_io.py` — an OpenCV-based
[DataSource](../../concepts/data_source_target.md) driven by
`file:` URLs.

**Why you'd use it**: pull decoded frames from a video file in the
legacy wrapper style, e.g. as the input half of the
[video_example](video_example.md) CLI:

```python
from aiko_services.elements.gstreamer import VideoFileReader
reader = VideoFileReader("football_test_0.mp4", 1280, 720)
while True:
    frame = reader.read_frame(0.01)
    if frame and frame["type"] == "EOS":
        break
```

The equivalent raw GStreamer sanity check (from the source notes, Mac
OS X sink):

```bash
gst-launch-1.0 filesrc location=../football_test_1.mp4 ! qtdemux ! \
  avdec_h264 ! videoconvert ! osxvideosink
```

## For application developers

### Command-line usage

No `__main__` of its own — exercised via the
[video_example](video_example.md) CLI:

```bash
./video_example.py -if input_filename -of output_filename \
  -r width height -f framerate [-cv]
```

### Public API

```python
class VideoFileReader:
    def __init__(self, input_filename, width, height): ...
    def queue_size(self): ...
    def read_frame(self, timeout=None): ...
```

- `__init__()` raises `ValueError` if `input_filename` does not exist,
  then builds
  `filesrc location=… ! qtdemux ! <get_h264_decoder()> ! videoconvert !
  video/x-raw, format=RGB ! appsink` with appsink caps
  `video/x-raw, format=RGB, width=…, height=…`, and wraps it in a
  [VideoReader](video_reader.md) (raises `GStreamerError` if the
  pipeline will not play).
- `read_frame(timeout)` / `queue_size()` delegate to the VideoReader
  queue: frames are
  `{"type": "image", "id": n, "image": ndarray, "timestamp": unix_time}`
  followed by `{"type": "EOS"}` at end of file; `timeout=None` is
  non-blocking.

Contract limits: MP4/QuickTime containers with H.264 video only
(`qtdemux` + the platform H.264 decoder); no framerate in the caps, so
frames are decoded as fast as the consumer drains the bounded queue
(30 frames) — pacing is the consumer's job.

## For framework developers (internals)

### Design

```
 file.mp4 ─► filesrc ─► qtdemux ─► avdec_h264 ─► videoconvert
                                                     │
             caps: RGB, width x height (no fps)      ▼
                                          appsink ─► VideoReader
                                                     Queue(30)
                                                        │
                                               read_frame() ─► caller
```

A thin Facade over [VideoReader](video_reader.md), following the family
shape: validate the source, `parse_launch()` a source-specific
pipeline, set appsink caps from [utilities](utilities.md) helpers,
delegate. Decode-rate control comes only from the queue back-pressure
in VideoReader.

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `VideoFileReader` | Validate the input path; build the file-decode pipeline (`qtdemux`, platform H.264 decoder) with RGB caps; expose `read_frame()` / `queue_size()` | [VideoReader](video_reader.md) (delegate), [utilities](utilities.md) (`gst_initialise()`, `get_h264_decoder()`, `get_format()`), `Gst` `parse_launch()` |

## Current limitations and roadmap

The source To Do list is empty ("None, yet"). Observed gaps:

- Container/codec support is fixed at MP4/QuickTime + H.264 (no
  `decodebin` fallback for other formats)
- Width/height are requested via caps, but there is no `videoscale`
  element in the pipeline — a file whose native resolution differs may
  fail to negotiate rather than be scaled
- No `stop()` passthrough; no resource release before process exit
  (inherited from [VideoReader](video_reader.md))
- No test coverage; only manual exercise via
  [video_example](video_example.md)
- Long-term, file reading is served by the current-style `VideoReadFile`
  ([DataSource](../../concepts/data_source_target.md) + `file:`
  [DataScheme](../../concepts/scheme.md)); this wrapper remains for the
  legacy path and GStreamer-specific decoding

## Related concepts

- [video_reader](video_reader.md) — the shared appsink wrapper this
  class delegates to
- [video_file_writer](video_file_writer.md) — the matching legacy file
  writer
- [video_example](video_example.md) — the CLI that exercises it
- [utilities](utilities.md) — platform decoder and format helpers
- [DataSource / DataTarget](../../concepts/data_source_target.md) — the
  current-style design for file sources
- [DataScheme](../../concepts/scheme.md) — `file:` URL handling in the
  current design
