---
title: GStreamer utilities
description: Shared helper module for the GStreamer elements — lazy
  GStreamer/PyGObject initialisation, platform H.264 codec selection,
  optional OpenCV enablement, and an experimental OpenCV codec prober
type: concept
audience: [developers, end-users]
status: work-in-progress
source:
  - src/aiko_services/elements/gstreamer/utilities.py
related: [scheme_rtsp, rtsp_io, video_reader, video_example,
  video_file_reader, video_file_writer, video_stream_reader,
  video_stream_writer, video_camera_reader]
version: "0.6"
last_updated: 2026-07-06
---

# GStreamer utilities

## Overview

`utilities.py` is the shared foundation of the
`aiko_services.elements.gstreamer` package — not a
[PipelineElement](../../concepts/pipeline_element.md) at all, but the
helper module both the current-style RTSP modules
([rtsp_io](rtsp_io.md), [scheme_rtsp](scheme_rtsp.md)) and the legacy
video wrappers ([video_reader](video_reader.md) and friends) depend on.
It owns three concerns:

1. **GStreamer initialisation** — `gst_initialise()` performs the lazy
   `gi.require_version` / `Gst.init([])` dance exactly once, optionally
   also loading `GstRtspServer` and `GLib` for RTSP serving.
2. **Platform codec selection** — Linux vs Mac OS X H.264
   encoder/decoder names (`avdec_h264`, `x264enc` / `vtenc_h264`) and
   the common pixel format (`"RGB"`).
3. **Optional OpenCV** — `enable_opencv()` imports `cv2` on request, and
   `process_video()` runs the legacy read-display-annotate-write loop
   used by [video_example](video_example.md).

It also contains an **experimental, currently broken** OpenCV codec
prober (`select_best_codec()` and helpers) — see Current limitations
and roadmap.

**Why you'd use it**: any new GStreamer-based element starts here —

```python
from aiko_services.elements.gstreamer import gst_initialise, get_h264_decoder
gst = gst_initialise()
pipeline = gst.parse_launch(f"rtspsrc … ! {get_h264_decoder()} ! …")
```

Requires either `pip install PyGObject` or
`apt-get install python3-gi` (from the source header).

## For application developers

### Command-line usage

The module has a `__main__` block intended to report the best available
OpenCV codec:

```bash
python3 src/aiko_services/elements/gstreamer/utilities.py
# intended output: "Using codec: H.264 (avc1) with extension .mp4"
```

**Currently broken**: the probe path calls the undefined
`has_h264_support()` and uses the `cv2` global without first calling
`enable_opencv()`, and `has_h263_support()` contains a leftover
`breakpoint()` — see roadmap. Treat the CLI as aspirational.

### Public API

Exported via `__all__` (and re-exported by the package `__init__.py`):

| Function | Effect |
|----------|--------|
| `gst_initialise(multiple_return_values=False, rtsp_server=False)` | Idempotently initialise GStreamer; returns `Gst`, or the 5-tuple `(Gst, GstBase, GLib, GstRtspServer, GObject)` when `multiple_return_values` or `rtsp_server` is set |
| `get_format()` | The common raw pixel format — currently always `"RGB"` |
| `get_h264_decoder()` | Platform H.264 decoder element name: `avdec_h264` (Linux and Mac OS X) |
| `get_h264_encoder()` | Platform H.264 encoder: `x264enc` (Linux) / `vtenc_h264` (Mac OS X) |
| `get_h264_encoder_options()` | Extra encoder options — Linux only: `tune=zerolatency speed-preset=ultrafast sliced-threads=true key-int-max=30`; empty string elsewhere |
| `GStreamerError` | Exception raised by the wrappers on pipeline construction/state failures |
| `enable_opencv()` | Import `cv2` if available, storing it in the module-global `cv2`; returns the module or `None` |
| `process_video(video_reader, video_writer)` | Blocking copy loop: read frames, optionally display and overlay the frame id via OpenCV (`q` to quit), write frames |

Not exported (module-internal / experimental): `has_h263_support()`,
`can_use_codec(fourcc_str, ext)`, `select_best_codec()`,
`operating_system`, and the codec lookup dicts.

Contract notes:

- `gst_initialise()` caches the `gi.repository` modules in
  module-level globals, so every caller shares one initialised
  GStreamer. Calling it with `multiple_return_values=True` but
  *without* `rtsp_server=True` returns `None` for the `GLib` and
  `GstRtspServer` slots unless a previous call loaded them.
