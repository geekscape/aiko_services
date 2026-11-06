---
title: Web view of a Pipeline
description: VideoShowWeb — a pass-through PipelineElement that shows the
  latest image as a live MJPEG stream in a browser, with the shared state
  of chosen elements, aiming overlays and a `focus_assist` switch, at no
  cost while nobody watches
type: concept
audience: [developers, end-users]
status: work-in-progress
ste: adapted
source:
  - src/aiko_services/elements/web/web_io.py
  - src/aiko_services/elements/web/pipelines/web_pipeline_0.json
related: [pipeline_element, share, dashboard, gigev_io, depthai_io,
  rtsp_io, synthetic_io]
version: "0.8-dev"
last_updated: 2026-09-30
---

# Web view of a Pipeline

## Overview

**`VideoShowWeb`** is a pass-through
[PipelineElement](../../concepts/pipeline_element.md). Every frame goes
on to the next element unchanged. A web server thread shows the latest
image in a browser as a live MJPEG stream. The page also shows the
[shared state](../../concepts/share.md) of chosen elements, by default
the Pipeline's source. For a camera, that is its `sensor.*` values, the
same values that `aiko_dashboard` shows.

The page draws aiming aids over the image: a grid of thirds, a center
cross and a level line. The browser draws them, so the host does no
work for them. A button turns the camera's `focus_assist` on and off, for
a manual focus ring.

**Why to use it**: check where a camera points, and how it is doing, from
a laptop on the same network, while the Pipeline records:

```bash
cd src/aiko_services/elements/web
aiko_pipeline create pipelines/web_pipeline_0.json -s 1
# then open http://<this-host>:8090
```

The element costs nothing while nobody watches. It was measured on an
embedded ARM computer, with a GigE camera at 1920x1080 and 8 fps. There,
one browser at 4 fps cost 8 % of one core. The camera held 8.0 fps and
dropped no frame.

## For application developers

### Command-line usage

Put the element after the camera and before the element that writes the
frames:

```json
"graph": ["(VideoReadGigE CaptureLimit VideoShowWeb VideoWriteStoreForward)"]
```

```bash
# Another port, when two camera Pipelines share one host
aiko_pipeline create <PipelineDefinition> -s 1 -p VideoShowWeb.port 8091

# Fewer, smaller images for a slow network
aiko_pipeline create <PipelineDefinition> -s 1  \
  -p VideoShowWeb.max_fps 2 -p VideoShowWeb.width 640

# Show the writer's state too
aiko_pipeline create <PipelineDefinition> -s 1  \
  -p VideoShowWeb.status_elements "(VideoReadGigE VideoWriteStoreForward)"
```

### Public API

| Class | Kind | Inputs → Outputs | Parameters |
|-------|------|------------------|------------|
| `VideoShowWeb` | PipelineElement | `images: [image]` → `images: [image]` (unchanged) | `port` (`8090`, `0` picks a free one), `host` (`0.0.0.0`), `max_fps` (`4.0`), `width` (`960`, `0` keeps the size), `quality` (`80`), `title` (the Pipeline's name), `status_elements` (the source element) |
| `FrameWebServer` | Class | `offer(image)` | The same settings, plus a status function and an update function. It has no framework dependency |

Service protocol: `video_show_web:0`.

Web page paths:

| Path | Response |
|------|----------|
| `/` | The page: the live view, the overlays, the `focus_assist` switch and the shared state |
| `/stream.mjpg` | The live view, scaled to `width`, at most `max_fps` frames a second |
| `/snapshot.jpg` | One frame at full size |
| `/status` | JSON: the viewer counts and the shared state of each chosen element |
| `/update?element=E&name=N&value=V` | Sends `(update N V)` to element E, as `aiko_dashboard` does. Only `focus_assist` is accepted |

Shared state: `state` (`serving`, `error` or `stopped`), `url`, `port`,
`viewers` and `frames_encoded`.

**Stream lifecycle behavior:**

- `start_stream()` starts the web server and logs its address. It then
  follows the shared state of the chosen elements with ECConsumers. A
  failure in either step logs a warning and never fails the Stream.
- `process_frame()` keeps a reference to the last image and returns the
  images unchanged.
- `stop_stream()` stops following, and stops the web server.

## For framework developers (internals)

### Design

```
 event-loop thread           encoder thread            web server threads
 ─────────────────           ──────────────            ──────────────────
 process_frame()             wait: a viewer and        GET /stream.mjpg
   offer(image): keep a        a new image               viewers += 1
   reference, O(1)           scale to width, JPEG      wait: a new JPEG
 ECConsumer handlers         at most max_fps  ───────► write one part
   copy the shared state                               GET /status
   under a lock  ─────────────────────────────────────► read the copy
 timer: publish viewers                                GET /update
                                                         publish (update ...)
```

- **Observe, never reach in.** The page shows other elements' shared
  state through ECConsumers, as `aiko_dashboard` does. The element never
  reads another element's attributes.
- **Encode once, for all viewers.** One encoder thread encodes the
  newest image, and every viewer sends the same JPEG. With no viewer the
  encoder waits, and `frames_encoded` stays constant.
- **The web part is separate.** `FrameWebServer` knows nothing of the
  framework. The unit tests drive it on a free local port with no
  Pipeline and no broker.

### Implementation notes

- The page filters out the `#` comment keys that a PipelineDefinition
  puts in an element's shared state.
- `/update` accepts only the names in `WRITABLE_KEYS`, and a value
  without spaces. The server has no authentication. Use it on a trusted
  network only.
- Port 8090 is the default because a store / forward tunnel often holds
  8080.

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `VideoShowWeb` | Pass frames through; start and stop the web server; follow chosen elements' shared state; relay the `focus_assist` switch; publish viewer counts | [PipelineElement](../../concepts/pipeline_element.md), ECConsumer ([Share](../../concepts/share.md)), `FrameWebServer` |
| `FrameWebServer` | Keep the latest image; encode it for viewers at a capped rate; serve the page, the stream, a snapshot, the status and the update path | Python `http.server`, OpenCV |

## Current limitations and roadmap

From the source To Do list:

- With several images per frame, the view shows the last one

Also:

- No authentication and no HTTPS
- The only writable key is `focus_assist`

## Related concepts

- [gigev_io](../cameras/gigev_io.md), [depthai_io](../cameras/depthai_io.md)
  and [rtsp_io](../gstreamer/rtsp_io.md) — the cameras it shows
- [Share](../../concepts/share.md) — the shared state on the page
- [Dashboard](../../concepts/dashboard.md) — the terminal view of the same
  state
- [synthetic_io](../media/synthetic_io.md) — the source of the example
