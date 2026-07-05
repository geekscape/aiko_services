---
title: VideoReader
description: Legacy core GStreamer appsink wrapper — runs a given GStreamer
  pipeline on a background thread and turns appsink samples into a queue of
  timestamped numpy image frame dictionaries
type: concept
audience: [developers, end-users]
status: work-in-progress
source:
  - src/aiko_services/elements/gstreamer/video_reader.py
related: [utilities, video_camera_reader, video_file_reader,
  video_stream_reader, scheme_rtsp, rtsp_io, pipeline_element]
version: "0.6"
last_updated: 2026-07-06
---

# VideoReader

## Overview

**`VideoReader`** is the core of the **legacy** (pre-PipelineElement)
GStreamer wrapper family: given an already-constructed GStreamer
pipeline and its `appsink`, it sets the pipeline playing, services the
GStreamer bus on a daemon thread, and converts each appsink sample into
a Python frame dictionary on an internal queue that callers poll with
`read_frame()`.

Every reading wrapper delegates to it —
[VideoCameraReader](video_camera_reader.md) (V4L2 camera),
[VideoFileReader](video_file_reader.md) (MP4 file),
[VideoStreamReader](video_stream_reader.md) (RTSP/RTP) — and, notably,
so does the *current-style* [DataSchemeRTSP](scheme_rtsp.md): this is
where the legacy and
[PipelineElement](../../concepts/pipeline_element.md) worlds meet.

**Why you'd use it**: to add a new GStreamer *source* without redoing
appsink plumbing — build a pipeline ending in
`... ! appsink name=sink`, hand both to `VideoReader`, then poll:

```python
gst = gst_initialise()
pipeline = gst.parse_launch("videotestsrc ! videoconvert ! appsink name=sink")
reader = VideoReader(pipeline, pipeline.get_by_name("sink"))
frame = reader.read_frame(0.01)   # {"type": "image", "image": ndarray, ...}
```

## For application developers

### Command-line usage

None — `VideoReader` is a library class. It is exercised indirectly via
[video_example](video_example.md) (legacy CLI) and via `aiko_pipeline`
with the RTSP PipelineDefinitions (see [rtsp_io](rtsp_io.md)).

### Public API

```python
class VideoReader:
    def __init__(self, pipeline, sink): ...
    def read_frame(self, timeout=None): ...  # frame dict or None
    def queue_size(self): ...                # internal Queue depth
    def stop(self): ...                      # terminate the bus thread
    def gst_to_opencv(self, buffer_data, caps): ...  # ndarray view helper
```

Constructor contract: `pipeline` is a GStreamer pipeline whose `sink`
element is an `appsink`; the constructor enables `emit-signals`,
connects `new-sample`, and sets the pipeline to PLAYING — raising
`GStreamerError` (from [utilities](utilities.md)) if that fails.

Frame dictionaries produced on the internal `Queue(maxsize=30)`:

```python
{"type": "image", "id": frame_id, "image": ndarray,  # HxWx3 uint8 (RGB)
 "timestamp": unix_time}                              # float, time.time()
{"type": "EOS"}                                       # end of stream
```

`read_frame(timeout)` semantics follow `Queue.get()`: `timeout=None`
means *non-blocking* (`block=False`) and returns `None` when empty;
a numeric timeout blocks up to that many seconds, then returns `None`.
Note this inverts the usual convention where `None` means "block
forever".

`stop()` only sets the terminate flag for the bus-service thread — it
does **not** set the pipeline state to NULL (see roadmap).

## For framework developers (internals)

### Design

```
 GStreamer callback thread          bus-service daemon thread (_run)
 ─────────────────────────          ────────────────────────────────
 appsink "new-sample"               loop until terminate:
   └► sample_image():                 bus.timed_pop_filtered(1 ms, ANY)
        buffer.map(READ)              if self.image is not None:
        self.image = ndarray.copy()     queue.put({"type": "image", ...})
        self.timestamp = time.time()    self.image = None; frame_id += 1
                                      ERROR → print + break
        single-slot handoff           EOS   → queue.put({"type": "EOS"})
        (latest image wins)           STATE_CHANGED → print transition
                                            │
                                            ▼
                              caller: read_frame() ← Queue(maxsize=30)
```

