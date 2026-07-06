---
title: System Pipelines transport elements
description: Base64ToImages and ImagesToBase64 — PipelineElements that
  serialize NumPy images to compressed base64 strings so Frames can
  cross a remote Pipeline boundary
type: concept
audience: [developers, end-users]
status: draft
source:
  - src/aiko_services/examples/system_pipelines/elements.py
related: [pipeline_element, pipeline, stream, process_manager, yolo]
version: "0.6"
last_updated: 2026-07-06
---

# System Pipelines transport elements

## Overview

`elements.py` provides the two
[PipelineElements](../../concepts/pipeline_element.md) that let the
System Pipelines example split image processing across *two*
[Pipelines](../../concepts/pipeline.md) — a local webcam Pipeline
and a remote YOLOE detection Pipeline:

- **`ImagesToBase64`** — serializes a Frame's first image
  (`numpy.ndarray`) into a zlib-compressed, base64-encoded string.
- **`Base64ToImages`** — the inverse: decodes a base64 string back
  into a single-image `images` list.

Frame data crossing a remote PipelineElement boundary travels over
MQTT as text, so binary image arrays must be encoded into a
string-safe form first. These elements make that encoding an
explicit, visible graph step at each end of the remote hop.

**Why you'd use it**: run detection on a different host (or process)
from the camera, without changing either Pipeline's internals:

```
(VideoReadWebcam ... ImagesToBase64 Detector Base64ToImages ... VideoShow)
                                    ^^^^^^^^ remote p_yoloe Pipeline
```

See the [package index](ReadMe.md) for the full two-Pipeline example
launched via [ProcessManager](../../concepts/process_manager.md).

## For application developers

### Command-line usage

There is no console script; the elements are deployed by
`pipeline_webcam.json` and `pipeline_yoloe.json`. From the source
header, run from `src/aiko_services/examples/system_pipelines/`:

```bash
aiko_process run 0_process_manager.json   # launches both Pipelines
aiko_dashboard
```

### Public API

| Class | Kind | Inputs → Outputs | Parameters |
|-------|------|------------------|------------|
| `ImagesToBase64` | codec | `images: [image]` → `base64_data: base64_data` | (none) |
| `Base64ToImages` | codec | `base64_data: base64_data` → `images: [image]` | (none) |

Service protocols: `images_to_base64:0`, `base64_to_images:0`.

The module also exposes two plain helper functions, usable outside
any Pipeline (the source header shows the round-trip):

```python
image = (np.random.rand(480, 640, 3) * 255).astype(np.uint8)
base64_data = numpy_array_to_base64(image)
image_copy  = base64_to_numpy_array(base64_data)
```

- `numpy_array_to_base64(arr, *, compress_level=6)` — validates the
  argument is a `numpy.ndarray` and `compress_level` is in `[0..9]`,
  makes the array C-contiguous if needed, then
  `np.save` → `zlib.compress` → `base64.b64encode`.
- `base64_to_numpy_array(b64, *, dtype=None, shape=None,
  validate=True)` — `base64.b64decode` → `zlib.decompress` →
  `np.load(..., allow_pickle=False)`, with optional post-hoc `dtype`
  and `shape` checks that raise `ValueError` on mismatch.

The encoding wire format is therefore:
`base64( zlib( numpy .npy bytes ) )` — self-describing (dtype and
shape ride along in the `.npy` header) and pickle-free.

## For framework developers (internals)

### Design

```
 local Pipeline (p_webcam)                 remote Pipeline (p_yoloe)
+--------------------------+   base64    +---------------------------+
| ... -> ImagesToBase64 ---+--- MQTT --->| Base64ToImages -> YOLOE   |
|                          |             |   -> ImageOverlay         |
| ... <- Base64ToImages <--+--- MQTT ----+-- ImagesToBase64 <- ...   |
+--------------------------+   base64    +---------------------------+
```

- The codec pair appears in *both* PipelineDefinitions: the webcam
  Pipeline encodes before its remote `Detector` element and decodes
  the annotated result; the YOLOE Pipeline decodes on entry and
  re-encodes annotated images on exit.
- `np.save` / `np.load` with `allow_pickle=False` keeps the channel
  free of arbitrary-code-execution risk while preserving dtype and
  shape — a deliberate contrast to pickling.
- Compression level 6 (zlib default) balances CPU against MQTT
  payload size; the helpers expose it, the elements do not.

### Implementation notes

- `ImagesToBase64.process_frame()` serializes `images[0]` only —
  Frames carrying more than one image silently lose all but the
  first. `Base64ToImages` correspondingly always emits a one-image
  list.
- Neither element defines `start_stream()` / `stop_stream()`; they
  are [Stream](../../concepts/stream.md)-lifecycle-neutral codecs.
- The helper functions carry full argument validation and keyword-only
  options, unusual polish for example code — they are intended for
  reuse.

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `ImagesToBase64` | Encode the Frame's first image to a compressed base64 string | [PipelineElement](../../concepts/pipeline_element.md), `numpy_array_to_base64()` |
| `Base64ToImages` | Decode a base64 string back to a one-image list | [PipelineElement](../../concepts/pipeline_element.md), `base64_to_numpy_array()` |

## Current limitations and roadmap

The source has no To Do list. Observed limitations of the
implemented behaviour:

- Single-image Frames only: `images[0]` is encoded, the rest of the
  batch is dropped (see Implementation notes).
- No parameters: compression level, and the optional `dtype` /
  `shape` validation of the helpers, are not exposed as
  PipelineDefinition parameters.
- Base64-over-MQTT is a simple but bandwidth-heavy transport; the
  neighbouring uncommitted `*_zmq` PipelineDefinition variants in
  the same source directory experiment with ZeroMQ instead.

## Related concepts

- [PipelineElement](../../concepts/pipeline_element.md) — the
  contract both codecs implement
- [Pipeline](../../concepts/pipeline.md) — local and remote
  PipelineElement deployment
- [ProcessManager](../../concepts/process_manager.md) — launches the
  two-Pipeline system from `0_process_manager.json`
- [Stream](../../concepts/stream.md) — Frames and StreamEvent
  semantics
- [YOLO example](../yolo/yolo.md) — the `YoloDetector` deployed in
  the remote Pipeline
