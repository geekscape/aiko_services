---
title: Luxonis OAK camera source
description: VideoReadDepthAI — a DataSource PipelineElement that reads a
  Luxonis OAK camera through the depthai DataScheme and the DepthAI v3 SDK
type: concept
audience: [developers, end-users]
status: work-in-progress
ste: adapted
source:
  - src/aiko_services/elements/cameras/depthai_io.py
  - src/aiko_services/elements/cameras/camera_oak_d.py
  - src/aiko_services/elements/cameras/pipelines/depthai_pipeline_0.json
  - src/aiko_services/elements/cameras/pipelines/depthai_pipeline_1.json
related: [scheme_depthai, scheme_camera, camera, image_dewarp,
  data_source_target, pipeline_element, scheme, parameters, share]
version: "0.8-dev"
last_updated: 2026-09-23
---

# Luxonis OAK camera source

## Overview

**`VideoReadDepthAI`** is a [DataSource](../../concepts/data_source_target.md)
[PipelineElement](../../concepts/pipeline_element.md) for Luxonis OAK
cameras, through the DepthAI v3 SDK. It emits the standard
`images: [image]` frame data, NumPy `uint8` HxWx3 RGB. The
[depthai DataScheme](scheme_depthai.md) owns the camera, its warm-up and
the shared state. The element is thin, as `VideoReadRTSP` and
`SyntheticVideoRead` are.

The device layer `camera_oak_d.py` delivers a scaled output of any size
from the ISP, or the sensor's native 4000x3000. An auxiliary 640x480
stream keeps the sensor busy, so auto-focus and auto-exposure converge
about four times faster. It is skipped when the main output is that
size or smaller, because two identical outputs crashed the SDK.

**Why to use it**: put an OAK camera into any video Pipeline by changing
one element:

```bash
pip install "aiko_services[depthai]"
cd src/aiko_services/elements/cameras

aiko_pipeline create pipelines/depthai_pipeline_0.json -s 1   # view live
```

## For application developers

### Command-line usage

All commands run from `src/aiko_services/elements/cameras`.

```bash
# The first OAK camera on the network: 1920x1080 at 25 fps, 10 s or "x"
aiko_pipeline create pipelines/depthai_pipeline_0.json -s 1

# One camera, by IP address or device id
aiko_pipeline create pipelines/depthai_pipeline_0.json -s 1  \
  -p VideoReadDepthAI.data_sources "(depthai://<camera-address>)"

# The video regime of a store / forward Pipeline: 1080p at 8 fps
aiko_pipeline create pipelines/depthai_pipeline_0.json -s 1  \
  -p VideoReadDepthAI.frame_rate 8 -p CaptureLimit.duration 10m

# Stills: native 4000x3000 at 2 fps, dewarped, three PNG files
aiko_pipeline create pipelines/depthai_pipeline_1.json -s 1
```

Network notes for the PoE models: discovery uses UDP port 11491 on the
same subnet, and data flows on TCP 11490. Without DHCP the camera falls
back to a link-local address, so give the host interface one too. On
macOS, grant Local Network permission to the process. A second active
interface can break discovery, so turn Wi-Fi off, or give the address.
A device reboots when its handle closes and is not discoverable again
for some seconds, so `open()` retries the boot for up to 30 seconds.

### Public API

| Class | Kind | Inputs → Outputs | Parameters |
|-------|------|------------------|------------|
| `VideoReadDepthAI` | DataSource | `images: [image]` → `images: [image]` | `data_sources` (`(depthai://)` or `(depthai://<address>)`), `resolution` (`1920x1080`), `frame_rate` (`25.0`), `settle` (`30`), `aux_stream` (`true`), `resize_mode`, `rate`, `capture_timeout`, `log_frames`, `media_type` |

Service protocol: `video_read_depthai:0`.

