---
title: Synthetic DataScheme
description: The synth DataScheme — synthesizes video frames without a
  camera, with the frame id and a timestamp as text, through an extensible
  synth://kind/pattern?options URL grammar
type: concept
audience: [developers, end-users]
status: work-in-progress
ste: adapted
source:
  - src/aiko_services/elements/media/scheme_synth.py
  - src/aiko_services/elements/media/pipelines/synthetic_pipeline_0.json
  - src/aiko_services/elements/media/pipelines/synthetic_pipeline_1.json
related: [scheme, data_source_target, pipeline_element, stream, parameters,
  synthetic_io, scheme_file, image_io, video_io, elements]
version: "0.8-dev"
last_updated: 2026-09-10
---

# Synthetic DataScheme

## Overview

**`DataSchemeSynthetic`** implements the `synth` URL scheme of the
[DataScheme](../../concepts/scheme.md) plug-in design. A `synth://` URL
names data that the framework generates internally, instead of data that
it reads from a device, a file or a network. The full word is
**Synthetic** in every class name and document. The URL scheme and the
source file name are the only abbreviations: `synth://` and
`scheme_synth.py`.

Synthetic data is a data provenance, not only test tooling. Calibration,
health checks, benchmarking, deterministic regression tests,
demonstrations and CI all need a data source that exists without
hardware. The first implemented kind is `video`, with one pattern,
`plain`: a plain background with the frame id (large) and a timestamp
(small) as centered text. Thus a person can check the frame order and
the frame rate by eye, or in a recording.

This scheme is unrelated to the `Mock` PipelineElement in
[elements](elements.md). `Mock` is a structural stand-in for an element
that does not exist yet (Pipeline topology). Synthetic is about where the
data comes from (data provenance). The two combine freely in one graph.

**Why to use it**: exercise any video Pipeline with no camera attached:

```bash
cd src/aiko_services/elements/media

aiko_pipeline create pipelines/synthetic_pipeline_0.json -s 1  # view live
```

## For application developers

### Command-line usage

`DataSchemeSynthetic` has no CLI of its own. The
[SyntheticVideoRead](synthetic_io.md) element selects it with a
`data_sources` URL. All commands run from
`src/aiko_services/elements/media`:

```bash
# Synthetic frames --> CaptureLimit --> resize --> display for 10 s, or "x"
aiko_pipeline create pipelines/synthetic_pipeline_0.json -s 1

# Synthetic frames --> CaptureLimit --> record 10 s to data_out/synthetic_0.mp4
aiko_pipeline create pipelines/synthetic_pipeline_1.json -s 1

# A smaller frame with the frame id only, in orange
aiko_pipeline create pipelines/synthetic_pipeline_0.json -s 1  \
  -p SyntheticVideoRead.data_sources  \
     "(synth://video/plain?width=640&height=360&text=frame_id&color=orange)"

# Unpaced: as fast as the Pipeline can process
aiko_pipeline create pipelines/synthetic_pipeline_0.json -s 1  \
  -p SyntheticVideoRead.rate 0 -p CaptureLimit.frame_count 300
```

### Public API

URL grammar accepted in `data_sources`:

```
synth://                                   all defaults (below)
synth://<kind>/<pattern>?<option>=<value>&<option>=<value>
synth://video/plain?width=1280&height=720&text=frame_id
```

The default URL `synth://` is the same as
`synth://video/plain?width=1920&height=1080&text=frame_id,timestamp&color=white&background=black`.

Options of the `video/plain` pattern:

| Option | Default | Meaning |
|--------|---------|---------|
| `width`, `height` | `1920`, `1080` | Frame size in pixels, positive integers. The size is a URL option because `resolution` is already an `ImageResize` and `VideoWriteFile` parameter, which a Pipeline-level value would feed too |
| `text` | `frame_id,timestamp` | Comma list of the text items to show, or `none` for a blank frame |
| `color` | `white` | Text color: a Pillow color name, percent-encoded hex (`%23ff8800`) or bare hex (`ff8800`) |
| `background` | `black` | Background color, same forms as `color` |

An unknown kind, pattern or option key returns `StreamEvent.ERROR` from
`start_stream()`. A value that does not validate does the same. The
`diagnostic` names the URL and the supported kinds.

The element parameter `rate` (default `15.0` frames per second) paces
the frame generator. A `rate` of `0` is unpaced: the generator runs as
fast as the Pipeline mailbox permits.

Frame data delivered to the owning element's `process_frame()`:
`{"images": [image]}`, where `image` is a NumPy `uint8` array of shape
`(height, width, 3)` in RGB order. The scheme also sets
`stream.variables["timestamps"]` to the render time. That is the same
instant that the timestamp text shows, as ISO 8601 UTC with
milliseconds, for example `2026-09-10T00:47:46.866Z`.

Pure helpers, exported for tests and for other renderers:

| Function | Meaning |
|----------|---------|
| `parse_synth_url(url)` | Returns `(kind, pattern, options)`. Raises `ValueError` for a repeated option key, or a path with more than one segment |
| `render_text_frame(frame_id, timestamp, width, height, text, color, background)` | Returns the rendered frame. `timestamp` is seconds since the epoch, an argument so that a test is deterministic |

