---
title: YOLO object detection example
description: YoloDetector — a PipelineElement wrapping Ultralytics YOLO,
  running either a fine-tuned YOLOv8 checkpoint or an open-vocabulary
  YOLOE model prompted with class names
type: concept
audience: [developers, end-users]
status: draft
source:
  - src/aiko_services/examples/yolo/yolo.py
related: [pipeline_element, pipeline, stream, parameters, image_io,
  video_io, webcam_io, aruco, elements]
version: "0.6"
last_updated: 2026-07-06
---

# YOLO object detection example

## Overview

`yolo.py` provides **`YoloDetector`**, a single
[PipelineElement](../../concepts/pipeline_element.md) that wraps the
Ultralytics YOLO family of object detectors. One class serves two
distinct models, selected by the `model` parameter:

- **Fine-tuned YOLOv8** — the default checkpoint
  `yolov8n_robotdog.pt` (committed alongside `yolo.py`), a YOLOv8-nano
  model fine-tuned with extra robot-dog classes such as `tennis_ball`,
  `red_cup`, `orange_cone`, `stop_sign` and `xgomini2`. Detections
  are filtered to only those custom class ids (`_ROBOTDOG_CLASSES`).
- **YOLOE open-vocabulary** — any checkpoint whose file name starts
  with `yoloe` (e.g `yoloe-11s-seg.pt`) switches the element into
  YOLOE mode: the `names` parameter supplies a free-text class list
  as an S-expression, and every detection passes unfiltered.

Each Frame's images are run through the model and the detections are
emitted as an `overlay` — objects (`name`, `confidence`) and bounding
`rectangles` (`x`, `y`, `w`, `h`) — drawn onto the images downstream
by the [`ImageOverlay`](../../elements/media/image_io.md) element.

**Why you'd use it**: point a webcam at your desk and watch YOLOE
find whatever you name, with no training step:

```bash
aiko_pipeline create yoloe_pipeline_0.json -s 1
# "names": "(apple ball banana cat dog fork glasses knife spoon
#           lightbulb mug person)"  --> live labelled boxes on screen
```

The `yolov8n_robotdog.pt` model file (about 6.5 MB) is git-committed
in `src/aiko_services/examples/yolo/`; the YOLOE checkpoints
(`yoloe-11[sml]-seg.pt`) are not committed and are downloaded by the
Ultralytics package on first use. The robot example's
[OODA-loop Pipeline](../robot/ooda/elements.md) reuses
`yolov8n_robotdog.pt` via a symbolic link.

## For application developers

### Command-line usage

There is no console script; `YoloDetector` is deployed by the
PipelineDefinitions in this package (see the
[package index](ReadMe.md)). From the source header, run from
`src/aiko_services/examples/yolo/`:

```bash
aiko_pipeline create yolo_pipeline_0.json -s 1   # aiko_dashboard --> logging

AIKO_LOG_LEVEL=DEBUG aiko_pipeline create yolo_pipeline_0.json -s 1

aiko_pipeline create yolo_pipeline_0.json -s 1  \
    -sp VideoReadWebcam.path /dev/video2  # Linux: select camera device
```

On NVIDIA platforms using TensorRT, the source header notes the extra
setup:

```bash
pip install tensorrt
RT_PATH=$HOME/venvs/venv_3.12.7/lib/python3.12/site-packages/tensorrt_libs
export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:$RT_PATH
```

### Public API

| Class | Kind | Inputs → Outputs | Parameters |
|-------|------|------------------|------------|
| `YoloDetector` | ML inference | `images: [image]` → `overlay: [overlay]` | `model` (default `yolov8n_robotdog.pt`), `names` (YOLOE only) |

Service protocol: `object_detector:0`.

[Parameters](../../concepts/parameters.md), resolved in
`start_stream()`:

- **`model`** — pathname of the YOLO checkpoint. A file name starting
  with `yoloe` selects YOLOE mode.
- **`names`** — YOLOE only: the open-vocabulary class list as an
  S-expression, e.g `"(apple ball banana person)"`, parsed with
  `parse(names, car_cdr=False)` and passed to
  `yolo_model.set_classes(names, yolo_model.get_text_pe(names))`.
  If the value is not a non-empty list, a warning is logged
  (`Parameter "names" must be a list`) and the model runs with its
  default classes.

