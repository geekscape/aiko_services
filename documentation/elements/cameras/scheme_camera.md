---
title: Camera DataScheme base
description: DataSchemeCamera — the base of the depthai and gigev
  DataSchemes: the common parameters, the camera open, the warm-up, the
  frame generator, the dashboard state and the writable keys
type: concept
audience: [developers, end-users]
status: work-in-progress
ste: adapted
source:
  - src/aiko_services/elements/cameras/scheme_camera.py
related: [camera, scheme_depthai, scheme_gigev, scheme, data_source_target,
  pipeline_element, stream, parameters, share, dashboard]
version: "0.8-dev"
last_updated: 2026-09-23
---

# Camera DataScheme base

## Overview

**`DataSchemeCamera`** is the [DataScheme](../../concepts/scheme.md)
base class that the [depthai](scheme_depthai.md) and
[gigev](scheme_gigev.md) schemes extend. It owns everything the two
cameras have in common: the parameters, the device open, the warm-up,
the frame generator and the shared state on the dashboard. A subclass
names its URL scheme, chooses its device class and adds its own
parameters.

One scheme instance exists per [Stream](../../concepts/stream.md). The
camera, the counters and the warm-up state live on that instance.

**Why to use it**: it is the reason two very different cameras behave
the same way in a Pipeline, on the command line and on the dashboard:

```bash
cd src/aiko_services/elements/cameras

aiko_pipeline create pipelines/depthai_pipeline_0.json -s 1
aiko_pipeline create pipelines/gigev_pipeline_0.json -s 1
aiko_dashboard      # the same keys for both: state, frames, measured_fps ...
```

## For application developers

### Command-line usage

The base has no command line of its own. Every parameter below is set on
the camera element, with `-p <Element>.<parameter> <value>`, in a
PipelineDefinition, or as a Pipeline-level parameter.

```bash
# The URL: discovery, or one camera
-p VideoReadDepthAI.data_sources "(depthai://)"
-p VideoReadDepthAI.data_sources "(depthai://<address>)"

# The regime
-p VideoReadDepthAI.resolution 1920x1080 -p VideoReadDepthAI.frame_rate 8
-p VideoReadDepthAI.resolution native -p VideoReadDepthAI.frame_rate 2

# Diagnostics: one debug log line per frame
-p VideoReadDepthAI.log_frames true
```

### Public API

URL grammar of every camera scheme:

```
<scheme>://              the first camera found
<scheme>://<address>     one camera; the address form is the SDK's
```

The URL carries no options. A `?` in the URL is an error that points at
the parameters.

Parameters common to every camera scheme:

| Parameter | Default | Meaning |
|-----------|---------|---------|
| `resolution` | `1920x1080` | `WxH`, or `native` / `full` for the sensor's own size. The camera delivers the nearest size it can and reports the actual size as `sensor.resolution` |
| `frame_rate` | `25.0` | Frames per second: a number, or a fraction such as `25/1`, the `VideoReadRTSP` form. `fps` is a deprecated alias |
| `rate` | none | A delivery throttle for `create_frames()`. By default the camera paces the Stream |
| `resize_mode` | `crop` | For a scaled output: `crop` keeps the aspect ratio, `letterbox` pads, `stretch` does not keep it |
| `settle` | the subclass's | Frames discarded while the camera converges after start, as a count or a time such as `3s` |
| `capture_timeout` | `1.0` | Seconds per capture. Ten consecutive timeouts end the Stream |
| `log_frames` | `false` | One debug log line per frame |
| `data_batch_size` | `1` | Only `1` is supported |
| `media_type` | none | Element level: `numpy` or `pil` |

Shared state on the dashboard, and through an `ECConsumer`:

| Key | Meaning |
|-----|---------|
| `state` | `opening`, `settling`, `streaming`, `stopped` or `error` |
| `device_id`, `address`, `sdk_version` | What is open, and through what |
| `settled` | `waiting`, `<n>_frames`, `timeout_<n>_frames` or `off` |
| `frames`, `measured_fps` | Frames delivered, and the rate over the last two seconds |
| `capture_timeouts`, `last_frame_utc`, `last_error` | Is it delivering, when did it last, what failed last (`<token>@UTC`) |
| `sensor.*` | What the device reports: `resolution` (delivered), `exposure_us`, `gain`, `iso_sensitivity`, `lens_position`, `color_temperature_k` |
| `resolution`, `frame_rate`, `settle`, `resize_mode`, `capture_timeout`, `log_frames` | The configuration in force, as valid parameter values |

