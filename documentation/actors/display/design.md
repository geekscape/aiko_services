---
title: Display Actor design — what it proves, what it taught, where it goes
description: The design record of the Display Actor (protocol display:0).
  It gives the value of the work, the Dashboard plug-in pattern, the
  thin-client design, the framework findings and their fixes, the
  measurements, and the future directions of the protocol
type: concept
audience: [project-lead, architects, developers, ai-coding-agents]
status: draft
ste: false
source:
  - src/aiko_services/actors/display
related: [actor, dashboard, dashboard_plugin, registrar, share, lease,
  ../../../constitution/adr/ADR-025_RemoteDisplayAbstraction]
version: "0.8-dev"
last_updated: 2026-09-28
---

# Display Actor design — what it proves, what it taught, where it goes

The Display Actor started as an example that drove an SSD1306 OLED. It
became a design and an evaluation of an Interface: a wire protocol,
`display:0`, that any pixel surface can register, and the clients that
drive any such surface without change. ADR-025 records the decisions.
This document records the reasons, the learning and the directions.

Navigation: [display index](ReadMe.md) · [actors index](../ReadMe.md)

## 1. What the work proves

- **One protocol, many surfaces.** `display:0` is the composite of three
  aspects: `Canvas` (draw), `Screen` (the settings of the glass and the
  frame mirror) and `Interaction` (keys). The protocol names nothing
  that is specific to an OLED. An e-paper panel, an LED matrix, a
  terminal or a web canvas is one `Output` implementation, or one Actor
  that registers `display:0`.
- **Thin clients.** The key map is on the device. Every client (the
  `aiko_display` command, the keys console, the pygame window and the
  Dashboard page) sends the same `(key K tap)`. Each client keeps only
  its own exit keys. Parity tests bind all four to the declared
  Interfaces.
- **Capabilities are advertised.** A client reads what a display can do
  from the share: `settings`, `applets`, `keys.*`, `size`, `depth`,
  `mirrors`. It adapts without code. This is the evidence for the
  candidate principle CP-M.
- **A second implementation.** The simple example in
  `examples/oled/oled_actor.py` implements only part of the `Canvas`
  aspect. The same clients drive it (see §6).

## 2. The Dashboard plug-in pattern

- `plugins = {protocol_type: Frame}`. The key is the protocol type, the
  text before the `:` of the protocol.
- `__init__()` ends with `fix()` and runs again on each resize. Thus it
  must be fast and must not subscribe.
- Do not create a second ECConsumer with id 0. Read the cache of the
  consumer that the Dashboard gives, in `_update()`.
- asciimatics runs on the main thread, the event loop on another
  thread. A message handler only stores. `_update()` draws.
- The Dashboard keeps these keys: `D ? x X Tab`. The page aliases `m` to
  the demo key `D`.
- curses reports a key press and its auto-repeats, never a release. The
  page sends an arrow as `down` on the first press, ignores the repeats,
  and sends `up` after 0.25 s without a repeat. The Actor limits `down`
  to 2 s, so a held arrow sends `down` again each second.
- A pure page model (`DisplayPage`) and a pure renderer
  (`render_mirror()`) keep the tests free of a screen.
- A pseudo-terminal (`pty.fork()` and `TIOCSWINSZ`) runs a page with no
  person at the keyboard, at any size.
- A binary feed has one subscription for each Dashboard process, on the
  topic path of the Dashboard, and the page never removes it. The lease
  on the Actor stops the traffic. Thus `remove_message_handler()` is
  never on the path (see §4).
- Each `-p` option replaces the default plug-in module. The Dashboard
  ignores a bad `-p` module and gives no message.

## 3. Terminals

asciimatics decides Unicode from the locale encoding only, and the
colours from terminfo. A pseudo-terminal test runs the page in each
combination of these (`test_terminal_matrix`):

| TERM | `LANG=en_AU.UTF-8` | `LANG=C` | `LC_ALL=C` | Colours |
|---|---|---|---|---|
| `xterm-256color` | Unicode | Unicode (Python changes `C` to `C.UTF-8`) | ASCII | 256 |
| `xterm` | Unicode | Unicode | ASCII | 8 |
| `linux` | Unicode | Unicode | ASCII | 8 |
| `vt100` | no Dashboard | no Dashboard | no Dashboard | — |

- With `LC_ALL=C`, the mirror uses plain ASCII: one character for each
  pair of pixels, or for each 2x4 cell. `AIKO_DISPLAY_MIRROR=ascii`
  selects the same, and `AIKO_DISPLAY_MIRROR=off` (or the page key `M`)
  stops the feed.
