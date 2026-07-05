---
title: DataScheme
description: The pluggable mapping from URL schemes such as file: or zmq:
  in data_sources / data_targets parameters to concrete data access code
type: concept
audience: [architects, developers, end-users]
status: work-in-progress
source:
  - src/aiko_services/main/scheme.py
related: [design_overview, data_source_target, pipeline, pipeline_element,
  stream, parameters]
version: "0.6"
last_updated: 2026-07-05
---

# DataScheme

## Overview

A **DataScheme** turns the *scheme* part of a URL — `file:`, `tty:`,
`zmq:`, `rtsp:` — into the code that actually reads or writes the data.
It is the plug-in half of the
[DataSource / DataTarget](data_source_target.md) design: the
PipelineElement decides *when* frames start and stop, the DataScheme
decides *how* bytes at a location become frames (and vice versa). Each
scheme registers itself in a class-level lookup table, and each
[Stream](stream.md) gets its own DataScheme instance, so scheme state is
naturally per-Stream.

**Why you'd use it**: the same [Pipeline](pipeline.md) definition can read
from files today and a network socket tomorrow by changing only a URL
parameter — no PipelineElement code changes:

```bash
aiko_pipeline create pipelines/text_pipeline_0.json -s 1  \
  -p TextReadFile.data_sources file:data_in/in_{}.txt

aiko_pipeline create pipelines/text_zmq_pipeline_0.json -s 1 -sr  \
  -p TextReadZMQ.data_sources zmq://0.0.0.0:6502
```

## For application developers

### Command-line usage

DataScheme has no CLI of its own — it is exercised through
`aiko_pipeline`, whose `-p` (Pipeline parameters) and `-sp` (Stream
parameters) options set the `data_sources` / `data_targets` URLs that
select a scheme, as shown above. See
[DataSource / DataTarget](data_source_target.md) for worked sessions.

### Public API

The base class (`aiko_services.main.scheme`, exported as
`aiko.DataScheme`):

```python
class DataScheme:
    LOOKUP = {}  # key: name, value: class

    def __init__(self, pipeline_element): ...

    @classmethod
    def add_data_scheme(cls, name, data_scheme_class): ...

    @abstractmethod
    def create_sources(self, stream, data_sources,
        frame_generator=None, use_create_frame=True): ...

    def create_targets(self, stream, data_targets): ...
    def destroy_sources(self, stream): ...
    def destroy_targets(self, stream): ...
```

| Operation | Effect |
|-----------|--------|
| `add_data_scheme(name, cls)` | Register `cls` for URL scheme `name`; raises `RuntimeError` if the scheme already exists |
| `create_sources(stream, data_sources, frame_generator, use_create_frame)` | Set up reading from the URLs; start frame creation on the owning PipelineElement; returns `(StreamEvent, dict)` |
| `create_targets(stream, data_targets)` | Set up writing to the URLs; returns `(StreamEvent, dict)` |
| `destroy_sources(stream)` / `destroy_targets(stream)` | Release per-Stream resources on `stop_stream()` |
| `parse_url_scheme(url)` | Return the scheme in lower case; a URL with no `:` defaults to `"file"` |
| `parse_url_path(url)` | Return everything after `scheme:` with a leading `//` stripped (currently authority *and* path — see roadmap) |
| `contains_all(source, match)` | Helper: true when every character of `match` appears in `source` — used to detect `{}` templates in paths |

A DataScheme instance is constructed with the owning PipelineElement and
keeps `self.pipeline_element` and `self.share`; per-Stream state belongs
in `stream.variables`, not on `self` beyond that.

**Registered schemes** (each module registers at import time):

| Scheme | Class | Source |
|--------|-------|--------|
| `file` | `DataSchemeFile` | `src/aiko_services/elements/media/scheme_file.py` |
| `tty` | `DataSchemeTTY` | `src/aiko_services/elements/media/scheme_tty.py` |
| `zmq` | `DataSchemeZMQ` | `src/aiko_services/elements/media/scheme_zmq.py` |
| `rtsp` | `DataSchemeRTSP` | `src/aiko_services/elements/gstreamer/scheme_rtsp.py` |
| `colab` | `DataSchemeColab` | `src/aiko_services/examples/colab/scheme_colab.py` |

(A `webcam://` scheme is planned — `webcam_io.py` currently selects the
camera by parameter instead.)

**URL grammar** accepted by the parse helpers:

```
scheme:path                    file:data_in/in_00.txt
scheme://authority/path        zmq://0.0.0.0:6502
path                           data_in/in_00.txt   (scheme defaults to file)
```