The compute device is chosen automatically per
[Stream](../../concepts/stream.md): `cuda` if available, else `mps`
(Apple silicon), else `cpu`.

`process_frame(stream, images)` returns
`StreamEvent.OKAY, {"overlay": overlay}` where:

```python
overlay = {
    "objects":    [{"name": str, "confidence": float}, ...],  # 2 dp
    "rectangles": [{"x": int, "y": int, "w": int, "h": int}, ...]
}
```

`x, y` is the box top-left corner (from `box.xyxy`); `w, h` are the
box width and height (from `box.xywh`). The two lists are parallel:
`objects[i]` describes `rectangles[i]`, accumulated across all images
in the Frame. In YOLOv8 mode only detections whose class id is in
`_ROBOTDOG_CLASSES` are kept; in YOLOE mode all detections are kept.

## For framework developers (internals)

### Design

```
    images                 +---------------+     overlay
  ----------------------->| YoloDetector  |------------------>
  [np.ndarray, ...]        |  YOLO(model)  |  {objects,
                           |  cuda|mps|cpu |   rectangles}
                           +---------------+
```

- The Ultralytics model is loaded once per Stream in
  `start_stream()`, so a long-lived [Pipeline](../../concepts/pipeline.md)
  pays the checkpoint-load cost only at Stream creation, and each
  Stream may select a different `model`.
- One class, two behaviours: YOLOE mode is detected by the file-name
  prefix test `yolo_model_pathname.startswith("yoloe")` — both model
  kinds are constructed through the `YOLO` class.
- `torch` and `ultralytics` are imported at module level with no
  guard, unlike the sibling `aruco.py` / `face.py` modules which wrap
  optional imports in try/except — importing this module without
  those packages installed raises `ModuleNotFoundError` directly.

### Implementation notes

- The `startswith("yoloe")` test is applied to the whole `model`
  parameter value, so a checkpoint given with a directory prefix
  (e.g `models/yoloe-11s-seg.pt`) would *not* be recognised as YOLOE.
- `from ultralytics import YOLO, YOLOE` imports `YOLOE`, but it is
  never used — YOLOE checkpoints are loaded via `YOLO(...)`.
- The `image_id` / `detection_id` / `box_id` loop counters only feed
  a commented-out `print()`; `box_id` increments inside the
  class-filter branch while the others count every iteration.

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `YoloDetector` | Load a YOLO / YOLOE checkpoint per Stream; select compute device; run inference per Frame; filter and reshape detections into an `overlay` | [PipelineElement](../../concepts/pipeline_element.md), [Parameters](../../concepts/parameters.md), [Stream](../../concepts/stream.md), Ultralytics `YOLO`, `torch`, [`ImageOverlay`](../../elements/media/image_io.md) (downstream consumer) |

## Current limitations and roadmap

From the source To Do list — **planned**, not implemented:

- Multiple simultaneous YOLO model checkpoints, referenced by name.
- More flexible search for the default model pathname
  (`_YOLO_MODEL_PATHNAME`), which is currently resolved relative to
  the working directory.
- Inference rate control (ignore frames) and GPU efficiency review.
- YOLOE class confidence level(s) as a PipelineDefinition parameter.
- YOLOE segmentation overlay with different colors per class —
  segmentation checkpoints are used, but only bounding boxes are
  emitted today.
- YOLOE streaming for local and YouTube videos (live stream).
- Note: the first To Do item ("YOLO checkpoint file pathname should
  be a parameter") is stale — the `model` parameter already exists.

## Related concepts

- [PipelineElement](../../concepts/pipeline_element.md) — the
  contract `YoloDetector` implements
- [Pipeline](../../concepts/pipeline.md) — the graphs that deploy it
- [Parameters](../../concepts/parameters.md) — `model` and `names`
  resolution
- [Stream](../../concepts/stream.md) — per-Stream model loading in
  `start_stream()`
- [image_io](../../elements/media/image_io.md) — `ImageResize`
  upstream and `ImageOverlay` downstream
- [webcam_io](../../elements/media/webcam_io.md) — the usual live
  image DataSource
- [ArUco marker example](../aruco_marker/aruco.md) — combined with
  `YoloDetector` in `yolo_pipeline_1.json` / `yolo_pipeline_2.json`
- [System Pipelines example](../system_pipelines/ReadMe.md) —
  `YoloDetector` deployed in a *remote* Pipeline
