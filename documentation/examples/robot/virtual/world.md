---
title: Panda3D virtual robot world
description: world.py — a Panda3D virtual world whose rendered frames
  become an Aiko Services Pipeline image DataSource, standing in for a
  real robot's camera
type: concept
audience: [developers, end-users]
status: draft
source:
  - src/aiko_services/examples/robot/virtual/world.py
  - src/aiko_services/examples/robot/virtual/world_pipeline.json
related: [pipeline, pipeline_element, stream, data_source_target,
  elements, ooda_elements]
version: "0.6"
last_updated: 2026-07-06
---

# Panda3D virtual robot world

## Overview

`world.py` creates a 3D virtual world using the Panda3D engine — a
keyboard-driven robot character roaming uneven terrain, with a chase
camera and a top-down minimap — and turns its rendered frames into an
Aiko Services [Pipeline](../../../concepts/pipeline.md) image source.
The `World` [PipelineElement](../../../concepts/pipeline_element.md)
emits each rendered frame as a NumPy RGB image, so the same
machine-learning Pipelines that process a real robot's camera (see
the [OODA-loop elements](../ooda/elements.md)) can be developed and
tested without hardware.

**Why you'd use it**: exercise the whole robot OODA loop — YOLO
detection, LLM decisions, robot commands — on a laptop, driving a
simulated robot with the arrow keys instead of powering up a real
robot dog.

```bash
./world.py -gp World_OODA -ll debug   # render, detect, overlay, show
```

The code derives from the Panda3D "Roaming Ralph" sample (author
Ryan Myers; models by Jeff Styers and Reagan Heller) under a Modified
BSD licence — see the adjacent `LICENSE` file. The `models/`
directory holds the Panda3D assets (`world.egg.pz`, `robot.egg.pz`,
`robot-run.egg.pz`, `robot-walk.egg.pz` and textures), and
`yolov8n_robotdog.pt` is a symbolic link to the fine-tuned YOLOv8
model in `src/aiko_services/examples/yolo/` used by the
`YoloDetector` element.

## For application developers

### Command-line usage

Run from `src/aiko_services/examples/robot/virtual/` — the Panda3D
models load relative to the current directory:

```bash
./world.py [--help]
    [--collision_mask 4]            # -cm  collision diagnostics bits
    [--data_targets zmq://host:port]  # -dt  ImageWriteZMQ override
    [--definition_pathname pathname]  # -dp  default world_pipeline.json
    [--frame_rate_pipeline 4]       # -frp Pipeline frames per second
    [--frame_rate_world 10]         # -frw Panda3D frames per second
    [--graph_path name]             # -gp  Graph Path head element
    [--log_level error|warning|info|debug]   # -ll
    [--log_mqtt all|false|true]     # -lm
    [--name pipeline_name]          # -n   default "p_world"
    [--stream_id "{}"]              # -s   "{}" replaced by process id

./world.py -gp World      -ll debug   # images -> Metrics only
./world.py -gp World_OODA -ll debug   # local YOLO detect and display
```

Over the network, the world publishes images via ZeroMQ (see
[scheme_zmq](../../../elements/media/scheme_zmq.md)) to a separate
machine-learning Pipeline:

```bash
./world.py -gp World_ZMQ -ll debug -dt zmq://192.168.0.1:6502

# ... consumed by either ...
aiko_pipeline create world_pipeline.json    -s 1 -ll debug -gp ZMQ_OODA
aiko_pipeline create ../robot_pipeline.json -s 1 -ll debug
```

Panda3D asset inspection one-liners from the source header:

```bash
pview models/robot.egg.pz models/robot-run.egg.pz   # preview animation
punzip models/world.egg.pz -o models/world.egg      # decompress model
```

Keyboard controls shown on screen: arrow keys run / walk / rotate the
robot, `a` / `d` yaw the camera, `x` exits. Additional bindings:
`0` / `1` render mode, `2` / `3` bounds, `shift-c` reset camera,
`shift-e` show events, `shift-k` print keyboard map, `shift-o` OOBE
camera, `shift-r` reset robot, `t` toggle camera tracking. Further
camera translate / pitch / roll / yaw keys (`w s q z i k u m j l`)
are mapped into `key_map` but not yet acted upon — see limitations.

### Public API

`World` is the only importable PipelineElement (protocol
`device:0`); `PhysicsEngine` is the Panda3D application class.

| Class | Kind | Inputs -> Outputs | Parameters |
|-------|------|-------------------|------------|
| `World` | image DataSource (by behaviour) | (none) -> `images` `[image]` | `rate` (default 20), `physics_engine` (passed in-process) |

`World.start_stream()` schedules `create_frames()` with a
`frame_generator` at `rate` frames per second; each
`process_frame()` returns the most recent rendered frame as
`{"images": [numpy_rgb_array]}`, or `[]` before the first frame is
available.

`world_pipeline.json` (`p_world`) defines one PipelineDefinition
with five Graph Paths, selected by `--graph_path` / `-gp`:

| Graph Path | Flow |
|------------|------|
| `World` | `World` -> `Metrics` |
| `World_OODA` | `World` -> `OODA` -> `ImageResize` -> `YoloDetector` -> `ImageOverlay` -> `VideoShow` (+ `Metrics`) |
| `World_ZMQ` | `World` -> `ImageWriteZMQ` (default `zmq://localhost:6502`) |
| `ZMQ_OODA` | `ImageReadZMQ` (`zmq://0.0.0.0:6502`) -> `OODA` -> ... -> `VideoShow` |
| `OODA` | the shared detect-and-display tail (head `NoOp`) |

