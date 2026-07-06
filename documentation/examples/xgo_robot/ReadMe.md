---
title: XGO robot example index
description: Index of the XGO-Mini 2 robot dog example concept
  documents — the on-robot Actor, the laptop-side remote control and
  the extracted robot Interface, plus the operational shell scripts
type: index
audience: [developers, end-users]
status: draft
source:
  - src/aiko_services/examples/xgo_robot
related: [actor, service, message, share]
version: "0.6"
last_updated: 2026-07-06
---

# XGO robot example index

One concept document per Python module in
`src/aiko_services/examples/xgo_robot/` — controlling the LuWu
Dynamics XGO-Mini 2 quadruped robot dog (Raspberry Pi CM4, camera,
LCD, 3 DoF arm with gripper) as an Aiko Services
[Actor](../../concepts/actor.md). The source
`src/aiko_services/examples/xgo_robot/ReadMe.md` introduces the
hardware, with links to the vendor wiki and KickStarter campaign;
only the XGO-Mini 2 is supported, not the original XGO-Mini.

Navigation: [concepts guide](../../concepts/ReadMe.md) ·
[robot example](../robot/ReadMe.md)

## Module documents

| Document | Summary |
|----------|---------|
| [xgo_robot](xgo_robot.md) | The Actor running on the robot: remote commands, camera video over MQTT, battery monitor, buttons; hardware calls currently mocked out |
| [robot_control](robot_control.md) | Laptop-side `RobotControl` (video viewer with YOLO detection and speech-command relay) and `VideoTest` (webcam publisher) |
| [robot](robot.md) | Work-in-progress extraction of the `XGORobot` Interface towards a generic `Robot` interface; not yet imported by `xgo_robot.py` |

## Shell scripts

Operational helpers, run on or against the robot; each contains
`AIKO_MQTT_HOST` / `ROBOT_HOSTNAME` placeholders to fill in:

| Script | Purpose |
|--------|---------|
| `xgo_robot.sh` | On-robot launcher: activate the venv, set `PYTHONPATH` (Aiko Services plus the vendor `cm4-main` tree), start `xgo_robot.py` |
| `action.sh [action]` | Find the running `xgo_robot` process id and publish `(action <name>)` (default `sit`) to its `/in` topic via `mosquitto_pub` |
| `terminate.sh` | Likewise publish `(terminate)` to shut the Actor down |

The scripts' shared To Do list: use discovery to find the topic
path, combine `action.sh` / `terminate.sh` into a common code base,
and add a full robot-shutdown option.

## Related documentation

- [Actor](../../concepts/actor.md) — remote robot function calls
- [Service](../../concepts/service.md) — protocols and discovery
- [Message](../../concepts/message.md) — MQTT command and video
  topics
- [Share](../../concepts/share.md) — battery and live-tunable state
- [Robot example](../robot/ReadMe.md) — the OODA-loop Pipeline and
  Panda3D virtual world that command this robot
