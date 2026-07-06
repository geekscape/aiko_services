---
title: Robot example index
description: Index of the robot example concept documents — the
  OODA-loop PipelineElements, the Panda3D virtual world, and the
  robot_pipeline.json / world_pipeline.json PipelineDefinitions
type: index
audience: [developers, end-users]
status: draft
source:
  - src/aiko_services/examples/robot
related: [pipeline, pipeline_element, actor, discovery]
version: "0.6"
last_updated: 2026-07-06
---

# Robot example index

The robot example under `src/aiko_services/examples/robot/` builds an
Observe-Orient-Decide-Act (OODA) loop as an Aiko Services
[Pipeline](../../concepts/pipeline.md): camera images and typed text
in, YOLO / ArUco detections and LLM decisions in the middle, and
commands to a discovered robot [Actor](../../concepts/actor.md) out.
The robot can be real — the
[XGO-Mini 2 robot dog](../xgo_robot/ReadMe.md) — or simulated by the
Panda3D virtual world.

Navigation: [concepts guide](../../concepts/ReadMe.md) ·
[media elements](../../elements/media/ReadMe.md) ·
[XGO robot example](../xgo_robot/ReadMe.md)

## Module documents

| Document | Summary |
|----------|---------|
| [ooda/elements](ooda/elements.md) | `RobotAgents`, `PromptMediaFusion` (stub) and `RobotActions` — text commands to discovered-robot function calls |
| [virtual/world](virtual/world.md) | Panda3D virtual world whose rendered frames become a Pipeline image source |

## PipelineDefinitions

| PipelineDefinition | Document(s) | Purpose |
|--------------------|-------------|---------|
| `robot_pipeline.json` | [ooda/elements](ooda/elements.md) | The `p_robot` OODA loop: ZeroMQ images and terminal text in, ArUco + YOLO detection, LLM decision, robot commands out. Elements are annotated `++ DONE ++`, `-- TODO --` or `noop` (Mock placeholder) — audio (microphone, speech-to-text, text-to-speech, speaker) and `SceneDescription` are placeholders |
| `virtual/world_pipeline.json` | [virtual/world](virtual/world.md) | The `p_world` Pipeline with five Graph Paths: `World` (Metrics only), `World_OODA` (local detect and display), `World_ZMQ` (publish images via ZeroMQ), `ZMQ_OODA` (consume ZeroMQ images) and the shared `OODA` tail |

`robot_pipeline.json` also deploys elements from neighbouring
examples (`examples/llm/elements.py`, `examples/yolo/yolo.py`,
`examples/aruco_marker/aruco.py`) and from the standard
[media element families](../../elements/media/ReadMe.md)
([image_io](../../elements/media/image_io.md),
[text_io](../../elements/media/text_io.md),
[video_io](../../elements/media/video_io.md),
[scheme_tty](../../elements/media/scheme_tty.md),
[scheme_zmq](../../elements/media/scheme_zmq.md)).

## Model and asset files

| Path | Purpose |
|------|---------|
| `ooda/yolov8n_robotdog.pt` | Symbolic link to `../../yolo/yolov8n_robotdog.pt` — YOLOv8 model fine-tuned for the robot-dog scene |
| `virtual/yolov8n_robotdog.pt` | The same symbolic link, for the virtual world's `YoloDetector` |
| `virtual/models/` | Panda3D assets: `world.egg.pz` terrain, `robot.egg.pz` with `robot-run` / `robot-walk` animations, and textures (`ground.jpg`, `hedge.jpg`, `robot.jpg`, `rock03.jpg`, `tree.jpg`) |
| `virtual/LICENSE` | Modified BSD licence for the Panda3D "Roaming Ralph" sample the virtual world derives from |

The `z_notes.txt` and `z_todo.txt` scratch files record the working
terminal sessions and the example-wide To Do list.

## Related documentation

- [Pipeline](../../concepts/pipeline.md) — PipelineDefinitions,
  Graph Paths and element deployment
- [PipelineElement](../../concepts/pipeline_element.md) — the
  contract implemented by the OODA elements and `World`
- [Discovery](../../concepts/discovery.md) — how `RobotActions`
  finds a robot by Service name
- [Actor](../../concepts/actor.md) — remote robot function calls
- [XGO robot example](../xgo_robot/ReadMe.md) — the real robot dog
  this example commands
- [Media elements index](../../elements/media/ReadMe.md) — the
  standard element families reused here