- OpenCV is strictly opt-in: `process_video()` only displays when
  `enable_opencv()` has been called (as
  [video_example](video_example.md) does for its `-cv` option).

## For framework developers (internals)

### Design

```
                 utilities.py
   ┌───────────────────────────────────────────┐
   │ gst_initialise() ── lazy, global, shared  │◄── every gstreamer module
   │ platform table:  linux / mac_os_x         │
   │   h264_decoder / h264_encoder / format    │◄── pipeline builders
   │ enable_opencv() ── optional cv2 global    │◄── video_example -cv
   │ process_video() ── reader→(cv2)→writer    │◄── video_example main loop
   │ select_best_codec() ── OpenCV probe (WIP) │◄── __main__ (broken)
   └───────────────────────────────────────────┘
```

- **Global-module pattern.** GStreamer bindings and OpenCV are held as
  module globals rather than passed around — simple, but it means
  importing order and `enable_opencv()` timing are implicit contracts.
- **Platform table, not detection.** Codec choice is a two-entry dict
  keyed by `operating_system` (`linux` / `mac_os_x`, else `"unknown"` —
  which would `KeyError` on lookup); no capability probing on the
  GStreamer side.
- The OpenCV codec-probing trio (`can_use_codec()` writes a throwaway
  `__test*` file to test a `VideoWriter`) belongs conceptually to the
  media elements' OpenCV writers, not to GStreamer — a sign this module
  is accreting a second responsibility.

### Implementation notes

- `process_video()` assumes every queued frame has an `"image"` key
  when OpenCV is enabled; the `{"type": "EOS"}` frame emitted by
  [VideoReader](video_reader.md) has none, so the display path would
  `KeyError` at end-of-stream — the non-OpenCV path forwards EOS to the
  writer correctly. The loop also never returns normally except via the
  OpenCV `q` key.
- The module-level name `format` shadows the Python builtin within this
  module.
- `gst_initialise(rtsp_server=True)` forces
  `multiple_return_values=True` — callers wanting an RTSP server must
  unpack the 5-tuple, as `DataSchemeRTSP.create_targets()` does.

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `GStreamerError` (Exception) | Signal pipeline construction / state-change failures from the wrapper classes | [VideoReader](video_reader.md), [VideoStreamReader](video_stream_reader.md), [video_example](video_example.md) (catcher) |
| *(module functions)* | Initialise GStreamer once; supply platform codec/format names; opt-in OpenCV; run the legacy reader→writer copy loop; probe OpenCV codecs (WIP) | `gi` / `Gst` / `GstRtspServer`, `cv2`, every sibling module in this package |

## Current limitations and roadmap

The source has no formal To Do list; the observable gaps:

- **`has_h263_support()` contains a live `breakpoint()`** — invoking it
  drops into the debugger. The name also says H.263 while the body
  checks FFMPEG/x264 (H.264) support.
- **`select_best_codec()` calls `has_h264_support()`, which does not
  exist** (the defined name is `has_h263_support`) — the H.264 candidate
  path raises `NameError`.
- The codec probe and the `__main__` block use the `cv2` global without
  calling `enable_opencv()` first, so they fail with `AttributeError`
  (`None.getBuildInformation` / `None.VideoWriter_fourcc`) as shipped.
- `operating_system` other than Linux / Mac OS X (e.g. Windows) makes
  `get_h264_decoder()` / `get_h264_encoder()` raise `KeyError`.
- `process_video()` EOS-with-OpenCV `KeyError` (see Implementation
  notes).
- Roadmap direction: fold codec probing into the media elements' codec
  selection (compare `VideoWriteFiles` `FORMAT` parameter), and replace
  the platform table with capability detection.

## Related concepts

- [scheme_rtsp](scheme_rtsp.md) — main current-style consumer
  (`gst_initialise()`, `get_format()`, `get_h264_decoder()`)
- [rtsp_io](rtsp_io.md) — the RTSP PipelineElements above the scheme
- [video_reader](video_reader.md) — raises `GStreamerError`; module-level
  `gst_initialise()` at import
- [video_example](video_example.md) — drives `enable_opencv()` and
  `process_video()`
- [video_file_reader](video_file_reader.md),
  [video_file_writer](video_file_writer.md),
  [video_stream_reader](video_stream_reader.md),
  [video_stream_writer](video_stream_writer.md),
  [video_camera_reader](video_camera_reader.md) — legacy wrappers built
  on these helpers
