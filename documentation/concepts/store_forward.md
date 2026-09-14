---
title: StoreForward
description: The SegmentStoreForward Actor takes custody of segments (files)
  for a peer host across an unreliable link and delivers them, verified by
  sha256, resuming after interruption, through a pluggable
  StoreForwardMessage layer (HTTP today)
type: concept
audience: [architects, developers, end-users]
status: draft
ste: adapted
source:
  - src/aiko_services/main/store_forward/store_forward.py
  - src/aiko_services/main/store_forward/store_forward_message.py
  - src/aiko_services/main/store_forward/store_forward_http.py
related: [design_overview, actor, share, connection, data_source_target,
  scheme, dashboard]
version: "0.8-dev"
last_updated: 2026-09-14
---

# StoreForward

## Overview

Source code: `src/aiko_services/main/store_forward/`

**`SegmentStoreForward`** is an [Actor](actor.md), one per host. It takes
custody of *segments* (files: video segments, images, tensors) for a peer
host across an unreliable link. It delivers them when the link permits. A
segment dropped into the Actor's outbox arrives in the peer's inbox with
its sha256 verified. A transfer that a link drop interrupts resumes from
the byte where it stopped. Nothing large travels over MQTT: the bytes move
out of band through a pluggable **`StoreForwardMessage`** layer, of which
one implementation exists today, HTTP.

A host has one of two roles. The **server** role runs the HTTP routes. The
**edge** role is always the client: it polls the server and needs no
inbound port, which suits a host behind Wi-Fi or a NAT. Both roles send
and receive. No Aiko Services traffic crosses the link in this first cut.
Each host runs its own mosquitto and `aiko_registrar`, so its Actor
appears on its own [Dashboard](dashboard.md).

**Why you would use it.** A forklift appliance records camera video as
segments while its Wi-Fi comes and goes. The segments must reach the site
server complete, in order of no importance, without an operator. Two
commands give that:

```bash
aiko_store_forward server --inbox ~/store_forward/in --outbox ~/store_forward/out   # site host
aiko_store_forward edge --inbox ~/store_forward/in --outbox ~/store_forward/out  \
    --server_host site.local                                  # forklift
cp segment.mp4 ~/store_forward/out                # arrives in the site host's inbox
```

## For application developers

### Command-line usage

The console script is `aiko_store_forward`. Prerequisites on each host:
mosquitto and `aiko_registrar` with `AIKO_MQTT_HOST=localhost`
(`scripts/system_start.sh`). The server host also needs Flask
(`pip install flask`). The edge host needs only the core dependencies.

```bash
aiko_store_forward server --inbox DIR --outbox DIR  \
    [--http_port_range 8080-8089] [--bind 0.0.0.0] [--advertise_host HOST]  \
    [--link_timeout 10] [--outbox_period 2] [--partial_max_age 86400]

aiko_store_forward edge --inbox DIR --outbox DIR  \
    --server_host HOST [--server_port 8080] | --server_url URL  \
    [--poll_period 2] [--outbox_period 2] [--partial_max_age 86400]
```

`--server_host` takes the server host's IP address or host name. Give
the IP address on a network where `.local` names do not resolve.
`--server_url` is the alternative for a full endpoint, for example an
`https://` one, and wins when both are given.

Sending is triggered by a file in the outbox: the Actor scans the outbox
every `--outbox_period` seconds, waits until the size and time of the
file stop changing, then sends it. A file name must match
`[A-Za-z0-9_-][A-Za-z0-9._-]{0,127}`. After the peer verifies the sha256,
the file moves to `outbox/.sent/`. A segment can also be sent by hand,
with the topic that the Actor prints at start:

```bash
mosquitto_pub -t $TOPIC_IN -m "(send_segment 0123abcd notes.txt)"
mosquitto_pub -t $TOPIC_IN -m "(cancel 0123abcd)"
mosquitto_pub -t $TOPIC_IN -m "(forget 0123abcd)"
```

A Pipeline writes video segments into the outbox with the
`store_forward://` [DataScheme](scheme.md) and the `VideoWriteStoreForward`
DataTarget, documented in
[elements/media/store_forward_io](../elements/media/store_forward_io.md).

### Public API

```python
class SegmentStoreForward(Actor):
    Interface.default("SegmentStoreForward",
        "aiko_services.main.store_forward.store_forward.SegmentStoreForwardImpl")
```

| Method and wire form | Effect |
|----------------------|--------|
| `send_segment(segment_id, name)` `(send_segment ID NAME)` | Get the outbox file `name` to the peer. Idempotent for a known id |
| `fetch_segment(segment_id, name, size, sha256)` `(fetch_segment ID NAME SIZE SHA256)` | Edge role only: download a segment the server offered |
| `acknowledge(segment_id, sha256, status)` `(acknowledge ID SHA256 STATUS)` | The receiver confirms a segment arrived intact |
| `cancel(segment_id)` `(cancel ID)` | Stop a segment in progress |
| `forget(segment_id)` `(forget ID)` | Remove a segment from the shared state tables |

Every method is one-way. A segment id is a hexadecimal token of 8 to 32
characters, chosen by the sender (the outbox watcher uses 12). Outcomes
are observed in `share`, never returned:

| Item | Content |
|------|---------|
| `role`, `inbox`, `outbox`, `http_endpoint` or `server_url` | Configuration |
| `link` | `up@UTC` or `down@UTC`, stamped when it last changed. Edge: from the poll. Server: from edge activity, down after `--link_timeout` seconds without a poll |
| `link_cause`, `link_changed_utc` | One token (`server_reachable`, `edge_polling`, `no_poll_<n>s`, `ConnectionError`, ...) and the time |
| `store_forwards.<id>` | Sender side: `queued`, `hashing`, `offered`, `connecting`, `sending`, `fetching`, `verifying`, `done`, `acked`, `cancelled`, `failed_*`, `rejected_*` |
| `received.<id>` | Receiver side: `receiving`, `verifying`, `ok`, `failed_sha256`, `failed_timeout` |
| `progress.<id>` | `<bytes>/<size>` |
| `last_error` | `<state>/<segment id or ->@UTC` of the latest failure |
| `queue.depth`, `queue.oldest_s`, `queue.bytes`, `sampled_utc` | Segments in the outbox not yet delivered, refreshed by every scan |
| `metrics.*` | `sent_bytes`, `received_bytes`, `resumes`, `retries`, `failures`, `rejected_commands`, `out_dropped`, `link_downs` |

`done` means the receiver verified the sha256 and is the reliable
terminal state. `acked` means the receiver's acknowledgment also
arrived, which is at-most-once. Each per-segment table keeps the last
three segments. Timestamps are ISO 8601 UTC to the second with a `Z`
suffix, one token. Values are single tokens because the incremental
[Share](share.md) encoding does not quote them.

**Delivery rules.** A send that fails (`failed_*` or `rejected_busy`)
returns to the outbox watcher after a doubling back-off from 60 s to
3600 s. The watcher then re-sends it with a fresh id. An offer the edge
did not acknowledge within 600 s is withdrawn and re-offered. Both roles remove
partial files older than `--partial_max_age` seconds. So nothing stays
stuck and nothing grows without bound.

**HTTP protocol** (server role). Upload is a minimal subset of the tus
resumable upload protocol, download uses HTTP `Range`:

| Route | Purpose |
|-------|---------|
| `POST /in` | One S-expression from the edge host: 202, 400 (unparsable), 403 (not an Interface method), 429 (rate) |
| `GET /out?after=SEQ` | Outstanding commands for the edge host, retained until a later poll carries `after >= seq` |
| `POST /data/<id>` | Create an upload `{name, size, sha256}`: 201 with `Upload-Offset` (the resume point) |
| `HEAD /data/<id>` | `Upload-Offset` of an upload, or `Content-Length` and `X-Sha256` of an offered download |
| `PATCH /data/<id>` | Append one chunk at `Upload-Offset`: 204, or 409 with the true offset |
| `POST /data/<id>/complete` | Verify the sha256 and move the file into the inbox: 200 or 422 |
| `GET /data/<id>` | Download an offered segment, `Range` honored |
| `GET /health` | `{"role": "server", "version": "v0", "package": ...}`; `v0` is the route contract |

Only the edge host opens connections. The `/in` and `/out` routes carry
`(command ...)` S-expressions between the two Actors. Only the abstract
methods of the Interface may be dispatched from them (P12).

Edge host to server host, an upload:

```
 Edge Actor          Edge message layer            Server message layer      Server Actor
     │ send_segment          │                              │                     │
     │──────────────────────►│ POST /data/id {name,size,sha}│                     │
     │                       │─────────────────────────────►│ 201 Upload-Offset   │
     │                       │ PATCH chunks from the offset │                     │
     │                       │─────────────────────────────►│ 204 ... (409: resync)│
     │                       │ POST /data/id/complete       │ sha256 verified,    │
     │                       │─────────────────────────────►│ moved into inbox    │
     │ store_forwards.id done│◄──────────── 200 ────────────│ received.id ok ────►│
     │                       │ GET /out (poll)              │ (acknowledge ...)   │
     │ store_forwards.id acked◄─────────────────────────────│◄────────────────────│
```

Server host to edge host, a download: the server hashes the file and
offers it as `(fetch_segment ID NAME SIZE SHA256)` on `/out`. The edge
host downloads it with `GET /data/<id>` and a `Range` header for resume.
Then it posts `(acknowledge ...)` to `/in`.

## For framework developers (internals)

### Design

Three layers, one process per host:

```
 outbox/                       SegmentStoreForwardImpl (Actor, event loop)
 │ notes.txt ◄── cp / Pipeline   │ owns share, validates every argument,
 │   watcher: size stable        │ hands SendJob / FetchJob to the layer
 │   (send_segment ID NAME)      │ below, receives events on its mailbox
 │ .sent/notes.txt ◄── done      │
 inbox/                         StoreForwardMessage (ABC, no framework import)
 │ .partial/<id>.part ◄── bytes    │ start(on_command, on_event) -> endpoint
 │ .partial/<id>.meta {sha256}     │ send_segment(job)  fetch_segment(job)
 │ notes.txt ◄── os.replace        │ send_command(sexpr)  cancel(id)  stop()
                                 StoreForwardMessageHTTPServer | ...HTTPClient
                                   Flask routes / requests session, threads
```