Registration (module import side-effect):

```python
aiko.DataScheme.add_data_scheme("synth", DataSchemeSynthetic)
```

**Stream lifecycle behavior:**

- `create_sources()` parses the URL, validates the options and builds a
  per-Stream render function. It then starts `create_frames()` at
  `rate` frames per second. A validation error returns
  `StreamEvent.ERROR` on the main thread, which is the correct place.
- `frame_generator()` renders one frame with the current time and
  returns `StreamEvent.OKAY`. A render failure returns
  `StreamEvent.STOP`, not `ERROR`. An `ERROR` on the generator thread
  destroys the Stream on that thread, and the process lingers. `STOP`
  posts a graceful `destroy_stream()` to the main event thread.
- `destroy_sources()` sets a `stopped` flag. The next
  `frame_generator()` call returns `STOP`, which ends the generator
  thread. The framework does not stop that thread itself.

## For framework developers (internals)

### Design

```
data_sources: "(synth://video/plain?width=640&text=frame_id)"
   │  parse_synth_url()  ─► ("video", "plain", {"width": "640", ...})
   ▼
_FACTORIES[(kind, pattern)] ─► _video_plain(options)
   │  validate every option, then close over them
   ▼
render(frame_id, timestamp) ──► {"images": [uint8 HxWx3 RGB]}
   ▲
   │ frame_generator() on the create_frames() thread, at "rate" fps
   │ stopped ─► StreamEvent.STOP
```

- **Pattern is the background, text is an overlay.** The `text`,
  `color` and `background` options are not specific to `plain`. A future
  `checkerboard` or `test_pattern` pattern gets the same overlay, so the
  frame id stays visible on every pattern.
- **One factory table.** `_FACTORIES` maps `(kind, pattern)` to a
  factory. A new pattern or a new kind is one more entry. The factory
  validates at `create_sources()` time, so a bad URL fails before the
  first frame.
- **Per-Stream state.** The render function and the `stopped` flag live
  on the scheme instance, which is one per
  [Stream](../../concepts/stream.md).

### Implementation notes

- Text is rendered with Pillow only. `ImageFont.load_default(size)`
  gives a scalable built-in font (Pillow 10.1 and later), so no TrueType
  file is needed. Fonts are cached per size with `lru_cache`.
- The font size is computed from a measurement at 100 points, because
  text metrics scale linearly. Thus a nine digit frame id still fits in
  a small frame.
- The rendered `PIL.Image` is copied with `np.array()`, so the frame is
  writable. Downstream elements that draw on the image in place work.
- `parse_synth_url()` uses `urllib.parse`, as the
  [DataScheme](../../concepts/scheme.md) roadmap asks. The kind is the
  URL authority and the pattern is the path.
- Pillow renders text with anti-aliasing. Thus the text edges hold gray
  pixels, and the exact pixels are not identical across Pillow releases.
  A test must not compare a frame with a stored image.

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `DataSchemeSynthetic` | Parse and validate a `synth://` URL; build a per-Stream render function; generate paced frames on the `create_frames()` thread; stop the generator when the Stream is destroyed | [DataScheme](../../concepts/scheme.md) (base, registry), [SyntheticVideoRead](synthetic_io.md) (owner), [PipelineElement](../../concepts/pipeline_element.md) (`create_frames()`, `get_parameter()`), [Stream](../../concepts/stream.md) |
| `parse_synth_url()`, `render_text_frame()` | Pure helpers with no framework dependency, unit tested in `tests/unit/test_scheme_synth.py` | Pillow, NumPy |

## Current limitations and roadmap

From the source To Do list:

- Support `data_batch_size` (several images per frame)
- More video patterns: `test_pattern` (color bars), `checkerboard` and a
  moving marker
- Other kinds: `audio/sine`, `image/...`, `text/...`
- A verifying `synth://` DataTarget, `SyntheticVideoWrite`. A DataTarget
  is where data goes. A synthetic target can not store data, so it is a
  consuming endpoint: discard frames as a benchmark sink, or decode the
  frame id from each image and check that the sequence is complete and
  monotonic. That check finds dropped and reordered frames on any
  transport. It needs a machine-readable frame id in the image, for
  example a block code strip

Known limits: the unpaced mode (`rate` 0) relies on the Pipeline mailbox
throttle in `create_frames()`. Pixel output is not identical across
Pillow releases (see Implementation notes).

## Related concepts

- [DataScheme](../../concepts/scheme.md) — the plug-in base class and
  registry
- [DataSource / DataTarget](../../concepts/data_source_target.md) — the
  elements that instantiate this scheme per Stream
- [PipelineElement](../../concepts/pipeline_element.md) —
  `create_frames()` invoked by the scheme
- [Stream](../../concepts/stream.md) — scope of all scheme state
- [Parameters](../../concepts/parameters.md) — `data_sources`, `rate`
- [synthetic_io](synthetic_io.md) — `SyntheticVideoRead`, the element
  built on this scheme
- [scheme_file](scheme_file.md) — the canonical sibling scheme
- [elements](elements.md) — the unrelated `Mock` placeholder element
