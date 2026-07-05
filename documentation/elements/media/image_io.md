---
title: Image I/O elements
description: PipelineElements that read, convert, resize, overlay and write
  frames of images — via files or ZeroMQ sockets, as PIL or NumPy images
type: concept
audience: [developers, end-users]
status: work-in-progress
source:
  - src/aiko_services/elements/media/image_io.py
  - src/aiko_services/elements/media/pipelines/image_pipeline_0.json
  - src/aiko_services/elements/media/pipelines/image_pipeline_1.json
  - src/aiko_services/elements/media/pipelines/image_zmq_pipeline_0.json
  - src/aiko_services/elements/media/pipelines/image_zmq_pipeline_1.json
  - src/aiko_services/elements/media/pipelines/video_to_images_pipeline.json
  - src/aiko_services/elements/media/pipelines/images_to_video_pipeline.json
related: [pipeline_element, data_source_target, scheme, stream, parameters,
  scheme_file, scheme_zmq, text_io, video_io, webcam_io]
version: "0.6"
last_updated: 2026-07-06
---

# Image I/O elements

## Overview

The **image I/O elements** carry still images through an Aiko Services
[Pipeline](../../concepts/pipeline.md): sources that read image files or
receive images over ZeroMQ, transforms that convert, resize, crop and
overlay, and targets that write image files or send images over ZeroMQ.
The frame data convention is `images: [image]`, where an image may be a
PIL `Image.Image` or a NumPy `ndarray` — the module provides conversion
helpers and an `ImageConvert` element so a
[PipelineDefinition](../../concepts/pipeline.md) can pick the
representation each stage needs.

This family follows the same
[DataSource / DataTarget](../../concepts/data_source_target.md) +
[DataScheme](../../concepts/scheme.md) design as
[text_io](text_io.md); the video elements ([video_io](video_io.md),
[webcam_io](webcam_io.md)) produce the same `images` frame data, so
image transforms slot into video pipelines unchanged.

**Why you'd use it**: batch-process a directory of images, or stream a
webcam between hosts, with the wiring in JSON and the locations as URL
parameters:

```bash
cd src/aiko_services/elements/media

aiko_pipeline create pipelines/image_pipeline_0.json -s 1  \
  -p ImageReadFile.data_sources file:data_in/in_00.jpeg  \
  -p ImageResize.resolution 320x240                        \
  -p ImageWriteFile.data_targets file:data_out/out_00.jpeg
```

## For application developers

### Command-line usage

All commands run from `src/aiko_services/elements/media`. Options:
`-s 1` create Stream 1, `-sr` show the response, `-ll debug` log level,
`-gt 10` grace time, `-p ELEMENT.name value` element parameters.

File pipelines (from the `image_io.py` usage header):

```bash
# Read JPEGs matching a template, resize, write JPEGs
aiko_pipeline create pipelines/image_pipeline_0.json -s 1 -sr -ll debug

# Pace at 1 frame per second
aiko_pipeline create pipelines/image_pipeline_0.json -s 1 -p rate 1.0

# Batch 8 images per frame
aiko_pipeline create pipelines/image_pipeline_0.json -s 1  \
  -p ImageReadFile.data_batch_size 8

# Directory glob template
aiko_pipeline create pipelines/image_pipeline_0.json -s 1  \
  -p ImageReadFile.data_sources file:data_in/in_{}.jpeg

# Explicit single image in / out with a resize
aiko_pipeline create pipelines/image_pipeline_0.json -s 1  \
  -p ImageReadFile.data_sources file:data_in/in_00.jpeg  \
  -p ImageResize.resolution 320x240                        \
  -p ImageWriteFile.data_targets file:data_out/out_00.jpeg

# Read images and display them in a window (VideoShow from video_io)
aiko_pipeline create pipelines/image_pipeline_1.json -s 1
```

ZeroMQ pipelines — run the server (reader) first, then the client
(writer):

