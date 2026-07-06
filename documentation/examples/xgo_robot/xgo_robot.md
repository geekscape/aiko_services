---
title: XGO-Mini 2 robot dog Actor (xgo_robot.py)
description: The Actor that runs on the XGO-Mini 2 robot dog —
  remote robot commands over MQTT, camera video publishing, battery
  monitoring and on-robot button handling
type: concept
audience: [developers, end-users]
status: draft
source:
  - src/aiko_services/examples/xgo_robot/xgo_robot.py
related: [actor, service, message, share, event, robot,
  robot_control]
version: "0.6"
last_updated: 2026-07-06
---

# XGO-Mini 2 robot dog Actor (xgo_robot.py)

## Overview

`xgo_robot.py` is the [Actor](../../concepts/actor.md) that runs on
the XGO-Mini 2 quadruped robot dog (Raspberry Pi CM4 with camera,
LCD screen, buttons, a 3 DoF arm with gripper, and an ESP32 driving
the servos — see the source `ReadMe.md`). It exposes the robot as an
Aiko Services [Service](../../concepts/service.md) with protocol
`.../xgo_robot:0`: every robot command — `action`, `arm`, `claw`,
`move`, `turn`, `attitude`, ... — is a remote function call, and the
camera is published as a compressed video stream over MQTT for the
laptop-side [robot_control](robot_control.md) viewer or the
Pipeline-based [OODA loop](../robot/ooda/elements.md).

**Why you'd use it**: command a robot dog from anywhere on the
[message](../../concepts/message.md) transport:

```bash
mosquitto_pub --topic $TOPIC_PATH/in --message "(action sit)"
```

The same file also defines the `XGORobot` Interface (duplicated in
[robot.py](robot.md), the in-progress extraction) and gates all
hardware access behind `is_robot()` — a hostname check against
`REAL_ROBOTS = ["laika", "oscar"]` — so the module can run,
mocked, on a development host.

## For application developers

### Command-line usage

```bash
./xgo_robot.py           # run the Actor (foreground)
```

On the robot itself, the sibling shell scripts wrap common
operations (each has placeholder `AIKO_MQTT_HOST` /
`ROBOT_HOSTNAME` variables to fill in):

- `xgo_robot.sh` — activate the venv, set `PYTHONPATH` (including
  the vendor `cm4-main` tree) and start `xgo_robot.py`.
- `action.sh [action]` — find the running process id and publish
  `(action <name>)` (default `sit`) to the Actor's `/in` topic.
- `terminate.sh` — likewise publish `(terminate)`.

### Public API

The `XGORobot` Interface — see [robot.py](robot.md) for the full
argument-range table:

`action(value)`, `arm(x, z)`, `arm_mode(stabilize)`,
`attitude(pitch, roll, yaw)`, `body_mode(stabilize)`, `claw(grip)`,
`move(direction, stride)`, `reset()`, `screen_detail(enabled)`,
`stop()`, `terminate(immediate)`, `translation(x, y, z)`,
`turn(speed)`.

`action()` accepts the twenty `ACTIONS` names, mapped to XGO
firmware action numbers:

```
fall, stand, crawl, circle, step, squat, roll, pitch, yaw,
roll_pitch_yaw, pee, sit, beckon, stretch, wave, wiggle_body,
wiggle_tail, sniff, shake_paw, arm
```

[Share](../../concepts/share.md) state: `battery` (refreshed every
10 s), `screen_detail`, `sleep_period` (video loop period, default
0.2 s, live-tunable), `source_file`, `topic_video`,
`version_firmware` and `version_xgolib` (real robot only).

Video is published to `<namespace>/video` as zlib-compressed
`numpy.save` RGB frames (camera at 320x240, mirrored). Each command
also echoes an S-expression such as `(claw 128)` or
`(battery 85)` to the Actor's `/out` topic, so observers can track
what the robot was told to do.

## For framework developers (internals)

### Design

```
                XGORobot (Interface, Actor)
                     ^            ^
                     |            |
               XGORobotImpl -- RobotCore
                     |             |
   is_robot()?       |             +-- _run() thread:
   +-- True:  xgolib.XGO serial        camera read -> flip -> RGB
   |          Button, LCD_2inch        -> LCD overlay (disabled)
   |          RPi.GPIO, spidev         -> publish video over MQTT
   +-- False: hardware calls
              remain mocked out
```

Key design points:

