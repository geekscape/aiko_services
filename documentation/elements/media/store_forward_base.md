---
title: StoreForward generic elements and text segments
description: WriteStoreForward, ReadStoreForward and CommitStoreForward —
  generic PipelineElements that write frames as segments into a
  SegmentStoreForward outbox and read them back in order from an inbox,
  with at-least-once delivery; TextWriteStoreForward and
  TextReadStoreForward apply them to text with TextCodec
type: concept
audience: [developers, end-users]
status: work-in-progress
ste: adapted
source:
  - src/aiko_services/elements/media/store_forward_base.py
  - src/aiko_services/elements/media/store_forward_io.py
  - src/aiko_services/elements/media/scheme_store_forward.py
related: [pipeline_element, data_source_target, scheme, stream, share,
  store_forward, scheme_store_forward, store_forward_io, text_io]
version: "0.8-dev"
last_updated: 2026-11-23
---

# StoreForward generic elements and text segments

## Overview

Three generic [PipelineElements](../../concepts/pipeline_element.md) put
a Pipeline on each side of a [StoreForward](../../concepts/store_forward.md)
link:

- **`WriteStoreForward`**, a
  [DataTarget](../../concepts/data_source_target.md), writes each frame
  as one or more *segments* (files) into the outbox of a
  `SegmentStoreForward` Actor.
- **`ReadStoreForward`**, a DataSource, reads the segments that the peer
  Actor puts in its inbox. It emits their frames one segment at a time,
  in the order that each writer wrote them.
- **`CommitStoreForward`**, the last element after the reader, marks a
  segment as done only after every element before it has returned
  `StreamEvent.OKAY`.

A media type supplies a small *segment codec* and a subclass that names
it. The first codec is **`TextCodec`**, with the elements
**`TextWriteStoreForward`** and **`TextReadStoreForward`**. They carry a
text field and any other frame fields, for example a CSV record batch and
its sensor name.

Delivery is at-least-once. A segment that a restart interrupts is
emitted again. The consumer must apply a segment idempotently, for
example with `INSERT … ON CONFLICT DO NOTHING`.

## For application developers

### Command-line usage

The sending host writes CSV records as gzip text segments:

```json
"graph": ["(CSVSource TextWriteStoreForward)"],
{ "name": "TextWriteStoreForward",
  "parameters": {
    "data_targets":   "(store_forward://~/store_forward/out)",
    "segment_prefix": "host3",
    "compress":       "gzip"
  },
  "input": [{"name": "text", "type": "str"},
            {"name": "sensor", "type": "str"}],
  "output": [],
  "deploy": {"local": {
    "module": "aiko_services.elements.media.store_forward_io"}} }
```

The receiving host reads them in order and commits each one after the
database write:

```json
"graph": ["(TextReadStoreForward DatabaseWriter CommitStoreForward)"],
{ "name": "TextReadStoreForward",
  "parameters": {
    "data_sources":   "(store_forward:///srv/inbox/host3)",
    "work_directory": "~/store_forward/host3",
    "compress":       "gzip"
  },
  "input":  [{"name": "text", "type": "str"},
             {"name": "sensor", "type": "str"},
             {"name": "segment", "type": "str"}],
  "output": [{"name": "text", "type": "str"},
             {"name": "sensor", "type": "str"},
             {"name": "segment", "type": "str"}],
  "deploy": {"local": {
    "module": "aiko_services.elements.media.store_forward_io"}} },
{ "name": "CommitStoreForward",
  "input": [{"name": "segment", "type": "str"}], "output": [],
  "deploy": {"local": {
    "module": "aiko_services.elements.media.store_forward_base"}} }
```

The two Actors between them move the files:

```bash
aiko_store_forward edge --inbox ~/store_forward/in --outbox ~/store_forward/out --server_url http://server:8080
```

```bash
aiko_store_forward server --inbox /srv/inbox/host3 --outbox ~/store_forward/host3/out --partial_directory ~/store_forward/host3/partial --http_port_range 8080
```

### Public API

| Element | Protocol | Inputs | Outputs |
|---------|----------|--------|---------|
| `TextWriteStoreForward` | `text_write_store_forward:0` | The text field and the fields to carry | None |
| `TextReadStoreForward` | `text_read_store_forward:0` | Must list the outputs (a DataSource) | The writer's fields and `segment` |
| `CommitStoreForward` | `commit_store_forward:0` | `segment` | None |

Writer parameters:

| Parameter | Default | Meaning |
|-----------|---------|---------|
| `data_targets` | must be set | `(store_forward://OUTBOX)` |
| `segment_prefix` | must be set | Writer id, `[A-Za-z0-9-]`, 1 to 24 characters. It must be unique for each sending host |
| `state_directory` | `.` | Holds `store_forward_write_<writer>.json`: the epoch and the last sequence |
| `text_field` | `text` | The frame field that holds the text |
| `segment_extension` | `csv` | File name extension |
| `compress` | `none` | `none` or `gzip`. With `gzip`, the extension gains `.gz` |
| `max_segment_bytes` | 33554432 | A larger text is divided at line boundaries into consecutive segments |

Reader parameters:

