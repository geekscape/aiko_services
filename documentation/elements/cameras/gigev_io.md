---
title: GigE Vision camera source
description: VideoReadGigE — a DataSource PipelineElement that reads a
  GenICam GigE Vision camera through the gigev DataScheme, with IDS peak
  or the experimental Aravis backend
type: concept
audience: [developers, end-users]
status: work-in-progress
ste: adapted
source:
  - src/aiko_services/elements/cameras/gigev_io.py
  - src/aiko_services/elements/cameras/camera_ids_peak.py
  - src/aiko_services/elements/cameras/camera_aravis.py
  - src/aiko_services/elements/cameras/pipelines/gigev_pipeline_0.json
  - src/aiko_services/elements/cameras/pipelines/gigev_pipeline_1.json
related: [scheme_gigev, scheme_camera, camera, data_source_target,
  pipeline_element, scheme, parameters, share]
version: "0.8-dev"
last_updated: 2026-09-23
---

# GigE Vision camera source

## Overview

**`VideoReadGigE`** is a [DataSource](../../concepts/data_source_target.md)
[PipelineElement](../../concepts/pipeline_element.md) for GenICam GigE
Vision cameras. It emits the standard `images: [image]` frame data,
NumPy `uint8` HxWx3 RGB. The [gigev DataScheme](scheme_gigev.md) owns
the camera backend, the exposure warm-up and the shared state. The
element is thin.

Two device layers implement the [Camera](camera.md) contract. **IDS
peak** (`camera_ids_peak.py`) is the working backend, on Linux and
Windows. **Aravis** (`camera_aravis.py`) is the vendor-independent
implementation and the only path on macOS. It is experimental: with the
tested camera firmware it discovers and controls the camera, but no
frames arrive.

**Why to use it**: an industrial camera in any video Pipeline by
changing one element:

```bash
pip install "aiko_services[ids_peak]"     # Linux, plus the native IDS SDK
cd src/aiko_services/elements/cameras

aiko_pipeline create pipelines/gigev_pipeline_0.json -s 1     # view live
```

## For application developers

### Command-line usage

All commands run from `src/aiko_services/elements/cameras`.

```bash
# The first camera found: 1920x1080 at 8 fps, exposure by auto-expose
aiko_pipeline create pipelines/gigev_pipeline_0.json -s 1

# One camera, by a substring of its name, key or serial number
aiko_pipeline create pipelines/gigev_pipeline_0.json -s 1  \
  -p VideoReadGigE.data_sources "(gigev://<camera-address>)"

# Stills: native 4000x3000, one software trigger a second, fixed exposure
aiko_pipeline create pipelines/gigev_pipeline_0.json -s 1  \
  -p VideoReadGigE.resolution native -p VideoReadGigE.frame_rate 1  \
  -p VideoReadGigE.exposure_us 20000 -p VideoReadGigE.gain 2.0

# The video regime of a store / forward Pipeline: 1080p at 8 fps for
# 30 s into data_out/gigev_0.mp4, with no display (a headless host)
aiko_pipeline create pipelines/gigev_pipeline_1.json -s 1

# A manual-focus lens: watch sensor.sharpness on aiko_dashboard and
# turn the focus ring until it peaks
aiko_pipeline create pipelines/gigev_pipeline_0.json -s 1  \
  -p VideoReadGigE.focus_assist true -p CaptureLimit.duration 10m

# The Aravis backend, experimental
aiko_pipeline create pipelines/gigev_pipeline_0.json -s 1  \
  -p VideoReadGigE.backend aravis
```

Install notes for IDS peak: the pip extra brings the Python bindings.
The native IDS peak SDK, from the vendor, gives the drivers and the
GenTL producer, a `.cti` file. The loader finds it through
`GENICAM_GENTL64_PATH`, which the package sets for new login shells
only, so the device layer searches the standard install locations too.
Give the camera an IP address first, with the IDS peak Cockpit or the
IDS IP Config tool. Full 12 megapixel frames at more than a few frames
per second need a NIC MTU of 9000 and a larger receive buffer.

### Public API

