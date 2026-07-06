---
title: XGO robot remote control (robot_control.py)
description: Laptop-side Actors — RobotControl, a video viewer with
  YOLO detection and speech-command relay for the XGO robot dog, and
  VideoTest, a webcam publisher for testing the video path
type: concept
audience: [developers, end-users]
status: draft
source:
  - src/aiko_services/examples/xgo_robot/robot_control.py
related: [actor, message, share, xgo_robot, robot]
version: "0.6"
last_updated: 2026-07-06
---

# XGO robot remote control (robot_control.py)

## Overview

`robot_control.py` runs on a laptop and pairs with the
[xgo_robot](xgo_robot.md) [Actor](../../concepts/actor.md) running on
the XGO-Mini 2 robot dog. It provides two Actors:

- **`RobotControl`** (`ui` sub-command) — subscribes to the robot's
  compressed video topic, runs YOLOv8 detection over each frame,
  displays the annotated video in an OpenCV window with keyboard
  controls, publishes detection names, and relays spoken / typed
  `action` commands to the robot as S-expression
  [messages](../../concepts/message.md).
- **`VideoTest`** (`video_test` sub-command) — publishes the local
  webcam over the same compressed-video encoding, for testing the
  video transmission and display path without a robot.

**Why you'd use it**: see through the robot's camera, with
detections overlaid, and drive it from your keyboard and voice:

```bash
./robot_control.py ui aiko/oscar/1234/1   # robot Actor topic path
```

## For application developers

### Command-line usage

```bash
# https://github.com/ultralytics/ultralytics/issues/3005
pip uninstall av   # conflict between PyTorch and OpenCV imshow()

./robot_control.py ui [robot_topic]  # Control robot, display camera
./robot_control.py video_test        # Test video transmit / display
```

`robot_topic` is the robot Actor's topic path (e.g
`aiko/oscar/<pid>/<sid>`); its second element is taken as the robot
name, which selects the video topic
`<namespace>/<robot_name>/video`. Although the argument is declared
optional, omitting it crashes `ui` — see limitations.

Keyboard commands in the video window:

| Key | Effect |
|-----|--------|
| `r` | Reset robot actuators (`(reset)` then `(claw 128)`) |
| `s` | Save the current image as `z_image_??????.jpg` |
| `v` | Toggle verbose screen detail on the robot (`(screen_detail)`) |
| `x` | Exit |

The YOLO model is loaded from the relative path
`../yolo/yolov8n_robotdog.pt`, so run from
`src/aiko_services/examples/xgo_robot/`. Torch device selection
prefers `cuda`, then Apple `mps`, then `cpu`.

### Public API

Service protocols: `.../robot_control:0` (ui) and
`.../video_test:0`.

MQTT topics (namespace from `get_namespace()`):

| Topic | Direction | Payload |
|-------|-----------|---------|
| `<namespace>/<robot_name>/video` | subscribe (binary) | zlib-compressed `numpy.save` RGB image |
| `<namespace>/speech` | subscribe | `(action <verb> [args])` command texts |
| `<namespace>/detections` | publish | `<robot_name>: <detected class names>` |
| `<robot_topic>/in` | publish | robot commands, e.g `(move x 10)`, `(claw 0)` |

The `speech()` handler recognises the same command vocabulary as
the OODA-loop
[RobotActions element](../robot/ooda/elements.md) — `arm lower` /
`raise`, `backwards`, `crawl`, `forwards`, `hand close` / `open`,
`pee`, `pitch down` / `up`, `reset`, `sit`, `sniff`, `stop`,
`stretch`, `turn left` / `right`, `wag` — but emits them as wire
payloads rather than proxy calls. It also implements robot
selection: `action select <name|all>` (with the alias `bruce` ->
`laika`); commands are ignored until this instance's robot is
selected.

[Share](../../concepts/share.md) state: `frame_id` (incremented per
received video frame), `robot_topic`, `topic_video`, `source_file`;
`VideoTest` additionally shares a live-tunable `sleep_period`
(default 0.2 s).

## For framework developers (internals)

### Design

