---
title: GigE Vision DataScheme
description: The gigev DataScheme — backend selection between IDS peak and
  Aravis, the stills and video regimes through the trigger rule, and
  exposure and gain with an auto-expose warm-up
type: concept
audience: [developers, end-users]
status: work-in-progress
ste: adapted
source:
  - src/aiko_services/elements/cameras/scheme_gigev.py
  - src/aiko_services/elements/cameras/pipelines/gigev_pipeline_0.json
related: [scheme_camera, gigev_io, camera, scheme, data_source_target,
  stream, parameters, share]
version: "0.8-dev"
last_updated: 2026-09-23
---

# GigE Vision DataScheme

## Overview

**`DataSchemeGigE`** implements the `gigev` URL scheme of the
[DataScheme](../../concepts/scheme.md) plug-in design, on the
[camera scheme base](scheme_camera.md). A `gigev://` URL names a GenICam
GigE Vision camera. The scheme selects a backend, opens the camera,
brings the exposure to a usable value, then delivers frames. A camera
with its own auto exposure and white balance runs them. The picture
then follows the light all day, and the host does less image work.

The name is the interface's, not a vendor's: any GigE Vision camera that
IDS peak or Aravis can drive is in scope.

**Why to use it**: select the camera in one parameter, and tune the
exposure from the dashboard while it runs:

```bash
cd src/aiko_services/elements/cameras

aiko_pipeline create pipelines/gigev_pipeline_0.json -s 1  \
  -p VideoReadGigE.data_sources "(gigev://<camera-address>)"
```

## For application developers

### Command-line usage

The scheme has no command line of its own. The
[VideoReadGigE](gigev_io.md) element selects it with a `data_sources`
URL:

```bash
# The first camera found, IDS peak when it imports, else Aravis
-p VideoReadGigE.data_sources "(gigev://)"

# A backend by name
-p VideoReadGigE.backend peak

# Fixed exposure and gain instead of the auto-expose warm-up
-p VideoReadGigE.exposure_us 20000 -p VideoReadGigE.gain 2.0

# Video of a moving scene: auto-expose, but never longer than 30 ms
-p VideoReadGigE.max_exposure_us 30000

# Free-running video at 1 fps, where the rule would trigger stills
-p VideoReadGigE.frame_rate 1 -p VideoReadGigE.trigger off
```

### Public API

URL grammar accepted in `data_sources`:

```
gigev://                       the first camera found
gigev://<address-substring>    IDS peak: a substring of the display name,
                               the key or the serial number
                               Aravis: the device id or IP address
```

Parameters, in addition to the [common ones](scheme_camera.md):

| Parameter | Default | Meaning |
|-----------|---------|---------|
| `backend` | `auto` | `auto`, `peak` or `aravis`. `auto` takes IDS peak when its bindings imported, else Aravis |
| `trigger` | `auto` | `software`: one trigger per frame, so each exposure is fresh and the link idles between stills. `off`: free-running at `frame_rate`. `auto` takes `software` at 2 fps and below, else `off` |
| `exposure_us` | `auto` | A number: a fixed exposure in microseconds. `camera`: the camera's own continuous auto exposure and gain, capped by `max_exposure_us`, with `frame_rate` held. `host`: the highlight-based auto-expose runs once before the first frame, then the exposure stays fixed. `auto` takes `camera` when the camera has its own and free-runs, else `host` |
| `gain` | none | Analog gain, applied with a fixed `exposure_us` |
| `brightness_target` | `auto` | The target of the camera's auto exposure, from 3 to 253. `auto` keeps the camera's own, 150 on IDS cameras. Higher is brighter |
| `white_balance` | `auto` | `auto`: the camera's continuous white balance, when it has one. `once`: balance once, then hold. `off` |
| `max_exposure_us` | `auto` | The auto-expose ceiling. `auto` is 80 % of the frame period when free-running, 100 ms at 8 fps, and 250 ms with the software trigger. An exposure longer than the frame period slows the camera below `frame_rate`. A moving scene blurs well before that, so a video Pipeline often sets it lower, for example `30000` |
| `settle` | `2` | Frames discarded after an exposure change. With the camera's auto exposure, frames are discarded until its status stops converging, at most `max(settle, 30)`. `0` turns that off |

In software-trigger mode `rate` defaults to `frame_rate`: the frame
generator triggers one exposure per delivered frame.

Shared state adds `backend`, `trigger`, `exposure_mode` (`camera`,
`host` or `fixed`), `exposure_us`, `gain`, `max_exposure_us`,
`brightness_target` and `white_balance`. The configuration keys hold the
configured values, so a later Stream at another frame rate gets its own
defaults. After the host auto-expose, `exposure_us` holds the value it
settled on. The camera's live values are the `sensor.*` keys:
`exposure_us`, `gain`, `auto_status` (for example `AecActive`, `Done`,
`AecStuckHigh`) and `white_balance` (`Active`, `Done`) each frame, and
`temperature_c` and `packets_dropped` once a second.

