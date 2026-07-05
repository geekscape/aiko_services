---
title: PipelineElement
description: The unit of work in a Pipeline — an Actor implementing the
  start_stream / process_frame / stop_stream contract, deployable in-process
  (local) or in another process (remote)
type: concept
audience: [architects, developers, end-users]
status: work-in-progress
source:
  - src/aiko_services/main/pipeline.py
related: [design_overview, pipeline, parameters, stream, actor, share,
  hook, data_source_target, proxy]
version: "0.6"
last_updated: 2026-07-05
---

# PipelineElement

## Overview

A **PipelineElement** is the unit of work inside a
[Pipeline](pipeline.md) graph: an [Actor](actor.md) whose
`process_frame()` method transforms one Frame of a [Stream](stream.md),
taking named inputs produced by its predecessor elements and returning
named outputs for its successors. The application developer writes only
the transformation; the framework supplies discovery, remote invocation,
shared state, [Parameters](parameters.md) resolution and Stream lifecycle
management.

Every PipelineElement declares its `input` and `output` names and types
in the PipelineDefinition, and may be deployed **local** (its Python
class loaded into the Pipeline's process) or **remote** (a proxy to an
element or whole Pipeline running elsewhere) — the element code is
identical either way.

**Why you'd use it**: to package a step of a data or media application —
decode, infer, overlay, publish — as a small reusable class. A complete
element (verbatim from `src/aiko_services/examples/pipeline/elements.py`):

```python
class PE_0(aiko.PipelineElement):
    def __init__(self, context):
        context.set_protocol("increment:0")
        context.call_init(self, "PipelineElement", context)

    def process_frame(self, stream, a) -> Tuple[aiko.StreamEvent, dict]:
        pe_0_inc, _ = self.get_parameter("pe_0_inc", 1)
        b = int(a) + int(pe_0_inc)
        self.logger.info(f"{self.my_id()} in a: {a}, out b: {b}")
        return aiko.StreamEvent.OKAY, {"b": b}
```

## For application developers

### Command-line usage

PipelineElement has no CLI of its own — elements are hosted, exercised
and parameterised through the `aiko_pipeline` CLI (see
[Pipeline](pipeline.md)):

```bash
cd src/aiko_services/examples/pipeline

# Host elements and pass parameters through to them (-p Element.name value)
aiko_pipeline create pipeline_local.json -ll debug \
    -p Inspect.enable true -p Inspect.target log -p Metrics.enable true

# Feed a Frame to the graph head element's declared input "b"
aiko_pipeline update p_local -fd "(b: 0)"

# Set an element parameter for the next Frame
aiko_pipeline update p_local -p PE_1.pe_1_inc 2 -fd "(b: 0)"

# Trace element execution with the pe / pep hooks
aiko_pipeline create pipeline_local.json --hooks all -fd "(b: 0)"
```

Element `log_level` can be raised for every element at once with
`-ll debug_all`.

### Public API

The Interface an element developer programs against
(`PipelineElement(Actor)` — `Interface.default("PipelineElement",
"aiko_services.main.pipeline.PipelineElementImpl")`):

| Operation | Role |
|-----------|------|
| `process_frame(stream, **inputs) -> (StreamEvent, dict)` | **Must implement.** Transform one Frame; return a [StreamEvent](stream.md) and the output data dict |
| `start_stream(stream, stream_id) -> (StreamEvent, dict)` | Optional; per-Stream set-up (default returns `StreamEvent.OKAY, None`) |
| `stop_stream(stream, stream_id) -> (StreamEvent, dict)` | Optional; per-Stream tear-down (default returns `StreamEvent.OKAY, None`) |
| `create_frame(stream, frame_data, frame_id, graph_path)` | Submit a new Frame to the owning Pipeline |
| `create_frames(stream, frame_generator, frame_id, rate)` | Start a background generator thread producing Frames at `rate` Hz |
| `get_parameter(name, default, required, use_pipeline)` | Resolve a parameter — see [Parameters](parameters.md) |
| `get_stream()` | Current `(stream, frame_id)` from thread-local context |
| `get_variables(stream)` | Merged view: pipeline/element parameters + shares + stream parameters + current Frame swag |
| `my_id(all=False)` | `"Name<stream_id:frame_id>"` identity string for logging |
| `is_local()` *(classmethod)* | `True` for in-process elements, `False` for `PipelineRemote` |

**The `process_frame()` contract.** The Pipeline matches the element's
declared `input` names against the Frame's accumulated data (the *swag*)
and passes them as keyword arguments — so the Python signature *is* the
data contract:

