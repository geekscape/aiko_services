---
title: The shape of Parameters and Streams — the Display Actor as the pilot
description: A proposal for e_03 task T6. It records how Pipeline
  parameters and streams work today, and proposes two aspects, Parameters
  and Streams, that compose into an Actor. The Display Actor's declared
  settings table and its leased frame mirror are the worked example.
  Specification only, no code change
type: concept
audience: [project-lead, architects, developers, ai-coding-agents]
status: draft
ste: adapted
source:
  - src/aiko_services/main/pipeline.py
  - src/aiko_services/main/stream.py
  - src/aiko_services/main/lease.py
  - src/aiko_services/actors/display/display.py
related: [parameters, pipeline, stream, lease, share, actor]
version: "0.8-dev"
last_updated: 2026-09-28
---

# The shape of Parameters and Streams — the Display Actor as the pilot

**Status: a proposal.** This document is the input to task T6 of
[e_03 First Class Agents](../../../constitution/e_03_FirstClassAgents.md)
(Phase 2, "Parameter/Stream orthogonalization"). It changes no code.
`pipeline.py` stays as it is. The review hands the document to the
session that owns e_03 T6.

Navigation: [display index](ReadMe.md) · [actors index](../ReadMe.md)

## 1. Why

Today, only a Pipeline and its PipelineElements have parameters and
streams. Other Actors need the same two things. The Display Actor
needed both, and it built them by hand:

- **Declared settings.** `SETTINGS_SPEC` is a table of named settings.
  Each has a kind, a default and a range. The Actor validates every
  write and rejects a bad one. A Pipeline parameter does the same, but
  without the declaration and the validation.
- **A stream on a lease.** `Screen.mirror(topic, seconds)` creates a
  frame feed that a client holds on a `Lease`. The client extends the
  lease, or the feed stops when the lease expires.
  `PipelineImpl.create_stream()` does the same for a Pipeline stream.

The proposal is to extract both into aspects that any Actor can compose.
The display is the first user.

## 2. Today, from the code

The line numbers are for `src/aiko_services/main/pipeline.py` at
master `d516775`.

### 2.1 Parameters

- **Resolution** (`PipelineElementImpl.get_parameter()`, line 562). The
  first match wins:
  1. the stream parameter `ELEMENT.NAME`
  2. the element's own share, when `NAME` is in the element definition
     and `self_share_priority` is true, else the element definition
  3. the stream parameter `NAME`
  4. the Pipeline's share, when `NAME` is in the Pipeline definition,
     else the Pipeline definition
  5. the `default` argument, with `found` left false
- **Return value.** `(value, found)`. With `required=True`, a missing
  name raises `KeyError`.
- **Writes** (`PipelineImpl.set_parameter()`, line 1606). The value goes
  directly into a `share` dictionary, or into `stream.parameters`. It
  does not go through `ec_producer.update()`. Thus a Dashboard does not
  see the change, and no change handler runs. The method ignores an
  unknown element name.
- **Types.** Values from the CLI or from MQTT are strings. Each element
  converts them itself (`int(...)`, `float(...)`, `== "true"`). The Avro
  schema of a Pipeline definition accepts only `boolean int null string`
  as parameter values. It does not accept a float.
- **Declaration.** None. No list gives the names that an element accepts
  (see "Known gaps" in [parameters.md](../../concepts/parameters.md)).
- **Use.** 106 calls of `get_parameter(` in 30 files under `src/`.

### 2.2 Streams

- `stream.py` already holds the value types: `Stream`, `Frame`,
  `StreamEvent` and `StreamState`.
- The life cycle is in `PipelineImpl`. `create_stream(stream_id,
  graph_path, parameters, grace_time, ...)` makes a
  `Lease(grace_time, stream_id, lease_expired_handler=destroy_stream)`
  (line 978). `destroy_stream()` ends the stream.
- The frame context is thread-local (`_enable_thread_local()`, line
  785). During `process_frame()`, `get_stream()` returns the current
  stream and frame.
- Stream parameters are not in the share (the To Do at line 558).

### 2.3 Two signature mismatches

- The `PipelineElement` Interface declares
  `get_parameter(name, default, required, use_pipeline)`. The
  implementation adds `self_share_priority`.
- The Interface declares `get_variables()`. The implementation takes
  `get_variables(stream)`.

The extraction must correct both before the Interfaces move.

## 3. The pilot: what the Display Actor does

| Need | Display Actor | Pipeline today |
|---|---|---|
| Declare a name | `Setting(name, kind, default, low, high, values, description)` in `SETTINGS_SPEC` | none |
| Advertise the names | share key `settings` | none |
| Default | `Setting.default` | the `parameters` of the definition |
| Start value | a command-line option (`--contrast`, `--font`) | the definition, or `create_stream(parameters=)` |
| Live change | `(update NAME VALUE)` on `control`, applied by the change handler | `set_parameter()`, a direct dictionary write |
| Validate | by kind at the boundary: `int`, `float` with a range, `flag`, and the custom kinds `applet`, `title`, `font`, `color` | none |
| Reject | `last_error` = `set_NAME_not_int@...`, a count in `metrics.rejected`, and the value in force published again | silent |
| Read | `self._applied[name]`, local | `get_parameter()` |
| A stream | `mirror(topic, seconds)`: a `Lease`, 4 holders at most, `mirrors` in the share | `create_stream()`: a `Lease` for each stream id |

