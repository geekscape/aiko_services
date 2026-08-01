---
title: Face detection example
description: FaceDetector — a PipelineElement wrapping DeepFace
  RetinaFace face extraction, publishing a running detection count via
  the Share mechanism
type: concept
audience: [developers, end-users]
status: draft
ste: adapted
source:
  - src/aiko_services/examples/face/face.py
related: [pipeline_element, pipeline, stream, share, image_io, yolo]
version: "0.6"
last_updated: 2026-08-01
---

# Face detection example

## Overview

`face.py` gives **`FaceDetector`**, a
[PipelineElement](../../concepts/pipeline_element.md) that finds
human faces in each Frame's images using the
[DeepFace](https://github.com/serengil/deepface) library's
`extract_faces()` with the RetinaFace detector backend. Detected face
bounding boxes are emitted as an `overlay` of `rectangles`, for the
downstream [`ImageOverlay`](../../elements/media/image_io.md) element.
A running `detections` counter is published through the
[Share](../../concepts/share.md) mechanism. Thus the count is visible
live in `aiko_dashboard`.

**Why to use it**: for a complete live face-detection demo in one
command. It is also a worked example of a PipelineElement that updates
shared state, which any Dashboard or remote Service can watch:

```bash
aiko_pipeline create face_pipeline.json -s 1
# aiko_dashboard --> select p_face / FaceDetector --> "detections" ticks up
```

Needs `opencv-python` (install Aiko Services with
`--extras "opencv"`) and the `deepface` package (which brings in
TensorFlow — the source header points Apple silicon users at
`tensorflow-metal`).

## For application developers

### Command-line usage

There is no console script. `FaceDetector` is deployed by
`face_pipeline.json` (see the [package index](ReadMe.md)). From the
source header, run from `src/aiko_services/examples/face/`:

```bash
aiko_pipeline create face_pipeline.json -s 1   # aiko_dashboard --> logging

AIKO_LOG_LEVEL=DEBUG aiko_pipeline create face_pipeline.json -s 1

aiko_pipeline create face_pipeline.json -s 1  \
    -p VideoReadWebcam.path /dev/video2  # Linux: select camera device
```

On NVIDIA platforms using TensorRT, the source header notes:

```bash
RT_PATH=$HOME/venvs/venv_3.10.7/lib/python3.10/site-packages/tensorrt_libs
export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:$RT_PATH
```

### Public API

| Class | Kind | Inputs → Outputs | Parameters |
|-------|------|------------------|------------|
| `FaceDetector` | ML inference | `images: [image]` → `overlay: {rectangles}` | (none) |

Service protocol: `face_detector:0`.

`process_frame(stream, images)` returns
`StreamEvent.OKAY, {"overlay": overlay}` where:

```python
overlay = {"rectangles": [facial_area, ...]}
# facial_area is DeepFace's dict, e.g {"x": .., "y": .., "w": .., "h": ..}
```

Shared state ([Share](../../concepts/share.md)):

- **`detections`** — cumulative count of faces detected since the
  element started. The constructor initializes it to `0`. Each Frame
  that contains faces updates it through
  `self.ec_producer.update("detections", ...)`.

The detector backend is hard-coded to `"retinaface"`
(`self.detector_backend`). Note that it is *assigned but not passed* to
`extract_faces()`. Thus `extract_faces()` runs with the default backend
of DeepFace (refer to the Implementation notes). Frames in which DeepFace finds
no face raise `ValueError` internally. The element catches this and
emits an empty `rectangles` list for that image.

## For framework developers (internals)

### Design

```
    images     +--------------+   overlay              share
  ----------->| FaceDetector |------------->      "detections" = N
              |  DeepFace    |  {rectangles}   (ECProducer update)
              |  extract_faces|
              +--------------+
```

- Images arrive RGB (or grayscale). OpenCV converts them to BGR before
  the call to DeepFace, which expects BGR. The source To Do asks
  whether this conversion belongs in a common media module.
- Unlike `YoloDetector`, all state is set up in the constructor —
  there is no `start_stream()` model loading. DeepFace loads its
  model weights lazily on the first `extract_faces()` call.
- The cumulative `detections` counter demonstrates the
  ECProducer-side of the [Share](../../concepts/share.md) design from
  inside a PipelineElement.

### Implementation notes

- `self.detector_backend = "retinaface"` is never passed to
  `extract_faces(image_bgr)` — the call uses DeepFace's default
  detector backend, so the assignment is currently dead.
- The `except ValueError: pass` treats *any* `ValueError` as
  "no face found", which also silences genuine argument errors.
- In the `cv2` import-failure path, `face.py` calls
  `aiko.logger(__name__)`. That attribute is not part of the
  `aiko_services` public API. The sibling `aruco.py` uses
  `aiko.process.logger(__name__)`. Thus the failure path would raise
  `AttributeError` before the intended `ModuleNotFoundError`.
- `image_id` and `face_id` counters are unused (debug leftovers).

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `FaceDetector` | Convert images to BGR; extract faces per Frame; emit `facial_area` rectangles as an overlay; maintain the shared `detections` count | [PipelineElement](../../concepts/pipeline_element.md), [Share](../../concepts/share.md) (ECProducer), DeepFace `extract_faces`, `cv2`, [`ImageOverlay`](../../elements/media/image_io.md) (downstream consumer) |

## Current limitations and roadmap

From the source To Do list — **planned**, not implemented:

- Confirm whether the RGB → BGR conversion is needed at all, and
  move OpenCV color conversion into a shared
  `elements/media/common_io.py`.
- Inference rate control (ignore frames).
- GPU efficiency review.

Additional observations, not in the To Do list. The detector backend is
configurable in name only (refer to the Implementation notes). There are
also no element parameters. The backend choice and the confidence
thresholds would be natural PipelineDefinition parameters.

## Related concepts

- [PipelineElement](../../concepts/pipeline_element.md) — the
  contract `FaceDetector` implements
- [Pipeline](../../concepts/pipeline.md) — the deploying graph
- [Share](../../concepts/share.md) — the `detections` counter
  published through ECProducer
- [Stream](../../concepts/stream.md) — StreamEvent semantics
- [image_io](../../elements/media/image_io.md) — `ImageResize`
  upstream and `ImageOverlay` downstream
- [webcam_io](../../elements/media/webcam_io.md) — the live image
  DataSource
- [YOLO example](../yolo/yolo.md) — the same detect-overlay-display
  Pipeline shape with a different detector
