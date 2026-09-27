---
title: Aiko Services Examples documentation
description: Index of OKF concept documents for the example applications
  in src/aiko_services/examples/ — from the AlohaHonua hello-world Actor
  tutorial through Pipeline teaching examples to computer vision, speech,
  LLM, Google Colab, robot and OLED display applications
type: index
audience: [developers, end-users]
status: draft
ste: adapted
version: "0.8-dev"
last_updated: 2026-09-26
---

# Aiko Services: Examples documentation

This directory documents the **example applications** —
`src/aiko_services/examples/` — complete, runnable programs that show
how the [Concepts](../concepts/ReadMe.md) and the
[PipelineElement library](../elements/ReadMe.md) come together. One OKF
concept document per source module, grouped by example package,
mirroring the source layout. Each package index maps the committed
example PipelineDefinitions to the documents covering the elements they
exercise.

Only git-committed `.py` and `.json` sources are documented. The
`hyperspace/` example contains no Python or JSON sources. It is a
committed HyperSpace data tree with its own source `ReadMe.md`.
[HyperSpace](../concepts/hyperspace.md) covers it conceptually.

These documents follow the same audience-first template as the
Concepts and PipelineElements documentation
(`constitution/t_00_OkfConceptTemplate.md`).

## Packages

| Package | Contents |
|---------|----------|
| [aloha_honua/](aloha_honua/ReadMe.md) | The graduated four-stage hello-world Actor tutorial — plain Actor, discovery client, remote stop, request/response |
| [oled/](../actors/display/ReadMe.md) | Moved to the actors tier: the SSD1306 OLED Display Actor — a status display for headless hosts, an aiko_engine_mp compatible canvas, settings in the shared state, applets, a keys console, emulated on a desktop, with a test guide and unit tests |
| [pipeline/](pipeline/ReadMe.md) | Teaching Pipelines — local and remote deployment, Graph Paths, frame data encode/decode, plus the multitude/ scale stress tests |
| [colab/](colab/ReadMe.md) | Google Colab integration — running Pipelines inside a notebook with browser camera, microphone and speaker widgets |
| [speech/](speech/ReadMe.md) | Speech processing — microphone capture, WhisperX transcription, Coqui text-to-speech and the speech-to-LLM round trip |
| [llm/](llm/ReadMe.md) | Large Language Model elements — LangChain over Ollama or OpenAI, driven by the speech pipelines or a terminal |
| [yolo/](yolo/ReadMe.md) | YOLOv8 and YOLOE open-vocabulary object detection Pipelines |
| [aruco_marker/](aruco_marker/ReadMe.md) | ArUco fiducial marker detection and overlay |
| [face/](face/ReadMe.md) | Face detection using DeepFace, with shared detection counters |
| [robot/](robot/ReadMe.md) | Robot OODA-loop elements and the Panda3D virtual robot world |
| [xgo_robot/](xgo_robot/ReadMe.md) | XGO-Mini 2 robot dog — on-robot Actor, laptop-side remote control and video monitor |
| [system_pipelines/](system_pipelines/ReadMe.md) | System bootstrap through ProcessManager and the distributed webcam-to-YOLOE Pipeline pair |

## Reading paths

- **First contact with Aiko Services**:
  [aloha_honua/](aloha_honua/ReadMe.md) end-to-end — it introduces
  [Service](../concepts/service.md), [Actor](../concepts/actor.md),
  [discovery](../concepts/discovery.md) and remote invocation in four
  files under 110 lines each.
- **Learning Pipelines**: [pipeline/](pipeline/ReadMe.md) — the
  teaching elements and the local / remote / Graph Path
  PipelineDefinitions, then [multitude/](pipeline/multitude/ReadMe.md)
  for chaining many Pipelines together.
- **Computer vision**: [yolo/](yolo/ReadMe.md),
  [aruco_marker/](aruco_marker/ReadMe.md) and [face/](face/ReadMe.md),
  fed by the webcam and video elements documented in the
  [media package](../elements/media/ReadMe.md).
- **Speech and language**: [speech/](speech/ReadMe.md) then
  [llm/](llm/ReadMe.md) — three cooperating Pipelines forming a
  voice-in, voice-out LLM loop.
- **Headless hosts and small displays**: [actors/display/](../actors/display/ReadMe.md) — an
  Actor that shows the host's status on an OLED, with its settings in
  the [shared state](../concepts/share.md) for the Dashboard. Its
  [test guide](../actors/display/testing.md) runs on a desktop without hardware.
- **Distributed systems**:
  [system_pipelines/](system_pipelines/ReadMe.md) for
  [ProcessManager](../concepts/process_manager.md) bootstrap, and
  [xgo_robot/](xgo_robot/ReadMe.md) plus [robot/](robot/ReadMe.md) for
  multi-host Actors and remote control.

## Status

The examples are working material for a framework under active
development and vary widely in maturity: aloha_honua, pipeline and oled
are current and instructive. Colab, speech, llm and the robot examples
mix working code with stubs, mocks and work-in-progress. Each document
separates implemented behavior from planned behavior, based on the
source code as of 2026-07-06 (oled: 2026-09-26). Only the oled package
has automated tests: 104 unit tests that need no hardware. Several
packages depend on hardware (microphone, webcam, CUDA GPU, XGO-Mini
robot, an SSD1306 OLED) or external services (Ollama, Google Colab).

## Related documentation

- [Concepts guide](../concepts/ReadMe.md) — the framework concepts the
  examples are built on
- [PipelineElements guide](../elements/ReadMe.md) — the reusable
  element library the example Pipelines deploy alongside their own
  elements
