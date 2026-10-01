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
brings the exposure to a usable value, then delivers frames.

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
| `exposure_us` | `auto` | A fixed exposure in microseconds. `auto` runs the highlight-based auto-expose before the first frame, because the IDS default user set has no auto-exposure |
| `gain` | none | Analog gain, applied with a fixed `exposure_us` |
| `settle` | `2` | Frames discarded after an exposure change |

In software-trigger mode `rate` defaults to `frame_rate`: the frame
generator triggers one exposure per delivered frame.

Shared state adds `backend`, `trigger`, `exposure_us` and `gain`. While
the auto-expose runs, `exposure_us` reads `auto` and `state` reads
`settling`. Then both hold the values the camera accepted.

Writable keys: `exposure_us` (a number, or `auto` to run the auto-expose
again), `gain`, and the base's `capture_timeout` and `log_frames`. A
written value acts on the open camera at once, two settle frames are
discarded, and the next Stream starts from the written value.

Registration (module import side effect):

```python
aiko.DataScheme.add_data_scheme("gigev", DataSchemeGigE)
```

`select_backend(name)` is exported: it returns the backend name and the
device class, or raises `RuntimeError` that names what to install.

**Stream lifecycle behavior:** as the [camera scheme base](scheme_camera.md)
describes. The GigE specifics: with no `exposure_us`, the frame
generator runs the auto-expose steps before any frame. There are at most
eight steps, and a scene that stays too dark gets a warning. A missing
backend returns `StreamEvent.ERROR` that names every SDK and its install
line.

## For framework developers (internals)

### Design

```
 DataSchemeGigE(DataSchemeCamera)
   _camera_class()   -> select_backend(backend): BACKENDS, BACKEND_ORDER
   _extra_settings() -> backend, trigger (rule), exposure_us, gain, rate
   _start_warm_up()  -> CountdownSettle(settle)
                        exposure_us given: set it (and gain), publish
                        else: warm_up_steps = auto_expose() steps
   _apply_update()   -> exposure_us | gain on the open camera, publish
```

- **The backend table is the seam.** `BACKENDS` maps a name to a device
  class. The unit tests add a fake entry and select it by name, so the
  whole scheme runs with no SDK on any platform.
- **The trigger rule follows the use.** Stills at a low rate want a
  fresh exposure each and a quiet link. Video wants the camera to run
  free. The rule chooses, and `trigger` overrides it.
- **Auto-expose as warm-up steps.** `camera.auto_expose()` yields one
  step per generator call, so the Stream can be destroyed during it.

### Implementation notes

- A written `exposure_us` publishes the value the camera accepted, under
  the same key. The base's publishing flag stops the handler from
  applying that publication a second time.
- `_optional_float()` accepts `auto`, `none` or an empty value as "not
  given", so a PipelineDefinition can state the default explicitly.

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `DataSchemeGigE` | Name the scheme; select the backend; apply the trigger rule; set or warm up the exposure; apply written exposure and gain | [DataSchemeCamera](scheme_camera.md) (base), `IdsPeakCamera` and `AravisCamera` ([gigev_io](gigev_io.md)), `auto_expose()` and `CountdownSettle` ([camera](camera.md)) |
| `select_backend()` | Map a backend name to a usable device class, or explain what is missing | `BACKENDS`, the device classes' `available()` and `diagnostic()` |

## Current limitations and roadmap

From the source To Do list:

- Region of interest offsets as parameters. The crop is centered
- Retest Aravis streaming after the camera firmware update

## Related concepts

- [scheme_camera](scheme_camera.md) — everything not GigE specific
- [gigev_io](gigev_io.md) — the element and the two device layers
- [camera](camera.md) — `auto_expose()`, `plan_resolution()` and the
  helpers
- [DataScheme](../../concepts/scheme.md) — the registry
- [scheme_depthai](scheme_depthai.md) — the sibling scheme
