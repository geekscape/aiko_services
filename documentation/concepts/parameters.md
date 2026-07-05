---
title: Parameters
description: How PipelineElement and Pipeline parameters are declared in
  the PipelineDefinition, overridden per-Stream or via shared state, and
  resolved by get_parameter()
type: concept
audience: [architects, developers, end-users]
status: work-in-progress
source:
  - src/aiko_services/main/pipeline.py
related: [design_overview, pipeline, pipeline_element, stream, share,
  dashboard]
version: "0.6"
last_updated: 2026-07-05
---

# Parameters

## Overview

**Parameters** are the configuration mechanism for
[Pipelines](pipeline.md) and [PipelineElements](pipeline_element.md):
named values that an element reads at run-time with `get_parameter()`,
layered so that the most specific, most recent source wins. A parameter
may be declared Pipeline-wide or per-element in the PipelineDefinition
JSON, overridden for a single [Stream](stream.md) at creation time,
or updated live through shared state ([Share](share.md)) — from the
Dashboard, the CLI or another Service — without touching the definition
file.

Parameters is a concept *currently implemented inside*
`src/aiko_services/main/pipeline.py` (chiefly
`PipelineElementImpl.get_parameter()` and `PipelineImpl.set_parameter()`);
the project intent is to refactor it into its own module — see the
roadmap below.

**Why you'd use it**: write the element once, tune it everywhere. The
same `PE_Add` element can add 1 by default, 10 for one deployment, and 2
for a single Stream:

```bash
aiko_pipeline create pipeline_example.json -s 1 -p limit 1000 -p rate 1
aiko_pipeline update p_local -p PE_1.pe_1_inc 2 -fd "(b: 0)"
```

```python
constant, found = self.get_parameter("constant", default=1)
```

## For application developers

### Command-line usage

Parameters has no CLI of its own; it is exercised through the
`aiko_pipeline` CLI options:

```bash
# Stream parameters at Pipeline creation: -p NAME VALUE (repeatable)
# Bare names apply to any element; "Element.name" targets one element
aiko_pipeline create pipeline_local.json -ll debug \
    -p Inspect.enable true -p Inspect.target log -p Metrics.enable true

# (-sp / --stream_parameters is a DEPRECATED alias for --parameters)

# Per-Stream parameters on an existing Pipeline
aiko_pipeline update p_local -s 1 -fd "(b: 0)" -p PE_1.pe_1_inc 2

# Without --stream_id, update sets Pipeline / element share values instead
aiko_pipeline update p_local -p PE_1.pe_1_inc 2 -fd "(b: 0)"

# Change a DataSource element's input for successive Streams
aiko_pipeline update p_text_0 -s 1 \
    -p TextReadFile.data_sources "(file://data_in/in_00.txt)"
```

Planned but unimplemented commands (source To Do list):
`aiko_pipeline get <service_filter> <parameter_name>` (or wildcard `*`)
and `aiko_pipeline set <service_filter> <parameter_name> <value>`.

### Public API

Declaration, in the PipelineDefinition JSON — both levels are optional
and default to `{}`; the Avro schema allows values of type boolean,
integer, null or string:

```json
{ "name": "p_local", "...": "...",
  "parameters": { "log_level": "DEBUG", "p_1": true, "p_2": 0 },
  "elements": [
    { "name": "PE_1",
      "parameters": { "pe_1_inc": 1 },
      "...": "..." } ] }
```

Reading, from inside an element:

```python
value, found = self.get_parameter(name,
    default=None,       # returned when not found ("found" stays False)
    required=False,     # raise KeyError when not found
    use_pipeline=True)  # fall back to Pipeline-level parameters
```

**Resolution order** (first match wins):

```
1. Stream parameters:   "ElementName.name"     (this element, this Stream)
2. Element definition parameters "name"
      └─ overridden by element self.share["name"] when present
3. Stream parameters:   "name"                 (bare name, this Stream)
4. Pipeline definition parameters "name"
      └─ overridden by pipeline share["name"] when present
5. default argument                            (found == False)
```

Steps 3–4 apply only when `use_pipeline=True` and the caller is not
itself the Pipeline. The share overrides in steps 2 and 4 are what make
live updates from the [Dashboard](dashboard.md) (or any `ECProducer`
update) take effect on the next Frame.

Writing, on the Pipeline Interface:

```python
pipeline.set_parameter(stream_id, name, value)
pipeline.set_parameters(stream_id, parameters)   # iterable of (name, value)
```

- `stream_id=None`, `name="p_x"` → Pipeline `share["p_x"]`
- `stream_id=None`, `name="PE_1.pe_1_inc"` → element `share["pe_1_inc"]`
  (unknown element names are silently ignored)
- `stream_id="1"` → the Stream's `parameters[name]`

Per-Stream parameters can also be supplied directly to
`pipeline.create_stream(stream_id, parameters={...})`.

**Well-known parameter names.** A convention of `_underscored_` names for
framework-reserved parameters is emerging:

| Name | Effect |
|------|--------|
| `log_level` | Overrides the `AIKO_LOG_LEVEL` environment variable; a `*_all` value propagates to every element |
| `_create_stream_` | Stream id to create automatically at Pipeline start-up |
| `_destroy_stream_exit_` | Stream id whose destruction terminates the Pipeline process |
| `_graph_path_` | Graph Path used by frame generators when creating Frames |
| `sliding_windows` | Enables the experimental distributed windows protocol |

