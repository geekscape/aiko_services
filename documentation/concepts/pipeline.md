---
title: Pipeline
description: An Actor that executes a graph of PipelineElements, defined by
  a validated PipelineDefinition JSON file, processing Streams of Frames
  locally or distributed across processes and hosts
type: concept
audience: [architects, developers, end-users]
status: work-in-progress
source:
  - src/aiko_services/main/pipeline.py
related: [design_overview, pipeline_element, parameters, stream, actor,
  category, hook, proxy, registrar, lease, dashboard]
version: "0.6"
last_updated: 2026-07-05
---

# Pipeline

## Overview

A **Pipeline** is an Actor that manages a directed graph of
[PipelineElements](pipeline_element.md), moving [Streams](stream.md) of
Frames through the graph — each PipelineElement transforming the frame data
produced by its predecessors. The graph, the elements and their
[Parameters](parameters.md) are declared in a **PipelineDefinition** JSON
file, validated against an Avro schema that is deliberately hard-coded into
`pipeline.py` so the schema always matches the implementation.

A Pipeline **is-a** PipelineElement, so Pipelines compose: a graph node may
be deployed `local` (a Python class loaded into the same process) or
`remote` (a proxy for a PipelineElement or an entire Pipeline running in
another process, discovered via the [Registrar](registrar.md)). The source
notes the design intent that a Pipeline is also a
[Category](category.md) of PipelineElements.

**Why you'd use it**: to build a media, machine-learning or data processing
application as declarative, distributable building blocks rather than a
monolith. For example, running a two-element pipeline that generates random
integers and stops after two frames:

```bash
cd src/aiko_services/examples/pipeline
aiko_pipeline create pipeline_example.json -s 1 -p limit 1000 -p rate 1
aiko_dashboard  # select "pe_randomintegers" and watch "random" update
```

## For application developers

### Command-line usage

The console script is `aiko_pipeline` (defined in `pyproject.toml`;
module fallback `python -m aiko_services.main.pipeline` or
`./pipeline.py`):

```bash
aiko_pipeline create  [--name PIPELINE_NAME] DEFINITION_PATHNAME
aiko_pipeline destroy PIPELINE_NAME
aiko_pipeline list    [--watch]
aiko_pipeline update  PIPELINE_NAME [options]
```

`create` options (most also apply to `update`):

```
-n,  --name NAME             Pipeline name (default: PipelineDefinition name)
-gp, --graph_path NODE       Select sub-graph by head PipelineElement name
-s,  --stream_id ID          Create a Stream ("name_{}" appends process id)
-p,  --parameters NAME VALUE Define (Stream) parameters; repeatable
-sp, --stream_parameters     DEPRECATED: replaced by --parameters
-gt, --grace_time SECONDS    Stream receive-frame time-out (default 60)
-fi, --frame_id ID           Process Frame with identifier (default 0)
-fd, --frame_data "(a: 0)"   Process Frame with data (S-expression)
-r,  --stream_reset          destroy_stream() first, then create_stream()
-sr, --show_response         Show Pipeline output response
-ll, --log_level LEVEL       error, warning, info, debug plus "_all" suffix
-lm, --log_mqtt              all, false (console), true (mqtt)
-h,  --hooks HOOKS           Some combination of am,pe,pep,pf,all,none
-w,  --windows               Experimental distributed sliding-window protocol
```

Example sessions (from the source usage comments):

```bash
# Create a local Pipeline, then drive it remotely
aiko_pipeline create ../examples/pipeline/pipeline_local.json -ll debug

aiko_pipeline update p_local -fd "(b: 0)"           # Create Frame
aiko_pipeline update p_local -fd "(b: 0)" -sr       # Create Frame, Response
aiko_pipeline update p_local -p PE_1.pe_1_inc 2 -fd "(b: 0)"  # Set parameter
aiko_pipeline update p_local -s 1                   # Create Stream
aiko_pipeline update p_local -s 2 -gt 3             # Stream with grace time
aiko_pipeline update p_local -s 3 -fd "(b: 0)" -r   # Stream reset and Frame
aiko_pipeline update p_local -ll debug_all          # Pipeline and elements

# Select a specific Graph Path (see pipeline_paths.json)
aiko_pipeline create ../examples/pipeline/pipeline_paths.json -ll debug
aiko_pipeline update p_paths -s 1 -fd "(in_a: hello)" -gp PE_IN_1
```

