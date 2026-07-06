---
title: YOLO example index
description: Index of the YOLO object detection example — the
  YoloDetector PipelineElement, the fine-tuned yolov8n_robotdog.pt
  checkpoint and the five committed PipelineDefinitions
type: index
audience: [developers, end-users]
status: draft
source:
  - src/aiko_services/examples/yolo
related: [pipeline, pipeline_element, aruco, elements]
version: "0.6"
last_updated: 2026-07-06
---

# YOLO example index

The YOLO example under `src/aiko_services/examples/yolo/` runs
Ultralytics object detection inside an Aiko Services
[Pipeline](../../concepts/pipeline.md): live webcam or video-file
images in, labelled bounding boxes drawn and displayed (or written to
video) out. One [PipelineElement](../../concepts/pipeline_element.md),
`YoloDetector`, covers both a fine-tuned YOLOv8 checkpoint and
open-vocabulary YOLOE models — see [yolo](yolo.md).

Navigation: [concepts guide](../../concepts/ReadMe.md) ·
[media elements](../../elements/media/ReadMe.md) ·
[ArUco marker example](../aruco_marker/ReadMe.md)

## Module documents

| Document | Summary |
|----------|---------|
| [yolo](yolo.md) | `YoloDetector` — YOLOv8 (robot-dog classes) or YOLOE (prompted class names) inference producing an `overlay` of objects and rectangles |

The committed `yolov8n_robotdog.pt` model file is the default
checkpoint: YOLOv8-nano fine-tuned with robot-dog classes (balls,
cups, cones, signs, trees, the XGO-Mini 2 robot). YOLOE checkpoints
(`yoloe-11[sml]-seg.pt`) are not committed — the Ultralytics package
downloads them on first use.

## PipelineDefinitions

Five committed PipelineDefinitions. Run from
`src/aiko_services/examples/yolo/`, e.g:

```bash
aiko_pipeline create yolo_pipeline_0.json -s 1
aiko_pipeline create yoloe_pipeline_0.json -s 1
aiko_pipeline create yolo_pipeline_0.json -s 1  \
    -sp VideoReadWebcam.path /dev/video2  # Linux: select camera
```

| PipelineDefinition | Pipeline name | Purpose |
|--------------------|---------------|---------|
| `yolo_pipeline_0.json` | `p_yolo` | YOLOv8 baseline: webcam → resize → `YoloDetector` → overlay → display, plus [`Metrics`](../../elements/observe/elements.md) timing |
| `yolo_pipeline_1.json` | `p_aruco_yolo_1` | Combined detectors: webcam → resize → [`ArucoMarkerDetector`](../aruco_marker/aruco.md) + `YoloDetector` → both overlays → display and record MP4 (`VideoWriteFile`) |
| `yolo_pipeline_2.json` | `p_aruco_yolo_2` | As `yolo_pipeline_1.json` plus `VideoSample` (drop every second frame) and `Metrics` — throughput tuning variant |
| `yoloe_pipeline_0.json` | `p_yoloe` | YOLOE open-vocabulary live: webcam → resize → `YoloDetector` with `model yoloe-11s-seg.pt` and a twelve-name `names` prompt → overlay → display → `Metrics` |
| `yoloe_pipeline_3.json` | `p_yoloe` | YOLOE batch file-to-file: `VideoReadFile` `data_in/things.mp4` → detect → overlay → `VideoWriteFile` `data_out/things.mp4` (MP4V, 10 fps, 640x360) — no display |

Notes:

- `yolo_pipeline_1.json` and `yolo_pipeline_2.json` are *combined*
  ArUco + YOLO Pipelines (their names say `p_aruco_yolo_*`), pairing
  this example with the
  [ArUco marker example](../aruco_marker/ReadMe.md).
- There is no committed `yoloe_pipeline_1.json` or
  `yoloe_pipeline_2.json` — the numbering gap is intentional in the
  working tree.
- `yoloe_pipeline_3.json` expects `data_in/things.mp4`, which is not
  committed — supply your own input video.

## Related documentation

- [yolo](yolo.md) — the `YoloDetector` concept document
- [ArUco marker example](../aruco_marker/ReadMe.md) — the other
  detector in the combined Pipelines
- [System Pipelines example](../system_pipelines/ReadMe.md) —
  `YoloDetector` running in a remote Pipeline behind a
  ProcessManager bootstrap
- [webcam_io](../../elements/media/webcam_io.md),
  [image_io](../../elements/media/image_io.md),
  [video_io](../../elements/media/video_io.md) — the media elements
  these Pipelines are built from
- [Robot example](../robot/ReadMe.md) — reuses
  `yolov8n_robotdog.pt` in its OODA-loop Pipeline