**Wire form.** When the target Pipeline is remote, parameters travel as
ordinary Actor messages on its `.../in` topic: Stream parameters as the
`parameters` argument of `create_stream(...)` (the CLI `update -s -p`
path calls `pipeline.create_stream(stream_id, graph_path,
dict(parameters), ...)` on the discovered proxy), and share overrides as
`set_parameter(stream_id, name, value)` / `set_parameters(...)` calls.

## For framework developers (internals)

### Design

```
             lowest precedence ──────────────► highest precedence
  ┌────────────────────┬────────────────────┬────────────────────┐
  │ PipelineDefinition │  PipelineElement   │  Stream parameters │
  │    "parameters"    │    "parameters"    │  (per create_stream│
  │  (whole Pipeline)  │   (one element)    │   or update -s -p) │
  ├────────────────────┼────────────────────┤                    │
  │  pipeline.share[]  │  element.share[]   │                    │
  │  (live overrides via ECProducer / Dashboard / set_parameter) │
  └────────────────────┴────────────────────┴────────────────────┘
```

Design points:

- **Definition = defaults, share = live state, stream = invocation
  scope.** The JSON definition provides immutable defaults; element
  definition parameters are copied into `self.share` at init so they are
  observable and remotely mutable; Stream parameters exist only for the
  Stream's lifetime and win over everything.
- **Namespacing by dotted prefix.** `ElementName.parameter` scopes a
  Stream parameter (or a `set_parameter` call) to one element; bare names
  are shared across elements and the Pipeline. There is no registry of
  declared parameter names — spelling mistakes silently fall through to
  the default.
- The `self_share_priority` keyword (default `True`) lets internal
  callers read the *original* definition value, bypassing share
  overrides — used for `log_level` during `__init__()`.

### Implementation notes

- `get_parameter()` fetches Stream parameters via
  `_get_stream_parameters()`, which relies on the Pipeline's
  thread-local Stream context (`get_stream()`); outside a
  Stream-processing call path it quietly returns `{}`
  (`AttributeError` is swallowed).
- When a parameter is found only as a `default`, `found` is deliberately
  left `False` — callers can distinguish "configured" from "defaulted".
- `PipelineImpl.parse_pipeline_definition()` inserts `parameters: {}`
  when the optional field is absent, at both Pipeline and element level,
  before dataclass construction.
- `update_pipeline()` (CLI `create` / `update` path): with a
  `--stream_id`, CLI `-p` pairs become the new Stream's parameters; with
  no stream id, they are applied via `set_parameters(None, ...)` to
  Pipeline / element shares. Without `-s`, the Pipeline also consults its
  own `_create_stream_` parameter for an id.
- `PipelineImpl.set_parameter()` writes directly to `share[...]`
  dictionaries rather than through `ec_producer.update()`, so remote
  ECConsumers are not notified of these changes.

### CRC card

Parameters has no class of its own yet (see roadmap) — behaviour lives on
the Pipeline / PipelineElement implementations:

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `PipelineElementImpl` (partial) | `get_parameter()` resolution chain; `_get_stream_parameters()`; `get_variables()` merged view | [Stream](stream.md) (thread-local context), `share` dictionaries ([Share](share.md)) |
| `PipelineImpl` (partial) | `set_parameter()` / `set_parameters()` routing to Pipeline share, element share or Stream parameters; CLI `-p` plumbing in `update_pipeline()` | [Pipeline](pipeline.md) graph nodes, `stream_leases` |
| `PipelineDefinition` / `PipelineElementDefinition` (dataclasses) | Carry the `parameters` dictionaries parsed from JSON | `PipelineDefinitionSchema` (Avro) |

## Current limitations and roadmap

- **Refactoring intent (project owner):** Parameters is to be moved
  **out of `pipeline.py` into its own module**. The same intent is
  recorded in `stream.py`: *"Refactor from pipeline.py, extract Stream
  concepts including Parameters"*. This document describes the concept
  as it exists today, embedded in `pipeline.py`.
- TODO (source): during `process_frame()`, Stream parameters should be
  reflected into `self.share[]` just like definition parameters —
  with attention to the performance implications.
- TODO (source): Pipeline-level parameters should also be updatable
  through the same share-override path as element parameters.
- The Avro schema restricts parameter values to boolean / int / null /
  string, yet shipped definitions use floats (e.g. `"rate": 1.0` in
  `examples/pipeline/pipeline_example.json`) — and the schema
  validation result is not currently enforced (see below), so this
  passes silently.
- `PipelineDefinitionSchema.validate()`'s boolean return value is
  ignored by `parse_pipeline_definition()` (only exceptions are
  handled), so a definition that fails Avro validation is still
  accepted.
- No declaration or validation of *which* parameter names an element
  accepts; `set_parameter()` silently ignores unknown element names;
  values arriving from the CLI or MQTT are strings, and each element
  must coerce types itself (`int(...)`, `float(...)`, `.lower() ==
  "true"`).
- Planned CLI: `get` / `set` parameter commands with Service filters.
- No unit tests target parameter resolution precedence.

## Related concepts

- [Design overview](design_overview.md)
- [Pipeline](pipeline.md) — Pipeline-wide parameters, `set_parameter()`
- [PipelineElement](pipeline_element.md) — `get_parameter()` call site
- [Stream](stream.md) — per-Stream parameter scope and thread-local
  context
- [Share](share.md) — the live-override layer (ECProducer shared state)
- [Dashboard](dashboard.md) — interactive parameter inspection and update