| Class | Kind | Inputs → Outputs | Parameters |
|-------|------|------------------|------------|
| `VideoReadGigE` | DataSource | `images: [image]` → `images: [image]` | `data_sources` (`(gigev://)` or `(gigev://<address>)`), `backend` (`auto`), `resolution` (`1920x1080`), `frame_rate` (`8.0`), `trigger` (`auto`), `exposure_us` (`auto`: the camera's own when it has one), `gain`, `max_exposure_us` (`auto`), `brightness_target` (`auto`), `white_balance` (`auto`), `settle` (`2`), `resize_mode`, `rate`, `capture_timeout`, `log_frames`, `focus_assist` (`false`), `media_type` |

Service protocol: `video_read_gigev:0`.

Live shared state: the keys of the [camera scheme base](scheme_camera.md)
plus `backend`, `trigger`, `exposure_mode`, `exposure_us`, `gain`,
`max_exposure_us`, `brightness_target` and `white_balance`. The camera's
live values add `sensor.auto_status`, `sensor.white_balance`,
`sensor.temperature_c` and `sensor.packets_dropped`. Writable keys:
`exposure_us` (a number, `auto`, `camera` or `host`), `gain`,
`max_exposure_us`, `brightness_target`, `white_balance`,
`capture_timeout`, `log_frames` and `focus_assist`. A written value acts
on the open camera at once, and what the camera accepted is published
back.

**Stream lifecycle behavior:**

- `start_stream()` is the `DataSource` base method. It selects the
  [gigev DataScheme](scheme_gigev.md) from the `data_sources` URL. The
  scheme selects the backend, opens the camera and starts the frame
  generator, which runs the auto-expose steps first when no exposure is
  given.
- `process_frame()` applies the optional `media_type` conversion and
  passes the images through.
- `stop_stream()` calls the scheme's `destroy_sources()`, which stops
  the generator and closes the camera.

## For framework developers (internals)

### Design

```
 VideoReadGigE (thin DataSource)
   start_stream() ── DataScheme.LOOKUP["gigev"] ── DataSchemeGigE
                                                     │ select_backend()
                                                     │ IdsPeakCamera
                                                     │ | AravisCamera
   process_frame(images) ◄── {"images": [image]} ◄── frame generator
```

- **Two regimes in the device layer.** With `trigger` `software`, one
  software trigger per `capture()`: fresh exposures, and an idle link
  between stills. With `trigger` `off`, free-running acquisition at
  `AcquisitionFrameRate`. The scheme picks the regime from `frame_rate`
  unless told otherwise.
- **Resolution in three parts.** `plan_resolution()` gives an area of
  interest, a decimation factor and a host resize. The IDS layer applies
  the offsets, the size and the `Decimation*` or `Binning*` nodes it
  finds, and resizes on the host for the remainder.
- **Bounded capture.** `WaitForFinishedBuffer(ms)` with the timeout
  becomes `CaptureTimeout`. An incomplete buffer names the network
  tuning in its error.

### Implementation notes

- Both SDKs are guarded imports. `IdsPeakCamera.available()` and
  `AravisCamera.available()` tell `select_backend()` what can be used.
- The IDS layer loads the `Default` user set first, so every run starts
  from the same camera state. That user set has no auto-exposure, which
  is why the scheme brings its own.
- Node names for frame rate, decimation and binning are probed in order,
  with a warning and a fallback when a camera lacks them.
- The Aravis demosaic uses OpenCV's `BayerBG` code for GenICam
  `BayerRG8`. Verify the colors on a new camera model.

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `VideoReadGigE` | Own the Stream lifecycle as a DataSource; optional `media_type` conversion | [DataSource](../../concepts/data_source_target.md) (base), [gigev DataScheme](scheme_gigev.md) |
| `IdsPeakCamera` | Discover and open through IDS peak; apply the area of interest, decimation, trigger and frame rate; capture with a timeout and debayer; set exposure and gain; close | the [Camera](camera.md) contract, `ids_peak`, `ids_peak_ipl` |
| `AravisCamera` | The same through Aravis 0.8, experimental | the [Camera](camera.md) contract, PyGObject, Aravis |

## Current limitations and roadmap

From the source To Do list:

- Retest Aravis streaming after the camera firmware update
- IDS peak IPL is deprecated in favor of ICV: migrate the debayer
- Verify the frame rate and decimation node names on more models
- Binning through `Aravis.Camera.set_binning()`

Known limits: IDS peak has no macOS support, so on macOS only the
experimental Aravis path exists. The unit tests cover the scheme with a
fake backend on every platform, and the integration test needs a Linux
host with a camera.

## Related concepts

- [scheme_gigev](scheme_gigev.md) — the URL, the backends and the
  regimes
- [scheme_camera](scheme_camera.md) — the common parameters and the
  dashboard keys
- [camera](camera.md) — the device contract and `auto_expose()`
- [depthai_io](depthai_io.md) — the other machine-vision camera
- [gstreamer/rtsp_io](../gstreamer/rtsp_io.md) — the network camera
