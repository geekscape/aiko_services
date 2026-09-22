---
title: Camera device contract
description: The Camera contract and the helpers that every camera
  DataScheme shares — parameter coercion, resolution planning, host resize,
  the settle and auto-expose warm-up helpers and the rate meter
type: concept
audience: [developers]
status: work-in-progress
ste: adapted
source:
  - src/aiko_services/elements/cameras/camera.py
related: [scheme_camera, scheme_depthai, scheme_gigev, data_source_target,
  scheme, stream, parameters]
version: "0.8-dev"
last_updated: 2026-09-23
---

# Camera device contract

## Overview

`camera.py` holds what every camera has in common, with no camera SDK and
no OpenCV imported. The **`Camera`** class is the duck-typed device
contract that a device layer implements, for example `OakDCamera` in
[depthai_io](depthai_io.md) or `IdsPeakCamera` in
[gigev_io](gigev_io.md). The [camera scheme base](scheme_camera.md), the
warm-up helpers, an integration test and the unit-test fake all use only
this contract. Thus a new camera SDK is one new device class.

The pure helpers coerce the camera parameters and plan how a sensor
delivers a requested size. They also resize on the host and run the
warm-up one step at a time.

**Why to use it**: add a camera SDK, or test a scheme without hardware:

```python
from aiko_services.elements.cameras import camera

class MyCamera(camera.Camera):
    def open(self): ...
    def capture(self, timeout_s=camera.CAPTURE_TIMEOUT_S): ...  # RGB, dict
    def close(self): ...
```

## For application developers

### Command-line usage

`camera.py` has no command line of its own. Its parameters appear on the
camera elements. All camera elements accept them in the same forms:

```bash
cd src/aiko_services/elements/cameras

aiko_pipeline create pipelines/depthai_pipeline_0.json -s 1  \
  -p VideoReadDepthAI.resolution 1280x720  \
  -p VideoReadDepthAI.frame_rate 25/1  \
  -p VideoReadDepthAI.settle 3s
```

### Public API

The device contract:

| Method | Meaning |
|--------|---------|
| `Camera(address, resolution, frame_rate, resize_mode, trigger, aux_stream, logger)` | The requested settings. `address` `None` means the first camera found. `resolution` `None` means the sensor's native size |
| `open()` | Connect and configure. Raises `RuntimeError` with the reason |
| `capture(timeout_s)` | Returns `(image, metadata)`: a NumPy `uint8` HxWx3 RGB image and a dictionary such as `exposure_us`, `gain`, `lens_position`. Raises `CaptureTimeout` when no frame arrives within `timeout_s` |
| `close()` | Release the device. Safe to call twice |
| `device_id()` | The device's own identifier, or `None` |
| `resolution()`, `frame_rate()` | The actual values, known after `open()` or the first frame |
| `set_exposure(exposure_us)`, `set_gain(gain)` | Return the actual value the camera accepted |
| `available()`, `diagnostic()`, `sdk_version()` | Class methods: did the SDK import, what to install, which version |

A bounded `capture()` matters. The frame generator holds the Stream lock
while it runs, and `destroy_stream()` needs that lock. A device wait that
never returns would keep the Stream alive for ever. The `lock` attribute
serializes `capture()` against the setters, which the dashboard handler
calls from the event-loop thread.

The pure helpers, each raising `ValueError` with the parameter name:

