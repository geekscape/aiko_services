---
title: Dashboard page for the display Actor (dashboard_plugin.py)
description: The Aiko Dashboard plug-in page for a display Actor — a live
  mirror of the panel through the leased frame feed, the shared state with
  editable settings, the process log, and the same keys as the console,
  sent to the Actor's own key map
type: concept
audience: [developers, end-users]
status: draft
ste: adapted
source:
  - src/aiko_services/actors/display/dashboard_plugin.py
  - src/aiko_services/actors/display/oled.py
related: [oled, oled_protocol, testing, dashboard, dashboard_plugin, share]
version: "0.8-dev"
last_updated: 2026-09-27
---

# Dashboard page for the display Actor (dashboard_plugin.py)

## Overview

The Aiko [Dashboard](../../concepts/dashboard.md) shows every Service's
shared state and log. A [plug-in page](../../concepts/dashboard_plugin.md)
adds what a display Actor needs: the panel itself. `dashboard_plugin.py`
is that page. It mirrors the panel live, in the panel's colors, through
the Actor's leased frame feed. It lists the shared state and edits the
settings. It shows the process log. And it sends every key to the Actor,
where the key map lives, so the page, the console and the emulator
window behave the same.

**Why to use it**: a headless SBC in a cupboard has a display nobody sees.
From a desktop, the page shows what the panel shows, and drives it,
without a second terminal.

## For application developers

### Command-line usage

The example is not in the wheel, so the plug-in needs an editable
install, or its file path. Any `-p` replaces the Dashboard's default
plug-ins, so give both:

```bash
aiko_dashboard -p aiko_services.main.dashboard_plugins \
               -p aiko_services.examples.oled.dashboard_plugin
```

Select the display Actor in the Services list and press `S`. The page
opens with the mirror, the state, the legend and the log. `D`, `Esc`,
`Backspace` or `q` returns to the Dashboard. `x` quits the Dashboard.

The page has three layouts, chosen from the terminal size when the page
is built, and again after a resize:

| Terminal | Mirror | State | Legend | Log |
|----------|--------|-------|--------|-----|
| At least 132x48 | Half blocks: 32 rows of 128 columns, in the panel's colors | Every key, `metrics.*` and `keys.*` expanded | Two rows | The rest |
| At least 80x24 | Braille: 16 rows of 64 columns, beside a column of twelve keys | The twelve keys of the console's status line | One row | The rest |
| Smaller | A line says the terminal is too small (80x24) | Eight rows | One row | The rest |

The mirror applies the panel's emulation, the same `Appearance` the
terminal output uses:
`power` off shows dark glass, `all_on` lights every pixel, `invert` swaps
lit and unlit, `contrast` dims the foreground, and `foreground` and
`background` color it. A terminal with 256 colors shows the colors. One
with 8 colors shows white on black, bold when the contrast is 128 or
more. A terminal that is not Unicode aware shows a note instead of the
mirror. The service bar's right end says `mirror 5 Hz  fps 30`, or
`mirror: waiting for frames`, `mirror: no frames N s`, `mirror: not
supported by this Actor` (an Actor before Epic 1) or `MQTT down`.
`last_error` shows red for five seconds after it changes.

**Keys.** Every letter, digit and symbol of the Actor's key map is sent as
`(key K tap)`, and the arrow keys too. The Actor runs a mapped key's
preset, or changes its setting, and passes any other key to the running
applet. Four keys differ from the console, because the Dashboard reserves
them on every page:

| Key | On the page | Why |
|-----|-------------|-----|
| `m` | `(key D tap)`: the demo applet | `D` is back to the Dashboard |
| `K` | Stop the Actor, after a confirmation | `X` quits the Dashboard |
| `H` | This page's help | `?` is the Dashboard's help. `h` still shows the help applet on the panel |
| `Esc`, `Backspace`, `q` | Back to the Dashboard | `x` quits the Dashboard |

Page-only keys: `Enter` on a state row edits it, when the row is a
setting. The pop-up shows the setting's values, and a bad value converges
back with `last_error` telling why. `L` opens the log level pop-up. The
arrow keys send one `(key NAME tap)` per press. A held key repeats at the
terminal's rate, and the page sends at most ten a second per arrow.

### Public API

The page has no wire protocol of its own. It uses the display protocol
([oled_protocol](oled_protocol.md)):

- `(mirror TOPIC 30)` on the `in` topic asks for the feed on the
  Dashboard's own topic, `NAMESPACE/HOST/PID/0/display/mirror`, and a
  timer extends it every 10 seconds. Leaving the page sends
  `(mirror TOPIC 0)`. A page that quits without leaving, or crashes,
  costs the Actor at most 30 seconds of frames.