`list` without `--watch` prints matching Pipelines once (via the Services
cache) and exits; with `--watch` it shows on-going add/remove actions.
`destroy` discovers the named Pipeline and invokes `stop()` on it.

Planned but unimplemented CLI commands (from the To Do list):
`show <service_filter>`, `get`/`set <parameter_name>`, and `--hooks` for
`update` (currently commented out).

### Public API

```python
class Pipeline(PipelineElement):
    Interface.default("Pipeline", "aiko_services.main.pipeline.PipelineImpl")
```

| Operation | Effect |
|-----------|--------|
| `create_stream(stream_id, graph_path, parameters, grace_time, queue_response, topic_response)` | Create a Stream lease and invoke `start_stream()` on each local element |
| `destroy_stream(stream_id, graceful)` | Invoke `stop_stream()` on each element; `graceful` waits for in-flight frames |
| `create_frame(stream, frame_data, frame_id, graph_path)` | Post a `process_frame` message onto the Pipeline's own mailbox |
| `process_frame(stream_dict, frame_data)` | Run one Frame through the graph (also the MQTT entry point) |
| `process_frame_response(stream_dict, frame_data)` | Resume a paused Frame after a remote element responds |
| `set_parameter(stream_id, name, value)` / `set_parameters(...)` | Update Pipeline, PipelineElement or Stream parameters |
| `parse_pipeline_definition(pathname)` *(classmethod)* | Load, Avro-validate and dataclass-ify a PipelineDefinition |
| `create_pipeline(...)` / `update_pipeline(...)` *(classmethods)* | Programmatic equivalents of the `create` / `update` CLI commands |

Creating a Pipeline in-process:

```python
pipeline_definition = PipelineImpl.parse_pipeline_definition(pathname)
init_args = pipeline_args(name,
    protocol=PROTOCOL_PIPELINE,
    definition=pipeline_definition,
    definition_pathname=pathname,
    graph_path=graph_path)
pipeline = compose_instance(PipelineImpl, init_args)
pipeline.run(mqtt_connection_required=False)
```

**PipelineDefinition JSON.** Top-level fields: `version` (must be `0`),
`name`, `runtime` (must be `"python"`), `graph`, optional `parameters` and
`elements`. Any `"#"` field is a comment, discarded by the parser. Each
element declares `name`, `input`, `output` (lists of `{name, type}`
records), optional `parameters` and exactly one `deploy` entry:

```json
"deploy": { "local":  { "class_name": "PE_4",  "#": "optional, default: name",
                        "module": "aiko_services.examples.pipeline.elements" }}
"deploy": { "remote": { "module": "...",
                        "service_filter": { "topic_path": "*", "name": "p_local",
                          "owner": "*", "protocol": "*", "transport": "*",
                          "tags": "*" }}}
```