```bash
# Server: receive image records, resize and display
aiko_pipeline create pipelines/image_zmq_pipeline_0.json -s 1 -sr  \
           -ll debug -gt 10
aiko_pipeline create pipelines/image_zmq_pipeline_0.json -s 1 -sr  \
           -p ImageReadZMQ.data_sources zmq://0.0.0.0:6502

# Client: read image files, send image records to the server
aiko_pipeline create pipelines/image_zmq_pipeline_1.json -s 1 -sr  \
           -ll debug                                               \
           -p ImageReadFile.rate 2.0                               \
           -p ImageWriteZMQ.data_targets zmq://192.168.0.1:6502
```

Conversion pipelines shared with [video_io](video_io.md):

```bash
# Explode a video into JPEG frames (rate 0.0 = flat out)
aiko_pipeline create pipelines/video_to_images_pipeline.json -s 1

# Assemble JPEG frames into an MP4
aiko_pipeline create pipelines/images_to_video_pipeline.json -s 1
```

### Public API

Conversion helpers (plain functions, importable from
`aiko_services.elements.media`):

| Function | Effect |
|----------|--------|
| `image_to_bytes(image, format="JPEG")` | Encode a PIL/NumPy image to `bytes` ("JPEG" or "PNG") |
| `bytes_to_image(image_bytes)` | Decode `bytes` into a PIL `Image.Image` |
| `convert_image(image, media_type)` / `convert_images(images, media_type)` | Convert to `"numpy"` or `"pil"`; unknown media types raise `ValueError` |
| `convert_image_to_numpy(image)` / `convert_image_to_pil(image)` | Direct converters; return `None` for unknown input types |

PipelineElement classes:

| Class | Kind | Inputs → Outputs | Parameters |
|-------|------|------------------|------------|
| `ImageReadFile` | DataSource | `paths: [Path]` → `images: [image]` | `data_sources` (`file:` URL, required), `data_batch_size` (default 1), `rate`, `media_type` (`numpy` \| `pil`, default: PIL as loaded) |
| `ImageReadZMQ` | DataSource | `records: [bytes]` → `images: [image]` | `data_sources` (`zmq://host:port_range`), `data_batch_size`, `media_type` (accepts `image/pil` form), `compressed` (default `false`: zlib-decompress each record) |
| `ImageConvert` | transform | `images` → `images` | `media_type` (`numpy` \| `pil`; unset = pass through) |
| `ImageResize` | transform | `images` → `images` | `resolution` `"WxH"` (unset = pass through); handles PIL and NumPy |
| `ImageTransform` | transform | `images` → `images` | `resolution` `"WxH"` — currently a duplicate of `ImageResize` (see roadmap) |
| `ImageSquareCenterCrop` | transform | `images` → `images` | (none) — centre-crop to the shortest side, PIL or NumPy |
| `ImageOverlay` | transform | `images`, `overlay` → `images` | (none yet) — draw `overlay["rectangles"]` and `overlay["objects"]` name/confidence labels (OpenCV) |
| `ImageOverlayFilter` | transform | `overlay` → `overlay` | `deny` (list of names, default `[]`), `threshold` (default 0.0) — drop overlay objects by name or low confidence |
| `ImageWriteFile` | DataTarget | `images` → (none) | `data_targets` (`file:` URL, required); `{}` template formats `target_file_id` per image |
| `ImageWriteZMQ` | DataTarget | `images` → (none) | `data_targets` (`zmq://host:port`), `compressed` (default `false`: zlib-compress) |
| `ImageOutput` | pass-through | `images` → `images` | (none) — response tail |

Service protocols: `image_read_file:0`, `image_read_zmq:0`,
`image_convert:0`, `image_resize:0`, `image_transform:0`,
`image_square_center_crop:0`, `image_overlay:0`,
`image_overlay_filter:0`, `image_write_file:0`, `image_write_zmq:0`,
`image_output:0`.

