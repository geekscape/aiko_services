---
title: StoreForward video segment writer
description: VideoWriteStoreForward — a DataTarget PipelineElement that
  groups video frames into MP4 segments and writes each closed segment into
  the outbox of a SegmentStoreForward Actor, which forwards it to another
  host
type: concept
audience: [developers, end-users]
status: work-in-progress
ste: adapted
source:
  - src/aiko_services/elements/media/store_forward_io.py
  - src/aiko_services/elements/media/pipelines/store_forward_pipeline_0.json
related: [pipeline_element, data_source_target, scheme, stream, parameters,
  share, store_forward, scheme_store_forward, synthetic_io, video_io]
version: "0.8-dev"
last_updated: 2026-09-13
---

# StoreForward video segment writer

## Overview

**`VideoWriteStoreForward`** is a
[DataTarget](../../concepts/data_source_target.md)
[PipelineElement](../../concepts/pipeline_element.md) at the end of a
video Pipeline. It receives the standard `images: [image]` frame data
and encodes the frames into MP4 segments with OpenCV. It closes a segment
after `segment_seconds` or `segment_frames`, whichever comes first. Each
closed segment is written into the outbox named by the
[`store_forward://`](scheme_store_forward.md) URL. There a
[SegmentStoreForward](../../concepts/store_forward.md) Actor takes custody
of it and delivers it to the peer host.

The class name follows the `<Media>Write<Scheme>` pattern of
[`VideoWriteFile`](video_io.md), which it resembles: the same OpenCV
writer, RGB frames converted to BGR, the same `format` and `frame_rate`
parameters.

**Why to use it**: a camera Pipeline on a host with intermittent
connectivity keeps recording while the link is down. The segments queue
in the outbox and the Actor forwards them when the link returns. No
camera is needed to try it: the
[synthetic video source](synthetic_io.md) stands in.

```bash
aiko_pipeline create pipelines/store_forward_pipeline_0.json -s 1
```

## For application developers

### Command-line usage

Three processes on the sending host and one on the receiving host. The
receiving host runs the server-role Actor:

```bash
mkdir -p ~/store_forward/in ~/store_forward/out
aiko_store_forward server --inbox ~/store_forward/in --outbox ~/store_forward/out
```

The sending host runs the edge-role Actor watching an outbox, then the
Pipeline writing into that outbox:

```bash
cd src/aiko_services/elements/media
mkdir -p ~/store_forward/in data_out/outbox
aiko_store_forward edge --inbox ~/store_forward/in --outbox data_out/outbox  \
    --server_url http://RECEIVER:8080

# Synthetic frames for 30 s, written as 10 s segments (the definition)
aiko_pipeline create pipelines/store_forward_pipeline_0.json -s 1

# Another outbox, 5 s segments, 20 s in total
aiko_pipeline create pipelines/store_forward_pipeline_0.json -s 1  \
    -p VideoWriteStoreForward.data_targets "(store_forward://~/store_forward/out)"  \
    -p VideoWriteStoreForward.segment_seconds 5 -p CaptureLimit.duration 20

# Segments of 45 frames each
aiko_pipeline create pipelines/store_forward_pipeline_0.json -s 1  \
    -p VideoWriteStoreForward.segment_frames 45  \
    -p VideoWriteStoreForward.segment_seconds 0
```

Watch `segments_written` on the Pipeline in `aiko_dashboard`, and
`store_forwards.<id>` on the edge Actor.

### Public API

```python
class VideoWriteStoreForward(aiko.DataTarget):
    def start_stream(self, stream, stream_id)
    def process_frame(self, stream, images) -> Tuple[StreamEvent, dict]
    def stop_stream(self, stream, stream_id)
```

Element definition:

```json
{ "name": "VideoWriteStoreForward",
  "parameters": {
    "data_targets":    "(store_forward://data_out/outbox)",
    "segment_seconds": 10.0,
    "format":          "mp4v"
  },
  "input":  [{"name": "images", "type": "[image]"}],
  "output": [],
  "deploy": {
    "local": {"module": "aiko_services.elements.media.store_forward_io"}
  }
}
```

