---
title: GStreamer elements index
description: Index of the OKF concept documents for
  src/aiko_services/elements/gstreamer/ — the RTSP PipelineElements and
  DataScheme (current style) and the legacy GStreamer video wrapper classes
type: index
audience: [developers, end-users]
status: work-in-progress
source:
  - src/aiko_services/elements/gstreamer/__init__.py
related: [rtsp_io, scheme_rtsp, utilities, video_reader,
  video_camera_reader, video_example, video_file_reader, video_file_writer,
  video_stream_reader, video_stream_writer, data_source_target, scheme,
  pipeline_element]
version: "0.6"
last_updated: 2026-07-06
---

# GStreamer elements index

The `src/aiko_services/elements/gstreamer/` package contains two
generations of code side by side:

- **Current style** — [PipelineElements](../../concepts/pipeline_element.md)
  built on [DataSource / DataTarget](../../concepts/data_source_target.md)
  with a pluggable [DataScheme](../../concepts/scheme.md), hosted by
  `aiko_pipeline`: the RTSP modules.
- **Legacy style** — pre-PipelineElement wrapper classes around GStreamer
  pipelines, sharing an informal `read_frame()` / `write_frame()` queue
  contract, exercised by the stand-alone `video_example.py` CLI.

One OKF concept document per Python module:

## Module documents

| Document | Module | Style | Summary |
|----------|--------|-------|---------|
| [rtsp_io](rtsp_io.md) | `rtsp_io.py` | current | `VideoReadRTSP` DataSource reading a network camera (implemented); `VideoWriteRTSP` DataTarget RTSP server (stub) |
| [scheme_rtsp](scheme_rtsp.md) | `scheme_rtsp.py` | current | `DataSchemeRTSP` — the `rtsp:` URL DataScheme: GStreamer RTSP client (implemented), RTSP server (broken work-in-progress) |
| [utilities](utilities.md) | `utilities.py` | shared | `gst_initialise()`, platform H.264 codec selection, optional OpenCV, `process_video()` loop, experimental codec prober |
| [video_reader](video_reader.md) | `video_reader.py` | legacy (core) | `VideoReader` — appsink-to-queue wrapper all readers (and `DataSchemeRTSP`) delegate to |
| [video_camera_reader](video_camera_reader.md) | `video_camera_reader.py` | legacy | `VideoCameraReader` — Linux V4L2 camera capture (mirrored, 10 fps hard-wired) |
| [video_example](video_example.md) | `video_example.py` | legacy | Stand-alone CLI copying video between file and network endpoints, optional OpenCV display |
| [video_file_reader](video_file_reader.md) | `video_file_reader.py` | legacy | `VideoFileReader` — MP4/QuickTime H.264 file decode to numpy frames |
| [video_file_writer](video_file_writer.md) | `video_file_writer.py` | legacy | `VideoFileWriter` — queued frames encoded to an H.264 file (output geometry currently hard-wired) |
| [video_stream_reader](video_stream_reader.md) | `video_stream_reader.py` | legacy | `VideoStreamReader` — RTSP or RTP/UDP receive via a hand-built (non `parse_launch`) pipeline |
| [video_stream_writer](video_stream_writer.md) | `video_stream_writer.py` | legacy | `VideoStreamWriter` — queued frames encoded and sent as RTP/UDP, or to RTMP |

## Example PipelineDefinitions

The two committed PipelineDefinitions under
`src/aiko_services/elements/gstreamer/pipelines/` (run with
`aiko_pipeline create …` — see [Pipeline](../../concepts/pipeline.md)):

| PipelineDefinition | Graph | Exercises |
|--------------------|-------|-----------|
| `rtsp_pipeline_0.json` (`p_rtsp_video_0`) | `(VideoReadRTSP VideoShow)` | [rtsp_io](rtsp_io.md) + [scheme_rtsp](scheme_rtsp.md) reading a network camera; `VideoShow` from `aiko_services.elements.media.video_io` for local display |
| `rtsp_pipeline_1.json` (`p_rtsp_video_1`) | `(VideoReadRTSP VideoShow VideoWriteFiles Metrics)` | As above, plus `VideoWriteFiles` (timestamped MP4 recording, `media.video_io`) and `Metrics` (`elements.observe.elements`) |

Both definitions carry placeholder camera credentials in their
`data_sources` URLs — override with
`-p VideoReadRTSP.data_sources rtsp://…` at launch.

## Package exports

`__init__.py` (declaration order follows static-reference dependencies)
re-exports:

- from `utilities`: `get_format`, `get_h264_decoder`,
  `get_h264_encoder`, `get_h264_encoder_options`, `GStreamerError`,
  `gst_initialise`, `enable_opencv`, `process_video`
- the classes `VideoReader`, `VideoCameraReader`, `VideoFileReader`,
  `VideoFileWriter`, `VideoStreamReader`, `VideoStreamWriter`,
  `VideoReadRTSP`, `DataSchemeRTSP`

Notes: importing the package initialises GStreamer as a side effect
(module-level `gst_initialise()` in `video_reader.py`), and registers
the `rtsp` scheme in `DataScheme.LOOKUP` (import side effect of
`scheme_rtsp.py`). `VideoWriteRTSP` (the stub in `rtsp_io.py`) is *not*
exported. `video_example.py` is a script, not an export.

## See also

- [Elements documentation index](../ReadMe.md)
- [Concepts guide](../../concepts/ReadMe.md) — in particular
  [PipelineElement](../../concepts/pipeline_element.md),
  [DataSource / DataTarget](../../concepts/data_source_target.md) and
  [DataScheme](../../concepts/scheme.md)
