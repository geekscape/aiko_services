---
title: Image dewarp
description: ImageDewarp — a PipelineElement that undistorts each image
  with an OpenCV lens calibration from a JSON file, with cached remap
  tables and live alpha and calibration updates
type: concept
audience: [developers, end-users]
status: work-in-progress
ste: adapted
source:
  - src/aiko_services/elements/cameras/image_dewarp.py
  - src/aiko_services/elements/cameras/data_in/calibration_identity.json
  - src/aiko_services/elements/cameras/pipelines/depthai_pipeline_1.json
related: [depthai_io, gigev_io, camera, pipeline_element, parameters,
  share, image_io]
version: "0.8-dev"
last_updated: 2026-09-23
---

# Image dewarp

## Overview

**`ImageDewarp`** is a [PipelineElement](../../concepts/pipeline_element.md)
that removes a lens's barrel or pincushion distortion from each image,
with the OpenCV pinhole model. A calibration belongs to one camera and
lens, which is why the element lives with the cameras. It sits directly
after a camera source and before measurement, detection or recording.

The calibration is a JSON file. `data_in/calibration_identity.json` is
a zero-distortion placeholder, a pass-through, so a Pipeline runs before
a real calibration exists.

**Why to use it**: a wide lens makes a straight edge curve and a marker
at the corner smaller than one at the center. Undistort before you
measure:

```bash
cd src/aiko_services/elements/cameras

aiko_pipeline create pipelines/depthai_pipeline_1.json -s 1  \
  -p ImageDewarp.calibration_path <your-camera>.json
```

## For application developers

### Command-line usage

All commands run from `src/aiko_services/elements/cameras`.

```bash
# OAK camera stills, dewarped with the placeholder calibration
aiko_pipeline create pipelines/depthai_pipeline_1.json -s 1

# Your camera's calibration, keeping every source pixel (black borders)
aiko_pipeline create pipelines/depthai_pipeline_1.json -s 1  \
  -p ImageDewarp.calibration_path <your-camera>.json  \
  -p ImageDewarp.alpha 1.0
```

The calibration JSON:

```json
{
  "camera_matrix": [[fx, 0, cx], [0, fy, cy], [0, 0, 1]],
  "dist_coeffs":   [k1, k2, p1, p2, k3],
  "image_size":    [width, height],
  "source":        "free text"
}
```

`camera_matrix` is 3x3 and `dist_coeffs` holds 4, 5, 8, 12 or 14
values, as `cv2.calibrateCamera()` produces them. `image_size` is
optional: the size the fit was made at. When it differs from the frame,
the camera matrix is scaled. That is exact for a scaled or stretched
frame and approximate for a centered crop. `source` is optional
provenance. A device's factory calibration converts to this shape.

### Public API

| Class | Kind | Inputs → Outputs | Parameters |
|-------|------|------------------|------------|
| `ImageDewarp` | PipelineElement | `images: [image]` → `images: [image]` | `calibration_path` (no default), `alpha` (`0.0`: crop to the valid pixels, `1.0`: keep every source pixel with black borders) |

Service protocol: `image_dewarp:0`.

Live shared state:

| Key | Meaning |
|-----|---------|
| `calibration_path`, `image_size`, `coefficients` | The file in use, the size it was fitted at, the coefficient count |
| `alpha` | The value in use |
| `frames`, `maps` | Images dewarped, and remap tables cached |
| `last_error` | `<token>@UTC` of the latest rejected update or failed load |

Writable keys: `alpha` rebuilds the remap tables on the next frame.
`calibration_path` reloads the file, and a bad file records `last_error`
and keeps the current calibration. The framework reads a share item
before the element parameter of the same name, so a written value also
applies to the next Stream.

Pure helpers, exported for tests and for tools: `load_calibration(path)`
returns the matrix, the coefficients and the size, or raises
`ValueError`. `scale_camera_matrix(matrix, from_size, to_size)` scales
for another frame size. `Dewarper` holds one calibration with its
cached maps and applies it to an image.

**Stream lifecycle behavior:**

- `start_stream()` loads the calibration named by `calibration_path`
  and reads `alpha`. A missing parameter, a missing file or a bad file
  returns `StreamEvent.ERROR` with a diagnostic.
- `process_frame()` remaps every image with the tables for its size and
  the current `alpha`, and counts the frames.

## For framework developers (internals)

### Design

```
 ImageDewarp                       Dewarper
   start_stream() ── load() ──────► camera_matrix, dist_coeffs, image_size
   process_frame() ── apply() ────► maps(size): cached per (w, h, alpha)
                                      getOptimalNewCameraMatrix()
                                      initUndistortRectifyMap(CV_16SC2)
                                    cv2.remap(INTER_LINEAR)
   share handler ── set_alpha(), load()
```

- **The element is thin, the Dewarper is testable.** All of the
  arithmetic and the cache live in `Dewarper`, which needs no Pipeline.
  The unit tests prove that an identity calibration is a pass-through
  and that the cache is keyed by size and alpha.
- **Fixed-point maps.** `CV_16SC2` tables are compact and fast. After
  interpolation a pixel can differ by one level from the source, even
  with an identity calibration.

### Implementation notes

- OpenCV is a guarded import. The package imports without it, and
  `start_stream()` reports the install line when it is absent.
- The remap tables are rebuilt when `alpha` changes or a frame of a new
  size arrives, and cleared on a reload.
- The share handler ignores the element's own publications, as the
  camera schemes do, because `ECProducer.update()` calls every handler.

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `ImageDewarp` | Load the calibration per Stream; dewarp each image; publish the state; apply written `alpha` and `calibration_path` | [PipelineElement](../../concepts/pipeline_element.md), `Dewarper`, `ECProducer` ([Share](../../concepts/share.md)) |
| `Dewarper` | Hold one calibration and its remap tables; scale the matrix for another frame size; apply | OpenCV, NumPy, `load_calibration()` |

## Current limitations and roadmap

From the source To Do list:

- A `camera_matrix` and `dist_coeffs` pair as parameters, without a
  file

Known limits: one calibration per element. Two cameras need two
elements.

## Related concepts

- [depthai_io](depthai_io.md) — `depthai_pipeline_1.json` uses this
  element
- [gigev_io](gigev_io.md) — the other camera it serves
- [camera](camera.md) — the shared helpers it borrows for share tokens
- [image_io](../media/image_io.md) — `ImageResize` and the image writers
- [Share](../../concepts/share.md) — the writable keys
