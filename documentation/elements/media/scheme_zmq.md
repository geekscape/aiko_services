---
title: DataSchemeZMQ
description: The zmq DataScheme — out-of-band record transport between
  Pipelines over ZeroMQ PUSH/PULL sockets, with port ranges and batching
type: concept
audience: [developers, end-users]
status: work-in-progress
source:
  - src/aiko_services/elements/media/scheme_zmq.py
related: [scheme, data_source_target, pipeline_element, stream, parameters,
  text_io, image_io, scheme_file, scheme_tty]
version: "0.6"
last_updated: 2026-07-06
---

# DataSchemeZMQ

## Overview

**`DataSchemeZMQ`** implements the `zmq` URL scheme of the
[DataScheme](../../concepts/scheme.md) plug-in design: it moves frames
of `bytes` records between processes over ZeroMQ, **out-of-band** from
the MQTT control plane. A
[DataTarget](../../concepts/data_source_target.md) end (`TextWriteZMQ`,
`ImageWriteZMQ`) is a PUSH client that connects; a DataSource end
(`TextReadZMQ`, `ImageReadZMQ`) is a PULL server that binds — so bulk
media bypasses the MQTT broker entirely while the Pipelines remain
ordinary Aiko Services.

This is the current answer to "stream a webcam or text feed between
hosts": pair a writer pipeline on one machine with a reader pipeline on
another, and only the `zmq://` URLs change.

**Why you'd use it**: connect two Pipelines across the network with two
URL parameters:

```bash
# Host A (server): bind and consume
aiko_pipeline create pipelines/text_zmq_pipeline_0.json -s 1 -sr  \
           -p TextReadZMQ.data_sources zmq://0.0.0.0:6502

# Host B (client): produce and send
aiko_pipeline create pipelines/text_zmq_pipeline_1.json -s 1 -sr  \
           -p TextWriteZMQ.data_targets zmq://192.168.0.1:6502
```

## For application developers

### Command-line usage

`DataSchemeZMQ` has no CLI of its own — it is selected by `zmq://` URLs
on ZMQ-suffixed elements. Worked sessions live in
[text_io](text_io.md) (text records) and [image_io](image_io.md)
(image records, optional zlib compression); the webcam-to-network
pipeline is in [webcam_io](webcam_io.md):

```bash
cd src/aiko_services/elements/media

# Text: server then client
aiko_pipeline create pipelines/text_zmq_pipeline_0.json -s 1 -sr -ll debug -gt 10
aiko_pipeline create pipelines/text_zmq_pipeline_1.json -s 1 -sr -ll debug

# Images: server then client
aiko_pipeline create pipelines/image_zmq_pipeline_0.json -s 1 -sr -ll debug -gt 10
aiko_pipeline create pipelines/image_zmq_pipeline_1.json -s 1 -sr -ll debug

# Webcam --> network
aiko_pipeline create pipelines/webcam_zmq_pipeline_0.json -s 1 -sr \
           -p ImageWriteZMQ.data_targets zmq://192.168.0.1:6502
```

`-gt 10` (grace time) matters on the server: it waits for frames
without timing the Stream out while the client starts.

### Public API

URL forms (from the source header) — each list should contain a single
entry.

`data_sources` (**server bind**, incoming); `port_range` may be a
single port or a range:

```
(zmq://*:*)                any available TCP port      (only localhost)
(zmq://*:6502)             a given TCP port            (only localhost)
(zmq://*:6502-6510)        any TCP port in the specified range
(zmq://localhost:6502)     given hostname and TCP port
(zmq://0.0.0.0:*)          any available TCP port      (from any host)
(zmq://0.0.0.0:6502)       a given TCP port            (from any host)
(zmq://0.0.0.0:6502-6510)  any TCP port in the specified range
```

`data_targets` (**client connect**, outgoing) — single port only:

```
(zmq://*:6502)             localhost and TCP port
(zmq://localhost:6502)     localhost and TCP port
(zmq://192.168.0.1:6502)   given hostname and TCP port
```

A malformed URL returns `StreamEvent.ERROR` from `start_stream()`
(`'ZMQ Data URL "..." must be "zmq://host:port_range"'`). The resolved
URL is published to shared state as `zmq_url`, so the Aiko Services
Dashboard shows which port a range-bound server actually took.

Parameters read by the scheme:

| Parameter | Default | Meaning |
|-----------|---------|---------|
| `data_batch_size` | 1 | Maximum records grouped per frame (source side) |

Source behaviour: a PULL socket is bound (`RCVTIMEO` 1 s), a daemon
thread receives payloads into a queue, and the frame generator drains
up to `data_batch_size` queued records into
`{"records": [bytes, ...]}` — the owning element's
`process_frame(stream, records)` decodes them. An empty queue returns
`StreamEvent.NO_FRAME`; the Stream never self-stops (a network source
has no natural end — use `-gt`, `-s` Stream management or Ctrl-C).