- **Single-slot handoff, deliberate frame dropping.** The appsink
  callback overwrites `self.image`; the bus thread drains it into the
  queue at ~1 kHz. If the consumer falls behind, intermediate images are
  silently replaced — the source To Do proposes an image ring-buffer
  queue with a bounded length (and optionally a lossless mode).
- **GStreamer initialised at import.** The module runs
  `Gst = gst_initialise()` at module level, so importing
  `aiko_services.elements.gstreamer` (whose `__init__.py` imports this
  module) initialises GStreamer as a side effect.
- Frame `id` is a local counter starting at 1, not a GStreamer
  timestamp; capture time is wall-clock `time.time()` taken in the
  callback (buffer `pts`/`dts` access is present but commented out).

### Implementation notes

- `sample_image()` uses `buffer.map(Gst.MapFlags.READ)` /
  `buffer.unmap()` rather than `buffer.extract_dup()` — the source
  comments call out the memory leak common in on-line examples, and the
  `.copy()` of the numpy view (~400 µs) is what makes the buffer safe to
  unmap.
- The single-slot handoff between the two threads is unlocked: `image`
  and `timestamp` are written by the callback and read/cleared by the
  bus thread. After queuing, the bus thread sets `self.timestamp = None`
  — a frame whose image arrives between the two writes can pair an image
  with a `None` timestamp (downstream sentinels in
  [scheme_rtsp](scheme_rtsp.md) / [rtsp_io](rtsp_io.md) exist partly for
  this).
- Bus `ERROR` and `EOS` both `break` the thread loop; `ERROR` prints
  the diagnostic but enqueues nothing, so a consumer blocked in
  `read_frame(timeout)` simply times out — there is no error frame type.
- `gst_to_opencv()` builds the `np.ndarray` from the mapped buffer using
  the caps' width/height, hard-coding 3 channels and `uint8`; the caps
  `format` value is read but unused.

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `VideoReader` | Set a supplied pipeline playing; convert appsink samples to timestamped numpy frame dicts; service the GStreamer bus (ERROR / EOS / STATE_CHANGED); buffer frames in a bounded queue; expose `read_frame()` / `queue_size()` / `stop()` | `Gst` via [utilities](utilities.md) `gst_initialise()`; `GStreamerError`; wrapped by [VideoCameraReader](video_camera_reader.md), [VideoFileReader](video_file_reader.md), [VideoStreamReader](video_stream_reader.md) and [DataSchemeRTSP](scheme_rtsp.md) |

## Current limitations and roadmap

From the source To Do list:

- Replace the single `self.image` slot with an image queue: bounded
  ring buffer to cap memory, with an optional lossless "image queue"
  mode so no images are dropped
- When the pipeline cannot reach the playing state, extract and report
  the underlying GStreamer problem in the diagnostic, and have the
  command-line utilities catch and report it

Additional observed gaps:

- `stop()` does not set the pipeline to `Gst.State.NULL` or join the
  thread — GStreamer resources are only released at process exit
- Bus-thread diagnostics go to `print()`, not a logger
- Un-synchronised image/timestamp handoff (see Implementation notes)
- `read_frame(timeout=None)` being non-blocking is an easy misuse trap

## Related concepts

- [utilities](utilities.md) — `gst_initialise()` and `GStreamerError`
- [video_camera_reader](video_camera_reader.md),
  [video_file_reader](video_file_reader.md),
  [video_stream_reader](video_stream_reader.md) — the legacy wrappers
  that build pipelines for this class
- [scheme_rtsp](scheme_rtsp.md) — the current-style DataScheme that
  reuses this class
- [rtsp_io](rtsp_io.md) — the PipelineElements ultimately fed by it
- [PipelineElement](../../concepts/pipeline_element.md) — the current
  design this class predates
