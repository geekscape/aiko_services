---
title: System Pipelines example index
description: Index of the System Pipelines example — a ProcessManager
  bootstrap launching a local webcam Pipeline and a remote YOLOE
  detection Pipeline connected by base64 image transport
type: index
audience: [developers, end-users]
status: draft
source:
  - src/aiko_services/examples/system_pipelines
related: [pipeline, pipeline_element, process_manager, yolo]
version: "0.6"
last_updated: 2026-07-06
---

# System Pipelines example index

The System Pipelines example under
`src/aiko_services/examples/system_pipelines/` demonstrates a small
*system of Pipelines*: an overall data-flow
[Pipeline](../../concepts/pipeline.md) reading from a web camera,
which delegates object detection to a *remote* Pipeline containing a
YOLOE [PipelineElement](../../concepts/pipeline_element.md) — both
launched together by one
[ProcessManager](../../concepts/process_manager.md) command. It
exercises three framework features at once:

1. **Bootstrap** — `aiko_process run 0_process_manager.json` starts
   both Pipelines as managed child processes.
2. **Remote PipelineElement deployment** — the webcam Pipeline's
   `Detector` element is deployed `"remote"` with a
   `service_filter` naming `p_yoloe`; the Pipeline discovers the
   remote detection Pipeline and proxies Frames to it.
3. **Image transport** — `ImagesToBase64` / `Base64ToImages` encode
   NumPy images as compressed base64 strings to cross the remote
   boundary (see [elements](elements.md)).

Navigation: [concepts guide](../../concepts/ReadMe.md) ·
[media elements](../../elements/media/ReadMe.md) ·
[YOLO example](../yolo/ReadMe.md)

## Running the example

From `src/aiko_services/examples/system_pipelines/`:

```bash
aiko_process run 0_process_manager.json
aiko_dashboard   # observe p_webcam, p_yoloe and the ProcessManager
```

`0_process_manager.json` is not a PipelineDefinition — it is a
ProcessManager *process definition*: a JSON list of command lines,
each started as a managed child process:

```json
[
  "aiko_pipeline create pipeline_webcam.json -ll DEBUG_ALL --windows",
  "aiko_pipeline create pipeline_yoloe.json  -ll DEBUG_ALL"
]
```

Commands are split on whitespace (no shell quoting), so each entry
must be a simple argument list.

## Module documents

| Document | Summary |
|----------|---------|
| [elements](elements.md) | `Base64ToImages` and `ImagesToBase64` — NumPy image ⇄ compressed base64 string codecs, plus the reusable helper functions |

## PipelineDefinitions

| Definition | Name | Purpose |
|------------|------|---------|
| `0_process_manager.json` | — | ProcessManager process definition: launch the two Pipelines below |
| `pipeline_webcam.json` | `p_webcam` | Webcam (throttled to 1 Hz) → resize (320x240) → `ImagesToBase64` → **remote** `Detector` (service_filter `name: p_yoloe`) → `Base64ToImages` → display, plus [`Metrics`](../../elements/observe/elements.md) |
| `pipeline_yoloe.json` | `p_yoloe` | The remote detection service: `Base64ToImages` → [`YoloDetector`](../yolo/yolo.md) (`yoloe-11s-seg.pt`, names `(glasses person)`) → `ImageOverlay` → `ImagesToBase64`, plus `Metrics` |

Notes:

- `pipeline_webcam.json` uses `"_create_stream_": "*"` /
  `"_destroy_stream_exit_": "*"` (wildcard), unlike the single-stream
  `"1"` used by the standalone [YOLO](../yolo/ReadMe.md) Pipelines.
- The remote `Detector` element's `deploy.remote.module` refers to
  `aiko_services.examples.pipeline.elements` — for a remote
  deployment the element is realised by discovery of the `p_yoloe`
  Service, not by importing that module locally.
- The YOLOE checkpoint `yoloe-11s-seg.pt` is not committed; the
  Ultralytics package downloads it on first use.

## Related documentation

- [elements](elements.md) — the base64 transport codec elements
- [ProcessManager](../../concepts/process_manager.md) — `aiko_process
  run` and managed child processes
- [Pipeline](../../concepts/pipeline.md) — local and remote
  PipelineElement deployment
- [YOLO example](../yolo/ReadMe.md) — `YoloDetector` and the
  standalone YOLOE Pipelines
- [webcam_io](../../elements/media/webcam_io.md),
  [image_io](../../elements/media/image_io.md),
  [video_io](../../elements/media/video_io.md) — the media elements
  these Pipelines are built from
