---
title: Video I/O elements
description: PipelineElements that decode video files into image frames,
  sample and display them, and encode image frames back into video files
type: concept
audience: [developers, end-users]
status: work-in-progress
source:
  - src/aiko_services/elements/media/video_io.py
  - src/aiko_services/elements/media/pipelines/video_pipeline_0.json
  - src/aiko_services/elements/media/pipelines/video_pipeline_1.json
  - src/aiko_services/elements/media/pipelines/video_to_images_pipeline.json
  - src/aiko_services/elements/media/pipelines/images_to_video_pipeline.json
related: [pipeline_element, data_source_target, scheme, stream, parameters,
  scheme_file, image_io, webcam_io, images_to_video, video_example]
version: "0.6"
last_updated: 2026-07-06
---

# Video I/O elements

## Overview

The **video I/O elements** move video through an Aiko Services
[Pipeline](../../concepts/pipeline.md) one image frame at a time:
`VideoReadFile` decodes video files into `images: [image]` frame data
(NumPy RGB arrays via OpenCV), `VideoSample` drops frames,
`VideoShow` displays them in an OpenCV window, and `VideoWriteFile` /
`VideoWriteFiles` encode images back into video files. Because the
frame data is the same `images` convention used by
[image_io](image_io.md) and [webcam_io](webcam_io.md), image transforms
(resize, overlay, …) drop straight into video pipelines.

The module also exports `open_video_capture()`, the platform-aware
`cv2.VideoCapture` factory used by both video-file decoding and the
webcam element.

**Why you'd use it**: process a video file frame-by-frame — resize,
display, re-encode — with the graph in JSON and the file locations as
URL parameters:

```bash
cd src/aiko_services/elements/media

aiko_pipeline create pipelines/video_pipeline_0.json -s 1  \
  -p VideoReadFile.data_sources file:data_in/in_00.mp4   \
  -p ImageResize.resolution 320x240                        \
  -p VideoWriteFile.data_targets file:data_out/out_00.mp4
```

## For application developers

### Command-line usage

All commands run from `src/aiko_services/elements/media`. Options:
`-s 1` create Stream 1, `-sr` show the response, `-ll debug` log level,
`-p ELEMENT.name value` element parameters.

From the `video_io.py` usage header:

```bash
# Decode, resize, display, re-encode (with optional Metrics element)
aiko_pipeline create pipelines/video_pipeline_0.json -s 1 -sr -ll debug

# Pace decoding at 4 frames per second
aiko_pipeline create pipelines/video_pipeline_0.json -s 1 -p rate 4.0

# Batch size parameter (accepted, but not yet used by frame_generator())
aiko_pipeline create pipelines/video_pipeline_0.json -s 1  \
  -p VideoReadFile.data_batch_size 8

# Directory of videos matching a "{}" template, played in sorted order
aiko_pipeline create pipelines/video_pipeline_0.json -s 1  \
  -p VideoReadFile.data_sources file:data_in/in_{}.mp4

# Explicit single video in / out
aiko_pipeline create pipelines/video_pipeline_0.json -s 1  \
  -p VideoReadFile.data_sources file:data_in/in_00.mp4   \
  -p ImageResize.resolution 320x240                        \
  -p VideoWriteFile.data_targets file:data_out/out_00.mp4

# Drop frame test: keep every 10th frame, display
aiko_pipeline create pipelines/video_pipeline_1.json -s 1 -ll debug
```

Conversion pipelines shared with [image_io](image_io.md):

```bash
# Explode a video into JPEG frames ("rate": 0.0 --> flat out)
aiko_pipeline create pipelines/video_to_images_pipeline.json -s 1

# Assemble JPEG frames into an MP4 (MP4V at 30 fps)
aiko_pipeline create pipelines/images_to_video_pipeline.json -s 1
```

In `VideoShow`'s window, press `x` to stop the Stream (or exit the
process when `system_exit` is true).

### Public API

