---
title: DataSource and DataTarget
description: PipelineElement base classes that load frames of data from,
  and store frames of data to, locations named by URL parameters
type: concept
audience: [architects, developers, end-users]
status: work-in-progress
source:
  - src/aiko_services/main/source_target.py
related: [design_overview, scheme, pipeline, pipeline_element, stream,
  parameters]
version: "0.6"
last_updated: 2026-07-05
---

# DataSource and DataTarget

## Overview

**DataSource** and **DataTarget** are the standard base classes for
[PipelineElements](pipeline_element.md) that sit at the edges of a
[Pipeline](pipeline.md): a DataSource *loads* frames of data from given
locations (files, a terminal, a socket, a camera stream), a DataTarget
*stores* frames at given locations. The locations are URLs supplied
through the `data_sources` / `data_targets`
[Parameters](parameters.md), and the URL scheme selects a pluggable
[DataScheme](scheme.md) implementation that does the actual I/O — so one
element class works across many transports.

Concrete subclasses live with the media elements, e.g. `TextReadFile`,
`ImageReadFile`, `VideoReadFile`, `AudioWriteFile`, `TextWriteZMQ`
(`src/aiko_services/elements/media/`) and the GStreamer RTSP elements.

**Why you'd use it**: write the domain logic (`process_frame()`) once and
let the base class plus a DataScheme handle discovery of inputs, frame
generation pacing, batching and clean-up. Change where the data comes
from at launch time:

```bash
aiko_pipeline create pipelines/text_pipeline_0.json -s 1 \
  -p TextReadFile.data_sources file:data_in/in_00.txt  \
  -p TextTransform.transform titlecase                   \
  -p TextWriteFile.data_targets file:data_out/out_00.txt
```

## For application developers

### Command-line usage

DataSource and DataTarget have no CLI of their own — they are exercised
via `aiko_pipeline`, using `-p` (Pipeline parameters) or `-sp` (Stream
parameters) to set their URLs and knobs (examples from the
`text_io.py` usage header):

```bash
# Read a directory of files matching a template, one frame per file
aiko_pipeline create pipelines/text_pipeline_0.json -s 1  \
  -p TextReadFile.data_sources file:data_in/in_{}.txt

# Batch 8 items per frame
aiko_pipeline create pipelines/text_pipeline_0.json -s 1  \
  -p TextReadFile.data_batch_size 8

# Pace frame creation at 1 frame per second
aiko_pipeline create pipelines/text_pipeline_0.json -s 1 -p rate 1.0

# Stream between hosts over ZeroMQ instead of files
aiko_pipeline create pipelines/text_zmq_pipeline_1.json -s 1 -sr  \
  -p TextReadFile.rate 2.0                                        \
  -p TextWriteZMQ.data_targets zmq://192.168.0.1:6502
```

### Public API

Both classes extend `PipelineElementImpl` and are exported as
`aiko.DataSource` and `aiko.DataTarget`. A subclass normally implements
only `__init__()` and `process_frame()` — the base class owns the Stream
lifecycle:

```python
class DataSource(PipelineElementImpl):
    def start_stream(self, stream, stream_id,
        frame_generator=None, use_create_frame=True): ...
    def stop_stream(self, stream, stream_id): ...

class DataTarget(PipelineElementImpl):
    def start_stream(self, stream, stream_id): ...
    def stop_stream(self, stream, stream_id): ...
```

Parameters (from the source header comments):

| Parameter | Applies to | Meaning |
|-----------|-----------|---------|
| `data_sources` | DataSource | List of URLs to load data from (**required**) |
| `data_targets` | DataTarget | List of URLs to store data at (**required**) |
| `data_batch_size` | DataSource | How many data items grouped per frame, default `1` |
| `rate` | DataSource | Frames created per second, default `None` (as fast as possible) |

The URL list is an S-expression, e.g.
`"(file:pathname_0 file:pathname_1 ...)"` — a single URL needs no
parentheses. The *first* URL's scheme selects the
[DataScheme](scheme.md) for the whole list.

`start_stream()` returns the standard `(StreamEvent, dict)` pair:
`StreamEvent.ERROR` with a `diagnostic` when `data_sources` /
`data_targets` is missing (`required=True`) or the URL scheme is not in
`DataScheme.LOOKUP` — e.g.
`'DataSource URL scheme "smb" is not supported'`.

The `use_create_frame` argument lets a single-input Stream use the more
efficient, thread-less `create_frame()` instead of `create_frames()`
with a frame generator (which requires a thread); subclasses may also
pass their own `frame_generator` when the scheme's default is not
suitable.

A complete DataSource subclass (verbatim from
`src/aiko_services/elements/media/text_io.py`):

```python
class TextReadFile(aiko.DataSource):  # PipelineElement
    def __init__(self, context: aiko.ContextPipelineElement):
        context.set_protocol("text_read_file:0")
        context.call_init(self, "PipelineElement", context)

    def process_frame(self, stream, paths) -> Tuple[aiko.StreamEvent, dict]:
        texts = []
        for path in paths:
            try:
                with path.open("r") as file:
                    text = file.read()
                texts.append(text)
                self.logger.debug(f"{self.my_id()}: {path} ({len(text)})")
            except Exception as exception:
                diagnostic = f"Error loading text: {exception}"
                return aiko.StreamEvent.ERROR, {"diagnostic": diagnostic}

        return aiko.StreamEvent.OKAY, {"texts": texts}
```