The `file` scheme additionally treats `{}` in a path as a template /
filename filter: `file:data_in/in_{}.txt` reads every matching file in
the directory (sorted), deriving a `file_id` from the matched portion.

Registering your own scheme is one call at module scope, as
`DataSchemeFile` does:

```python
aiko.DataScheme.add_data_scheme("file", DataSchemeFile)
```

## For framework developers (internals)

### Design

```
DataSource.start_stream(stream)
   │  data_sources = ["zmq://0.0.0.0:6502", …]
   │  scheme = parse_url_scheme(data_sources[0])
   ▼
DataScheme.LOOKUP ── "file" ─► DataSchemeFile
   registry         "tty"  ─► DataSchemeTTY
                    "zmq"  ─► DataSchemeZMQ ── instantiated per Stream
                                  │
                                  ▼
                    stream.variables["data_scheme"]
                    create_sources() ─► pipeline_element.create_frame()
                                        or create_frames(frame_generator)
```

Key design points:

- **Registry, not enumeration.** `LOOKUP` is a plain class-level dict
  populated by import side-effects; a Pipeline only supports the schemes
  whose modules it has imported (the media / gstreamer element modules do
  this when they are loaded as PipelineElement definitions).
- **Instance per Stream.** The owning
  [DataSource or DataTarget](data_source_target.md) constructs a fresh
  DataScheme in `start_stream()` and stores it in
  `stream.variables["data_scheme"]` — "DataScheme instance variables are
  per-Stream variables".
- **Frame-creation policy stays with the scheme.** `create_sources()`
  decides between the thread-less `create_frame()` (single known input,
  when `use_create_frame` is enabled) and `create_frames()` with a frame
  generator and optional `rate` — see `DataSchemeFile.create_sources()`
  for the canonical example.

### Implementation notes

- `DataScheme` is a plain Python base class, **not** an Aiko Services
  Interface / Component — there is no `Interface.default()` binding and
  no remote proxy; schemes are always in-process with their
  PipelineElement.
- `create_sources()` is decorated `@abstractmethod`, but `DataScheme`
  does not inherit from `abc.ABC`, so instantiation is not actually
  blocked and the method has a default body returning
  `(StreamEvent.OKAY, {})`. Treat it as abstract by convention.
- `parse_data_url_path()` / `parse_data_url_scheme()` are the original
  names; `parse_url_path()` / `parse_url_scheme()` are the aliases to
  prefer.
- Duplicate registration raises `RuntimeError` — safe under normal module
  caching, but reloading a scheme module (or two modules claiming the
  same scheme) fails fast by design.

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `DataScheme` (base) | Own the scheme registry (`LOOKUP`, `add_data_scheme()`); define the per-Stream lifecycle contract (`create_sources()` / `create_targets()` / `destroy_*()`); parse URLs | [DataSource / DataTarget](data_source_target.md) (instantiation and lifecycle), [Stream](stream.md) (per-Stream state) |
| `DataSchemeFile` (exemplar) | Resolve `file:` paths — single file, directory, `{}` glob template; choose `create_frame()` vs `create_frames()`; batch via `data_batch_size`; pace via `rate` | `DataScheme`, [PipelineElement](pipeline_element.md) (`create_frame(s)`, `get_parameter()`) |

## Current limitations and roadmap

From the source To Do lists:

- Replace the hand-rolled parsing with `urllib.parse.urlparse()` —
  gaining `scheme`, `netloc`, `path`, `query`, `fragment`, `hostname`
  and `port`
- Provide `parse_url()` returning `scheme`, `authority` and `path`
  separately; `parse_url_path()` currently returns authority and path
  combined ("Should only return path")
- `DataSchemeFile`: `paths.append((path, None))` — the `None` should
  probably be a `file_id`
- A `webcam://` scheme (`webcam_io.py` To Do), and a `queue://` scheme
  backed by a Queue(Category) (Category roadmap)

Also note the enforcement gap described in Implementation notes:
`@abstractmethod` without `abc.ABC` means an incomplete scheme fails at
use time, not construction time.

## Related concepts

- [Design overview](design_overview.md)
- [DataSource / DataTarget](data_source_target.md) — the PipelineElement
  bases that select and drive a DataScheme
- [Pipeline](pipeline.md) — where data flows between elements
- [PipelineElement](pipeline_element.md) — `create_frame()` /
  `create_frames()` invoked by schemes
- [Stream](stream.md) — the unit a DataScheme instance is scoped to
- [Parameters](parameters.md) — how `data_sources` / `data_targets`
  reach the element