| Parameter | Default | Meaning |
|-----------|---------|---------|
| `data_targets` | must be set | `(store_forward://OUTBOX)`, see the [scheme](scheme_store_forward.md) |
| `segment_seconds` | `10.0` | Close a segment after this many seconds (0: unused) |
| `segment_frames` | `0` | Or after this many frames (0: unused). Either bound closes the segment |
| `frame_rate` | `15.0` | Encoded frames per second. Keep equal to the source `rate` |
| `format` | `mp4v` | OpenCV fourcc tag |
| `resolution` | first frame | `WxH`, otherwise the shape of the first frame of each segment |
| `segment_prefix` | `segment` | File name prefix, read by the scheme |

Parameters arrive as strings from the command line and are coerced.
Segment files are named `<prefix>_<UTC>_<nnnnnn>.mp4`, for example
`segment_20260913T010203Z_000001.mp4`, a name the Actor accepts. The
counter restarts at 1 for every Stream.

Share: `outbox`, `segment` (the open segment, `-` between segments),
`segments_written`, `frames_written`, `last_segment_utc`.

`process_frame()` returns `StreamEvent.OKAY` with no outputs. It returns
`ERROR` when a frame is not a NumPy array or a video writer cannot be
opened. `start_stream()` returns `ERROR` when OpenCV is absent.

## For framework developers (internals)

### Design

```
 images ──► process_frame()
              │ no open segment?  open .<name>.mp4 (dot-prefixed temp)
              │ write frame (RGB -> BGR)
              │ bound reached?    close: release, os.replace -> <name>.mp4
              ▼
 stop_stream() closes the open segment, then DataTarget.stop_stream()
```

The open segment is a dot-prefixed temporary file. The Actor's outbox
watcher ignores dot files, so a segment becomes visible only when it is
complete, and at once, through `os.replace()`. The watcher then waits
for one more scan to confirm the size is stable and sends it.

`stop_stream()` runs after every in-flight Frame (the Pipeline destroys a
Stream gracefully), so the last, short segment is closed and delivered
too. A segment with no frames leaves no file.

### Implementation notes

- OpenCV is a guarded import (`_CV2_IMPORTED`), as in `image_io.py`. The
  media package needs OpenCV at import anyway (`video_io.py`).
- The writer is opened on the first frame of each segment with that
  frame's shape, unless `resolution` says otherwise. OpenCV writes
  nothing for a frame of a different shape, so keep the source constant.
- Share updates go through `ec_producer.update()` on the event-loop
  thread, where `process_frame()` runs.
- The test `tests/unit/test_store_forward_io.py` verifies segment frame
  counts with `cv2.VideoCapture`. It keeps every parameter in the element
  definitions. A stray Frame from a finished run makes the Pipeline
  create a Stream without Stream parameters. A `start_stream()` failure
  there restarts the frame generator without end.

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `VideoWriteStoreForward` | Encode frames into bounded MP4 segments, publish each closed segment atomically into the outbox, report counts in share | `DataSchemeStoreForward`, `cv2.VideoWriter`, `SegmentStoreForward` (through the file system) |

## Current limitations and roadmap

- Segments are plain MP4 (`mp4v`). Fragmented MP4, so a partially
  received segment plays, is planned.
- The element does not announce a closed segment to the Actor. The
  watcher's scan period adds up to two scans of latency.
- A `VideoReadStoreForward` DataSource for the receiving host is planned.
- Segment names carry the UTC time of opening, not the capture time of
  the first frame.

## Related concepts

- [scheme_store_forward](scheme_store_forward.md), the URL scheme
- [StoreForward](../../concepts/store_forward.md), the Actor that
  forwards the segments
- [synthetic_io](synthetic_io.md) and [scheme_synth](scheme_synth.md),
  the camera stand-in
- [video_io](video_io.md), `VideoWriteFile`, the model for the encoder
- [control elements](../control/elements.md), `CaptureLimit`