**URL forms**: `file:path`, `file:dir/in_{}.jpeg` (glob template) via
[scheme_file](scheme_file.md); `zmq://host:port[-port]` via
[scheme_zmq](scheme_zmq.md).

**Stream lifecycle behaviour:**

- `ImageReadFile.process_frame(stream, paths)` opens each path with PIL,
  optionally converts per `media_type`, and sets
  `stream.variables["timestamps"]` (currently hard-coded to a 25 fps
  clock from `frame_id`). Load failure → `StreamEvent.ERROR`.
- `ImageReadZMQ` wire format: one ZeroMQ message per image, the raw
  JPEG/PNG bytes from `image_to_bytes()`, optionally zlib-compressed
  when `compressed` is true on both ends (`image_zmq_pipeline_0.json`
  documents `media_type: "image/pil"`; the element takes the subtype
  after `/`).
- `ImageWriteFile` converts to PIL before `image.save(path)`; a
  non-template `data_targets` overwrites the same path each frame, a
  `{}` template writes `out_00.jpeg`, `out_01.jpeg`, … per image.
- `ImageOverlay` expects `overlay` frame data shaped
  `{"rectangles": [{"x","y","w","h"}, …], "objects": [{"name",
  "confidence"}, …]}` — typically produced by an ML detector element and
  optionally pre-filtered by `ImageOverlayFilter`.

## For framework developers (internals)

### Design

```
 ImageReadFile    ImageReadZMQ                     DataSources
      │file:          │zmq://
      └───────┬───────┘
              ▼
        images: [image]        PIL and/or NumPy per stage
              │
  ImageConvert → ImageResize / ImageTransform
  ImageSquareCenterCrop → ImageOverlay(Filter)     transforms
              │
      ┌───────┴───────┐
 ImageWriteFile   ImageWriteZMQ                    DataTargets
      │file:          │zmq://
              │
         ImageOutput                               response tail
```

- **Dual image representation.** Elements accept PIL or NumPy where
  practical (`ImageResize`, `ImageSquareCenterCrop`,
  `convert_image_to_pil()` in `ImageWriteFile`); OpenCV-based elements
  (`ImageOverlay`) require NumPy. `ImageConvert` (or a source's
  `media_type` parameter) normalises the representation at the point it
  matters — e.g. `images_to_video_pipeline.json` needs NumPy before
  `VideoWriteFile`.
- **Optional native dependencies.** `cv2` and `numpy` imports are
  guarded (`_CV2_IMPORTED`, `_NUMPY_IMPORTED`) so the module imports
  without them, but the guards are not yet checked at use sites (TODOs
  in source) — using an OpenCV-dependent element without `cv2` fails at
  `process_frame()` time.
- The colour convention across the media elements is **RGB** in frame
  data; OpenCV elements convert to BGR internally and back.

### Implementation notes

- `ImageOverlay` hard-codes style (`color`, `font`, `font_scale`,
  `thickness`, `threshold`) on `self` — safe only because they are
  read-only per frame; TODOs plan to expose them as
  [Parameters](../../concepts/parameters.md).
- `ImageWriteFile` returns the placeholder diagnostic
  `"UNKNOWN IMAGE TYPE"` (marked `TODO: FIX ME !`) when
  `convert_image_to_pil()` cannot handle the input type.
- `ImageReadZMQ` and `ImageWriteZMQ` contain commented-out stubs for a
  planned `image:length:content` record header (media-type framing).