| Function | Meaning |
|----------|---------|
| `parse_resolution(value)` | `"1920x1080"`, `(w, h)`, `"native"` or `"full"` → `(w, h)`, or `None` for native |
| `parse_frame_rate(value)` | `25`, `"25"`, `"25.0"` or a fraction `"25/1"` → a float above zero |
| `parse_settle(value, frame_rate)` | A frame count `"30"`, a time `"3s"`, or `0` / `"none"` → frames |
| `parse_bool(value)`, `parse_resize_mode(value)` | `true` / `false` forms; `crop`, `letterbox` or `stretch` |
| `plan_resolution(native, target, mode, decimations)` | How a sensor delivers `target`: an area of interest, a decimation factor and a host resize size, or `None` |
| `resize_image(image, size, mode)` | Host-side resize: `crop` keeps the aspect ratio and crops, `letterbox` pads black, `stretch` ignores the aspect ratio |
| `auto_expose(camera, logger, ...)` | A generator: each step captures, meters the 99th percentile and adjusts exposure first, then gain. Yields `(done, exposure_us, gain)` |
| `SettleMonitor(max_frames)`, `CountdownSettle(frames)` | Warm-up objects with `feed(metadata) -> done`. The monitor is done once `lens_position` and `iso_sensitivity` are stable over three frames |
| `RateMeter(window_s)` | `tick()` returns frames per second over a sliding window |
| `share_token(text)`, `utc_now()` | One share token; ISO 8601 UTC to the second with a `Z` |

Constants: `NATIVE_RESOLUTION` (4000x3000, both supported sensors),
`DEFAULT_RESOLUTION` (`1920x1080`), `DEFAULT_FRAME_RATE` (25.0),
`CAPTURE_TIMEOUT_S` (1.0) and `CAPTURE_TIMEOUT_LIMIT` (10).

## For framework developers (internals)

### Design

```
 DataSchemeCamera (scheme_camera.py)         one instance per Stream
   │ parse_*()          parameters -> settings
   │ camera_class(...)  open()               the device layer
   │ create_frames() ── frame generator thread
   │                      capture(timeout) ──► (image, metadata)
   │                      warm-up: auto_expose() steps, SettleMonitor
   │                      OKAY {"images": [image]}
   ▼
 Camera contract (this module)               OakDCamera | IdsPeakCamera |
                                             AravisCamera | FakeCamera
```

- **The warm-up runs one step per generator call.** `auto_expose()` is a
  generator and the settle objects are fed one frame at a time. Thus
  `start_stream()` returns at once, and the Stream can be destroyed while
  a camera still converges.
- **Resolution planning is pure.** `plan_resolution()` decides the area
  of interest, the decimation factor and the host resize with no device
  access. The device layer applies the plan and reports what it could
  do.

### Implementation notes

- `resize_image()` imports `cv2` lazily. The package imports with no
  OpenCV, which the unit test `test_package_imports_without_sdks_or_cv2`
  proves in a subprocess.
- `auto_expose()` meters the 99th percentile of the image, so white
  targets in a mostly dark scene do not clip. Exposure rises first, to
  the cap, then gain. Eight steps at most.
- `SettleMonitor` copies the rule of the spike this code came from: the
  lens engaged and within two positions, ISO within five percent, over
  three frames.

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `Camera` | Hold the requested settings; define `open()`, `capture()`, `close()` and the setters; serialize capture and setters with a lock | `DataSchemeCamera` ([scheme_camera](scheme_camera.md)), the device classes |
| `SettleMonitor`, `CountdownSettle`, `auto_expose()` | Warm-up, one step per call | `DataSchemeCamera`, the `Camera` contract |
| `parse_*()`, `plan_resolution()`, `resize_image()`, `RateMeter` | Pure helpers, unit tested in `tests/unit/test_camera.py` | NumPy, `cv2` (lazy) |

## Current limitations and roadmap

From the source To Do list:

- Device-clock timestamps: both SDKs stamp their frames, and
  `stream.variables["timestamps"]` still holds the time of dequeue
- `NATIVE_RESOLUTION` is the size of the two sensors used so far. A
  device layer reads the real maximum from the camera when it can

## Related concepts

- [scheme_camera](scheme_camera.md) — the scheme that drives this
  contract
- [scheme_depthai](scheme_depthai.md), [scheme_gigev](scheme_gigev.md)
  — the two camera schemes
- [DataSource / DataTarget](../../concepts/data_source_target.md) — the
  element side
- [Parameters](../../concepts/parameters.md) — how values reach
  `parse_*()`
- [Stream](../../concepts/stream.md) — the lock that bounds `capture()`
