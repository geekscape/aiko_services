---
title: ArUco marker detection example
description: ArucoMarkerDetector and ArucoMarkerOverlay — OpenCV ArUco
  fiducial marker detection and annotation PipelineElements
type: concept
audience: [developers, end-users]
status: draft
source:
  - src/aiko_services/examples/aruco_marker/aruco.py
related: [pipeline_element, pipeline, stream, parameters, image_io,
  yolo]
version: "0.6"
last_updated: 2026-07-06
---

# ArUco marker detection example

## Overview

`aruco.py` provides two
[PipelineElements](../../concepts/pipeline_element.md) built on the
OpenCV `cv2.aruco` module:

- **`ArucoMarkerDetector`** — finds ArUco fiducial markers
  (`DICT_4X4_50` dictionary) in each image and emits their corner
  coordinates and marker ids as `overlays`.
- **`ArucoMarkerOverlay`** — draws each detected marker back onto the
  image: a yellow bounding box, a red centre dot and the marker id in
  purple text above the top-left corner.

ArUco markers are printed 2-D barcodes whose pose can be recovered
from a single calibrated camera — cheap, robust ground-truth for
robotics. The detector and overlay are separate elements so that the
detection result can also feed non-visual consumers (e.g the robot
example's OODA loop) without drawing anything.

**Why you'd use it**: hold a printed 4x4 ArUco marker up to your
webcam and see it boxed and numbered live:

```bash
aiko_pipeline create aruco_pipeline_0.json -s 1 -ll debug
```

Requires `opencv-python` (install Aiko Services with
`--extras "opencv"`); importing `aruco.py` without it raises
`ModuleNotFoundError` with installation instructions.

## For application developers

### Command-line usage

There is no console script; the elements are deployed by
`aruco_pipeline_0.json` (see the [package index](ReadMe.md)). From
the source header, run from
`src/aiko_services/examples/aruco_marker/`:

```bash
aiko_pipeline create aruco_pipeline_0.json -s 1 -ll debug

aiko_pipeline create aruco_pipeline_0.json -s 1  \
    -p VideoReadWebcam.path /dev/video2  # Linux: select camera device
```

The Pipeline records annotated output to
`data_out/out_{:02d}.mp4` via `VideoWriteFile`.

### Public API

| Class | Kind | Inputs → Outputs | Parameters |
|-------|------|------------------|------------|
| `ArucoMarkerDetector` | fiducial detection | `images: [image]` → `overlays: [overlay]` | (none) |
| `ArucoMarkerOverlay` | annotation | `images: [image]`, `overlays: [overlay]` → `images: [image]` | (none) |

Service protocols: `aruco_marker_detector:0`,
`aruco_marker_overlay:0`.

`ArucoMarkerDetector.process_frame()` returns
`StreamEvent.OKAY, {"overlays": overlays}` with one overlay per
image:

```python
overlay = {
    "corners": corners,  # tuple of (1, 4, 2) float arrays, one per marker
    "ids":     ids       # numpy array of marker ids, or None
}
```

This overlay format is *specific to* `ArucoMarkerOverlay` — it is not
the `objects` / `rectangles` format that
[`ImageOverlay`](../../elements/media/image_io.md) consumes, which is
why the ArUco pair travel together in a graph (the source To Do notes
a plan to integrate the two).

`ArucoMarkerOverlay` accepts PIL images or `numpy.ndarray`, handles
grayscale and RGB inputs, and returns the annotated images (RGB) as
`{"images": images_overlayed}`. Images with no detected markers pass
through unmodified.

Neither element currently takes parameters: the ArUco dictionary is
fixed at `DICT_4X4_50` (`_DEFAULT_ARUCO_TAGS`), although a full
`_ARUCO_TAGS_TABLE` of seventeen OpenCV dictionaries is already
defined, and the marker size constant `_ARUCO_MARKER_SIZE_CM = 70.0`
is a TODO-flagged candidate parameter.

## For framework developers (internals)

### Design

```
    images     +---------------------+  overlays   +--------------------+
  ----------->| ArucoMarkerDetector |------------>| ArucoMarkerOverlay |
              |  cv2.aruco detect   |  {corners,  |  box + dot + id    |
              +---------------------+   ids}      +--------------------+
    images ----------------------------------------------^      |
                                                    images (annotated)
```

- Detection state (`aruco_dict`, `aruco_param`, `aruco_detector`) is
  created once in the detector's constructor — not per
  [Stream](../../concepts/stream.md) — since the dictionary is fixed.
- The OpenCV API changed at 4.7.0: on 4.7.0+ a
  `cv2.aruco.ArucoDetector` instance is constructed and
  `detectMarkers()` is called on it; the pre-4.7.0 branch calls
  `cv2.aruco.ArucoDetector.detectMarkers(...)` statically — see
  Implementation notes.
- Pose estimation (distance and rotation via
  `cv2.aruco.estimatePoseSingleMarkers` and a
  `CameraCalibration.pckl` file) is present but fully commented out —
  **not implemented**. Supporting calibration scripts live in the
  uncommitted `calibration_pose_estimation/` directory alongside the
  source.

### Implementation notes

- The pre-4.7.0 fallback (`aruco.py` lines 104-107) appears broken:
  `cv2.aruco.ArucoDetector` does not exist before OpenCV 4.7.0 — the
  legacy call was `cv2.aruco.detectMarkers(...)`. On older OpenCV,
  the constructor also never assigns `self.aruco_detector`. In
  practice the element requires OpenCV >= 4.7.0.
- `numpy` import failure only logs a warning (unlike `cv2`, which
  raises), yet `ArucoMarkerOverlay` calls `np.array()`
  unconditionally — without numpy it fails at frame time, not import
  time.
- Inside the overlay's marker loop, `corners` is reassigned
  (`corners = marker_corner.reshape((4, 2))`), shadowing the outer
  per-image corners tuple; safe today because `zip()` has already
  captured it, but fragile.
- `import pickle` and the `_ARUCO_MARKER_SIZE_CM` constant serve only
  the commented-out calibration / pose code.

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `ArucoMarkerDetector` | Detect ArUco markers per image; emit corners and ids as `overlays` | [PipelineElement](../../concepts/pipeline_element.md), `cv2.aruco`, `ArucoMarkerOverlay` (consumer) |
| `ArucoMarkerOverlay` | Draw box, centre dot and id text per marker; pass annotated images downstream | [PipelineElement](../../concepts/pipeline_element.md), `cv2`, `numpy`, [Stream](../../concepts/stream.md) |

## Current limitations and roadmap

From the source To Do list — **planned**, not implemented:

- Implement "distance (tvec)" pose estimation and overlay it next to
  the marker id (code drafted but commented out; requires a camera
  calibration file).
- Determine and standardise the image type (PIL and/or
  `numpy.ndarray`).
- Integrate `ArucoMarkerOverlay` with the general-purpose
  [`ImageOverlay`](../../elements/media/image_io.md) element.
- An integrated camera calibration tool (CLI, desktop GUI): capture
  calibration video, perform calibration, standard multi-camera
  calibration file naming / format, and ArUco marker generation
  (calibration board, page of six markers, or one).
- Make `_ARUCO_MARKER_SIZE_CM` (and, implicitly, the ArUco
  dictionary) PipelineDefinition parameters.

## Related concepts

- [PipelineElement](../../concepts/pipeline_element.md) — the
  contract both elements implement
- [Pipeline](../../concepts/pipeline.md) — the deploying graph
- [Stream](../../concepts/stream.md) — StreamEvent semantics
- [image_io](../../elements/media/image_io.md) — `ImageResize`
  upstream; `ImageOverlay`, the planned integration target
- [webcam_io](../../elements/media/webcam_io.md) — the live image
  DataSource
- [YOLO example](../yolo/yolo.md) — combined with the ArUco pair in
  `yolo_pipeline_1.json` / `yolo_pipeline_2.json`
