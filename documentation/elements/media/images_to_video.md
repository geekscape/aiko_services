---
title: Images-to-video script (legacy)
description: A dormant Pipeline_2020-era script for assembling image files
  into a video — superseded by images_to_video_pipeline.json
type: concept
audience: [developers, end-users]
status: work-in-progress
source:
  - src/aiko_services/elements/media/images_to_video.py
  - src/aiko_services/elements/media/pipelines/images_to_video_pipeline.json
related: [pipeline, pipeline_element, image_io, video_io, video_example]
version: "0.6"
last_updated: 2026-07-06
---

# Images-to-video script (legacy)

## Overview

`images_to_video.py` is a **dormant legacy script** from the
`Pipeline_2020` generation of the framework: it declares a two-element
pipeline — `ImageReadFile → VideoWriteFile` — as a Python list of
dicts, intended to assemble numbered image files
(`z_input/image_{:06d}.jpg`) into a video (`z_output.mp4` at
29.97 fps). Its `__main__` block is entirely commented out, so
executing it does nothing; the `Pipeline_2020` class it targeted no
longer exists.

Its *job* is alive and well, done declaratively: the committed
PipelineDefinition
`src/aiko_services/elements/media/pipelines/images_to_video_pipeline.json`
wires the modern `ImageReadFile` ([image_io](image_io.md)) into
`VideoWriteFile` ([video_io](video_io.md)) under the current
[Pipeline](../../concepts/pipeline.md) engine. This document exists to
mark the file's status and point to the replacement.

**Why you'd use it**: you wouldn't — use the JSON pipeline:

```bash
cd src/aiko_services/elements/media
aiko_pipeline create pipelines/images_to_video_pipeline.json -s 1
```

## For application developers

### Command-line usage

The script's own usage header is historical and non-functional:

```bash
LOG_LEVEL=DEBUG ./images_to_video.py   # legacy; runs, but does nothing
```

The working equivalent (`p_images_to_video`):

```bash
cd src/aiko_services/elements/media

# data_in/in_{}.jpeg  -->  data_out/out.mp4  (MP4V, 30 fps)
aiko_pipeline create pipelines/images_to_video_pipeline.json -s 1

# The reverse conversion (see video_io.md / image_io.md)
aiko_pipeline create pipelines/video_to_images_pipeline.json -s 1
```

Note: `VideoWriteFile` requires NumPy images
([video_io](video_io.md)); the pipeline JSON's element parameter
intended for this is spelled `"MEDIA_TYPE": "numpy"` — parameter names
are lower-case (`media_type`), so as committed the conversion parameter
does not take effect (see Current limitations and roadmap).

### Public API

None. The module defines only constants and a `pipeline_definition`
list in the obsolete format (element dicts with `name`, `module`,
`successors`, `parameters`), and its parameters (`image_pathname`,
`video_pathname`, `video_frame_rate`) match no current element. The
module paths it references (`aiko_services.elements.image_io`,
`aiko_services.elements.video_io`) predate the `media` subpackage and
no longer resolve.

For the real elements' contracts, see [image_io](image_io.md)
(`ImageReadFile`) and [video_io](video_io.md) (`VideoWriteFile`).

## For framework developers (internals)

### Design

Historical interest only: the script shows the pre-JSON
PipelineDefinition style — Python dicts with `successors` links,
consumed by a `Pipeline_2020(pipeline_definition, FRAME_RATE).run()`
call. The modern engine replaced this with JSON definitions, an
S-expression `graph`, typed `input`/`output` declarations and
`deploy` local/remote sections (see
[Pipeline](../../concepts/pipeline.md) and
[PipelineElement](../../concepts/pipeline_element.md)).

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| (none — module holds only a legacy `pipeline_definition` literal) | Historical reference for the Pipeline_2020 definition format | `ImageReadFile` ([image_io](image_io.md)), `VideoWriteFile` ([video_io](video_io.md)) — its modern successors |

## Current limitations and roadmap

- The script is dead code: `Pipeline_2020` no longer exists, the
  `__main__` block is commented out, and the element module paths and
  parameter names are obsolete. Candidate for deletion once the
  team is satisfied nothing references it.
- In the replacement `images_to_video_pipeline.json` (as currently in
  the working tree), `ImageReadFile`'s conversion parameter is spelled
  `"MEDIA_TYPE"` — upper-case, so `get_parameter("media_type")` will
  not find it and images stay PIL, which `VideoWriteFile` rejects
  (`"Image media_type must be a numpy array"`). Correcting the key to
  `media_type` (value `numpy`) makes the pipeline work end-to-end.

## Related concepts

- [Pipeline](../../concepts/pipeline.md) — the modern engine and JSON
  definition format that replaced Pipeline_2020
- [PipelineElement](../../concepts/pipeline_element.md) — the current
  element contract
- [image_io](image_io.md) — `ImageReadFile`, the modern source end
- [video_io](video_io.md) — `VideoWriteFile`, the modern target end
- [video_example](video_example.md) — sibling legacy script from the
  same generation