Target behaviour: a PUSH socket connects and is stored in
`stream.variables["target_zmq_socket"]`; the DataTarget element calls
`.send(record)` per record in its own `process_frame()`.

**Wire format**: one ZeroMQ message per record — raw `bytes` with no
framing, no acknowledgement (PUSH/PULL is unidirectional and buffers
while the peer is absent). Content encoding belongs to the element
pair: UTF-8 text for `Text*ZMQ`, JPEG/PNG bytes (optionally
zlib-compressed) for `Image*ZMQ`; `text:length:content`-style headers
are planned, not implemented.

Registration (module import side-effect):

```python
aiko.DataScheme.add_data_scheme("zmq", DataSchemeZMQ)
```

## For framework developers (internals)

### Design

```
 writer Pipeline (client)              reader Pipeline (server)
 ─────────────────────────             ──────────────────────────
 create_targets():                     create_sources():
   PUSH socket.connect(url)              PULL socket.bind(url)
   stream.variables                      RCVTIMEO = 1s
     ["target_zmq_socket"]               daemon _run(): recv ─► queue
        │                                       │
 element.process_frame():              frame_generator():
   socket.send(record) ── ZeroMQ ──►     drain ≤ data_batch_size
                                         {"records": [...]} | NO_FRAME
```

- **Server = source, client = target.** The data *consumer* binds and
  the *producer* connects — matching the deployment reality that the
  processing host is the stable endpoint and camera/feeder clients come
  and go.
- **Same thread-plus-queue shape as [scheme_tty](scheme_tty.md)**: the
  blocking `recv()` lives on a daemon thread; the frame generator only
  polls. `RCVTIMEO` keeps the thread responsive to `terminate`.
- **Port ranges for fleet deployment.** `_parse_zmq_url()` expands
  `host:port_range`; when a genuine range is given on the source side,
  `get_network_port_free()` (from `aiko_services.main.utilities`) picks
  a free port, and `share["zmq_url"]` advertises the result.

### Implementation notes

- `create_sources()` overrides the base signature default with
  `use_create_frame=False` — a socket source always needs the
  generator thread.
- A single `*` or `0` port on the source side maps to port `0` in the
  bind URL (only proper ranges go through `get_network_port_free()`) —
  ZeroMQ's handling of `tcp://host:0` is what you get; prefer an
  explicit range.
- Socket lifecycle: `destroy_sources()` sets `terminate` and the reader
  thread's `finally:` closes socket and context; `destroy_targets()`
  closes directly (`_zmq_destroy()` is idempotent via `None` checks).
  `bind()` / `connect()` exception handling is a marked TODO — a port
  already in use currently raises out of `start_stream()`.
- Scheme state (`zmq_context`, `zmq_socket`, `queue`, `terminate`)
  lives on `self`; safe because one scheme instance exists per
  [Stream](../../concepts/stream.md).

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `DataSchemeZMQ` | Parse `zmq://host:port_range` URLs (free-port selection, `zmq_url` share); bind PULL + receive thread + queue on the source side; connect PUSH and expose `target_zmq_socket` on the target side; batch records per frame; tear down sockets | [DataScheme](../../concepts/scheme.md) (base, registry), [DataSource / DataTarget](../../concepts/data_source_target.md) (owners), [PipelineElement](../../concepts/pipeline_element.md) (`create_frames()`, `get_parameter()`), [Stream](../../concepts/stream.md), `get_network_port_free()`, `Text*ZMQ` ([text_io](text_io.md)) / `Image*ZMQ` ([image_io](image_io.md)) element pairs |

## Current limitations and roadmap

From the source To Do list — **planned**, not implemented:

- Aiko Services Dashboard metrics and Metrics-element support
- Media types `text` and `text/zip` (record framing headers)
- ZeroMQ REQ/REP for bidirectional request/response control flow —
  confirmation back to the client
- (From [text_io](text_io.md)) ZeroMQ as a full remote-PipelineElement
  transport, out-of-band alternative to in-band MQTT

Known sharp edges (see Implementation notes): no `bind()`/`connect()`
exception handling; single `*` port becomes literal port `0`; no
delivery acknowledgement — PUSH buffers silently while the server is
down.

## Related concepts

- [DataScheme](../../concepts/scheme.md) — the plug-in base class and
  registry
- [DataSource / DataTarget](../../concepts/data_source_target.md) — the
  elements that instantiate this scheme per Stream
- [PipelineElement](../../concepts/pipeline_element.md) —
  `create_frames()` and the frame contract
- [Stream](../../concepts/stream.md) — scope of the scheme instance;
  `-gt` grace time on network sources
- [Parameters](../../concepts/parameters.md) — `data_sources`,
  `data_targets`, `data_batch_size`
- [text_io](text_io.md), [image_io](image_io.md),
  [webcam_io](webcam_io.md) — the element pairs and pipelines that
  exercise this scheme
- [scheme_file](scheme_file.md), [scheme_tty](scheme_tty.md) — sibling
  schemes
