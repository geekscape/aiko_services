---
title: VideoFileWriter
description: Legacy GStreamer wrapper that encodes queued numpy image frames
  to an H.264 video file via appsrc and splitmuxsink on a background thread
type: concept
audience: [developers, end-users]
status: work-in-progress
source:
  - src/aiko_services/elements/gstreamer/video_file_writer.py
related: [video_reader, video_file_reader, video_stream_writer,
  video_example, utilities, data_source_target]
version: "0.6"
last_updated: 2026-07-06
---

# VideoFileWriter

## Overview

**`VideoFileWriter`** is a **legacy** (pre-PipelineElement) wrapper that
accepts frame dictionaries on a bounded queue and encodes them to an
H.264 video file — the *write* mirror of
[VideoFileReader](video_file_reader.md), sharing the same frame-dict
contract as [VideoReader](video_reader.md). The current-style
equivalent is `VideoWriteFile(s)` in
`src/aiko_services/elements/media/video_io.py`, exercised by
`pipelines/rtsp_pipeline_1.json` (see [rtsp_io](rtsp_io.md)).

**Why you'd use it**: as the output half of a legacy wrapper chain,
e.g. recording a network camera via the
[video_example](video_example.md) CLI:

```python
from aiko_services.elements.gstreamer import VideoFileWriter
writer = VideoFileWriter("out.mp4", 640, 480, "25/1")
writer.write_frame({"type": "image", "id": 1, "image": ndarray})
writer.write_frame({"type": "EOS"})   # finalise the file
```

## For application developers

### Command-line usage

No `__main__` of its own — exercised via the
[video_example](video_example.md) CLI:

```bash
./video_example.py -is input_hostname:port -of output_filename \
  -r width height -f framerate -cv [--RTP]
```

### Public API

```python
class VideoFileWriter:
    def __init__(self, filename, width, height, framerate): ...
    def write_frame(self, frame): ...   # enqueue; blocks when queue full
    def queue_size(self): ...
```

- Constructor arguments describe the **incoming** frames: `width`,
  `height`, `framerate` (GStreamer fraction string, e.g. `"25/1"`) set
  the appsrc caps, together with format `RGB` from
  [utilities](utilities.md) `get_format()`.
- `write_frame(frame)` accepts the family frame dicts:
  `{"type": "image", "image": ndarray, ...}` is encoded and written;
  `{"type": "EOS"}` emits GStreamer end-of-stream, finalising the file
  (essential — an MP4 without EOS finalisation may be unplayable).
  The internal `Queue(maxsize=30)` applies back-pressure by blocking
  the caller.
- There is no `close()`/`join()`; send the EOS frame, and note the
  encoder thread is a daemon (see Implementation notes).

**Caveat — output geometry is currently hard-wired**: the encode
pipeline scales and re-rates everything to `1280x768 @ 25/1` regardless
of the constructor arguments (see Current limitations and roadmap).

## For framework developers (internals)

### Design

```
 write_frame() ─► Queue(30) ─► daemon thread _run():
                                  image ─► ndarray.tobytes()
                                       ─► Gst.Buffer ─► appsrc push-buffer
                                  EOS  ─► appsrc end-of-stream
        appsrc (is-live, do-timestamp, TIME format)
          ! videoconvert ! videoscale ! videorate
          ! video/x-raw, 1280x768, 25/1          ← hard-wired
          ! <get_h264_encoder()>                 ← x264enc / vtenc_h264
          ! splitmuxsink location=<filename>
```

- Same producer/consumer shape as
  [VideoStreamWriter](video_stream_writer.md): a bounded queue decouples
  the caller from GStreamer; timestamps come from
  `do-timestamp=True` rather than from the frame dicts.
- `splitmuxsink` is used as the muxer/sink; the commented-out options
  (`location={}_%03d.mp4`, `max-files`, `max-size-bytes`,
  `max-size-time`) show the intended direction — time/size-based file
  splitting, which the current-style `VideoWriteFiles` element does at
  the application level instead. Alternative muxing one-liners
  (`mp4mux ! filesink`, `jpegenc ! avimux`, `mpegtsmux`) remain as
  comments.

### Implementation notes

- The `gst_launch_command` template contains two `{}` placeholders
  (encoder, filename) and is formatted with
  `utilities.get_h264_encoder()` and `filename`; note
  `get_h264_encoder_options()` is *not* applied here (unlike
  [VideoStreamWriter](video_stream_writer.md)), so Linux `x264enc` runs
  with default latency/threading options.
- A comment records `vtenc_h264` (Mac OS X) resolution quirks:
  "1280x768, 512x288, 256x144" — presumably why 1280x768 was chosen for
  the hard-wired scale.
- The encoder thread is `daemon=True` and loops forever on
  `queue.get()`; after EOS it keeps consuming (an image after EOS would
  be pushed into a stopped stream). Process exit while frames are
  buffered can truncate the file.
- The Python 2 `Queue` import fallback (`sys.version_info`) is dead
  code in a Python 3 codebase.

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `VideoFileWriter` | Accept frame dicts on a bounded queue; convert images to `Gst.Buffer` and push through appsrc; encode H.264 and write via `splitmuxsink`; finalise on EOS | [utilities](utilities.md) (`gst_initialise()`, `get_h264_encoder()`, `get_format()`), `Gst` `parse_launch()` / appsrc; fed by [VideoReader](video_reader.md)-family readers via [video_example](video_example.md) `process_video()` |

## Current limitations and roadmap

From the source To Do list:

- Replace `Gst.parse_launch()` with a hand-built pipeline (as
  [video_stream_reader](video_stream_reader.md) already does)

Additional observed gaps:

- **Hard-wired `1280x768 @ 25/1` output** in the launch string ignores
  the constructor's `width`/`height`/`framerate`, which only shape the
  appsrc input caps — output geometry should follow the constructor
- No clean shutdown: no `close()`, daemon thread, possible truncation
  on exit; no error reporting from the encode pipeline (bus is never
  read)
- `splitmuxsink` splitting options are commented out — single-file
  output only
- Encoder options helper not applied (Linux latency/threading defaults)
- Long-term: superseded by the current-style `VideoWriteFile(s)`
  [DataTarget](../../concepts/data_source_target.md) for application
  use; this wrapper remains the GStreamer-encoding path

## Related concepts

- [video_file_reader](video_file_reader.md) — the matching legacy file
  reader
- [video_stream_writer](video_stream_writer.md) — sibling writer with
  the same queue/thread shape (network output)
- [video_reader](video_reader.md) — origin of the frame-dict contract
- [video_example](video_example.md) — the CLI that exercises it
- [utilities](utilities.md) — platform encoder and format helpers
- [DataSource / DataTarget](../../concepts/data_source_target.md) — the
  current-style design for file targets
