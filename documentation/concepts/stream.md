---
title: Stream
description: A leased flow of Frames through a Pipeline — the Stream and
  Frame dataclasses, StreamEvent / StreamState semantics and the
  create_stream / process_frame / destroy_stream lifecycle
type: concept
audience: [architects, developers, end-users]
status: work-in-progress
source:
  - src/aiko_services/main/stream.py
  - src/aiko_services/main/pipeline.py
related: [design_overview, pipeline, pipeline_element, parameters, lease,
  event]
version: "0.6"
last_updated: 2026-07-05
---

# Stream

## Overview

A **Stream** is a flow of **Frames** through a [Pipeline](pipeline.md):
the unit of session state that groups related Frames — a video, a sensor
feed, one batch job — under a `stream_id`, with its own
[parameters](parameters.md), response routing and
[lease](lease.md)-based expiry. Each Frame carries the accumulated data
dictionary (the *swag* — "Stuff We All Get") that
[PipelineElements](pipeline_element.md) consume and extend, plus
per-element timing metrics.

The dataclasses and the event/state vocabulary live in
`src/aiko_services/main/stream.py`; the lifecycle machinery
(`create_stream()`, frame processing, `destroy_stream()`) currently
lives in `pipeline.py` — with a recorded intent to refactor it out (see
roadmap).

**Why you'd use it**: to process many independent inputs through one
Pipeline without restarting it, each with its own settings and clean
tear-down:

```bash
aiko_pipeline update p_text_0 -s 1 \
    -p TextReadFile.data_sources "(file://data_in/in_00.txt)"
aiko_pipeline update p_text_0 -s 2 \
    -p TextReadFile.data_sources "(file://data_in/in_01.txt)"
```

## For application developers

### Command-line usage

Stream has no CLI of its own; Streams are created, fed and destroyed
through the `aiko_pipeline` CLI (see [Pipeline](pipeline.md)):

```bash
aiko_pipeline create ../examples/pipeline/pipeline_local.json -ll debug

aiko_pipeline update p_local -s 1                   # Create Stream "1"
aiko_pipeline update p_local -s 2 -gt 3             # 3 second grace time
aiko_pipeline update p_local -s 3 -fd "(b: 0)"      # Stream and one Frame
aiko_pipeline update p_local -s 3 -fd "(b: 0)" -r   # destroy first (reset)
aiko_pipeline update p_local -s 4 -fd "(b: 0)" -sr  # ... and show response
```

Key options: `-s/--stream_id` (with `"name_{}"` substituting the process
id for a sort-of unique id), `-p/--parameters NAME VALUE` for Stream
parameters, `-gt/--grace_time` (default 60 s — the Stream is destroyed
if no Frame arrives within it), `-fd/--frame_data` and
`-fi/--frame_id` for Frames, `-gp/--graph_path` to bind the Stream to a
sub-graph, `-r/--stream_reset` and `-sr/--show_response`.

Or drive the Stream lifecycle directly over MQTT:

```bash
TOPIC=$NAMESPACE/$HOST/$PID/$SID/in
mosquitto_pub -h $HOST -t $TOPIC -m "(create_stream 1)"
mosquitto_pub -h $HOST -t $TOPIC -m "(process_frame (stream_id: 1) (a: 0))"
mosquitto_pub -h $HOST -t $TOPIC -m "(destroy_stream 1)"
```

### Public API

The dataclasses (`from aiko_services.main.stream import ...`, re-exported
by `aiko_services`):

```python
@dataclass
class Stream:
    stream_id: str = DEFAULT_STREAM_ID       # "*"
    frame_id: int = FIRST_FRAME_ID           # 0; updated by Pipeline thread
    frames: Dict[int, Frame]                 # in-flight Frames
    graph_path: str = None                   # head node name; default: first
    lock: Lock                               # created in __post_init__
    parameters: Dict[str, Any]
    queue_response: queue = None             # in-process response queue
    state: StreamState = StreamState.RUN
    topic_response: str = None               # MQTT response topic
    variables: Dict[str, Any]                # PipelineElement scratch space

@dataclass
class Frame:                                 # effectively a continuation :)
    metrics: Dict[str, Any]                  # per-element / pipeline timings
    paused_pe_name: str = None               # remote element awaiting response
    swag: Dict[str, Any]                     # accumulated frame data
```

**StreamEvent** — what a PipelineElement *returns* from
`start_stream()`, `process_frame()`, `stop_stream()` or a frame
generator — and **StreamState** — where the Stream *is*:

