---
title: Robot Interface extraction (robot.py)
description: Work-in-progress extraction of the XGORobot Actor
  Interface into its own module, towards a generic Robot interface
type: concept
audience: [developers]
status: draft
source:
  - src/aiko_services/examples/xgo_robot/robot.py
related: [actor, service, xgo_robot, robot_control]
version: "0.6"
last_updated: 2026-07-06
---

# Robot Interface extraction (robot.py)

## Overview

`robot.py` is the beginning of a refactor: it extracts the
`XGORobot` [Actor](../../concepts/actor.md) Interface — the abstract
robot command contract — out of the monolithic
[xgo_robot.py](xgo_robot.md) into its own module, on the way to a
generic `Robot` interface that specific robots (such as the
XGO-Mini 2) would extend. Today it duplicates the Interface that
`xgo_robot.py` still defines for itself; nothing imports this module
yet.

**Why you'd use it**: read this file for the cleanest statement of
the robot command contract and its argument ranges — every command a
robot Actor accepts remotely, e.g:

```bash
mosquitto_pub --topic $TOPIC_PATH/in --message "(action sit)"
```

## For application developers

### Command-line usage

None — the module defines an Interface only. The header records the
`mosquitto_pub` one-liner above for invoking a running robot Actor
directly over MQTT (see [Message](../../concepts/message.md)), and
reproduces the twenty-entry `ACTIONS` table (`fall`, `stand`,
`crawl`, ..., `shake_paw`, `arm`) implemented by `xgo_robot.py`.

### Public API

`XGORobot(aiko.Actor)` declares the contract; the default
implementation is bound with
`aiko.Interface.default("XGORobot", f"{MODULE_PATH}.XGORobotImpl")`.

| Method | Arguments and ranges |
|--------|----------------------|
| `action(value)` | one of the `ACTIONS` names |
| `arm(x, z)` | `x`: -80 to 155, `z`: -95 to 155 |
| `arm_mode(stabilize)` | `true` or `false` |
| `attitude(pitch, roll, yaw)` | pitch -15..15, roll -20..10, yaw -11..11; `"nil"` keeps the previous value |
| `body_mode(stabilize)` | `true` or `false` |
| `claw(grip)` | 0 (open) to 255 (closed) |
| `move(direction, stride)` | direction `"x"` or `"y"`; stride x -25..25 mm, y -18..18 mm |
| `reset()` | actuators to initial positions |
| `screen_detail(enabled)` | bool; default toggles |
| `stop()` | stop moving or rotating |
| `terminate(immediate)` | shut the Actor down |
| `translation(x, y, z)` | x -35..35, y -18..18, z 75..115; `"nil"` keeps the previous value |
| `turn(speed)` | -100 (clockwise) to 100 degrees / second |

The module-level helper `is_robot()` returns whether the current
hostname is in `REAL_ROBOTS` (`["laika", "oscar"]`) and selects
`MODULE_PATH` accordingly — the packaged module path on a real
robot, `"__main__"` otherwise.

## For framework developers (internals)

### Design

The intended shape (source To Do list, not yet realised):

```
Robot (generic Interface)          <-- planned
  ^
  |  extends
XGORobot (Interface)  ...........  robot.py (this module)
  ^
  |  implements
XGORobotImpl (Actor)  ...........  xgo_robot.py
```

`Interface.default()` registers the implementation class for
[compose_instance](../../concepts/component.md) resolution — the
same idiom every Aiko Services
[Service](../../concepts/service.md) uses.

### Implementation notes

- The `MODULE_PATH = "__main__"` fallback assumes the defining file
  is the process entry point; since `robot.py` has no `__main__`
  block and defines no `XGORobotImpl`, resolving the default
  implementation from this module on a non-robot host would fail.
- `attitude()` and `translation()` are declared without a `self`
  parameter (in both this file and `xgo_robot.py`) — harmless for
  abstract stubs, but a trap for implementers copying the
  signatures.

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `XGORobot` (Interface) | Declare the robot command contract and argument ranges | [Actor](../../concepts/actor.md), [XGORobotImpl](xgo_robot.md) |

## Current limitations and roadmap

- **Not yet wired in**: the source To Do list says to update
  `xgo_robot.py` to import this file and delete its duplicated
  `class XGORobot` — until then the two copies must be kept in sync
  by hand.
- **Planned**: design a generic `Robot` interface and rename, with
  `XGORobot` / `XGORobotImpl` extending it.
- `REAL_ROBOTS` hard-codes the hostnames `laika` and `oscar`;
  `xgo_robot.py`'s To Do list proposes a hostname-to-implementation
  mapping instead.

## Related concepts

- [Actor](../../concepts/actor.md) — the base Interface `XGORobot`
  extends
- [Service](../../concepts/service.md) — protocol and discovery
  underpinnings
- [xgo_robot](xgo_robot.md) — the implementation this Interface was
  extracted from
- [robot_control](robot_control.md) — the laptop-side remote
  control that sends these commands
