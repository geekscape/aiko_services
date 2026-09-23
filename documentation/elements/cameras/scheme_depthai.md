---
title: DepthAI DataScheme
description: The depthai DataScheme — a Luxonis OAK camera by discovery or
  by address, scaled or native output, and a settle rule that waits for
  auto-focus and auto-exposure
type: concept
audience: [developers, end-users]
status: work-in-progress
ste: adapted
source:
  - src/aiko_services/elements/cameras/scheme_depthai.py
  - src/aiko_services/elements/cameras/pipelines/depthai_pipeline_0.json
  - src/aiko_services/elements/cameras/pipelines/depthai_pipeline_1.json
related: [scheme_camera, depthai_io, camera, scheme, data_source_target,
  stream, parameters, share]
version: "0.8-dev"
last_updated: 2026-09-23
---

# DepthAI DataScheme

## Overview

**`DataSchemeDepthAI`** implements the `depthai` URL scheme of the
[DataScheme](../../concepts/scheme.md) plug-in design, on the
[camera scheme base](scheme_camera.md). A `depthai://` URL names a
Luxonis OAK camera. The scheme opens it through `OakDCamera`, waits for
the camera's auto-focus and auto-exposure to settle, then delivers
frames.

The name is the SDK's, not a vendor model: every OAK camera that
DepthAI v3 drives is in scope.

**Why to use it**: select the camera in one parameter and leave the rest
of the Pipeline as it is:

```bash
cd src/aiko_services/elements/cameras

aiko_pipeline create pipelines/depthai_pipeline_0.json -s 1  \
  -p VideoReadDepthAI.data_sources "(depthai://<camera-address>)"
```

## For application developers

### Command-line usage

The scheme has no command line of its own. The
[VideoReadDepthAI](depthai_io.md) element selects it with a
`data_sources` URL:

```bash
# Discovery: the first camera found
-p VideoReadDepthAI.data_sources "(depthai://)"

# One camera: an IP address, a device id or a USB path
-p VideoReadDepthAI.data_sources "(depthai://<camera-address>)"

# Faster start when the scene is bright and still: fewer settle frames
-p VideoReadDepthAI.settle 5

# The auxiliary 3A stream beside a scaled output (off by default there)
-p VideoReadDepthAI.aux_stream true
```

### Public API

URL grammar accepted in `data_sources`:

```
depthai://                the first camera found
depthai://<address>       whatever dai.DeviceInfo() accepts
```

Parameters, in addition to the [common ones](scheme_camera.md):

| Parameter | Default | Meaning |
|-----------|---------|---------|
| `settle` | `30` | The upper bound on frames discarded while the 3A loops converge. The wait ends early once `lens_position` is engaged and stable and `iso_sensitivity` is stable, over three frames |
| `aux_stream` | `auto` | The 640x480 stream at 10 fps that keeps the sensor pipeline busy, so the 3A loops converge about four times faster. `auto` is `true` for the native output only, where the sensor runs slowly. Beside a 1920x1080 output at 8 fps it stalls the device after one frame |

Shared state adds `aux_stream` and the `sensor.*` values of the camera:
`exposure_us`, `iso_sensitivity`, `lens_position` and
`color_temperature_k`. `settled` reports `<n>_frames` when the rule was
met, or `timeout_<n>_frames` when the bound was reached. After a timeout
frames flow anyway, with a warning in the log.

Writable keys: `capture_timeout` and `log_frames`. Exposure and ISO stay
under the camera's own control until the control queue is wired.

Registration (module import side effect):

```python
aiko.DataScheme.add_data_scheme("depthai", DataSchemeDepthAI)
```

**Stream lifecycle behavior:** as the [camera scheme base](scheme_camera.md)
describes. The OAK specifics: the warm-up is a `SettleMonitor` fed with
each frame's metadata, and a missing SDK returns `StreamEvent.ERROR`
with the install line before any device access.

## For framework developers (internals)

### Design

```
 DataSchemeDepthAI(DataSchemeCamera)
   _camera_class()   -> OakDCamera, or RuntimeError with the diagnostic
   _extra_settings() -> aux_stream
   _start_warm_up()  -> SettleMonitor(settle)
```

- **A module global as the seam.** The scheme reads `OakDCamera` from
  its module at call time. The unit tests replace it with a fake camera
  and drive the whole scheme with no SDK.
- **The settle rule is data.** `SettleMonitor` sees only the metadata
  dictionary. The same rule serves any camera that reports a lens
  position and a sensitivity.

### Implementation notes

- The default settle of 30 frames is a bound, not a delay. At 8 fps a
  bright scene converges in a second or two. At 2 fps in a dark scene
  the bound is 15 seconds, and `settled` shows the progress.
- The scheme lives in `scheme_depthai.py` and the device in
  `camera_oak_d.py`, so a second DepthAI device class, for example a
  stereo pair, would share the scheme.

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `DataSchemeDepthAI` | Name the scheme; select and open `OakDCamera`; read `aux_stream`; start the 3A settle monitor | [DataSchemeCamera](scheme_camera.md) (base), `OakDCamera` ([depthai_io](depthai_io.md)), `SettleMonitor` ([camera](camera.md)) |

## Current limitations and roadmap

From the source To Do list:

- Writable `exposure_us` and `iso` through the OAK control queue

## Related concepts

- [scheme_camera](scheme_camera.md) — everything not OAK specific
- [depthai_io](depthai_io.md) — the element and the device layer
- [camera](camera.md) — `SettleMonitor` and the helpers
- [DataScheme](../../concepts/scheme.md) — the registry
- [scheme_gigev](scheme_gigev.md) — the sibling scheme
