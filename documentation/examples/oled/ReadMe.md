---
title: OLED example index
description: Index of the SSD1306 OLED display Actor example concept
  documents — the Actor and its aiko_oled command line, and the oled:0
  wire protocol shared with the MicroPython aiko_engine_mp OLED
type: index
audience: [developers, end-users]
status: draft
ste: false
source:
  - src/aiko_services/examples/oled
related: [actor, service, share, discovery, dashboard]
version: "0.8-dev"
last_updated: 2026-09-26
---

# OLED example index

One concept document for the Actor, one for its wire protocol and a test
guide, all about `src/aiko_services/examples/oled/`.  These modules drive an SSD1306
128x64 OLED on a Raspberry Pi as an Aiko Services
[Actor](../../concepts/actor.md), or emulate it on a desktop.  The main
use is a status display for a headless host.  The source
`src/aiko_services/examples/oled/ReadMe.md` covers the hardware and the
install.

Navigation: [concepts guide](../../concepts/ReadMe.md) ·
[examples index](../ReadMe.md)

## Documents

| Document | Summary |
|----------|---------|
| [oled](oled.md) | The OLED Actor: status display, canvas, settings in the shared state, applets, display backends, the `aiko_oled` command line |
| [oled_protocol](oled_protocol.md) | The `oled:0` protocol: wire commands, shared state keys, failure behavior, the conformance trace, and compatibility with aiko_engine_mp |
| [testing](testing.md) | Step-by-step test guide: macOS and a Linux SBC, the command line, raw S-expressions, the shared state, the Dashboard, applets, the keys console, failure behavior |

## Files

| File | Purpose |
|------|---------|
| `oled.py` | Interfaces `OLED` and `OLEDApplets`, `OLEDImpl`, the `aiko_oled` command line |
| `display.py` | Display backends: SSD1306 over I2C (luma.oled), pygame window, terminal, PNG file, none, fake |
| `graphics.py` | The 5x7 font, image helpers, the bottom-left `Canvas`, the title row |
| `applets.py` | The `Applet` base class and registry; `status` (the default), `log`, `help`, `pattern`, `text`, `blink`, `demo` |
| `games.py` | `pong`, `asteroids`, `invaders`, `games`, `forklift`, `forklift_game` |
| `drawings.py` | `draw`: pencil-sketched cartoon scenes |
| `console.py` | `aiko_oled keys`: the interactive console |
| `aiko_oled.service` | systemd unit for a Raspberry Pi |
| `oled_test.py` | The original standalone spike, kept unchanged for reference |