| StreamEvent | Value | Meaning |
|-------------|-------|---------|
| `ERROR` | -2 | Move to StreamState.ERROR |
| `STOP` | -1 | Move to StreamState.STOP |
| `OKAY` | 0 | Stay calm and keep on running |
| `NO_FRAME` | 1 | No frame to process; keep running |
| `DROP_FRAME` | 2 | Abandon this frame; keep running |
| `LOOP_END` | 3 | Complete ControlFlowLoop; keep running |
| `USER` | 1024 | User-defined custom events start here |

| StreamState | Value | Meaning |
|-------------|-------|---------|
| `ERROR` | -2 | Don't generate new frames; ignore queued frames |
| `STOP` | -1 | Don't generate new frames; process queued frames |
| `RUN` | 0 | Generate new frames and process queued frames |
| `NO_FRAME` | 1 | Nothing to process, then back to RUN |
| `DROP_FRAME` | 2 | Stop processing current frame, then back to RUN |
| `USER` | 1024 | User-defined custom states start here |

Element-side usage (see [PipelineElement](pipeline_element.md) for the
full contract):

```python
def process_frame(self, stream, a) -> Tuple[aiko.StreamEvent, dict]:
    ...
    return aiko.StreamEvent.OKAY, {"b": b}          # or ...
    return aiko.StreamEvent.STOP, {"diagnostic": "Frame limit reached"}
```

Pipeline-side lifecycle operations:

```python
pipeline.create_stream(stream_id, graph_path=None, parameters=None,
    grace_time=60, queue_response=None, topic_response=None)
pipeline.create_frame(stream, frame_data)     # via PipelineElement
pipeline.destroy_stream(stream_id, graceful=False)
```

**Wire protocol.** The Stream travels between processes as a dictionary
inside the `process_frame` S-expression; `Stream.as_dict()` sends only
`stream_id`, `frame_id` and `graph_path`, and `Stream.update()`
re-hydrates (coercing `stream_id` to `str`, `frame_id` and `state` to
`int`):

```
(create_stream STREAM_ID [GRAPH_PATH])
(process_frame (stream_id: 1 frame_id: 0) (a: 0))
(destroy_stream STREAM_ID)
(process_frame_response (stream_id: 1 frame_id: 0 state: 0) (f: 4))
```

Stream lifecycle with lease expiry:

```
 create_stream(id, grace_time) ─► Lease(grace_time)
        │                            │ each Frame: lease.extend()
        ▼                            │ no Frame within grace_time:
 start_stream() per element          ▼
        │                     lease_expired_handler = destroy_stream
        ▼
 process_frame() × N  ── StreamEvent.STOP  ─► destroy_stream(graceful=True)
        │             ── StreamEvent.ERROR ─► destroy_stream() immediately
        ▼
 stop_stream() per element ─► Stream removed from stream_leases
```

If a `process_frame` arrives for an unknown `stream_id`, the Pipeline
automatically creates the Stream first (default mode), so simple
one-shot invocations don't need an explicit `create_stream`.

## For framework developers (internals)

### Design

```
  PipelineImpl
  ┌────────────────────────────────────────────────────────┐
  │ stream_leases: { "1": Lease ── stream: Stream          │
  │                                ├ parameters {…}        │
  │                                ├ state: RUN            │
  │                                └ frames: { 7: Frame ── │
  │                                    swag {a:…, b:…}     │
  │                                    metrics {…} }       │
  │ thread_local: (stream, frame_id)  ← current context    │
  └────────────────────────────────────────────────────────┘
```

- **One Stream object per lease, shared by every element.** Elements
  receive the same `Stream` instance in `start_stream()` /
  `process_frame()` / `stop_stream()`; per-Stream element state goes in
  `stream.variables`.
- **Frame as continuation.** A Frame stays in `stream.frames` while
  incomplete; `paused_pe_name` records the remote element being awaited
  so processing can resume with `iterate_after()`. In default
  (non-sliding-windows) mode the Frame cache entry is removed as soon as
  `process_frame()` completes; the experimental `_WINDOWS` protocol
  keeps Frames cached across the remote round-trip.
- **Grace time.** Each Stream is wrapped in a [Lease](lease.md) whose
  expiry handler is `destroy_stream`; `_process_initialize()` extends
  the lease on every Frame. Elements can extend it themselves
  (`self.pipeline.stream_leases[stream_id].extend(10)`), as shown
  commented in `examples/pipeline/elements.py`.
- **Response routing** is chosen per Stream: `queue_response`
  (in-process `queue.Queue`), `topic_response` (a
  `process_frame_response` message to another Service) or, by default,
  publication on the Pipeline's `.../out` topic. `queue_response` and
  `topic_response` are mutually exclusive.

### Implementation notes

