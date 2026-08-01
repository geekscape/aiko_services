---
title: Google Colab DataScheme (colab://)
description: DataSchemeColab — a work-in-progress DataScheme that turns
  the browser web camera in a Google Colab notebook into a DataSource;
  currently a browser-loopback demonstration, not yet Pipeline-connected
type: concept
audience: [developers]
status: draft
ste: adapted
source:
  - src/aiko_services/examples/colab/scheme_colab.py
related: [scheme, data_source_target, pipeline_element, stream,
  elements, colab_io]
version: "0.6"
last_updated: 2026-08-01
---

# Google Colab DataScheme (colab://)

## Overview

`scheme_colab.py` implements **`DataSchemeColab`**, which is registered
as the `colab` [DataScheme](../../concepts/scheme.md). Thus a
[DataSource](../../concepts/data_source_target.md) PipelineElement can
name the browser web camera of a Google Colab notebook as its media
source:

```json
"parameters": {"data_sources": "(colab://)"}
```

[scheme_file](../../elements/media/scheme_file.md) resolves a `file://`
URL to files on disk, and pulls records from them. But the `colab://`
scheme has no path and no authority. Its "device" is the browser of the
notebook user. The JavaScript-to-kernel callback bridge of Google Colab
reaches that browser. `create_sources()` injects a
JavaScript widget that captures 320x240 JPEG frames from the camera
and sends each one to a registered Python callback.

**Important**: this scheme is a **work-in-progress demonstration**. In
its current form the Python callback flips each image vertically, and
returns it straight to the browser. Thus the frames never reach the
[Pipeline](../../concepts/pipeline.md) (refer to Design). The
committed
consumer is `VideoReadColab` in the
[colab example elements](elements.md) through
`pipelines/colab_ds_pipeline_0.json`.

## For application developers

### Command-line usage

There is no usage comment in the source. The intended invocation,
inside a Google Colab notebook cell, follows the standard pattern:

```bash
aiko_pipeline create colab_ds_pipeline_0.json -s 1 -ll debug
```

Note: `colab_ds_pipeline_0.json` currently deploys `VideoReadColab`
from the module `aiko_services.elements.colab.elements`, which does not
exist. The correct module path is
`aiko_services.examples.colab.elements`. Thus the PipelineDefinition
fails to load as committed.

The `data_sources` list must contain exactly one entry, `(colab://)`.
`data_targets` would contain a single `(colab://)` entry in the same
way, after the DataTarget side is implemented (refer to the roadmap).

### Public API

```python
__all__ = ["DataSchemeColab"]
```

Applications do not call DataSchemes directly. The DataSource and
DataTarget machinery looks the scheme up from the URL in the
`data_sources` or `data_targets` parameter. The contract implemented:

| Method | Status | Behavior |
|--------|--------|-----------|
| `create_sources(stream, data_sources, ...)` | implemented (partial) | Create `queue_in` / `queue_out`, register the `notebook.handle_frame` kernel callback, inject the JavaScript camera widget; returns `StreamEvent.OKAY` |
| `create_targets(stream, data_targets)` | stub | Returns `StreamEvent.OKAY, {}` — no-op |
| `frame_generator(stream, frame_id)` | implemented, **unused** | Batch up to `data_batch_size` records from `queue_in`, else `StreamEvent.NO_FRAME` — never invoked because the `create_frames()` call is commented out |
| `destroy_sources()` / `destroy_targets()` | commented out | The base-class no-ops apply; the camera stream is only stopped by the widget's "Stop stream" button |

Registration happens at import time:

```python
aiko.DataScheme.add_data_scheme("colab", DataSchemeColab)
```

## For framework developers (internals)

### Design

The intended design mirrors the other DataSchemes. A frame generator
pulls batched records from a queue, and the transport feeds that queue.
But the connection between the kernel callback and the queue does not
exist yet:

```
Browser (JavaScript widget)          Colab kernel (Python)
  camera -> canvas -> JPEG data URL
      |  invokeFunction('notebook.handle_frame', dataUrl)
      v
  _handle_frame():  decode -> FLIP_TOP_BOTTOM -> re-encode
      |                    .
      |                    .  intended, not implemented:
      |                    .  queue_in.put(record)
      |                    .  frame_generator() -> Pipeline
      v                    .  Pipeline output -> queue_out
  JSON {data_url} returned to browser, drawn on output canvas
```

- **Pull-style skeleton, push-style reality**: `queue_in`,
  `queue_out`, `frame_generator()` and the (commented-out)
  `self.pipeline_element.create_frames(stream, frame_generator)` call
  sketch the standard DataScheme flow. The live code path is a direct
  browser loopback inside `_handle_frame()`.
- The JavaScript widget paces itself with `requestAnimationFrame()`,
  and it awaits each kernel round-trip. Thus the browser never queues
  more than one in-flight frame. Compare the slider-controlled interval
  in `do_start_stream()` of [colab_io](colab_io.md). That widget is the
  more developed sibling of this one, with audio support, pause, volume
  and rate controls.

### Implementation notes

- If `google.colab` cannot be imported, the module sets
  `_GOOGLE_COLAB_IMPORTED = False` and a `diagnostic` string. But
  `create_sources()` still references the undefined name `output`
  (`scheme_colab.py:42`). Thus it raises `NameError` outside Google
  Colab.
  The flag and diagnostic are never consulted (a `TODO: Optional
  warning flag` marks the spot).
- The kernel callback name `notebook.handle_frame` differs from the
  `notebook.handle_image_frame` callback registered by
  [colab_io](colab_io.md), so both modules can coexist in one
  notebook.
- `frame_generator()` reads the `data_batch_size` parameter (default
  1) from the owning PipelineElement, matching the batching convention
  of the other DataSchemes.

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `DataSchemeColab` | Register the `colab` scheme; inject the browser camera widget; receive frames through the kernel callback; (intended) feed records to the Pipeline through `frame_generator()` | [DataScheme](../../concepts/scheme.md) (base class and `LOOKUP` registry); [DataSource](../../concepts/data_source_target.md) `VideoReadColab` ([colab elements](elements.md)); `google.colab.output`; `IPython.display`; PIL |

## Current limitations and roadmap

From the source To Do list — **planned**, not implemented:

- Implement the DataTarget side (`create_targets()` is a stub).

Additional gaps, implemented-versus-intended:

- **Frames do not reach the Pipeline**: `create_frames()` is
  commented out (`scheme_colab.py:39`), `_handle_frame()` never feeds
  `queue_in`, and the vertical flip is hard-coded in the callback.
  The scheme currently demonstrates the browser / kernel transport
  only.
- `destroy_sources()` / `destroy_targets()` are commented out — no
  teardown of the callback or widget when the Stream stops.
- `NameError` when imported and used outside Google Colab (see
  Implementation notes).
- `pipelines/colab_ds_pipeline_0.json` references a wrong deploy
  module path (see Command-line usage).

## Related concepts

- [DataScheme](../../concepts/scheme.md) — the base class, registry
  and URL-parsing conventions
- [DataSource / DataTarget](../../concepts/data_source_target.md) —
  the PipelineElements that select schemes by URL
- [scheme_file](../../elements/media/scheme_file.md) — the default,
  fully implemented DataScheme to compare against
- [colab elements](elements.md) — `VideoReadColab`, the DataSource
  that names `(colab://)`
- [colab_io](colab_io.md) — the push-style alternative wiring for the
  same browser camera
- [Stream](../../concepts/stream.md) — StreamEvent semantics
  (`OKAY` / `NO_FRAME`)