```python
def process_frame(self, stream, d, e) -> Tuple[aiko.StreamEvent, dict]:
    f = int(d) + int(e)
    return aiko.StreamEvent.OKAY, {"f": f}
```

The returned dict is merged back into the swag for successor elements.
Return values steer the Stream (see [Stream](stream.md) for the full
StreamEvent table): `OKAY` continues, `DROP_FRAME` abandons this Frame,
`STOP` ends the Stream gracefully, `ERROR` ends it immediately with a
`{"diagnostic": ...}` payload.

**Source elements: `create_frames()` and frame generators.** An element
at the head of a graph typically starts a generator during
`start_stream()`:

```python
def start_stream(self, stream, stream_id):
    rate, _ = self.get_parameter("rate", default=1.0)
    self.create_frames(stream, self.frame_generator, rate=float(rate))
    return aiko.StreamEvent.OKAY, {}

def frame_generator(self, stream, frame_id):
    limit, _ = self.get_parameter("limit")
    if frame_id < int(limit):
        return aiko.StreamEvent.OKAY, {"random": random.randint(0, 9)}
    return aiko.StreamEvent.STOP, {"diagnostic": "Frame limit reached"}
```

A generator returns either one `{frame_data}` dict or a list of dicts
(several Frames at once); returning `StreamEvent.NO_FRAME` means "nothing
right now, keep running".

**Constructor idiom.** Every element `__init__(self, context)` must call
`context.call_init(self, "PipelineElement", context)` (optionally
preceded by `context.set_protocol(...)`). The
`ContextPipelineElement` supplies `context.get_definition()` (the
element's PipelineDefinition entry) and `context.get_pipeline()` (the
owning Pipeline; `None` when the element *is* the Pipeline).

**Wire protocol.** A local element is invoked by an in-process function
call; a remote element receives the standard Actor S-expression on its
`.../in` topic, with the element's declared input names as frame data:

```
(process_frame (stream_id: 1 frame_id: 0) (b: 0))
```

Distributed frame flow, as exercised by
`examples/pipeline/pipeline_remote.json` — where element `PE_1` is a
proxy for the whole remote Pipeline `p_local`:

```
Pipeline "p_remote"                     Pipeline "p_local" (remote)
      │                                       │
      │ PE_0.process_frame(a) → {b}           │
      │ node PE_1 is remote:                  │
      │ pause Frame (paused_pe_name)          │
      │──(process_frame (stream_id: … ───►    │  run own graph:
      │     frame_id: …) (b: 1))              │  PE_1 … PE_4 → {f}
      │                                       │
      │◄─(process_frame_response ─────────────│  (sliding-windows mode;
      │     (stream_id: …) (f: 4))            │   see Pipeline concept)
      │ resume graph after PE_1:              │
      │ Metrics.process_frame(f)              │
```

## For framework developers (internals)

### Design

```
        PipelineElement (Actor)          Interface
        ├── PipelineElementImpl          local, in-process
        │     └── PipelineImpl           a Pipeline is-a PipelineElement
        ├── PipelineElementLoop          control-flow loop marker
        └── PipelineRemote               "absent" placeholder, swapped for
                                         ServiceRemoteProxy when discovered
```

- An element carries **two identities**: a graph node (`definition.name`,
  unique within the Pipeline) and an Actor/Service (name, protocol —
  default `.../pipeline_element:0` — discoverable via the Registrar).
  Deploy `local` may reuse one class under several node names
  (`class_name` field), e.g. `PE_5` reusing `PE_4` in
  `pipeline_local.json`.
- **State placement**: element definition parameters are copied into
  `self.share` at init (so the [Dashboard](dashboard.md) can observe and
  update them); per-Stream state belongs on the `stream` object or in
  `stream.variables`, never on `self`, because one element instance
  serves every concurrent Stream.
- `PipelineElementLoop` is an Interface marker: the Pipeline records the
  loop head and remaining graph when such an element runs, and loops back
  until it returns `StreamEvent.LOOP_END` (boundary named by the
  `loop_boundary` stream variable).

### Implementation notes

- **`PipelineElementImpl.__init__()`** resolves `is_pipeline`
  (`pipeline is None`), defaults the protocol
  (`PROTOCOL_PIPELINE` vs `PROTOCOL_ELEMENT`), applies the `log_level`
  parameter over `AIKO_LOG_LEVEL`, records
  `share["source_file"]` and merges `definition.parameters` into
  `self.share` (a TODO notes the Dashboard/ECProducer interaction with a
  nested `share["parameters"]` approach is broken, hence the flat merge).
