---
title: OODA-loop robot PipelineElements
description: RobotAgents, PromptMediaFusion and RobotActions — the
  Observe-Orient-Decide-Act PipelineElements that turn detections and
  natural-language text into discovered-robot commands
type: concept
audience: [developers, end-users]
status: draft
source:
  - src/aiko_services/examples/robot/ooda/elements.py
  - src/aiko_services/examples/robot/robot_pipeline.json
related: [pipeline_element, pipeline, stream, discovery, actor,
  world, xgo_robot]
version: "0.6"
last_updated: 2026-07-06
---

# OODA-loop robot PipelineElements

## Overview

`elements.py` provides the three
[PipelineElements](../../../concepts/pipeline_element.md) at the heart
of the robot example's OODA loop — Observe, Orient, Decide, Act — as
wired up by `robot_pipeline.json` (the `p_robot`
[Pipeline](../../../concepts/pipeline.md)):

- **`RobotAgents`** — the fan-in point: seeds each Frame's
  `detections` and `texts` from whatever earlier elements placed in
  the Frame swag (implemented).
- **`PromptMediaFusion`** — intended to fuse a rolling memory of
  machine-learning detections with the text prompt (a stub: currently
  returns hard-coded detections).
- **`RobotActions`** — discovers a robot
  [Actor](../../../concepts/actor.md) by name and translates parsed
  text commands, e.g `action sit`, into remote robot function calls
  (implemented).

Observation arrives as images over ZeroMQ (from the
[Panda3D virtual world](../virtual/world.md) or a real camera), and as
text typed on the terminal; orientation is ArUco marker and YOLO
detection; the decision maker is the LLM element
(`aiko_services.examples.llm.elements`); action is a real or virtual
robot — such as the [XGO-Mini 2 robot dog](../../xgo_robot/xgo_robot.md).

**Why you'd use it**: type into the Pipeline's terminal prompt and
watch a discovered robot obey:

```console
# action sit        <-- typed at the TextReadTTY prompt
# ... RobotActions<1:37>: (tick): action sit
```

The `yolov8n_robotdog.pt` file alongside `elements.py` is a symbolic
link to the fine-tuned YOLOv8 model in
`src/aiko_services/examples/yolo/`, used by the `YoloDetector`
element in the same Pipeline.

## For application developers

### Command-line usage

There is no console script; the elements are deployed by
`robot_pipeline.json`. The source header records the working session
(three terminals, run from `src/aiko_services/examples/robot/ooda/`):

```bash
# Terminal 1: image DataSource ... either the virtual world ...
(cd ../virtual; ./world.py -gp World_ZMQ -frp 1)

# ... or a real webcam publishing over ZeroMQ
aiko_pipeline create ../../../elements/media/webcam_zmq_pipeline_0.json \
    -s 1 -p resolution 640x480

# Terminal 2: the OODA-loop Pipeline itself
aiko_pipeline create ../robot_pipeline.json -s 1 -gt 3600 -ll warning
```

`RobotActions` then waits to discover the robot named by its
`service_name` parameter (`"oscar"` in `robot_pipeline.json`):

```console
Waiting to discover robot "oscar"
Discovered robot: oscar
```

Text commands typed at the `TextReadTTY` prompt (see
[scheme_tty](../../../elements/media/scheme_tty.md)) flow through the
LLM to `RobotActions`. Each processed text is logged with a status
character — a tick (handled robot command), question mark (robot
present, command not recognised) or cross (no robot discovered).

### Public API

| Class | Status | Inputs -> Outputs | Parameters |
|-------|--------|-------------------|------------|
| `RobotAgents` | implemented | (none) -> `detections`, `texts` | (none) |
| `PromptMediaFusion` | stub | `detections`, `texts` -> `detections`, `texts` | (none) |
| `RobotActions` | implemented | `texts` -> (none) | `service_name` (required) |

All three declare Service protocol `robot_actions:0`.

`RobotActions` recognises these commands (each arrives as the text
`action <verb> [argument]`; `r` and `s` are shortcuts for
`action reset` and `action stop`):

| Command | Robot call(s) |
|---------|---------------|
| `arm lower` / `arm raise` | `arm(130, -40)` / `arm(80, 80)` |
| `backwards` | `stop()` then `move("x", -10)` |
| `crawl` | `action("crawl")` |
| `forwards` | `stop()` then `move("x", +10)` |
| `hand close` / `hand open` | `claw(255)` / `claw(0)` |
| `pee` | `action("pee")` |
| `pitch down` / `pitch up` | `attitude(15, 0, 0)` / `attitude(0, 0, 0)` |
| `reset` | `reset()` |
| `sit` | `action("sit")` |
| `sniff` | `action("sniff")` |
| `stop` | `stop()` |
| `stretch` | `action("stretch")` |
| `turn left` / `turn right` | `turn(+40)` / `turn(-40)` |
| `wag` | `action("wiggle_tail")` |

