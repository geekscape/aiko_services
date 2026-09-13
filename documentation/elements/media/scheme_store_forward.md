---
title: StoreForward DataScheme
description: The store_forward:// DataScheme — a target-only scheme that
  names the outbox directory a SegmentStoreForward Actor watches, so a
  Pipeline can hand finished segments to the store / forward custodian
type: concept
audience: [developers, end-users]
status: work-in-progress
ste: adapted
source:
  - src/aiko_services/elements/media/scheme_store_forward.py
related: [scheme, data_source_target, store_forward, store_forward_io,
  scheme_file]
version: "0.8-dev"
last_updated: 2026-09-13
---

# StoreForward DataScheme

## Overview

**`DataSchemeStoreForward`** registers the `store_forward://` URL scheme
for the [DataScheme](../../concepts/scheme.md) lookup. It is target-only:
a `data_targets` URL names the outbox directory that a
[SegmentStoreForward](../../concepts/store_forward.md) Actor watches. The
DataTarget element that uses it,
[`VideoWriteStoreForward`](store_forward_io.md), writes each finished
segment into that directory, and the Actor forwards it to the peer host.

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

# File name prefix (default "segment")
-p VideoWriteStoreForward.segment_prefix cam0
```

### Public API

```python
class DataSchemeStoreForward(aiko.DataScheme):
    def create_sources(self, stream, data_sources, ...)   # ERROR: target-only
    def create_targets(self, stream, data_targets)

aiko.DataScheme.add_data_scheme("store_forward", DataSchemeStoreForward)
```

`create_targets()` resolves the URL path (with `~` expanded) and checks
that it is an existing, writable directory. It validates the
`segment_prefix` parameter against `[A-Za-z0-9_-]{1,32}`. Then it sets
three Stream variables for the element: `target_outbox`, `target_prefix`
and `target_segment_id` (a counter starting at 0). It publishes `outbox` in
the element's share. A missing directory or a bad prefix returns
`StreamEvent.ERROR` with a diagnostic.

## For framework developers (internals)

### Design

```
 "(store_forward://~/store_forward/out)"
        │ parse_url_path()  expanduser()  realpath()
        ▼
 stream.variables: target_outbox, target_prefix, target_segment_id
        │
        ▼
 VideoWriteStoreForward  ──►  ~/store_forward/out/.segment_<UTC>_000001.mp4  (open)
                              ~/store_forward/out/segment_<UTC>_000001.mp4   (closed)
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
  rule `[A-Za-z0-9_-][A-Za-z0-9._-]{0,127}`.

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `DataSchemeStoreForward` | Resolve and validate the outbox URL, seed the Stream variables, refuse use as a source | `DataScheme`, `VideoWriteStoreForward` |

## Current limitations and roadmap

- Target-only. A `store_forward://` DataSource that reads segments
  arriving in an inbox into a Pipeline on the recipient host is planned.
- The element relies on the Actor's outbox watcher to notice a closed
  segment. Announcing it with `(send_segment ID NAME)` is planned.

## Related concepts

- [Scheme](../../concepts/scheme.md), the DataScheme lookup
- [Data Source / Target](../../concepts/data_source_target.md)
- [StoreForward](../../concepts/store_forward.md), the Actor that
  watches the outbox
- [store_forward_io](store_forward_io.md), the element that writes there
- [scheme_file](scheme_file.md), the model this scheme follows