Writable keys: `exposure_us` (a number, `auto`, `camera` or `host`),
`gain` (with a fixed exposure only), `max_exposure_us`,
`brightness_target`, `white_balance`, and the base's `capture_timeout`,
`log_frames` and `focus_assist`. A written value acts on the open camera
at once, and the frames of the change are discarded. The next Stream
starts from the written value. A fixed exposure longer than the frame
period logs a warning.

Registration (module import side effect):

```python
aiko.DataScheme.add_data_scheme("gigev", DataSchemeGigE)
```

`select_backend(name)` is exported: it returns the backend name and the
device class, or raises `RuntimeError` that names what to install.

**Stream lifecycle behavior:** as the [camera scheme base](scheme_camera.md)
describes. The GigE specifics: with the host auto-expose, the frame
generator runs its steps before any frame. There are at most eight
steps. After each one, the frames the camera had already queued are
skipped. A scene that stays too dark gets a warning. With the camera's auto
exposure, frames are discarded until it has converged. A missing backend
returns `StreamEvent.ERROR` that names every SDK and its install line.

## For framework developers (internals)

### Design

```
 DataSchemeGigE(DataSchemeCamera)
   _camera_class()   -> select_backend(backend): BACKENDS, BACKEND_ORDER
   _extra_settings() -> backend, trigger (rule), exposure mode, gain,
                        max_exposure_us, brightness_target, white_balance
   _start_warm_up()  -> fixed: set it (and gain)
                        camera: set_camera_auto(), CameraAutoSettle
                        host: warm_up_steps = auto_expose() steps
                        set_white_balance()
   _apply_update()   -> the writable keys on the open camera, publish
```

- **The backend table is the seam.** `BACKENDS` maps a name to a device
  class. The unit tests add a fake entry and select it by name, so the
  whole scheme runs with no SDK on any platform.
- **The trigger rule follows the use.** Stills at a low rate want a
  fresh exposure each and a quiet link. Video wants the camera to run
  free. The rule chooses, and `trigger` overrides it.
- **The camera does the work it can.** Measured on an embedded ARM
  computer at 1920x1080 and 8 fps, the host path delivered 7.0 fps:
  its auto-expose overshot to the maximum gain, and it left the color
  unbalanced. The camera's own auto exposure, at most 30 ms, and its
  white balance held 8.00 fps with neutral color. It also held
  10.00 fps with the host idle for 80 % of each frame period.
- **Auto-expose as warm-up steps.** `camera.auto_expose()` yields one
  step per generator call, so the Stream can be destroyed during it. A
  free-running camera's queued frames were exposed before a change, so
  the steps skip them (`Camera.queued_frames()`).
- **In-camera RGB is not used.** The IDS cameras offer `RGB8`, but it
  caps the frame rate at 3.76 fps at 1920x1080. The host debayers
  `BayerRG8` in about 10 ms instead.

### Implementation notes

- A written `exposure_us` publishes the value the camera accepted, under
  the same key. The base's publishing flag stops the handler from
  applying that publication a second time.
- `_optional_float()` accepts `auto`, `none` or an empty value as "not
  given", so a PipelineDefinition can state the default explicitly.

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `DataSchemeGigE` | Name the scheme; select the backend; apply the trigger rule; choose the camera's own or the host auto exposure, or a fixed one; apply white balance; apply written values | [DataSchemeCamera](scheme_camera.md) (base), `IdsPeakCamera` and `AravisCamera` ([gigev_io](gigev_io.md)), `auto_expose()`, `CameraAutoSettle` and `CountdownSettle` ([camera](camera.md)) |
| `select_backend()` | Map a backend name to a usable device class, or explain what is missing | `BACKENDS`, the device classes' `available()` and `diagnostic()` |

## Current limitations and roadmap

From the source To Do list:

- Region of interest offsets as parameters. The crop is centered
- The camera's auto exposure and white balance for Aravis: it uses the
  host auto-expose and no white balance
- Retest Aravis streaming after the camera firmware update

## Related concepts

- [scheme_camera](scheme_camera.md) — everything not GigE specific
- [gigev_io](gigev_io.md) — the element and the two device layers
- [camera](camera.md) — `auto_expose()`, `plan_resolution()` and the
  helpers
- [DataScheme](../../concepts/scheme.md) — the registry
- [scheme_depthai](scheme_depthai.md) — the sibling scheme