- **`RobotCore` / `XGORobotImpl` split**: `RobotCore` holds the
  hardware-agnostic state (attitude / translation accumulators,
  camera, video thread); `XGORobotImpl` mixes it with the Actor
  machinery and, on a real robot, opens the XGO serial port
  (`/dev/ttyAMA0`, `version="xgomini"`), reads firmware / library
  versions, and calls `claw(0)` once to "show signs of life".
- **Stateful actuator model**: `attitude()` and `translation()`
  keep the last pitch / roll / yaw and x / y / z, so a caller can
  update one axis and preserve the rest (`"nil"` arguments).
- **Battery monitoring** uses an
  [event](../../concepts/event.md) timer
  (`event.add_timer_handler(..., 10.0, immediate=True)`), updating
  the Share value and publishing `(battery N)`.
- **On-robot buttons** map to remote-control parity: top-left
  toggles `screen_detail()`, bottom-left calls `terminate()`.

### Implementation notes

- **The hardware calls are currently commented out**: every
  actuator method's `self._xgo.*` line is disabled with a `# MOCK`
  marker, leaving only the `/out` echo publish — as committed, the
  Actor does not drive the servos even on a real robot (only the
  startup `claw(0)` and battery reads use `xgolib`). The header
  notes why: `xgolib` blocks all threads until an action completes.
- The LCD screen is likewise disabled: `_screen_initialize()`
  returns `None`, so the status / detail overlay branch never runs.
- Hardware imports (`RPi`, `spidev`, `key.Button`, `LCD_2inch`,
  `xgolib`) only occur when `is_robot()` is true; these come from
  the vendor `cm4-main` tree on the robot's `PYTHONPATH`.

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `XGORobot` (Interface) | Declare the robot command contract | [Actor](../../concepts/actor.md), [robot.py](robot.md) |
| `RobotCore` | Share state; camera capture loop; video publishing; button handling | OpenCV, [Message](../../concepts/message.md), [Share](../../concepts/share.md) |
| `XGORobotImpl` | Implement each command against `xgolib.XGO`; battery timer; LCD overlay; terminate | `RobotCore`, `xgolib`, [Event](../../concepts/event.md), [robot_control](robot_control.md) |

## Current limitations and roadmap

**Sharp edges in the implemented code:**

- In `RobotCore._run()`, the button-check block, `_sleep()` and the
  FPS calculation sit *outside* the `while not self._terminated`
  loop — the capture loop never sleeps (ignoring `sleep_period`)
  and the on-robot buttons are only examined after termination.
- `translation()` publishes `(attitude x y z)` instead of
  `(translation x y z)` on the `/out` echo topic.
- Video topic is `<namespace>/video`, while
  `robot_control.py` subscribes to `<namespace>/<robot_name>/video`
  — the two ends currently disagree.
- The `XGORobot` Interface is duplicated here and in `robot.py`;
  the To Do list says to import `robot.py` instead.
- `attitude()` / `translation()` abstract declarations omit `self`.

**Planned** (source To Do list):

- Wrap the robot as a PipelineElement for an audio / video / LLM
  Pipeline, independent of `robot_control.py`.
- Replace `REAL_ROBOTS` hostnames with a hostname-to-implementation
  mapping (command-line implementation class).
- `(lambda NAME (COMMAND ...) ...)` scripted command sequences with
  `run` / `sleep` / `do` control, movement `period` arguments, and
  head nods for yes / no.
- Publish video and YOLO inferences as first-class DataSources;
  QR-code and ArUco readers driving actions; selectable on-robot ML
  model.
- Investigate making `xgolib` asynchronous (non-blocking); proper
  logging of syntax and runtime errors; CPU% display; new menu and
  button actions; LCD messages, sound and speech synthesis via
  `/in`; LIDAR (LD06), Oak-D Lite camera and ROS2 integration.

## Related concepts

- [Actor](../../concepts/actor.md) — remote function calls on the
  robot
- [Service](../../concepts/service.md) — protocol `xgo_robot:0`
  and discovery
- [Message](../../concepts/message.md) — command, echo and video
  topics
- [Share](../../concepts/share.md) — battery, sleep period and
  version state
- [Event](../../concepts/event.md) — the battery monitor timer
- [robot](robot.md) — the extracted Interface this file should
  import
- [robot_control](robot_control.md) — the laptop-side viewer and
  command relay
- [OODA-loop elements](../robot/ooda/elements.md) — Pipeline-based
  control that discovers this Actor