`OODA` and `ZMQ_OODA` are `NoOp` grouping nodes (see
[elements](../../../elements/media/elements.md)); the media elements
are documented under [image_io](../../../elements/media/image_io.md)
and [video_io](../../../elements/media/video_io.md).

## For framework developers (internals)

### Design

Two engines share one process: Panda3D owns the main thread and the
Aiko Services Pipeline runs in a daemon thread, with the latest
rendered image handed over through a shared attribute:

```
main thread                          daemon thread
~~~~~~~~~~~                          ~~~~~~~~~~~~~
PhysicsEngine(ShowBase).run()        pipeline.run()
  task update_robot  ------+           World.process_frame()
  task update_camera       |             reads stream.parameters
  task update_items        |               ["physics_engine"].image
                           v                      |
        win.get_screenshot()                      v
        -> RGBA -> RGB -> flip          {"images": [numpy array]}
        -> physics_engine.image        -> YoloDetector / ZMQ / ...
```

Key design points:

- **Frame handoff by attribute**: `update_robot()` (a Panda3D task)
  converts the window screenshot to a flipped RGB NumPy array and
  stores it in `physics_engine.image` (plus `image_count`). `World`
  polls that attribute at the Pipeline `rate` — the two frame rates
  (`-frw`, `-frp`) are independent, and slower Pipelines simply
  sample the newest frame.
- **The live `PhysicsEngine` object is passed as a Pipeline
  *parameter*** (`parameters={"physics_engine": ...}` to
  `PipelineImpl.create_pipeline()`), which only works because every
  element is deployed `local` — this Pipeline cannot be distributed
  as-is.
- **Roaming Ralph mechanics**: `CollisionHandlerPusher` (two spheres
  around the robot) keeps the robot out of obstacles; downward
  `CollisionRay`s from robot and camera clamp both to the terrain
  height; the camera is kept 5-10 units from the robot and looks at
  a "hover" node floating above it.
- **Minimap**: a second `Camera` 500 units above the robot renders
  into a `DisplayRegion` in the top-right corner.
- The world contains three spinning test items (two boxes and a
  "smiley" sphere) as detection targets.

### Implementation notes

- Panda3D injects builtins (`globalClock`, `taskMgr`, `loader`,
  `render`, `base`) after `ShowBase.__init__()` — hence the
  `# noqa: F821` markers.
- The Panda3D frame rate is capped with
  `ClockObject.MLimited` / `setFrameRate()`.
- `main()` replaces `"{}"` in `--stream_id` with the process id
  (`get_pid()`) for a sort-of unique Stream id, sets
  `AIKO_LOG_LEVEL` / `AIKO_LOG_MQTT` from options, then starts the
  Pipeline thread before entering `physics_engine.run()`.
- The trailing source comments document the
  `win.get_screenshot()` -> `Texture` -> `PNMImage` alternatives for
  future texture work.

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `PhysicsEngine` | Render the world, robot, items and minimap; handle keyboard, camera and collisions; expose the latest frame as `image` | Panda3D `ShowBase`, `Actor`, collision classes |
| `World` | Poll `physics_engine.image` at `rate`; emit Frames of `images` | [PipelineElement](../../../concepts/pipeline_element.md), [Stream](../../../concepts/stream.md), `PhysicsEngine` |
| `main()` | Parse options; construct `PhysicsEngine` and the Pipeline; run both | [Pipeline](../../../concepts/pipeline.md) (`PipelineImpl`) |

## Current limitations and roadmap

**Known gaps in the implemented code:**

- `World` is a plain PipelineElement — the source marks it
  "TODO: Should be a
  [DataSource](../../../concepts/data_source_target.md)".
- Only the `a` / `d` (camera-left / camera-right) keys are handled
  by `update_camera()`; the other twelve `camera-*` key-map entries
  (`w s q z i k u m j l`) are bound but ignored, and the header
  notes "FIX: Camera roll (y-axis) doesn't work".
- The `t` camera-tracking toggle flips `camera_tracking`, but
  nothing reads that flag — the camera always tracks the robot.
- `create_lights()` is defined but never called (the world model's
  baked lighting is used instead).
- World images are the chase-camera point of view, not the robot's
  point of view (header To Do).

**Planned** (source To Do list):

- Insert recognisable objects into the world model (Astra,
  XGO-Mini 2, monolith, DeLorean, ...) with collision handling.
- Robot HUD and shared variables via
  [Share](../../../concepts/share.md) eventual consistency; top-down
  navigation mini-map with robot tracks.
- A Panda3D NodePath per Aiko Services Actor / Pipeline /
  PipelineElement — an Aiko Services 3D GUI.
- Robot action / command functions (tool calling) using Pipeline
  `queue_response`.
- A World Interface offering DataSources (audio, LIDAR, telemetry,
  video) and DataTargets (audio, control).
- Investigate `panda3d.ai` behaviours; the adjacent `z_notes.txt`
  also lists alternative engines (Godot, Unity, Blender, Ogre3D).

## Related concepts

- [Pipeline](../../../concepts/pipeline.md) — created in-process by
  `main()` and run on a daemon thread
- [PipelineElement](../../../concepts/pipeline_element.md) — the
  `World` contract
- [Stream](../../../concepts/stream.md) — `create_frames()` and the
  frame generator idiom
- [DataSource / DataTarget](../../../concepts/data_source_target.md)
  — what `World` should become
- [OODA-loop elements](../ooda/elements.md) — the consumer of these
  images in the full robot example
- [scheme_zmq](../../../elements/media/scheme_zmq.md) — image
  transport for the `World_ZMQ` / `ZMQ_OODA` paths
