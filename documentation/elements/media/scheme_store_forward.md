---
title: StoreForward DataScheme
description: The store_forward:// DataScheme — as a target it names the
  outbox directory that a SegmentStoreForward Actor watches; as a source it
  names the inbox that the Actor fills, which a ReadStoreForward element
  reads in order
type: concept
audience: [developers, end-users]
status: work-in-progress
ste: adapted
source:
  - src/aiko_services/elements/media/scheme_store_forward.py
related: [scheme, data_source_target, store_forward, store_forward_io,
  store_forward_base, scheme_file]
version: "0.8-dev"
last_updated: 2026-11-23
---

# StoreForward DataScheme

## Overview

**`DataSchemeStoreForward`** registers the `store_forward://` URL scheme
for the [DataScheme](../../concepts/scheme.md) lookup. A `data_targets`
URL names the outbox directory that a
[SegmentStoreForward](../../concepts/store_forward.md) Actor watches. The
DataTarget elements that use it,
[`VideoWriteStoreForward`](store_forward_io.md) and
[`TextWriteStoreForward`](store_forward_base.md), write each finished
segment into that directory, and the Actor forwards it to the peer host.

A `data_sources` URL names the inbox that the peer Actor fills. Only a
[`ReadStoreForward`](store_forward_base.md) element, for example
`TextReadStoreForward`, can use it as a source.

**Why to use it**: a Pipeline stays a dataflow graph (P8) and knows
nothing about the network. It writes files. The Actor, a separate
process, takes custody of them:

```bash
aiko_pipeline create pipelines/store_forward_pipeline_0.json -s 1  \
    -p VideoWriteStoreForward.data_targets "(store_forward://~/store_forward/out)"
```

## For application developers

### Command-line usage

The scheme has no command line of its own. It is selected by the
`data_targets` parameter of a DataTarget element, on the command line or
in the PipelineDefinition:

```bash
# Relative to the working directory
-p VideoWriteStoreForward.data_targets "(store_forward://data_out/outbox)"

# Absolute: three slashes
-p VideoWriteStoreForward.data_targets "(store_forward:///home/pi/store_forward/out)"

# Home-relative
-p VideoWriteStoreForward.data_targets "(store_forward://~/store_forward/out)"

# Optional file name prefix (default: none)
-p VideoWriteStoreForward.segment_prefix cam0

# Source: the inbox, and a work directory outside it
-p TextReadStoreForward.data_sources "(store_forward:///srv/inbox/host3)"
-p TextReadStoreForward.work_directory "~/store_forward/host3"
```

### Public API

```python
class DataSchemeStoreForward(aiko.DataScheme):
    def create_sources(self, stream, data_sources, frame_generator, ...)
    def create_targets(self, stream, data_targets)

aiko.DataScheme.add_data_scheme("store_forward", DataSchemeStoreForward)
```

`create_targets()` resolves the URL path (with `~` expanded) and checks
that it is an existing, writable directory. It validates the optional
`segment_prefix` parameter against `[A-Za-z0-9_-]{0,32}`. The default is
empty, no prefix. Then it sets two Stream variables for the element:
`target_outbox` and `target_prefix`. It publishes `outbox` in the
element's share. A missing directory or a bad prefix returns
`StreamEvent.ERROR` with a diagnostic.

`create_sources()` accepts only a `ReadStoreForward` element. Such an
element puts a reader factory in the Stream variables before it calls the
scheme. The scheme resolves the inbox and checks that it is a readable
and writable directory. It checks that `work_directory` is set and is
outside the inbox. Then it asks the element for its `SegmentReader` and
publishes `inbox` in the share of the element. Last, it starts the frame
generator at `rate` polls each second (default 1.0).

## For framework developers (internals)

### Design

```
 "(store_forward://~/store_forward/out)"
        │ parse_url_path()  expanduser()  realpath()
        ▼
 stream.variables: target_outbox, target_prefix
        │
        ▼
 VideoWriteStoreForward  ──►  ~/store_forward/out/.2026-09-15_03-00-07-413882.mp4  (open)
                              ~/store_forward/out/2026-09-15_03-00-07-413882.mp4   (closed)
                                       │ SegmentStoreForward Actor watcher
                                       ▼ forwarded to the peer host
```

The scheme owns nothing at run time. It only resolves and validates the
target, in the same shape as `DataSchemeFile.create_targets()`, and
leaves the writing to the element. `destroy_targets()` is the base no-op:
the element closes its own writer in `stop_stream()`.

### Implementation notes

- `parse_url_path()` strips `//`, so `store_forward:///abs/path` yields
  `/abs/path` and `store_forward://rel/path` yields `rel/path`.
- The scheme is registered when `aiko_services.elements.media` is
  imported. `store_forward_io.py` imports the scheme module as well, so a
  PipelineDefinition that deploys only the element still finds the scheme.
- The prefix rule keeps every segment name inside the Actor's file name
  rule `[A-Za-z0-9_-][A-Za-z0-9._-]{0,127}`. An empty prefix gives a name
  that starts with a digit, which the rule accepts.

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `DataSchemeStoreForward` | Resolve and validate the outbox or inbox URL, seed the Stream variables, start the reader frame generator | `DataScheme`, `VideoWriteStoreForward`, `WriteStoreForward`, `ReadStoreForward` |

## Current limitations and roadmap

- Only a `ReadStoreForward` element can use the scheme as a source.
  A video reader is planned.
- The element relies on the Actor's outbox watcher to notice a closed
  segment. Announcing it with `(send_segment ID NAME)` is planned.

## Related concepts

- [Scheme](../../concepts/scheme.md), the DataScheme lookup
- [Data Source / Target](../../concepts/data_source_target.md)
- [StoreForward](../../concepts/store_forward.md), the Actor that
  watches the outbox
- [store_forward_io](store_forward_io.md), the video element that writes
  there
- [store_forward_base](store_forward_base.md), the generic and text
  elements for both sides
- [scheme_file](scheme_file.md), the model this scheme follows