```
xgo_robot.py (robot)                 robot_control.py (laptop)
~~~~~~~~~~~~~~~~~~~~                 ~~~~~~~~~~~~~~~~~~~~~~~~~
camera -> RGB -> np.save             image(): zlib decompress
       -> zlib ---- MQTT video ----> -> resize x4 -> YOLO plot
                                     -> cv2.imshow + keys r/s/v/x
                                            |
speech-to-text --- MQTT speech ----> speech(): parse S-expression
                                            |
actuators   <----- MQTT <topic>/in <-- "(move x 10)" etc
```

Key design points:

- **Daggy video over MQTT**: images travel as zlib-compressed NumPy
  archives on a plain topic, registered with
  `add_message_handler(..., binary=True)` — a deliberate
  lowest-common-denominator transport the source plans to
  generalise.
- **Command relay, two generations**: `speech()` parses structured
  `(action ...)` S-expressions; the older `speech_naive()` keyword
  matcher (substring matching on free text) is retained but no
  longer registered as a handler.
- **`VideoTestImpl`** mirrors the robot's capture loop: webcam at
  320x240, BGR -> RGB, an FPS / latency status line via
  `cv2.putText()`, publish, sleep `sleep_period`.

### Implementation notes

- All OpenCV window interaction happens inside the MQTT `image()`
  message handler (`cv2.imshow` / `waitKey`), so the UI is only as
  responsive as the incoming frame rate.
- `_image_detection()` publishes the *set* of detected class names
  only when this robot is selected.
- The exception handlers in `speech()` / `speech_naive()` are bare
  `except: pass` — malformed commands are silently dropped.
- The source Refactor list plans to move `_camera*()`,
  `_screen*()`, `_image_convert()` and `_image_resize()` into the
  shared media elements, and to replace low-level
  `aiko.message.publish()` with discovered high-level function
  calls (ServiceDiscovery / ActorDiscovery).

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `RobotControl` (Interface) | Declare the contract: `image()` handler | [Actor](../../concepts/actor.md) |
| `RobotControlImpl` | Receive / decode video; YOLO detect and display; relay speech commands; publish detections | [Message](../../concepts/message.md), [Share](../../concepts/share.md), YOLO, OpenCV, [xgo_robot](xgo_robot.md) |
| `VideoTest` (Interface) / `VideoTestImpl` | Publish webcam frames in the robot's video encoding | [Actor](../../concepts/actor.md), `open_video_capture()` |

## Current limitations and roadmap

**Sharp edges in the implemented code:**

- `ui` declares `robot_topic` as optional (`default=None`), then
  unconditionally calls `robot_topic.split("/")[1]` — omitting the
  argument raises `AttributeError`.
- `_image_resize(scale=2)` multiplies width and height by
  `scale * 2`, i.e 4x (320x240 -> 1280x960), while the call-site
  comment says "increase to 640x480".
- `video_test` never sets `ROBOT_NAME`, so `VideoTest` publishes to
  the literal topic `<namespace>/ROBOT_NAME/video`; meanwhile
  `xgo_robot.py` publishes to `<namespace>/video` — three video
  topic conventions coexist.
- `speech_naive()` is dead code kept for reference.

**Planned** (source To Do list):

- Discover the `xgo_robot` Actor and use `<topic_path>/video`
  instead of a constructed topic; show a "robot not found" image
  when absent.
- Flip the video image for correct robot-view orientation.
- On-screen keyboard help (`?`) and many more keys: terminate /
  halt, actions, arm and claw position, pitch / roll / yaw and
  translate via arrows, motor speed, ball pick-up.
- Frame id and robot status (battery, motor speed) in the payload;
  send text / video to the robot's LCD; audio to the speaker;
  microphone mute control.

## Related concepts

- [Actor](../../concepts/actor.md) — both classes are Actors
- [Message](../../concepts/message.md) — MQTT topics and binary
  payload handlers
- [Share](../../concepts/share.md) — `frame_id`, `sleep_period`
  live state
- [xgo_robot](xgo_robot.md) — the robot-side Actor this controls
- [robot](robot.md) — the extracted robot command Interface
- [OODA-loop elements](../robot/ooda/elements.md) — the
  Pipeline-based successor to this command relay