- `(key NAME tap)` for every key.
- `(update KEY VALUE)` on the control topic for an edited setting, exactly
  what the Dashboard's own page sends.
- `(stop)` for `K`.
- The shared state comes from the Dashboard's own ECConsumer. The page adds
  no consumer and no handler of its own.

## For framework developers (internals)

### Design

```text
Actor: _present() ──frame changed──► _mirror_frame() ──≤ mirror_rate──► publish(TOPIC, 1024 bytes)
                                                                              │ MQTT
Dashboard process, event-loop thread:  _mirror_handler() keeps the newest frame (a bytes reference)
Dashboard process, TUI thread:         DisplayFrame._update() ─► DisplayPage.rows() ─► MirrorWidget
                                       process_event() ─► DisplayPage.action() ─► proxies ─► (key ...)
```

- **One subscription per Dashboard process.** The first display page
  registers the binary handler on the Dashboard's own topic and never
  removes it. Switching Services destroys the old Actor's feed and asks
  the new one. The lease, not the subscription, stops the traffic. Thus
  the page never calls `remove_message_handler`, whose defect with binary
  topics is on the Epic 1 review agenda.
- **Two threads, one reference.** The handler runs on the event-loop
  thread and only replaces a bytes reference and a time. The widget reads
  it on the TUI thread. No lock, no drawing from the handler.
- **Guarded sends.** Every send checks the connection state first,
  because `publish()` busy-waits while MQTT is down, and the TUI thread
  would freeze.
- **Rebuilt on resize.** The Dashboard builds every page at start and
  after a resize, so `__init__` subscribes to nothing and only picks the
  layout. Start is idempotent, because the Dashboard calls it once per
  selected Service and never on reconnect.
- **Faster while frames arrive.** The page redraws at about 10 Hz while
  a frame arrived in the last two seconds, else at the Dashboard's 4 Hz.
- **Pure parts.** `DisplayPage` (what a key does, the feed status, the
  error flash) and `render_mirror()` (the rows and colors) have no
  asciimatics in them, so the unit tests run without a screen. The
  renderer is the `Appearance` value type and `text_lines()` from
  `display.py`, shared with the terminal output.

### Implementation notes

- The Dashboard's `ServiceFrame` gives the page its title and service
  bars, the `D` key, and the call to `_service_frame_start()` with the
  Dashboard's ECConsumer. The page must end its constructor with
  `fix()`.
- A frame is `Image.frombytes("1", size, data)` with `size` from the
  shared state, so a wider display (Epic 1 phase 4) needs no page change.
- Keys reserved by the Dashboard are `D`, `?`, `x`, `X`, `Ctrl-C` and
  `Tab`. The page returns them to the Dashboard untouched.
- The edit pop-up follows the Dashboard's own (`PopUpDialog` with a
  `TextBox`), and the log level pop-up is the Dashboard's
  `LogLevelPopupMenu`.

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `DisplayPage` | The page's model: what a key does, the aliases, arrow coalescing, the feed status, the error flash, the rendered rows | `render_mirror` |
| `render_mirror` | Rows of text and colors from a frame and the shared state | `Appearance`, `text_lines`, `xterm_color` |
| `MirrorWidget` | Prints the rows on the page's canvas | `DisplayPage` |
| `DisplayFrame` | The page: layouts, the Service's start and stop, the feed lease, the keys, the pop-ups, the state table, the log | `ServiceFrame`, `LogUI`, `LogLevelPopupMenu`, the `Canvas`, `Screen`, `Interaction` and `Display` proxies |

## Current limitations and roadmap

- Text entry for the canvas is not on the page. Use `aiko_oled text`.
- The arrow keys reach the Actor as taps, so a game gets no true hold.
  If the forklift game feels jerky over MQTT, a later change can send
  `down` on the first press and `up` after a pause.
- Verified under a pseudo-terminal with `TERM` `xterm-256color` (256
  colors, Unicode aware) at 132x48 and 80x24, against the Pi's panel: the
  half-block and Braille mirrors, the state table, the legend, the log,
  and keys sent to the Actor. The macOS Terminal, iTerm2 and the Linux
  console are left to try at the Epic 1 review.
- Two Dashboards mirroring one Actor cost it two publishes per frame. The
  Actor caps holders at four.

## Related concepts

- [oled](oled.md) — the Actor
- [oled_protocol](oled_protocol.md) — the wire protocol, the mirror rows
- [testing](testing.md) — the step-by-step test guide, section 8
- [Dashboard](../../concepts/dashboard.md),
  [Dashboard plug-in](../../concepts/dashboard_plugin.md)
- [Share](../../concepts/share.md) — the shared state the page reads and
  writes