The Actor owns all shared state and the one-way command surface. The
message layer moves bytes and commands on its own threads and reports
through two callbacks. `on_command(payload)` receives a `(command ...)`
from the peer. `on_event(segment_id, event, detail)` reports progress or,
with `-` as the id, a link change. The Actor's callbacks only post to its
own mailbox with `_post_message(ActorTopic.IN, ...)`, the same path that
`process_manager.py` uses from its reaper thread. All `ec_producer`
updates happen in the mailbox handler `_store_forward_event()` on the
event-loop thread (P2).

The HTTP command allow-list is the set of abstract methods of the
Interface. Thus the peer cannot reach a private method such as
`_store_forward_event`. The local bus can reach it, because Actor dispatch
resolves any attribute. Thus its arguments are validated as untrusted too.

Directories are the durable state. A `.part` file and its `.meta` sidecar
survive a process restart on either side, which is what makes resume
possible after a server restart. The in-memory tables (offers, the `/out`
cursor, pending acknowledgments) do not survive a restart. The retry
rules above cover the gaps.

**Connection ladder.** The link sensor drives `aiko.process.connection`
with a raise-only guard. Link up sets `ConnectionState.NETWORK` only from
`NONE`. Link down lowers to `NONE` only from exactly `NETWORK`. The
ladder is never touched at or above `TRANSPORT`. The ladder is one scalar
and lowering it from `REGISTRAR` would stop MQTT log publishing and
Registrar registration. With a local broker on each host the ladder
mirrors the broker, so it reflects this link only when no broker is
connected. See [Connection](connection.md).

### Implementation notes

- Every queue is bounded with a drop-newest policy (P9): send jobs 16,
  outgoing commands 64, `/out` items 256, concurrent uploads 4, offers 32,
  segment size 64 MiB, chunk 64 KiB. Progress events are rate-limited to
  one per eight chunks because framework mailboxes are unbounded.
- Deadlines: `requests` timeouts of 5 s to connect and 30 s to read,
  60 s to the first successful request, and a whole-transfer deadline of
  `max(120 s, size / 50 KiB per second)`. Back-off after a connection
  error doubles from 1 s to 30 s.
- Werkzeug calls `sys.exit(1)` on a busy port instead of raising, so the
  port-range fallback catches `SystemExit` as well as `OSError`.
- Flask is a guarded import. The package imports without it, and the
  server role reports `cannot start` when it is absent.
- The seam is a plain ABC, as `main/message/message.py` is. It is not yet
  composed as an Interface with `Interface.default()` (ADR-022), recorded
  as a TODO in its header.
- `last_error` and `link_cause` are single tokens by construction:
  non-token characters become `_` and the text is cut at 32 characters.

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `SegmentStoreForward` (Interface) | Declare the five one-way wire commands and the share contract | `Actor` |
| `SegmentStoreForwardImpl` | Validate commands, watch the outbox, own share, retry and sweep, drive the Connection ladder | `StoreForwardMessage`, `ECProducer`, `event` timers, `Connection` |
| `StoreForwardMessage` (ABC) | Move commands and bytes to the peer on its own threads, report by callback | `SendJob`, `FetchJob` |
| `StoreForwardMessageHTTPServer` | Flask routes, upload table, offers, `/out` queue, idle eviction | Flask, werkzeug |
| `StoreForwardMessageHTTPClient` | Poll `/out`, upload with resume, download with `Range`, post `/in` | `requests` |

## Current limitations and roadmap

Implemented: everything above, with unit tests that need no broker and
integration tests on `127.0.0.1` that need Flask.

Limitations:

- No discovery: the edge host is configured with `--server_host` or
  `--server_url`, a deliberate P5 exception while no Registrar spans the
  two hosts.
- No Aiko Services traffic crosses the link. `/in` and `/out` carry the
  S-expressions instead, with a latency of one poll period downward.
- HTTP is plain and unauthenticated. LAN only until TLS or capabilities
  exist. The werkzeug development server is used for the prototype.
- Offers, the `/out` cursor and pending acknowledgments are in memory.

Roadmap, in the order agreed with the Aiko Fleet / Aiko Server design:

1. Persist the state-of-play (SQLite3).
2. An MQTT push implementation of the seam through a bridged broker, with
   one Registrar per site.
3. Discovery by name, protocol and tags.
4. A `store_forward://` DataSource on the recipient host.
5. Fragmented MP4 segments.

## Related concepts

- [Actor](actor.md), the base of the custodian
- [Share (Eventual Consistency)](share.md), how outcomes are observed
- [Connection](connection.md), the ladder the link sensor drives
- [Data Source / Target](data_source_target.md) and [Scheme](scheme.md),
  the Pipeline side
- [elements/media/store_forward_io](../elements/media/store_forward_io.md)
  and [scheme_store_forward](../elements/media/scheme_store_forward.md),
  the segment writer
- [Dashboard](dashboard.md), where the share above is observed