The configuration keys carry the parameter names on purpose. The
framework reads a share item in preference to the element parameter of
the same name. Thus a dashboard `(update ...)` of a writable key takes
effect at once, and every configuration key is the value the next Stream
starts with. The base's writable keys are `capture_timeout` and
`log_frames`. A subclass adds its own.

**Stream lifecycle behavior:**

- `create_sources()` runs on the event-loop thread. It checks the URL,
  coerces the parameters, selects the device class, opens the camera and
  publishes the identity and configuration keys. Each failure returns
  `StreamEvent.ERROR` with a diagnostic, sets `state` to `error` and
  records `last_error`. Then it starts `create_frames()`.
- `frame_generator()` runs on the frame generator thread. It runs the
  optional warm-up steps first, then captures with a bounded timeout. A
  timeout returns `NO_FRAME`, and ten in a row return `STOP`. Any other
  failure returns `STOP`, never `ERROR`. An `ERROR` on the generator
  thread destroys the Stream on that thread, and the process lingers.
  While the settle object is not done, frames are discarded. Then each
  frame is delivered as `{"images": [image]}` with a timestamp.
- `destroy_sources()` stops the generator, removes the timer and the
  share handler, closes the camera and publishes `state stopped`.

## For framework developers (internals)

### Design

```
 event-loop thread                       frame generator thread
 ─────────────────                       ──────────────────────
 create_sources()                        frame_generator()
   settings = _camera_settings()           warm_up_steps? -> NO_FRAME
   camera = _camera_class().open()         capture(timeout)
   _start_warm_up()                          CaptureTimeout -> NO_FRAME
   publish identity, configuration          exception      -> STOP
   timer: _publish_handler() 1 s ◄──────── _pend(key, value)
   handler: writable keys                   settle.feed()  -> NO_FRAME
   create_frames()                          OKAY {"images": [image]}
 destroy_sources()
   stopped = True, close(), flush
```

- **Two threads, one rule.** The event-loop thread publishes to share
  directly. The generator thread never touches share: it records into a
  pending dictionary, and a one second timer on the event loop publishes
  what changed. This is the same rule as the StoreForward Actor's
  mailbox hand-off.
- **Subclass hooks.** `_camera_class()`, `_open_camera()`,
  `_extra_settings()`, `_start_warm_up()` and `_apply_update()` are the
  five points a camera scheme fills in.
- **Warm-up as steps.** `warm_up_steps` is an iterator that runs before
  any frame, one step per generator call, for example the auto-expose of
  the GigE scheme. The settle object then discards frames until it is
  done.

### Implementation notes

- `ECProducer.update()` calls every handler, this scheme's included. The
  scheme sets a flag while it publishes, and its handler ignores updates
  that carry that flag. Without it, a published actual value would be
  applied to the camera again.
- The share handler is attached in `create_sources()` and detached in
  `destroy_sources()`, as is the timer. The unit tests assert that both
  are gone after destroy, because a leftover timer runs into the next
  test's event loop.
- A capture in flight when the Stream stops is posted after the stop and
  re-creates the Stream. This is framework behavior. The generator
  checks the stopped flag after each capture, which narrows the window.
  The in-process tests pace delivery with `rate`, so the stop lands
  while the generator sleeps.

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `DataSchemeCamera` | Coerce parameters; open the camera; run the warm-up; generate frames with bounded captures; publish the dashboard state from the right thread; apply writable keys | [DataScheme](../../concepts/scheme.md) (base), the [Camera](camera.md) contract, [PipelineElement](../../concepts/pipeline_element.md) (`create_frames()`, `get_parameter()`, `ec_producer`), [Stream](../../concepts/stream.md), [Share](../../concepts/share.md) |

## Current limitations and roadmap

From the source To Do list:

- `data_batch_size` above one
- Device-clock timestamps in place of the time of dequeue

## Related concepts

- [camera](camera.md) — the device contract and the helpers
- [scheme_depthai](scheme_depthai.md), [scheme_gigev](scheme_gigev.md)
  — the subclasses
- [DataScheme](../../concepts/scheme.md) — the plug-in base class and
  registry
- [Share](../../concepts/share.md) — how the keys reach the dashboard
- [Dashboard](../../concepts/dashboard.md) — where to watch them