| Class | Kind | Inputs → Outputs | Parameters |
|-------|------|------------------|------------|
| `VideoReadFile` | DataSource | `images: [image]` → `images: [image]` | `data_sources` (`file:` URL, required), `rate`, `media_type` (`numpy` \| `pil`), `data_batch_size` (accepted, not yet honoured) |
| `VideoSample` | transform | `images` → `images` | `sample_rate` (default 1): keep frames where `frame_id % sample_rate == 0`, else `DROP_FRAME` |
| `VideoShow` | sink (display) | `images` → (none) | `title` (default `"Video"`), `position` (default `"1280:0"`, applied on frame 0), `system_exit` (default `false`) |
| `VideoWriteFile` | DataTarget | `images` → (none) | `data_targets` (`file:` URL, required), `format` (default `"MP4V"`), `frame_rate` (default 30.0), `resolution` (default: first image's size) |
| `VideoWriteFiles` | sink (rolling files) | `images` → (none) | `video_name` (default `"data_out"`), `directory` and `pathname` templates, `video_file_duration` (minutes, default 1), `frame_rate` (default 4.0), `resolution` (default `"640x480"`), `minute_range` (default `"*"`) |
| `VideoOutput` | pass-through | `images` → `images` | (none) — response tail |

Service protocols: `video_read_file:0`, `video_sample:0`,
`video_show:0`, `video_write_file:0`, `video_write_files:0`,
`video_output:0`.

Helper function:

```python
open_video_capture(camera_id=0)  # -> cv2.VideoCapture
```

selects the platform camera API (`CAP_AVFOUNDATION` on macOS,
`CAP_V4L2` on Linux, `CAP_MSMF` on Windows), falling back to
auto-select; it accepts a file pathname string equally well and is also
used by [webcam_io](webcam_io.md) and `audio_io` ([audio_io](audio_io.md)).

**URL forms**: `file:path.mp4` or `file:dir/in_{}.mp4` (glob template)
via [scheme_file](scheme_file.md).

**Stream lifecycle behaviour:**

- `VideoReadFile.start_stream()` initialises
  `stream.variables["video_capture"]` / `["video_frame_generator"]` and
  passes its own `frame_generator` to the scheme with
  `use_create_frame=False` — a video always needs the generator thread.
  The generator walks `source_paths_generator` (from the file scheme),
  opens each video with `open_video_capture()`, and yields **one image
  per Pipeline frame** (`{"images": [image_rgb]}`), converting BGR to
  RGB. End of the last file returns `StreamEvent.STOP`
  (`"End of video file(s)"`); an unopenable file returns
  `StreamEvent.ERROR`.
- `VideoReadFile.process_frame()` sets
  `stream.variables["timestamps"]` (currently a hard-coded 25 fps clock)
  and applies optional `media_type` conversion.
- `VideoWriteFile.start_stream()` resolves the target path (a `{}`
  template is formatted once with `target_file_id`, not per frame); the
  `cv2.VideoWriter` is created lazily on the first
  `process_frame()`, using the first image's resolution unless
  `resolution` is set. Images **must be NumPy arrays** — a PIL image
  produces `StreamEvent.ERROR` (`"Image media_type must be a numpy
  array"`); use `media_type: numpy` on the source or an `ImageConvert`
  element ([image_io](image_io.md)). `stop_stream()` releases the
  writer, finalising the file.
- `VideoWriteFiles` is a continuous-recording sink (not a DataTarget):
  it writes date/time-structured rolling files
  (`data_out/YYYY/MM/DD/HH/MMm_SSs.mp4` by default), starts a new file
  every `video_file_duration` minutes, only records inside
  `minute_range` (e.g. `"00-15"`), and publishes the current
  `video_pathname` to shared state for the Aiko Services Dashboard.

## For framework developers (internals)

### Design

```
 VideoReadFile ── file scheme paths ──┐        one video file
   frame_generator():                 │        at a time
     open_video_capture(path)         ▼
     video_frame_iterator ──► {"images": [image_rgb]}  1 image / frame
                                      │
                    VideoSample (frame_id % sample_rate)
                                      │
              ┌──────────┬────────────┴──────┐
          VideoShow  VideoWriteFile   VideoWriteFiles
          cv2.imshow  lazy VideoWriter  rolling files by
          "x" stops   released on stop  wall-clock minute
```

- **Two-level generator.** `VideoReadFile.frame_generator()` composes
  the scheme's *path* iterator with a per-video *image* iterator
  (`video_frame_iterator()`), both held in `stream.variables` — the
  canonical example of a DataSource overriding the scheme's default
  frame generator (the
  [DataSource / DataTarget](../../concepts/data_source_target.md)
  roadmap notes this pattern should be generalised).
- **Lazy writer creation.** `VideoWriteFile` cannot size the encoder
  until it has seen an image, so writer creation happens in
  `process_frame()`, not `start_stream()` — per-Stream state
  (`video_writer`, `video_path`) lives in `stream.variables`.
- **Wall-clock file rotation.** `VideoWriteFiles` keys rotation off
  `datetime.now().minute`, deliberately trading frame-accurate file
  lengths for predictable, time-addressable archives (CCTV-style).

### Implementation notes

- `VideoShow` names its clean-up method `stream_stop_handler()` — that
  is **not** part of the PipelineElement contract (`stop_stream()`), so
  `cv2.destroyAllWindows()` is never invoked by the framework. Window
  clean-up currently relies on process exit.
- Codec notes from the source: list codecs with
  `cv2.VideoWriter(..., fourcc=-1)`; `.avi` → `XVID`; `.mp4` → `MP4V`,
  `DIVX`, `H264`, `X264`; Linux supports `DIVX XVID MJPG X264 WMV1
  WMV2`, Windows `DIVX`.
- `VideoWriteFile._create_video_writer()` creates parent directories
  (`mkdir(parents=True)`) before writing.
- `VideoWriteFiles.process_frame()` re-reads `minute_range` every frame
  (and mirrors it into `self.share`), so recording windows can be
  changed live via shared state; it writes only `images[0]` per frame.
- `_CV2_IMPORTED` / `_NUMPY_IMPORTED` guards exist but are not yet
  checked at use sites (same gap as [image_io](image_io.md)).

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `VideoReadFile` | Iterate video files → decode → emit one RGB image per frame; manage `video_capture` lifecycle; optional `media_type` conversion | [DataSource](../../concepts/data_source_target.md), [DataSchemeFile](scheme_file.md), `open_video_capture()`, [Stream](../../concepts/stream.md), [Parameters](../../concepts/parameters.md) |
| `VideoSample` | Keep every Nth frame (`sample_rate`), else `DROP_FRAME` | [PipelineElement](../../concepts/pipeline_element.md), [Stream](../../concepts/stream.md) |
| `VideoShow` | Display images in an OpenCV window; position/title parameters; `x` key stops the Stream or exits | [PipelineElement](../../concepts/pipeline_element.md), [Parameters](../../concepts/parameters.md) |
| `VideoWriteFile` | Lazily create `cv2.VideoWriter` sized from the first image; encode NumPy RGB frames; release on stop | [DataTarget](../../concepts/data_source_target.md), [DataSchemeFile](scheme_file.md), [Stream](../../concepts/stream.md) |
| `VideoWriteFiles` | Continuous recording into date/time-templated rolling files; `minute_range` gating; publish `video_pathname` | [PipelineElement](../../concepts/pipeline_element.md), `ECProducer` shared state, [Parameters](../../concepts/parameters.md) |
| `VideoOutput` | Pass `images` through as the Pipeline response tail | [PipelineElement](../../concepts/pipeline_element.md) |

## Current limitations and roadmap

From the source To Do list — **planned**, not implemented:

- Refactor `VideoWriteFiles` to be a
  `DataTarget` subclass (of `VideoWriteFile`) rather than a standalone
  PipelineElement with its own path templates
- Fix: make `frame_rate` configurable and correct for the
  `timestamps` stream variable (currently hard-coded 1/25 s)
- Implement `data_batch_size` in `VideoReadFile.frame_generator()`
  (parameter is accepted but each frame carries exactly one image)
- `start_frame` / `stop_frame` parameters; `VideoSample` by image count
  rather than frame count, with a shared `video_sample()` helper
- Read video properties (`CAP_PROP_FRAME_WIDTH/HEIGHT/COUNT/FPS`) from
  the capture rather than assuming them
- Typed DataSources (URL + media type, e.g. `mp4`); metrics (frame
  rates); video windowing (multi-frame batches for ML, e.g. gesture
  analysis); CPU–GPU batch transfer efficiency
- `VideoShow` GUI work: missing `cv2.imshow()` icons, trackbars,
  tkinter integration — and moving clean-up into a real
  `stop_stream()` (see Implementation notes)
- Refactor optional module imports into a common function shared with
  [image_io](image_io.md)

## Related concepts

- [PipelineElement](../../concepts/pipeline_element.md) — the contract
  every class here implements
- [DataSource / DataTarget](../../concepts/data_source_target.md) —
  base classes; `VideoReadFile` is the motivating case for the planned
  frame-generator refactor
- [DataScheme](../../concepts/scheme.md) / [scheme_file](scheme_file.md)
  — `file:` URL resolution and path iteration
- [Stream](../../concepts/stream.md) — lifecycle and `stream.variables`
- [Parameters](../../concepts/parameters.md) — how `-p` values reach
  elements
- [image_io](image_io.md) — image transforms used inside video
  pipelines, and the image ends of the conversion pipelines
- [webcam_io](webcam_io.md) — live camera source built on
  `open_video_capture()`
- [images_to_video](images_to_video.md), [video_example](video_example.md)
  — legacy scripts superseded by the pipelines above