If `service_name` is not provided, `start_stream()` returns
`StreamEvent.ERROR` and the [Stream](../../../concepts/stream.md)
does not start.

## For framework developers (internals)

### Design

`robot_pipeline.json` lays the OODA loop out as Graph Paths — the
implemented elements are marked `++ DONE ++` in the definition, the
rest are `Mock` placeholders (`-- TODO --` or `noop`):

```
Observe                Orient                 Decide   Act
~~~~~~~                ~~~~~~                 ~~~~~~   ~~~
ImageReadZMQ --------> ArucoDetector,
                       YoloDetector --+
TextReadTTY ---------> RobotAgents ---+--> PromptMediaFusion*
AudioReadMicrophone*                            |
                                                v
TextWriteTTY <---------------------------------LLM --> RobotActions
                                                          |
                                              XGORobot <--+ (remote)
                                              * = Mock placeholder
```

Key design points:

- **Discovery, not configuration**: `RobotActions.start_stream()`
  calls `do_discovery(XGORobot, ServiceFilter("*", service_name,
  "*", "*", "*", "*"), ...)` — see
  [Discovery](../../../concepts/discovery.md) — and stores the
  discovered Actor proxy in
  `stream.variables["robot_actions_actor"]`. The add / remove
  handlers keep the proxy current as the robot appears and
  disappears; robot method calls are then plain remote function
  calls on the proxy.
- **Per-Stream state lives in `stream.variables`**, never on `self`:
  the robot proxy, the discovery handler details (removed again in
  `stop_stream()`) and the `robot_selected` flag.
- **`RobotAgents` seeds Frame data**: `create_initial_value()` reads
  the current Frame's swag so that `detections` and `texts` exist
  (possibly as `[]`) for downstream elements regardless of which
  Graph Path produced the Frame.
- The `XGORobot` import happens inside `start_stream()`, keeping the
  module importable on hosts without the robot example's
  dependencies.

### Implementation notes

- `RobotActions.process_command()` is a plain helper returning
  `True` / `False` (command handled or not) — it is not part of the
  PipelineElement contract.
- Normal-operation logging uses `logger.warning()` so that command
  feedback is visible at the `-ll warning` level recommended for
  this Pipeline.
- Robot selection (`action select <name|all>`) is present only as
  commented-out code; `stream.variables["robot_selected"]` is
  currently always `True`.

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `RobotAgents` | Seed `detections` and `texts` from the Frame swag | [PipelineElement](../../../concepts/pipeline_element.md), [Stream](../../../concepts/stream.md) |
| `PromptMediaFusion` | (planned) Fuse detection memory with prompts | `RobotAgents`, LLM element |
| `RobotActions` | Discover the named robot Actor; parse texts and invoke robot commands | [Discovery](../../../concepts/discovery.md), [Actor](../../../concepts/actor.md), [XGORobot](../../xgo_robot/xgo_robot.md) |
| `create_initial_value()` | Helper: read a Frame swag value or default to `[]` | [Stream](../../../concepts/stream.md) |

## Current limitations and roadmap

**Stub / work-in-progress:**

- `PromptMediaFusion.process_frame()` ignores its `detections` input
  and returns the hard-coded list `["octopus", "oak_tree"]`; the
  planned `ml_memory_detections` aging logic is comments only. The
  source suggests merging it with `RobotAgents`.
- Robot selection (`select <name|all>`) is commented out and
  `robot_selected` is always `True`.
- `create_initial_value()` is flagged to move into
  `main/stream.py`.

**Planned** (source To Do list):

- Console input / output as an Aiko Dashboard plug-in: change debug
  levels and parameters, select None / One / All robots (prompt
  showing the selection via `stream.variables[]`), emergency stop,
  response display, MQTT topic subscription.
- Microphone --> Speech-To-Text (push-to-talk) and Text-To-Speech
  --> Speaker (mute) — currently `Mock` placeholders in
  `robot_pipeline.json`.

**Sharp edges:**

- If `start_stream()` fails before discovery is registered (missing
  `service_name`), `stop_stream()` still reads
  `stream.variables["robot_actions_discovery_details"]` and will
  raise `KeyError`.
- All three elements share the `robot_actions:0` protocol name,
  which makes them indistinguishable by protocol.

## Related concepts

- [PipelineElement](../../../concepts/pipeline_element.md) — the
  contract all three classes implement
- [Pipeline](../../../concepts/pipeline.md) — `robot_pipeline.json`
  Graph Paths and element deployment
- [Stream](../../../concepts/stream.md) — per-Stream state in
  `stream.variables` and the Frame swag
- [Discovery](../../../concepts/discovery.md) — how `RobotActions`
  finds the robot Actor
- [Actor](../../../concepts/actor.md) — remote robot function calls
- [Virtual world](../virtual/world.md) — the Panda3D image
  DataSource for the Observe phase
- [XGO robot](../../xgo_robot/xgo_robot.md) — the real robot Actor
  that Act drives
