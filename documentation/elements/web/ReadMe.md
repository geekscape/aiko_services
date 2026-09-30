---
title: Web PipelineElements index
description: Index of the web PipelineElement concept documents — the
  VideoShowWeb element that shows a Pipeline's images and the shared state
  of its elements in a browser, and the committed example
  PipelineDefinition
type: index
audience: [developers, end-users]
status: work-in-progress
ste: adapted
source:
  - src/aiko_services/elements/web
related: [pipeline_element, pipeline, share, dashboard]
version: "0.8-dev"
last_updated: 2026-09-30
---

# Web PipelineElements index

One concept document per Python module in `src/aiko_services/elements/web/`.
A web element lets a browser on the same network look at what a
[Pipeline](../../concepts/pipeline.md) sees. It uses the standard library
HTTP server and OpenCV, which it imports lazily. So a camera Pipeline
gains a web view with no new dependency.

## Module documents

| Document | Module | Contents |
|----------|--------|----------|
| [web_io](web_io.md) | `web_io.py` | `VideoShowWeb`, a pass-through element with a live view, the shared state of chosen elements, aiming overlays and a `focus_assist` switch. `FrameWebServer`, its web part |

## Example PipelineDefinitions

| PipelineDefinition | Module document(s) | Purpose |
|--------------------|--------------------|---------|
| `web_pipeline_0.json` | [web_io](web_io.md), [synthetic_io](../media/synthetic_io.md), [control elements](../control/elements.md) | Synthetic frames in a browser for 10 minutes, with no camera |

Run it from `src/aiko_services/elements/web`, then open
`http://<this-host>:8090`.

## Package exports

```python
from aiko_services.elements.web import FrameWebServer, VideoShowWeb
```

Importing the package starts no server. A server starts with the first
Stream of a `VideoShowWeb` element.

## Suggested reading order

1. [web_io](web_io.md)
2. [Share](../../concepts/share.md), for the shared state the page shows
3. [cameras/](../cameras/ReadMe.md), for the camera elements it watches