- `ImageTransform` is byte-for-byte the same resize logic as
  `ImageResize`; `image_io.py` `__all__` exports it but
  `src/aiko_services/elements/media/__init__.py` does not import it —
  it is only loadable via `deploy.local.module`.

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `ImageReadFile` | Load image files from `paths`; optional `media_type` conversion; set `timestamps` | [DataSource](../../concepts/data_source_target.md), [DataSchemeFile](scheme_file.md), [Stream](../../concepts/stream.md), [Parameters](../../concepts/parameters.md) |
| `ImageReadZMQ` | Decode (optionally decompress) received image records | [DataSource](../../concepts/data_source_target.md), [DataSchemeZMQ](scheme_zmq.md) |
| `ImageConvert` | Convert images between PIL and NumPy per `media_type` | [PipelineElement](../../concepts/pipeline_element.md) |
| `ImageResize` / `ImageTransform` | Resize to `resolution` (PIL or NumPy backends) | [PipelineElement](../../concepts/pipeline_element.md), [Parameters](../../concepts/parameters.md) |
| `ImageSquareCenterCrop` | Centre-crop to square (helper `square_center_crop()`) | [PipelineElement](../../concepts/pipeline_element.md) |
| `ImageOverlay` | Draw rectangles and labels from `overlay` onto images (OpenCV) | [PipelineElement](../../concepts/pipeline_element.md) |
| `ImageOverlayFilter` | Filter `overlay` objects by `deny` list and confidence `threshold` | [PipelineElement](../../concepts/pipeline_element.md), [Parameters](../../concepts/parameters.md) |
| `ImageWriteFile` | Save images via PIL to path / `{}` template | [DataTarget](../../concepts/data_source_target.md), [DataSchemeFile](scheme_file.md) |
| `ImageWriteZMQ` | Encode (optionally compress) and send image records | [DataTarget](../../concepts/data_source_target.md), [DataSchemeZMQ](scheme_zmq.md) |
| `ImageOutput` | Pass `images` through as the Pipeline response tail | [PipelineElement](../../concepts/pipeline_element.md) |

## Current limitations and roadmap

From the source To Do list — **planned**, not implemented:

- Media-type encoding for image records
  (`image:length:content`, `image/jpeg:length:content`) and out-of-band
  encoding metadata
- Consolidate the multiple `media_pipeline_?.json` files using Graph
  Paths
- `ImageResize`: scale factors (`{"scale": "1/3"}`) and single-dimension
  resolutions; combine `ImageResize` and `ImageSquareCenterCrop` (and
  the duplicate `ImageTransform`) into one element with parameters;
  interpolation quality/speed parameter (`INTER_AREA` / `INTER_CUBIC` /
  `INTER_LINEAR`)
- Refactor the optional `cv2` / `numpy` import guards into a common
  function shared with [video_io](video_io.md), and actually check the
  guards at use sites
- Stream-close semantics: decide what closes a Stream when all
  `data_sources` are consumed and it is not the default Stream
- A Stream parameter selecting the output NumPy format; `ImageReadFile`
  accepting typed DataSources (URL + media type); metrics (frame rates)
- Archive (`tgz`, `zip`) DataSources with filename filters
- `ImageOverlay`: colours, fonts, camera name, date/time, FPS, ellipses,
  lines, masks, polygons, pose figures, metrics — all still TODO
- Hard-coded 25 fps `timestamps` in `ImageReadFile` / `ImageReadZMQ`
  needs a configurable frame rate (shared issue with
  [video_io](video_io.md) / [webcam_io](webcam_io.md))

## Related concepts

- [PipelineElement](../../concepts/pipeline_element.md) — the contract
  every class here implements
- [DataSource / DataTarget](../../concepts/data_source_target.md) — base
  classes for the read/write elements
- [DataScheme](../../concepts/scheme.md) — URL plug-ins; see
  [scheme_file](scheme_file.md) and [scheme_zmq](scheme_zmq.md)
- [Stream](../../concepts/stream.md) — lifecycle and `stream.variables`
- [Parameters](../../concepts/parameters.md) — how `-p` values reach
  elements
- [video_io](video_io.md) — video elements producing/consuming the same
  `images` frame data
- [webcam_io](webcam_io.md) — live camera DataSource
- [text_io](text_io.md) — the simplest exemplar of this element family
