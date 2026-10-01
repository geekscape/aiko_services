---
title: Display Actor index
description: Index of the Display Actor documents — the Actor and its
  aiko_display command line, the display:0 wire protocol shared with the
  MicroPython aiko_engine_mp OLED, the Dashboard page, the design record,
  the Parameters and Streams proposal, and the step-by-step test guide
type: index
audience: [developers, end-users]
status: draft
ste: adapted
source:
  - src/aiko_services/actors/display
related: [actor, service, share, discovery, dashboard]
version: "0.8-dev"
last_updated: 2026-09-28
---

# Display Actor index

These documents are about `src/aiko_services/actors/display/`, the
first package of the actors tier. The Display Actor drives an SSD1306
128x64 OLED on a Linux Single Board Computer (SBC) as an Aiko Services
[Actor](../../concepts/actor.md), with the protocol `display:0`. On a
desktop, it emulates the panel. The main use is a status display for a
headless host. Any client can also draw on it, and the same clients
drive any other Actor that registers `display:0`. The source
`src/aiko_services/actors/display/ReadMe.md` covers the hardware and the
install.

Navigation: [concepts guide](../../concepts/ReadMe.md) ·
[actors index](../ReadMe.md)

## Documents

| Document | Summary |
|----------|---------|
| [display](display.md) | The Display Actor: the status display, the canvas, settings in the shared state, the applets, the keys console, the outputs and the `aiko_display` command line |
| [display_protocol](display_protocol.md) | The `display:0` protocol: the Canvas, Screen and Interaction aspects and their tags, discovery, the topics, the wire commands and their grammar, the key map on the device, how long a key is held, the shared state keys, the rejection reasons, the conformance trace, and compatibility with aiko_engine_mp |
| [display_dashboard](display_dashboard.md) | The Dashboard plug-in page: a live mirror of the panel through the leased frame feed (Unicode or ASCII), the shared state with editable settings, the process log, the same keys as the console, and held arrow keys |
| [design](design.md) | The design record: what the protocol proves, the Dashboard plug-in pattern, the terminals, the framework findings, the measurements and the future directions |
| [parameters_streams_shape](parameters_streams_shape.md) | A proposal for e_03 task T6: Parameters and Streams as aspects of an Actor, with the Display Actor as the pilot |
| [testing](testing.md) | The step-by-step test guide: macOS and a Linux SBC, the unit tests, the command line, raw S-expressions, the shared state, the Dashboard, the applets, the keys console, the simple example, the terminals, failure behavior and systemd |

## Reading order

1. [display](display.md) — the Overview and Command-line usage. Then run
   the Actor emulated in a terminal.
2. [testing](testing.md) — follow the steps. They exercise every feature
   in about an hour.
3. [display_protocol](display_protocol.md) — when you write a client, or
   when you extend the Actor.
4. [design](design.md) — when you design another Actor, a Dashboard
   page, or a new kind of display.

## Files

| File | Purpose |
|------|---------|
| `display.py` | The `Canvas`, `Screen` and `Interaction` aspects, the `Display` composite, `DisplayImpl`, the settings table `SETTINGS_SPEC` and `service_filter()` |
| `outputs.py` | The output seam: the `Output` and `OutputControls` Interfaces, one Impl per backend (SSD1306 over I2C with luma.oled, pygame window, terminal, PNG file, none, fake), the `Appearance` emulation, and the frame as Unicode or ASCII text |
| `cli.py` | The `aiko_display` command line |
| `graphics.py` | The 5x7 font, image helpers, the bottom-left `FrameBuffer`, the title row |
| `applets.py` | The `Applet` base class and registry: `log`, `help`, `pattern`, `text`, `blink`, `demo` |
| `status.py` | `status`, the default: the host and Wi-Fi screens as text or charts, the sample history, the fan, signal and link readers (`pinctrl`, `iw`, `nmcli`) |
| `games.py` | `pong`, `asteroids`, `invaders`, `games`, `forklift`, `forklift_game` |
| `drawings.py` | `draw`: pencil-sketched cartoon scenes |
| `faces.py` | `clock`: an analog or a digital clock face. `eyes`: animated eyes with emotions |
| `keys.py` | The key map, run on the Actor: what each key does, and the `keys.*` legend |
| `console.py` | `aiko_display keys`: the interactive console, which sends every key to the Actor |
| `dashboard_plugin.py` | The Dashboard page: `aiko_dashboard -p aiko_services.actors.display.dashboard_plugin` |
| `aiko_display.service` | A systemd unit for a Linux SBC: the display comes up with the host |
| `tests/unit/test_display.py`, `test_display_cli.py`, `test_display_applets.py`, `test_display_dashboard_plugin.py` | 142 unit tests: graphics, the outputs, the Actor, dispatch, settings, the mirror, the command line, the applets at three canvas sizes, the Dashboard page and the terminals. No broker, no panel and no screen needed |

The one-file example `examples/oled/oled_actor.py` and the original
spike `examples/oled/oled_test.py` are in the examples tier (see the
[examples index](../../examples/ReadMe.md)).

## Status

Epic 0 is complete and approved (2026-09-27): the Actor, the status
display, the settings, the applets, the console, the tests and these
documents. Epic 1 (2026-09-27 and 2026-09-28) made the protocol the
`display:0` composite of three aspects. It added the leased frame
mirror, the Dashboard page, the composed output seam and the portable
applets. It moved the package to the actors tier, and it closed the
gaps of the Dashboard page. It wrote the design record and the
Parameters and Streams proposal, and it added the simple example. Two
framework fixes that the work found are on their own branches: the
Registrar liveness probe and the IPv4-first MQTT connection. The review
of Epic 1 is next. Both panels as one display (phase 4) and the
measurements (phase 8) wait for the lead's "Do it". Everything is
verified on macOS (Python 3.12, emulated displays) and on a Linux SBC (a
Raspberry Pi, Python 3.13, the panel at 0x3C). Convergence with
aiko_engine_mp is Epic 2.

## Related documentation

- [Actor](../../concepts/actor.md) — the Actor and remote commands
- [Service](../../concepts/service.md) — protocol `display:0` and
  discovery
- [Share](../../concepts/share.md) — the settings and the observations
- [Dashboard](../../concepts/dashboard.md) — editing the settings
- [XGO robot example](../../examples/xgo_robot/ReadMe.md) — another
  hardware Actor on an SBC
