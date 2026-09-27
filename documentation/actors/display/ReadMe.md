---
title: OLED example index
description: Index of the SSD1306 OLED Display Actor example documents —
  the Actor and its aiko_oled command line, the display:0 wire protocol
  shared with the MicroPython aiko_engine_mp OLED, and the step-by-step
  test guide
type: index
audience: [developers, end-users]
status: draft
ste: adapted
source:
  - src/aiko_services/actors/display
related: [actor, service, share, discovery, dashboard]
version: "0.8-dev"
last_updated: 2026-09-27
---

# OLED example index

Three documents about `src/aiko_services/actors/display/`: one concept
document for the Actor, one for its wire protocol, and a test guide.
These modules drive an SSD1306 128x64 OLED on a Linux Single Board
Computer (SBC) as an Aiko Services [Actor](../../concepts/actor.md). On
a desktop, they emulate it. The main use is a status display for a headless
host. The source `src/aiko_services/actors/display/ReadMe.md` covers the
hardware and the install.

Navigation: [concepts guide](../../concepts/ReadMe.md) ·
[actors index](../ReadMe.md)

## Documents

| Document | Summary |
|----------|---------|
| [oled](oled.md) | The OLED Actor: the status display, the canvas, settings in the shared state, the applets, the keys console, the display backends and the `aiko_oled` command line |
| [oled_protocol](oled_protocol.md) | The `display:0` protocol: the Canvas, Screen and Interaction aspects and their tags, discovery, the topics, the wire commands and their grammar, the key map on the device, the shared state keys, the rejection reasons, the conformance trace, and compatibility with aiko_engine_mp |
| [oled_dashboard](oled_dashboard.md) | The Dashboard plug-in page: a live mirror of the panel through the leased frame feed, the shared state with editable settings, the process log, and the same keys as the console |
| [design](design.md) | The design record: what the protocol proves, the Dashboard plug-in pattern, the terminals, the framework findings, the measurements and the future directions |
| [parameters_streams_shape](parameters_streams_shape.md) | A proposal for e_03 T6: Parameters and Streams as aspects of an Actor, with the Display Actor as the pilot |
| [testing](testing.md) | The step-by-step test guide: macOS and a Linux SBC, the unit tests, the command line, raw S-expressions, the shared state, the Dashboard, the applets, the keys console, failure behavior and systemd |

## Reading order

1. [oled](oled.md) — the Overview and Command-line usage. Then run the
   Actor emulated in a terminal.
2. [testing](testing.md) — follow the steps. They exercise every feature
   in about an hour.
3. [oled_protocol](oled_protocol.md) — when you write a client, or when
   you extend the Actor.

## Files

| File | Purpose |
|------|---------|
| `display.py` | The `Canvas`, `Screen` and `Interaction` aspects, the `Display` composite, `DisplayImpl`, and the `aiko_display` command line |
| `outputs.py` | The output seam: the `Output` and `OutputControls` Interfaces, one Impl per backend (SSD1306 over I2C with luma.oled, pygame window, terminal, PNG file, none, fake), and the `Appearance` emulation |
| `graphics.py` | The 5x7 font, image helpers, the bottom-left `FrameBuffer`, the title row |
| `applets.py` | The `Applet` base class and registry: `log`, `help`, `pattern`, `text`, `blink`, `demo` |
| `status.py` | `status`, the default: the host and Wi-Fi screens as text or charts, the sample history, the fan, signal and link readers (`pinctrl`, `iw`, `nmcli`) |
| `games.py` | `pong`, `asteroids`, `invaders`, `games`, `forklift`, `forklift_game` |
| `drawings.py` | `draw`: pencil-sketched cartoon scenes |
| `faces.py` | `clock`: an analog or a digital clock face. `eyes`: animated eyes with emotions |
| `keys.py` | The key map, run on the Actor: what each key does, and the `keys.*` legend |
| `console.py` | `aiko_oled keys`: the interactive console, which sends every key to the Actor |
| `dashboard_plugin.py` | The Dashboard page: `aiko_dashboard -p aiko_services.examples.oled.dashboard_plugin` |
| `aiko_oled.service` | A systemd unit for a Linux SBC: the display comes up with the host |
| `oled_test.py` | The original standalone spike, kept unchanged for reference. No module imports it |
| `tests/unit/test_display.py`, `test_display_cli.py`, `test_display_applets.py`, `test_display_dashboard_plugin.py` | 111 unit tests: graphics, the outputs, the Actor, dispatch, settings, the mirror, the command line, the applets at three canvas sizes, the Dashboard page. No broker, no panel and no screen needed |

## Status

Epic 0 is complete and approved (2026-09-27): the Actor, the status
display, the settings, the applets, the console, the tests and these
documents. Epic 1 is in progress: phase 1 (2026-09-27) made the protocol
the `display:0` composite of three aspects, declared the settings once,
and moved the key map to the Actor. Phase 2 (2026-09-27) added the
leased frame mirror and the Dashboard page. Phase 3 (2026-09-27)
composed the output seam and made the applets portable. The next phases
add both panels as one display, the 8x8 font and a `logs` applet.
Everything is verified on
macOS (Python 3.12, emulated displays) and on a Linux SBC (a Raspberry
Pi, Python 3.13, the panel at 0x3C). Convergence with aiko_engine_mp is
Epic 2.

## Related documentation

- [Actor](../../concepts/actor.md) — the Actor and remote commands
- [Service](../../concepts/service.md) — protocol `oled:0` and
  discovery
- [Share](../../concepts/share.md) — the settings and the observations
- [Dashboard](../../concepts/dashboard.md) — editing the settings
- [XGO robot example](../../examples/xgo_robot/ReadMe.md) — another hardware Actor
  on an SBC