**Graph grammar.** The `graph` field is a list of S-expressions, one per
sub-graph (each sub-graph's head node names a selectable *Graph Path*):

```
"graph": [
  "(PE_0 PE_1)",                                # linear
  "(PE_0 PE_1 (PE_2 PE_1))",                    # fan-in
  "(PE_0 (PE_1 (PE_3 PE_5)) (PE_2 (PE_4 PE_5)))"  # fan-out and fan-in
]
```

Output-to-input **name mapping**: when PE_1 outputs `a` and PE_2 outputs
`b`, but PE_3 expects inputs `x` and `y`:

```
"graph": ["(PE_0 (PE_1 PE_3 (a: x)) (PE_2 PE_3 (b: y)))"]
```

**Wire protocol.** A Pipeline is driven by S-expression messages on its
`.../in` topic (`NAMESPACE/HOST/PID/SID/in`):

```
(create_stream STREAM_ID [GRAPH_PATH])
(process_frame (stream_id: 1 frame_id: 0) (a: 0))
(destroy_stream STREAM_ID)
```

The frame data is an S-expression association list of
`(argument_name: argument_value ...)` pairs — the same form the
`--frame_data` CLI option takes. Pipeline output is published as
`(process_frame STREAM_INFO FRAME_DATA)` on the Pipeline's `.../out` topic,
where `STREAM_INFO` carries `stream_id`, `frame_id` and `state` — unless
the Stream was created with a `topic_response` (a
`(process_frame_response STREAM_INFO FRAME_DATA)` message is sent to that
topic) or a `queue_response` (in-process `queue.Queue`, used by
`create -sr`).

**Response round-trip** (`aiko_pipeline update p_local -fd "(b: 0)" -sr`):

```
CLI client process                     Pipeline "p_local"
      │                                       │
      │ do_command(): discover via Registrar; │
      │ listen on own aiko.topic_in           │
      │                                       │
      │──(process_frame (stream_id: … ────►   │  run graph:
      │    topic_response: CLIENT/in) (b: 0)) │  PE_1 → PE_2/PE_3 → PE_4 …
      │                                       │
      │◄─(process_frame_response ─────────────│
      │    (stream_id: … state: 0) (f: 4))    │
      │ print output, terminate               │
```

## For framework developers (internals)

### Design

```
  Pipeline (is-a PipelineElement, is-an Actor)
  ┌───────────────────────────────────────────────────────────┐
  │ definition: PipelineDefinition (parsed, Avro-validated)   │
  │ pipeline_graph: PipelineGraph                             │
  │   PE_1 ──► PE_2 ──► PE_4    (nodes hold element instances │
  │       └──► PE_3 ──┘          local or ServiceRemoteProxy) │
  │ stream_leases: {stream_id: Lease(grace_time, Stream)}     │
  │ share: lifecycle, element_count, streams, streams_frames  │
  │ remote_pipelines: {service_name: (name, proxy, topic)}    │
  └───────────────────────────────────────────────────────────┘
```

Key design points:

- **Composite deployment.** `_create_pipeline_graph()` loads each `local`
  element's module and composes an instance in-process; each `remote`
  element starts life as a `PipelineRemote` placeholder plus a
  `do_discovery()` registration. When the remote Service appears, the
  graph node's element is swapped for a `ServiceRemoteProxy`
  ([Proxy](proxy.md)); when it vanishes, the placeholder returns and
  reports `lifecycle` "absent". This realises the To Do design direction:
  *dynamic proxies that default to "absent" until discovered*.
- **Lifecycle gating.** The Pipeline's `lifecycle` share is "ready" only
  when every element on the current Graph Path is "ready". Calls to
  `create_stream()` / `process_frame()` / `destroy_stream()` arriving
  before readiness are re-posted to the Pipeline's own mailbox with a
  3-second delay — an unbounded retry noted as a TODO.
- **Everything through the mailbox.** `create_frame()` does no work
  itself; it posts a `process_frame` message to `ActorTopic.IN`, so local
  and remote frame submission follow the identical path and frames are
  processed one at a time by the event-loop thread.
- **Graph execution order** is computed by `PipelineGraph.get_path()`
  (depth-first with re-ordering so fan-in nodes run after all
  predecessors). `PipelineGraph.validate()` checks — currently loosely,
  and marked work-in-progress — that every element input is produced by
  some predecessor output or satisfied by a name mapping.
- **Hooks.** Three [Hook](hook.md) points wrap execution:
  `pipeline.process_frame:0`, `pipeline.process_element:0` and
  `pipeline.process_element_post:0`, enabled via `--hooks pf,pe,pep`
  (`am` adds the Actor message-call hook; `all` enables everything).

### Implementation notes

- **Thread-local Stream context.** The current Stream and frame id are
  thread-local (`_enable_thread_local()` / `get_stream()` /
  `_disable_thread_local()`), valid on the event-loop thread during
  `create_stream()`, `process_frame()` and `destroy_stream()`, and on
  each `_create_frames_generator()` thread. Always use the documented
  `try/finally` pattern when extending these code paths.
- **Frame execution** (`_process_frame_common()`): pop graph nodes in
  order; build each element's `inputs` from the Frame's `swag` (applying
  `map_in` renames); call `element.process_frame(stream, **inputs)`;
  convert the returned StreamEvent via `_process_stream_event()`; apply
  `map_out` renames; merge `frame_data_out` into the swag. Per-element
  and whole-pipeline timings are captured into `frame.metrics`
  (`psutil` memory metrics behind `_METRICS_MEMORY_ENABLE`; a refactor
  into `utilities/metrics.py` is a TODO).
- **Remote elements pause the Frame.** Reaching a non-local node sets
  `frame.paused_pe_name`, invokes `process_frame` on the proxy with only
  `{stream_id, frame_id}` and breaks out of the loop; the eventual
  `process_frame_response()` resumes with
  `pipeline_graph.iterate_after(paused_pe_name, graph_path)`. The resume
  path — and the retention of cached Frames it depends on — is only
  active under the experimental sliding-windows protocol (`--windows` /
  `_WINDOWS`); in default mode each Frame's cache entry is deleted as
  soon as `process_frame()` completes, and streams are auto-created per
  frame on the remote side.
- **`PipelineElementLoop`** marks control-flow loop heads: until it
  returns `StreamEvent.LOOP_END`, the node and the remaining graph are
  remembered in `stream.variables` ("loop_node" / "loop_graph") and
  re-queued when the element named by the "loop_boundary" variable
  completes.
- **Error containment.** Exceptions in `start_stream()`, `stop_stream()`,
  `process_frame()` and frame generators are caught, logged, and turned
  into `StreamEvent.ERROR` diagnostics rather than crashing the process.
  A missing cached frame id triggers verbose diagnostics and purges the
  Stream's in-flight frames (the `DEBUG` bookkeeping dated 2024-12-02).

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `Pipeline` (Interface) | Declare the contract: `create_stream()`, `destroy_stream()`, `process_frame_response()`, `set_parameter(s)()`, `parse_pipeline_definition()` | [PipelineElement](pipeline_element.md), `Actor` (parent Interfaces) |
| `PipelineImpl` | Parse and validate PipelineDefinitions; build and validate the PipelineGraph; manage Stream leases and thread-local context; execute Frames through the graph with map-in/map-out, metrics and hooks; route responses (queue, topic or `.../out`) | `PipelineGraph`, [Stream](stream.md)/`Frame`, `Lease` ([Lease](lease.md)), `ECProducer` ([Share](share.md)), [Hook](hook.md), [Proxy](proxy.md) via `get_service_proxy()` |
| `PipelineGraph` (Graph) | Hold Nodes and head nodes; compute execution order and Graph Paths; validate element inputs against predecessor outputs and mappings | `Graph`/`Node` utilities |
| `PipelineRemote` (PipelineElement) | Placeholder for an undiscovered remote element: report `lifecycle` "absent", log errors when invoked | `ServiceRemoteProxy` (its discovered replacement) |
| `PipelineDefinition` et al (dataclasses) | Typed in-memory form of the JSON definition: elements, deploy `local`/`remote`, service filters | `PipelineDefinitionSchema` (in-line Avro schema) |

## Current limitations and roadmap

From the source To Do list — highlights:

- **BUG (noted in source):** `PipelineImpl.create_frame(..., graph_path=None)`
  doesn't use its `graph_path` parameter at all
- Define Pipeline outputs explicitly, not just implicitly via element
  outputs; validate function inputs/outputs against the PipelineDefinition
- Move `is_local()` out of `pipeline.py` into `actor.py` or (better)
  `service.py`
- CLI additions: `show`, `get`, `set`; remote
  `update --hooks` support including `remove_hook_handler()`
- `start_stream()` / `stop_stream()` should return success/failure "swag"
  just like `process_frame()`
- Lists of sub-graphs for multiple sources of different data types, with
  StateMachine-driven dynamic Graph routing
- Ensure all shared updates occur via events executed solely by the
  event-loop thread; proper handling and retry limits for undiscovered
  remote Pipeline proxies
- Collect `local` / `remote` into a "deployment" configuration structure;
  a future `ServiceDefinition` / `PipelineElementDefinition` /
  `PipelineDefinition` hierarchy with service-level agreements
- Pipeline CLI option to act as the LifeCycleManager, recursively creating
  local *and remote* Pipelines / PipelineElements
- The sliding-windows distributed Stream protocol (`--windows`) is
  explicitly experimental; StreamState RUN/STOP/ERROR handling for the
  local and remote cases is still being checked case-by-case

## Related concepts

- [Design overview](design_overview.md)
- [PipelineElement](pipeline_element.md) — the nodes a Pipeline executes
- [Parameters](parameters.md) — how Pipeline and element parameters resolve
- [Stream](stream.md) — the Stream/Frame lifecycle a Pipeline manages
- [Actor](actor.md) — a Pipeline is-an Actor (mailbox, MQTT functions)
- [Hook](hook.md) — the process_frame / process_element instrumentation points
- [Proxy](proxy.md) — how remote PipelineElements are invoked
- [Registrar](registrar.md) — discovery of remote Pipelines
- [Lease](lease.md) — Stream grace-time expiry
- [Dashboard](dashboard.md) — observing `lifecycle`, `streams`, element state
