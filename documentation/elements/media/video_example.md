---
title: Video example script (legacy)
description: A dormant Pipeline_2020-era demonstration of a branching
  video pipeline with a StateMachine — superseded by the video and webcam
  PipelineDefinitions
type: concept
audience: [developers, end-users]
status: work-in-progress
source:
  - src/aiko_services/elements/media/video_example.py
related: [pipeline, pipeline_element, video_io, image_io, images_to_video]
version: "0.6"
last_updated: 2026-07-06
---

# Video example script (legacy)

## Overview

`video_example.py` is a **dormant legacy script** from the
`Pipeline_2020` generation of the framework. It sketches a
seven-element video-processing pipeline — read a video, annotate
frames along one of two branches chosen by a `StateMachine`
(`start` / `alternate` states), overlay, display, resize, and re-encode
— declared as a Python list of dicts. Its `__main__` block (including
the `StateMachine` wiring and an `event.add_timer_handler()` test) is
entirely commented out; the `Pipeline_2020` class, the
`ImageAnnotate1` / `ImageAnnotate2` elements and the module paths it
references no longer exist.

Two ideas in it remain interesting and are noted on modern roadmaps:
**state-dependent successors** (a per-element `successors` dict keyed
by state — cf. Graph Path selection in the current
[Pipeline](../../concepts/pipeline.md)) and a **windowed video player
interface** (`run()` / `pause()` / `step()`).

**Why you'd use it**: you wouldn't — the working equivalents are the
committed PipelineDefinitions:

```bash
cd src/aiko_services/elements/media
aiko_pipeline create pipelines/video_pipeline_0.json -s 1   # file video
aiko_pipeline create pipelines/webcam_pipeline_1.json -s 1  # live camera
```

## For application developers

### Command-line usage

The script's own usage header is historical and non-functional:

```bash
LOG_LEVEL=DEBUG ./video_example.py   # legacy; runs, but does nothing
```

For real video pipelines — decode, resize, display, re-encode — see
[video_io](video_io.md) (`video_pipeline_0.json`,
`video_pipeline_1.json`) and [webcam_io](webcam_io.md)
(`webcam_pipeline_*.json`).

### Public API

None executable. The module defines constants, a `StateMachineModel`
(states `start` / `alternate`, one transition) and a
`pipeline_definition` list in the obsolete dict format. Two features
have no modern JSON equivalent yet:

- `successors` as a dict keyed by StateMachine state
  (`"default"` / `"alternate"`), switching the graph branch at run time
- a `state_action` parameter (`(5, "alternate")` — commented out even
  here) that would trigger a state change at a given frame

The elements named (`ImageAnnotate1`, `ImageAnnotate2`) do not exist in
[image_io](image_io.md); `VideoShow` window parameters appear here as
`window_location` / `window_title` where the modern element uses
`position` / `title` ([video_io](video_io.md)).

## For framework developers (internals)

### Design

Historical interest only — but it documents where the branching-graph
idea came from:

```
 VideoReadFile ──(state "start")────► ImageAnnotate1 ─┐
       │                                              ├► ImageOverlay
       └──(state "alternate")───────► ImageAnnotate2 ─┘       │
                                                          VideoShow
                                                              │
                                                  ImageResize → VideoWriteFile
```

The modern engine expresses static graphs in the JSON `graph`
S-expression and selects sub-graphs with Graph Paths (`-gp`); dynamic,
state-driven branch switching as sketched here has no direct
replacement yet.

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `StateMachineModel` (legacy) | Declare `start` / `alternate` states and the transition for branch switching | the removed `StateMachine` / `Pipeline_2020` runtime |
| (pipeline_definition literal) | Historical reference for state-keyed `successors` | `VideoReadFile`, `VideoShow`, `VideoWriteFile` ([video_io](video_io.md)); `ImageResize` ([image_io](image_io.md)) |

## Current limitations and roadmap

The script is dead code, and its own To Do list is effectively a
feature wish-list for the modern elements:

- Turn it into an Aiko Services Service; CLI `--pause` (display first
  frame and pause); a player interface — `frame_rate()`, `run()`,
  `pause()`, `step(±frame_count)`
- Video overlay of `frame_id` and statistics (now an
  `ImageOverlay` TODO — see [image_io](image_io.md))
- `timer_test()` handler driving `state_action` state changes
- try/except around the OpenCV import with a simple message (now done
  via `_CV2_IMPORTED` guards in the modern modules); split into
  `video_opencv.py` / `video_scikit.py` / `video_gstreamer.py`; ensure
  the OpenCV path uses asyncio and does not block

Candidate for deletion once the state-keyed `successors` and player
ideas are captured on the [video_io](video_io.md) /
[Pipeline](../../concepts/pipeline.md) roadmaps.

## Related concepts

- [Pipeline](../../concepts/pipeline.md) — the modern engine, `graph`
  S-expressions and Graph Paths
- [PipelineElement](../../concepts/pipeline_element.md) — the current
  element contract
- [video_io](video_io.md) — the working video elements and pipelines
- [image_io](image_io.md) — overlay/resize elements referenced by the
  sketch
- [images_to_video](images_to_video.md) — sibling legacy script from
  the same generation