- asciimatics must hide the cursor. The `vt100` terminfo cannot, so no
  Dashboard starts there. This is not a fault of the page.
- The Linux console font has no Braille characters: use the wide page,
  or `ascii`.

A person must do these checks, because a test cannot see the glyphs:
macOS Terminal, iTerm2, the Linux console, ssh from the Mac to the Linux
SBC, and tmux. The test guide lists them.

## 4. Framework findings

| Finding | Status |
|---|---|
| A stale retained `(primary found ...)` after a power cycle kept every new Registrar secondary | Fixed on branch `andyg/registrar-liveness`: the Registrar probes a found primary and publishes `(primary absent)` when the probe gets no reply |
| A `.local` name that resolves to an unroutable IPv6 address stalled the MQTT client for 5 s | Fixed on branch `andyg/mqtt-ipv4-first`: IPv4 first, a 2 s limit for each address, and paho connects to the address that answered |
| `remove_message_handler()` raises on the last handler of a binary or wildcard topic and never unsubscribes (`process.py`) | Open: on the review agenda. The plug-in does not call it |
| `mqtt.publish()` waits in a loop when the client is disconnected | Open. The display guards each publish with the connection state |
| The event loop handles one message in each 10 ms pass | Open. A flood of `(pixels ...)` commands queues |
| Timers added before `run()` are re-based when the loop starts | Known |
| `compose_class()` reads `PROTOCOL` from the seed class only | Known: the aspect tags are the work-around (ADR-025) |
| A default Impl for several Interfaces must implement every method without its own `__init__()` | Recorded in s_02 |
| The wheel shipped tests that imported the excluded `examples/` | Fixed by the move to `actors/` |
| A test that patches `aiko.process.message` on the instance hides `ProcessData.message` from every later test | Fixed in the display tests: patch the class |

## 5. Measurements

- **Key to the next mirrored frame.** The forklift game on the Linux
  SBC, the Dashboard page on the Mac, `mirror_rate 10`: 54–196 ms over
  12 samples, median about 95 ms. The figure is an upper bound: it
  includes the 100 ms limit of the mirror.
- **Registrar recovery.** A stale announcement on the Linux SBC: the new
  Registrar published `(primary absent)` 4.9 s after its start, and
  `(primary found ...)` 5.9 s after its start, Python start-up included.

## 6. The simple example

Planned for phase 14: `examples/oled/oled_actor.py`, about 120 lines. It teaches one idea:
an Actor that draws on an SSD1306. It registers `display:0` with the
tags `device=ssd1306 canvas=0`, and implements `clear`, `log` and
`text` with the same wire forms and the same bottom-left origin. The
`aiko_display` command and the Dashboard page drive it without change.
The page shows "mirror: not supported by this Actor", because the share
has no `mirrors`.

## 7. Future directions

- **Any pixel surface is a display.** `depth` (bits for each pixel) is
  the hook for grey scale and colour, and it is additive (CP-G).
- **Epic 2, aiko_engine_mp.** The ESP32 firmware registers `display:0`
  with `device=esp32 canvas=0`, and passes the Canvas conformance trace
  in the protocol document. The 8x8 font (deferred phase 5) gives the
  same pixels.
- **Epic 3.** Events on `out`: `(applet NAME started|finished)`,
  `(rejected METHOD REASON)`, `(panel DEVICE ok|absent)`,
  `(mirror TOPIC created|destroyed)`, each also in the share. Promote
  `Canvas`, `Screen` and `Interaction` to framework Interfaces when
  Parameters and Streams compose with Actor
  ([the shape document](parameters_streams_shape.md)).
- **Projection.** Each method has `Projection: command|observation` in
  its docstring (e_10), so the MCP and A2A gateway (e_04) can expose a
  display without new code.
- **LISP applets.** The `Host` contract is the surface that a sandboxed
  evaluator can expose. Each `Host` call takes S-expression values.
- **HostMonitor.** `status source=host_monitor`, when a HostMonitor
  Actor exists. The status rows already use the s_03 `host.*` names.

## Related

- [Display Actor](oled.md) · [display:0 protocol](oled_protocol.md) ·
  [Dashboard page](oled_dashboard.md) · [test guide](testing.md)
- [Parameters and Streams shape](parameters_streams_shape.md)
- [ADR-025](../../../constitution/adr/ADR-025_RemoteDisplayAbstraction.md)