Two results from the pilot are important for the design:

- **A rejected write converges.** The Dashboard writes the share key
  first. When the Actor rejects the value, it publishes the value in
  force again. Thus every client sees the value that the Actor uses.
  This is the CP-A evidence in `p_02`.
- **A stream can be only an output.** The mirror does not process
  frames. It is a flow of output frames that a holder leases. Thus a
  `Streams` aspect must not need the frame machinery of the Pipeline.

## 4. The proposed aspects

Both aspects compose into `Actor` by default. A `Service` can opt in
(e_03 §4).

### 4.1 `ParameterSpec`, a value type

```python
class ParameterSpec(NamedTuple):
    name: str
    kind: str            # int float flag choice text, or a registered kind
    default: str
    low: float = None    # int and float
    high: float = None
    values: str = ""     # the grammar, for help; the choices for "choice"
    description: str = ""
```

This is the general form of `display.Setting`. A custom kind (the
`applet`, `title`, `font` and `color` kinds of the display) registers a
parse function with `register_kind(name, parse)`. The function
`parse(text)` returns the value, or raises `ValueError(reason)`.

### 4.2 `Parameters`, an Interface

| Method or key | Meaning |
|---|---|
| `declare(*specs)` | at composition, one time; the declaration default is the first layer |
| `(update NAME VALUE)` | the live write on `control`, as today for each share key |
| `get(name)` | the value in force, converted to its kind; local, no message |
| share `parameters` | the declared names |
| share `NAME` | the value in force, as text |
| share `last_error` | `NAME_not_KIND`, `NAME_range` or `NAME_unknown`, with the value |

- **Validation at the boundary** (ADR-023). The aspect rejects a write
  to an undeclared name (`NAME_unknown`). The exception is an Actor
  that declares no parameters: its share stays open, as today.
- **A rejected write converges.** The aspect publishes the value in
  force again.
- **Three layers**, as today: the declaration default, then the start
  value (command line or definition), then a live share write.

### 4.3 `Streams`, an Interface

| Method or key | Meaning |
|---|---|
| `create_stream(stream_id, seconds, parameters=None)` | a stream on a `Lease` |
| `extend_stream(stream_id, seconds)` | extend the lease |
| `destroy_stream(stream_id)` | end the stream now |
| share `streams` | the number of streams |
| share `ID.NAME` | a stream parameter, with the same `ParameterSpec` validation |

- The mirror maps directly. `mirror(topic, seconds)` is
  `create_stream(topic, seconds)` or `extend_stream()`, and
  `mirror(topic, 0)` is `destroy_stream(topic)`. The limit of four
  holders is a declared limit of the aspect.
- The frame context (the thread-local stream and frame id, and
  `process_frame()`) stays with `Pipeline`. A `Streams` aspect has a
  life cycle and parameters, but no frames.

### 4.4 What moves and what stays

| From | To |
|---|---|
| `PipelineElementImpl.get_parameter()` resolution, steps 1 and 2 | `Parameters.get()` of the element, with stream parameters from `Streams` |
| steps 3 and 4 (the layer of the Pipeline) | stays in `PipelineElementImpl`, which asks the `Parameters` of the Pipeline |
| `PipelineImpl.set_parameter()` | `(update ...)` through `ec_producer.update()`, validated |
| the lease and the destroy of `PipelineImpl.create_stream()` | `Streams`; the Pipeline adds its graph and frame context |
| the thread-local frame context, `process_frame()` | stays in `Pipeline` |
| `display.SETTINGS_SPEC`, `Setting` | `ParameterSpec`, with four registered kinds |
| the lease records of `display.mirror()` | `Streams` |

The display is the first migration. Its tests cover each rejection and
the mirror leases (`tests/unit/test_display.py`).

## 5. Open questions for T6 and the lead

1. **Floats in the schema.** Accept `double` in the parameter map of a
   Pipeline definition, or keep floats as text?
2. **The return value of `get_parameter()`.** Keep `(value, found)` for
   the 106 callers and add `Parameters.get()` as the new form, or change
   all the callers?
3. **Stream parameters in the share** (the To Do at `pipeline.py` line
   558). The display publishes its settings. A Pipeline with many short
   streams can flood the share. Make it an opt-in for each stream?
4. **An undeclared write.** Reject it always, or only when the Actor
   declares parameters (the compatible default in §4.2)?
5. **The two signature mismatches** in §2.3. Correct them in the
   Interface before the extraction, as a separate commit?

## Related

- [Display Actor](display.md): the settings and the mirror
- [display:0 protocol](display_protocol.md): the wire forms
- [Parameters](../../concepts/parameters.md): the resolution today
- [Pipeline](../../concepts/pipeline.md) · [Lease](../../concepts/lease.md)