Live shared state: the keys of the [camera scheme base](scheme_camera.md)
(`state`, `device_id`, `settled`, `frames`, `measured_fps`,
`capture_timeouts`, `last_frame_utc`, `last_error`, `sensor.*`) plus
`aux_stream`. The `sensor.*` group carries the camera's own 3A values
each frame: `exposure_us`, `iso_sensitivity`, `lens_position` and
`color_temperature_k`. Writable keys: `capture_timeout` and
`log_frames`.

**Stream lifecycle behavior:**

- `start_stream()` is the `DataSource` base method. It selects the
  [depthai DataScheme](scheme_depthai.md) from the `data_sources` URL.
  The scheme opens the camera and starts the frame generator.
- `process_frame()` applies the optional `media_type` conversion and
  passes the images through.
- `stop_stream()` calls the scheme's `destroy_sources()`, which stops
  the generator and closes the camera.

## For framework developers (internals)

### Design

```
 VideoReadDepthAI (thin DataSource)
   start_stream() ── DataScheme.LOOKUP["depthai"] ── DataSchemeDepthAI
                                                        │ OakDCamera
                                                        │   dai.Device
                                                        │   Camera node
                                                        │   aux 640x480
                                                        │   main output
   process_frame(images) ◄── {"images": [image]} ◄──── frame generator
```

- **Scaled or native output.** A `resolution` below 4000x3000 is a
  `requestOutput()` of that size with the resize mode. `native` or
  `full` is `requestFullResolutionOutput()` with the highest resolution
  flag, without which the output is capped below 4000x3000.
- **NV12 on the link.** Frames are requested as NV12, 1.5 bytes per
  pixel, and converted on the host. A `BGR888i` request at 1920x1080 and
  25 fps is 155 MB/s, more than a gigabit PoE link carries, and the
  device crashed under it. NV12 halves that twice.
- **Small non-blocking queues.** A 12 megapixel NV12 frame is 18 MB. The
  output queue holds two frames and drops the oldest.
- **Bounded capture.** `queue.get(timedelta)` returns `None` on timeout,
  which becomes `CaptureTimeout`, so the Stream can always be destroyed.

### Implementation notes

- `depthai` is a guarded import. `OakDCamera.available()` is false
  without it, and the scheme reports the install line as a diagnostic.
- `getCvFrame()` converts NV12 to BGR on the host, and a second copy
  flips it to RGB. A one-step conversion to RGB would save the copy and
  is on the To Do list.
- The element pre-populates only status keys in share, never a parameter
  name. The framework reads share before the element parameter of the
  same name, so a placeholder value there would replace the parameter.

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `VideoReadDepthAI` | Own the Stream lifecycle as a DataSource; optional `media_type` conversion | [DataSource](../../concepts/data_source_target.md) (base), [depthai DataScheme](scheme_depthai.md) |
| `OakDCamera` | Open a device, build the DepthAI pipeline with the auxiliary and the main output, capture with a timeout, report the 3A metadata, close | the [Camera](camera.md) contract, the `depthai` SDK |

## Current limitations and roadmap

From the source To Do list:

- Manual exposure and ISO through the camera control queue, which would
  make `exposure_us` writable as it is for the GigE camera
- A one-step NV12 to RGB conversion, to save the BGR to RGB copy
- Stereo depth and IMU outputs as further Frame data

Known limits: the scaled output path was designed from the SDK
documentation and is confirmed on hardware per size and rate. An
unsupported combination surfaces as a diagnostic from `start_stream()`.

## Related concepts

- [scheme_depthai](scheme_depthai.md) — the URL, the OAK parameters and
  the settle rule
- [scheme_camera](scheme_camera.md) — the common parameters and the
  dashboard keys
- [camera](camera.md) — the device contract
- [image_dewarp](image_dewarp.md) — used by `depthai_pipeline_1.json`
- [gigev_io](gigev_io.md) — the other machine-vision camera
- [gstreamer/rtsp_io](../gstreamer/rtsp_io.md) — the network camera
- [Control elements](../control/elements.md) — `CaptureLimit`
