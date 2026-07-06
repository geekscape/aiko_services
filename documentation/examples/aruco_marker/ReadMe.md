---
title: ArUco marker example index
description: Index of the ArUco fiducial marker example — the
  ArucoMarkerDetector / ArucoMarkerOverlay PipelineElements and the
  aruco_pipeline_0.json PipelineDefinition
type: index
audience: [developers, end-users]
status: draft
source:
  - src/aiko_services/examples/aruco_marker
related: [pipeline, pipeline_element, yolo]
version: "0.6"
last_updated: 2026-07-06
---

# ArUco marker example index

The ArUco marker example under
`src/aiko_services/examples/aruco_marker/` detects printed ArUco
fiducial markers in live webcam video and draws each marker's
bounding box, centre and id back onto the image — an Aiko Services
[Pipeline](../../concepts/pipeline.md) built from two example
[PipelineElements](../../concepts/pipeline_element.md) and the
standard [media element families](../../elements/media/ReadMe.md).
See [aruco](aruco.md).

Navigation: [concepts guide](../../concepts/ReadMe.md) ·
[media elements](../../elements/media/ReadMe.md) ·
[YOLO example](../yolo/ReadMe.md)

## Module documents

| Document | Summary |
|----------|---------|
| [aruco](aruco.md) | `ArucoMarkerDetector` (corners and ids per image) and `ArucoMarkerOverlay` (box, centre dot and id text) — pose estimation drafted but not implemented |

## PipelineDefinitions

Run from `src/aiko_services/examples/aruco_marker/`:

```bash
aiko_pipeline create aruco_pipeline_0.json -s 1 -ll debug

aiko_pipeline create aruco_pipeline_0.json -s 1  \
    -p VideoReadWebcam.path /dev/video2  # Linux: select camera
```

| PipelineDefinition | Pipeline name | Purpose |
|--------------------|---------------|---------|
| `aruco_pipeline_0.json` | `p_aruco_0` | Webcam → resize → `ArucoMarkerDetector` → `ArucoMarkerOverlay` → display (`VideoShow`) and record MP4 (`VideoWriteFile` to `data_out/out_{:02d}.mp4`) |

The combined ArUco + YOLO Pipelines `yolo_pipeline_1.json` and
`yolo_pipeline_2.json` live in the neighbouring
[YOLO example](../yolo/ReadMe.md) and deploy these elements
alongside `YoloDetector`.

## Related documentation

- [aruco](aruco.md) — the concept document for both elements
- [YOLO example](../yolo/ReadMe.md) — combined detection Pipelines
- [webcam_io](../../elements/media/webcam_io.md),
  [image_io](../../elements/media/image_io.md),
  [video_io](../../elements/media/video_io.md) — the media elements
  this Pipeline is built from
- [Robot example](../robot/ReadMe.md) — deploys
  `ArucoMarkerDetector` in its OODA-loop Pipeline
