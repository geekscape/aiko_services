---
title: Camera PipelineElements index
description: Index of the camera PipelineElement concept documents — the
  depthai and gigev DataSchemes for Luxonis OAK and GigE Vision cameras,
  the shared camera contract, the ImageDewarp element and the committed
  example PipelineDefinitions
type: index
audience: [developers, end-users]
status: work-in-progress
ste: adapted
source:
  - src/aiko_services/elements/cameras
related: [pipeline_element, data_source_target, scheme, pipeline, share]
version: "0.8-dev"
last_updated: 2026-09-23
---

# Camera PipelineElements index

One concept document per Python module in
`src/aiko_services/elements/cameras/`: machine-vision cameras as
[DataSource](../../concepts/data_source_target.md)
[PipelineElements](../../concepts/pipeline_element.md), one
[DataScheme](../../concepts/scheme.md) per camera SDK. A
PipelineDefinition selects the camera by its DataSource element and its
`data_sources` URL alone. The RTSP camera of
[gstreamer/rtsp_io](../gstreamer/rtsp_io.md), the OAK camera and the GigE
camera are interchangeable in a graph.

Every module imports without its camera SDK. The SDK is a guarded import,
and its absence is reported as a diagnostic when the scheme is used. Thus
the package, its tests and its PipelineDefinitions load on a machine with
no camera at all.

Navigation: [elements index](../ReadMe.md) ·
[concepts guide](../../concepts/ReadMe.md)

## Module documents

| Document | Summary |
|----------|---------|
| [camera](camera.md) | The `Camera` device contract, the parameter coercion, resolution planning, host resize, the warm-up helpers and the rate meter shared by every camera |
| [depthai_io](depthai_io.md) | `VideoReadDepthAI` — Luxonis OAK cameras through the DepthAI v3 SDK |
| [gigev_io](gigev_io.md) | `VideoReadGigE` — GenICam GigE Vision cameras through IDS peak, or Aravis as an experimental backend |
| [image_dewarp](image_dewarp.md) | `ImageDewarp` — undistorts images with an OpenCV lens calibration |
| [scheme_camera](scheme_camera.md) | `DataSchemeCamera` — the base of the camera schemes: parameters, warm-up, the frame generator and the dashboard state |
| [scheme_depthai](scheme_depthai.md) | `depthai://` DataScheme — discovery or one OAK camera by address, scaled or native output, 3A settle |
| [scheme_gigev](scheme_gigev.md) | `gigev://` DataScheme — backend selection, the stills and video regimes, exposure and gain with an auto-expose warm-up |

## Example PipelineDefinitions

The three committed PipelineDefinitions under
`src/aiko_services/elements/cameras/pipelines/`. Each uses a placeholder
URL that discovers the first camera. Run them from
`src/aiko_services/elements/cameras`.

| PipelineDefinition | Module document(s) | Purpose |
|--------------------|--------------------|---------|
| `depthai_pipeline_0.json` | [depthai_io](depthai_io.md), [scheme_depthai](scheme_depthai.md), [control elements](../control/elements.md), [image_io](../media/image_io.md), [video_io](../media/video_io.md) | OAK camera 1920x1080 at 8 fps → `CaptureLimit` (10 s) → resize → display |
| `depthai_pipeline_1.json` | [depthai_io](depthai_io.md), [image_dewarp](image_dewarp.md), [control elements](../control/elements.md), [image_io](../media/image_io.md) | OAK camera native 4000x3000 at 2 fps → dewarp → three PNG files |
| `depthai_pipeline_2.json` | [depthai_io](depthai_io.md), [control elements](../control/elements.md), [video_io](../media/video_io.md) | OAK camera 1920x1080 at 8 fps → `CaptureLimit` (30 s) → MP4 file, no display |
| `gigev_pipeline_0.json` | [gigev_io](gigev_io.md), [scheme_gigev](scheme_gigev.md), [control elements](../control/elements.md), [image_io](../media/image_io.md), [video_io](../media/video_io.md) | GigE camera 1920x1080 at 8 fps → `CaptureLimit` (10 s) → resize → display |

`data_in/calibration_identity.json` is a zero-distortion placeholder
calibration for `ImageDewarp`, so `depthai_pipeline_1.json` runs before
a real calibration exists.

## Package exports

`__init__.py` re-exports, in dependency order, the helpers of
[camera](camera.md) and the device classes `AravisCamera`,
`IdsPeakCamera` and `OakDCamera`. Then come the schemes
`DataSchemeCamera`, `DataSchemeDepthAI` and `DataSchemeGigE` with
`select_backend()`. Last come `Dewarper`, `ImageDewarp`,
`load_calibration()`, `VideoReadDepthAI` and `VideoReadGigE`.

Importing the package registers the `depthai` and `gigev` schemes in
`DataScheme.LOOKUP`. It imports no camera SDK and no OpenCV: `cv2` is
imported lazily where a resize or a dewarp needs it.

## Suggested reading order

1. [scheme_camera](scheme_camera.md) — the parameters, the shared state
   and the threads common to every camera
2. [depthai_io](depthai_io.md) with [scheme_depthai](scheme_depthai.md),
   or [gigev_io](gigev_io.md) with [scheme_gigev](scheme_gigev.md) — the
   camera at hand
3. [image_dewarp](image_dewarp.md) — when the lens distorts
4. [camera](camera.md) — the device contract, to add a camera SDK