| Parameter | Default | Meaning |
|-----------|---------|---------|
| `data_sources` | must be set | `(store_forward://INBOX)` |
| `work_directory` | must be set | Holds `processing/`, `done/`, `rejected/` and `store_forward_read.json`. It must be outside the inbox |
| `segment_extension`, `compress` | `csv`, `none` | Select the files to read |
| `rate` | 1.0 | Inbox polls each second |
| `gap_timeout` | 900 | Seconds to wait for a missing sequence |
| `commit_timeout` | 600 | Seconds before a segment that is not committed is emitted again |
| `max_attempts` | 3 | Emissions of one segment before it moves to `rejected/` |
| `done_max_age` | 2592000 | Seconds a segment stays in `done/` (30 days). Zero keeps all |

Shared state of the writer: `outbox`, `writer`, `epoch`, `sequence`,
`segments_written`, `last_segment_utc`. Shared state of the reader:
`inbox`, `claimed`, `applied`, `waiting`, `oldest_waiting_s`, `gaps`,
`duplicates`, `rejected`, `retries`.

Segment file name, for all media types:
`<writer>_<UTC open time to the microsecond>_<sequence><extension>`, for
example `host3_2026-11-23_01-02-03-413882_000017.csv.gz`. The name sorts
in write order and passes the name rule of the Actor.

Text segment format (`store_forward_text:0`): one header line, then the
text with its line endings unchanged. A leading byte order mark is
removed.

```
#store_forward_text:0 {"epoch": "...", "fields": {"sensor": "thermometer"}, "sequence": 17, "text_field": "text", "writer": "host3", ...}
2024-09-01T00:00:00Z,1,20.5
```

## For framework developers (internals)

### Design

```
 Sending host                     Actors            Receiving host
 WriteStoreForward                                   ReadStoreForward
   codec.split / open / append    outbox ──► inbox     scan, order, claim
   .<name> ──rename──► <name>                           inbox ─► processing/
   state: epoch, sequence                             emit frames + segment
                                                     ... consumer elements ...
                                                     CommitStoreForward
                                                       processing/ ─► done/
```

The directories are the only seam with the Actor. The writer creates a
segment as a dot-prefixed temporary file, which the watcher of the Actor
ignores. It calls `fsync` and then renames the file into place. Thus a
segment always appears complete. The writer persists a sequence only
after its segment is visible. Thus a failed write uses the same sequence
again.

The reader orders the segments for each key (writer, epoch). The next
segment for a key has sequence `last + 1`. A key with no state starts at
its lowest sequence. A sequence at or below the last applied one is a
duplicate. It moves to `done/` and is not emitted. A missing sequence is
held until the oldest segment that waits for that key has waited
`gap_timeout`. Then the reader continues and logs a warning.

The epoch is the UTC time to the microsecond and a random suffix. It is
made when the writer state is created. A writer whose state is lost thus
starts a new key and is never mistaken for an old one.

One segment is in flight at a time. `CommitStoreForward` runs only when
every element before it returned `OKAY`. When all frames of a segment are
committed, the segment moves to `done/`. If an element fails, the segment
stays in `processing/`. The reader emits it again after `commit_timeout`,
or at once after a restart.

### Implementation notes

- `SegmentCodec`, `SegmentWriter` and `SegmentReader` are in-process
  helpers with no event loop. They carry an ADR-022 exemption as value and
  data types. The unit tests drive them with an explicit clock.
- The frame generator of the reader calls `SegmentReader.poll()` on its
  own thread. `CommitStoreForward` calls `commit()` on the event-loop
  thread. A lock protects the reader state. The two elements find the same
  reader through a registry with the key `(id(pipeline), stream_id)`.
- Shared state changes only on the event-loop thread: the reader publishes
  its counters from `process_frame()`.
- `os.replace()` is tried again for 5 s when it raises
  `PermissionError`. On Windows, another process can hold the target.
- State files are written to a temporary file, with `fsync`, then
  renamed.
- `TextCodec` opens files with `newline=""`, so that CRLF line endings
  do not change.

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `SegmentCodec` | Turn frames into segment files and back. Divide large frames | — |
| `TextCodec` | Header line, verbatim text, optional gzip | `SegmentCodec` |
| `SegmentWriter` | Names, sequence state, temporary file and rename | `SegmentCodec` |
| `SegmentReader` | Scan, order, gaps, duplicates, claim, commit, retry, sweep | `SegmentCodec` |
| `WriteStoreForward`, `TextWriteStoreForward` | DataTarget around `SegmentWriter` | `DataSchemeStoreForward` |
| `ReadStoreForward`, `TextReadStoreForward` | DataSource around `SegmentReader` | `DataSchemeStoreForward` |
| `CommitStoreForward` | Commit a segment after the consumer | `SegmentReader` |

## Current limitations and roadmap

- `VideoWriteStoreForward` does not use `WriteStoreForward` yet. Its
  names have no writer and no sequence.
- A codec for binary media cannot carry a header line. Per-segment
  metadata in the upload description of the Actor would remove this
  limit.
- The Actor refuses segments above 64 MiB. `TextCodec` divides large
  texts. A binary codec must do the same.
- A multi-file artifact arrives as unrelated segments.
- The reader publishes its counters only when it emits a frame.

## Related concepts

- [StoreForward](../../concepts/store_forward.md), the Actor that moves
  the segments
- [scheme_store_forward](scheme_store_forward.md), the
  `store_forward://` DataScheme for both sides
- [store_forward_io](store_forward_io.md), `VideoWriteStoreForward`
- [Data Source / Target](../../concepts/data_source_target.md)
- [text_io](text_io.md), the other text elements