- **Thread-local context.** The current `(stream, frame_id)` pair is
  installed by `PipelineImpl._enable_thread_local()` and read by
  `get_stream()`; valid on the event-loop thread inside
  `create_stream()` / `process_frame()` / `destroy_stream()`, and on
  frame-generator threads. Extend these code paths only with the
  documented `try/finally` enable/disable pattern.
- **Locking.** Every Stream owns a named `Lock` (created in
  `__post_init__`). The Pipeline holds it across element invocation for
  a Frame; frame-generator threads hold it around each
  `frame_generator()` call — this serialises generators against frame
  processing (regression-tested by `tests/unit/test_stream_lock.py`
  after PR #42; StreamEvent.ERROR lock contention after PR #32 in
  `test_stream_event.py`).
- **`_process_stream_event()`** maps an element's returned StreamEvent
  onto the Stream state: `STOP` logs and posts a graceful
  `destroy_stream` message (deferred so queued frames finish); `ERROR`
  logs and calls `destroy_stream()` immediately (guarded against
  recursion when already inside `destroy_stream()`); `DROP_FRAME` /
  `NO_FRAME` set transient states that revert to `RUN`.
- **`Stream.set_state()`** intends to prevent downgrades out of
  `ERROR` / `STOP`, but its `if / if-else` structure means any state
  other than `STOP` falls into the final `else` and is assigned
  unconditionally — so `RUN` can overwrite `ERROR`. Suspected bug;
  treat the guards as aspirational.
- **`destroy_stream(graceful=True)`** re-posts itself with a 3-second
  delay while `stream.frames` is non-empty. The
  `_destroy_stream_exit_` parameter turns a matching Stream's
  destruction into process termination (`SystemExit`) — how bounded
  jobs like `pipeline_example.json` exit cleanly.
- The module docstring warns: don't confuse `stream.py:Frame` with
  `asciimatics.widgets.Frame` used by `dashboard.py`.

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `Stream` (dataclass) | Identify the session (`stream_id`, `graph_path`); hold parameters, state, in-flight `frames`, response routing, `variables` and the per-Stream `Lock`; serialise (`as_dict()`) and re-hydrate (`update()`) for the wire | `Frame`, `Lock` utility |
| `Frame` (dataclass) | Carry one frame's `swag`, `metrics` and remote-pause continuation (`paused_pe_name`) | [PipelineElement](pipeline_element.md) (swag producer/consumer) |
| `StreamEvent` / `StreamState` (+ name maps) | Define the event and state vocabularies, including `USER` extension ranges | `PipelineImpl._process_stream_event()` |
| `PipelineImpl` (partial — lifecycle host) | `create_stream()` / `destroy_stream()` with leases and per-element start/stop; frame admission, lease extension and auto-create in `_process_initialize()`; thread-local context | [Pipeline](pipeline.md), [Lease](lease.md), [event](event.md) mailboxes |

## Current limitations and roadmap

- **Refactoring intent (project owner):** Stream *handling* — the
  lifecycle machinery still in `pipeline.py` — is to be refactored
  **out of `pipeline.py`**. `stream.py`'s own To Do records it:
  *"Refactor from pipeline.py, extract Stream concepts including
  Parameters"* (reviewing `archive/main/stream_2020.py`), and
  `pipeline.py` carries the matching *"Consider refactoring Stream into
  stream.py"* note.
- Replace the free-form `metrics` dictionary with a `Metrics` dataclass
  (To Do in `stream.py`; `pipeline.py` also suggests
  `utilities/metrics.py`).
- Source TODO checklists: verify StreamState `RUN | STOP | ERROR`
  behaviour for both local and remote cases across
  `_create_frame_generator()`, `create_stream()`,
  `_process_frame_common()` and `destroy_stream()`; on generator
  `StreamEvent.ERROR`, destroy the Stream immediately (FIX note).
- `Stream.set_state()` downgrade guard appears ineffective (see
  Implementation notes).
- The sliding-windows protocol (`--windows`) for distributed Streams —
  cached Frames, `process_frame_response()` resume, remote
  `create_stream` fan-out — is experimental and off by default.
- Testing: `tests/unit/test_stream_event.py` and `test_stream_lock.py`
  cover specific regressions; their own To Do lists call for systematic
  OKAY/STOP/ERROR coverage across all four lifecycle functions and
  consolidation of the overlap between the two test files.

## Related concepts

- [Design overview](design_overview.md)
- [Pipeline](pipeline.md) — hosts the Stream lifecycle machinery today
- [PipelineElement](pipeline_element.md) — produces StreamEvents,
  consumes the swag
- [Parameters](parameters.md) — per-Stream parameter scope
- [Lease](lease.md) — grace-time expiry of idle Streams
- [Event](event.md) — mailboxes and timers the lifecycle runs on
