---
title: Aiko Services PipelineElements documentation
description: Index of OKF concept documents for the PipelineElement library
  in src/aiko_services/elements/ — control, gstreamer, media, observe and
  utilities packages, with their example PipelineDefinitions
type: index
audience: [developers, end-users]
status: draft
version: "0.6"
last_updated: 2026-07-06
---

# Aiko Services: PipelineElements documentation

This directory documents the **PipelineElement library** —
`src/aiko_services/elements/` — the processing nodes assembled into
[Pipelines](../concepts/pipeline.md) by PipelineDefinition JSON files.
One OKF concept document per source module, grouped by package,
mirroring the source layout. Each package index also maps the committed
example PipelineDefinitions to the documents covering the elements they
exercise.

These documents build on the [Concepts guide](../concepts/ReadMe.md) —
in particular [PipelineElement](../concepts/pipeline_element.md),
[Parameters](../concepts/parameters.md), [Stream](../concepts/stream.md),
[Data Source / Target](../concepts/data_source_target.md) and
[Scheme](../concepts/scheme.md) — and follow the same
audience-first template
(`documentation/constitution/t_00_OkfConceptTemplate.md`).

## Packages

| Package | Contents |
|---------|----------|
| [control/](control/ReadMe.md) | Control-flow elements — the Loop element repeating a graph section until an S-expression condition becomes false |
| [gstreamer/](gstreamer/ReadMe.md) | RTSP PipelineElements and the `rtsp` DataScheme (current style), plus the legacy GStreamer video reader/writer wrapper classes |
| [media/](media/ReadMe.md) | The largest family — text, image, video, webcam and audio elements, the `file` / `tty` / `zmq` DataSchemes, and twenty example PipelineDefinitions |
| [observe/](observe/ReadMe.md) | Observability elements — Inspect (log/file/stdout taps on Frame data) and Metrics (per-element timing and memory) |
| [utilities/](utilities/ReadMe.md) | The Expression element and S-expression evaluation helpers for defining, deleting and renaming Frame data values |

## Reading paths

- **Building a first Pipeline**: [media/elements.md](media/elements.md)
  (Mock and NoOp) and [media/text_io.md](media/text_io.md), driven by the
  example PipelineDefinitions in the [media index](media/ReadMe.md).
- **Working with cameras and video**:
  [media/webcam_io.md](media/webcam_io.md),
  [media/video_io.md](media/video_io.md), then
  [gstreamer/rtsp_io.md](gstreamer/rtsp_io.md) for network cameras.
- **Writing a new PipelineElement**: read
  [PipelineElement](../concepts/pipeline_element.md) and
  [Data Source / Target](../concepts/data_source_target.md) first, then
  copy the closest element here; [observe/](observe/ReadMe.md) and
  [utilities/](utilities/ReadMe.md) show the smallest complete examples.

## Status

The element library is under active development (version 0.6) and of
mixed maturity: some modules are current DataSource / DataTarget style,
some are legacy wrappers or dormant Pipeline_2020-era scripts — each
document states which, and separates implemented behaviour from
planned / work-in-progress, based on the source code as of 2026-07-06.

## Related documentation

- [Concepts guide](../concepts/ReadMe.md) — the framework concepts these
  elements are built on
- [Examples guide](../examples/ReadMe.md) — complete example
  applications whose Pipelines deploy these elements alongside their
  own