The frame arguments a subclass's `process_frame()` receives (here
`paths`) are produced by the DataScheme's frame generator; a DataTarget
subclass receives ordinary upstream frame data and uses the per-Stream
variables the scheme prepared (e.g. `target_path`,
`target_path_template`, `target_file_id` for the `file` scheme).

There is no wire protocol specific to these classes — frames travel via
the standard [Pipeline](pipeline.md) mechanisms.

## For framework developers (internals)

### Design

```
        DataSource(PipelineElementImpl)          DataTarget
        ───────────────────────────────          ──────────
start_stream():                            start_stream():
  data_sources ─ parse S-expression          data_targets ─ parse
  scheme = parse_url_scheme(url[0])          scheme = parse_url_scheme(url[0])
  data_scheme = LOOKUP[scheme](self)         data_scheme = LOOKUP[scheme](self)
  stream.variables["data_scheme"]            stream.variables["data_scheme"]
  data_scheme.create_sources()               data_scheme.create_targets()
        │ create_frame() /                          ▲
        ▼ create_frames(frame_generator)            │
  process_frame(stream, paths…) ──► … ──► process_frame(stream, data…)
                                             writes via stream.variables
stop_stream():                             stop_stream():
  data_scheme.destroy_sources()              data_scheme.destroy_targets()
```

Key design points:

- **Template Method.** The base classes fix the Stream lifecycle
  skeleton; the variable parts are delegated *down* to the
  [DataScheme](scheme.md) (how to reach the data) and *up* to the
  subclass (`process_frame()` — what the data means).
- **Per-Stream scheme instance.** "Each Pipeline Stream may have an
  individual DataSource DataScheme instance. Therefore, DataScheme
  instance variables are per-Stream variables" — all mutable state lives
  in `stream.variables`, keeping elements re-entrant across concurrent
  Streams.
- **Edge elements, ordinary elements.** A DataSource / DataTarget is
  still a plain PipelineElement — it can be filtered, composed and
  remoted like any other; only its relationship to frame *creation*
  (sources) and side-effects (targets) is special.

### Implementation notes

- `_get_data_sources()` / `_get_data_targets()` call
  `get_parameter(..., required=True)` — a missing parameter raises
  `KeyError`, which `start_stream()` converts into
  `StreamEvent.ERROR` with the exception as `diagnostic`.
- URL lists are parsed with `parse(data_sources, car_cdr=False)` from
  `aiko_services.main.utilities.parser`.
- Only the first URL's scheme is inspected; mixed-scheme lists are not
  detected — the remaining URLs are handed as-is to the chosen scheme.
- `stream.variables["data_scheme"]` is set to `None` *before* scheme
  lookup so `stop_stream()` can tell "never started" from "started".
  `DataSource.stop_stream()` guards against the `None`;
  `DataTarget.stop_stream()` currently does **not** — if
  `start_stream()` failed after storing `None` (unsupported scheme),
  `stop_stream()` raises `AttributeError`. Follow the DataSource pattern
  when touching this code.
- `use_create_frame=True` is only a *permission* — the scheme decides
  (e.g. `DataSchemeFile` uses `create_frame()` only when exactly one
  path resulted).

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `DataSource` | Resolve `data_sources` parameter; select and instantiate the DataScheme per Stream; start frame creation (`create_frame` / `create_frames`); destroy sources on `stop_stream()` | [DataScheme](scheme.md), `PipelineElementImpl` ([PipelineElement](pipeline_element.md)), [Stream](stream.md), [Parameters](parameters.md) |
| `DataTarget` | Resolve `data_targets` parameter; select and instantiate the DataScheme per Stream; prepare target state; destroy targets on `stop_stream()` | [DataScheme](scheme.md), `PipelineElementImpl`, [Stream](stream.md), [Parameters](parameters.md) |

## Current limitations and roadmap

From the source To Do list:

- Design refactor to disambiguate DataSource and DataScheme
  implementations — in particular, generalise
  `VideoReadFile.frame_generator()`
- Possibly move DataSource and DataTarget into
  `aiko_services.main.data_source.py`, and define `data_sources` /
  `data_targets` as Python data classes
- Improve `utilities/parser.py:parse()` to combine "command" and
  "parameters" into a single parameter

Known sharp edges (see Implementation notes): the missing `None` guard
in `DataTarget.stop_stream()`, and single-scheme-per-list selection
based on the first URL only.

## Related concepts

- [Design overview](design_overview.md)
- [DataScheme](scheme.md) — the pluggable I/O half selected by the URL
  scheme
- [Pipeline](pipeline.md) — where DataSources and DataTargets sit at the
  edges
- [PipelineElement](pipeline_element.md) — the base contract, including
  `create_frame()` / `create_frames()` and `process_frame()`
- [Stream](stream.md) — the lifecycle unit; scheme state is per-Stream
- [Parameters](parameters.md) — how `data_sources`, `data_targets`,
  `data_batch_size` and `rate` are supplied
