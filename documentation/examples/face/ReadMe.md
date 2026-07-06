---
title: Face example index
description: Index of the face detection example — the FaceDetector
  PipelineElement and the face_pipeline.json PipelineDefinition
type: index
audience: [developers, end-users]
status: draft
source:
  - src/aiko_services/examples/face
related: [pipeline, pipeline_element, share, yolo]
version: "0.6"
last_updated: 2026-07-06
---

# Face example index

The face example under `src/aiko_services/examples/face/` detects
human faces in live webcam video using DeepFace (RetinaFace) and
draws bounding boxes on screen — an Aiko Services
[Pipeline](../../concepts/pipeline.md) with the same
detect-overlay-display shape as the
[YOLO example](../yolo/ReadMe.md), plus a live `detections` counter
published via [Share](../../concepts/share.md). See [face](face.md).

Navigation: [concepts guide](../../concepts/ReadMe.md) ·
[media elements](../../elements/media/ReadMe.md) ·
[YOLO example](../yolo/ReadMe.md)

## Module documents

| Document | Summary |
|----------|---------|
| [face](face.md) | `FaceDetector` — DeepFace face extraction producing an overlay of `facial_area` rectangles and a shared cumulative `detections` count |

## PipelineDefinitions

Run from `src/aiko_services/examples/face/`:

```bash
aiko_pipeline create face_pipeline.json -s 1

aiko_pipeline create face_pipeline.json -s 1  \
    -p VideoReadWebcam.path /dev/video2  # Linux: select camera
```

| PipelineDefinition | Pipeline name | Purpose |
|--------------------|---------------|---------|
| `face_pipeline.json` | `p_face` | Webcam → resize → `FaceDetector` → `ImageOverlay` → display (`VideoShow`), plus [`Metrics`](../../elements/observe/elements.md) timing |

Note: `face_pipeline.json` declares the `FaceDetector` /
`ImageOverlay` overlay type as `"{rectangles]"` (mismatched
brackets) rather than the `"[overlay]"` used by the sibling
examples — the type strings are not currently validated.

## Related documentation

- [face](face.md) — the `FaceDetector` concept document
- [YOLO example](../yolo/ReadMe.md) — same Pipeline shape, different
  detector
- [Share](../../concepts/share.md) — how the `detections` counter
  reaches `aiko_dashboard`
- [webcam_io](../../elements/media/webcam_io.md),
  [image_io](../../elements/media/image_io.md),
  [video_io](../../elements/media/video_io.md) — the media elements
  this Pipeline is built from