- **`create_frame()`** copies the Stream (fresh `Stream` dataclass with
  the same ids, parameters and response routing) before handing it to
  `pipeline.create_frame()`, which posts a `process_frame` message to the
  Pipeline mailbox — element code never runs the graph directly.
- **`_create_frames_generator()`** runs on a daemon `Thread` per
  `create_frames()` call: it enables the Pipeline's thread-local Stream
  context, then loops while `stream.state == StreamState.RUN`, holding
  `stream.lock` around each `frame_generator()` call and
  `_process_stream_event()` dispatch. Back-pressure: when `rate` is
  falsy, it sleeps while the Pipeline's `in` mailbox queue is ≥ 32 deep
  (50 Hz check); `NO_FRAME` sleeps 0.02 s to avoid a busy loop; a fixed
  `rate` uses a period counter against `time.monotonic()` (TODOs note
  the `rate=0` vs `rate=None` distinction and rate-change handling need
  fixing).
- **`get_variables()`** is a plain dict-union precedence chain:
  pipeline definition parameters ∪ pipeline share ∪ element definition
  parameters ∪ element share ∪ stream parameters ∪ current Frame swag
  (rightmost wins).
- **`PipelineRemote`** returns `not self.absent` from
  `create_stream()` / `destroy_stream()` / `process_frame()` and logs
  "invoked when remote Pipeline hasn't been discovered"; discovery swaps
  the graph node's element for a `ServiceRemoteProxy` and flips
  `share["lifecycle"]` between "absent" and "ready".

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `PipelineElement` (Interface) | Declare the element contract: `process_frame()`, `start_stream()`, `stop_stream()`, `create_frame(s)()`, `get_parameter()`, `get_stream()`, `my_id()` | `Actor` (parent Interface) |
| `PipelineElementImpl` | Initialise from `ContextPipelineElement`; merge definition parameters into share; resolve parameters ([Parameters](parameters.md)); copy-and-submit Frames; run frame-generator threads with locking and back-pressure | [Pipeline](pipeline.md) (owner), [Stream](stream.md)/`Frame`, `ECProducer` ([Share](share.md)), `event` mailboxes |
| `PipelineElementLoop` (Interface) | Mark a control-flow loop head; signal completion with `StreamEvent.LOOP_END` | `PipelineImpl` (loop re-queueing) |
| `PipelineRemote` | Stand in for an undiscovered remote element: `is_local() == False`, `lifecycle` "absent", log invocations | [Proxy](proxy.md) (`ServiceRemoteProxy` replacement) |

## Current limitations and roadmap

From the source To Do list and in-line TODO/FIX comments:

- `is_local()` belongs in `actor.py` or `service.py`, not here
- `start_stream()` / `stop_stream()` should return success/failure
  results ("swag") just like `process_frame()`
- Frame generator `rate` handling: measure time since the last frame for
  accuracy; resolve `rate=0` (fills the mailbox) vs `rate=None`;
  throttle generators properly when `rate` is `None`; provide
  `event.get_mailbox_queue()` with size/throttle support; handle the
  case where the Pipeline `in` mailbox doesn't exist yet
- On generator `StreamEvent.ERROR`, destroy the Stream immediately
  (`graceful=False`) — noted as a FIX
- During `process_frame()`, stream parameters should be reflected into
  `self.share` like definition parameters (with attention to
  performance)
- Remote elements: improve Service/ActorDiscovery into a fully dynamic
  proxy with "absent"/"ready" status; collect `topic_path` etc into a
  proper `service_filter` structure; better module loading for local
  elements
- Reflect on `process_frame()` signatures to *generate*
  `definition.elements` (graph validation work-in-progress)
- Testing: `src/aiko_services/tests/unit/` covers graph name-mapping
  (`test_pipeline_graph.py`) and Stream lock/event regressions; there is
  no coverage yet of parameters resolution, remote elements or the CLI

## Related concepts

- [Design overview](design_overview.md)
- [Pipeline](pipeline.md) — the graph that hosts and drives elements
- [Parameters](parameters.md) — `get_parameter()` resolution order
- [Stream](stream.md) — Stream/Frame lifecycle, StreamEvent semantics
- [Actor](actor.md) — every element is-an Actor
- [Share](share.md) — element parameters observable as shared state
- [Hook](hook.md) — per-element instrumentation (`pe` / `pep` hooks)
- [DataSource and DataTarget](data_source_target.md) — the standard
  source/sink PipelineElement families
- [Proxy](proxy.md) — remote element invocation
