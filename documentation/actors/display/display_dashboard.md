---
title: Dashboard page for the Display Actor (dashboard_plugin.py)
description: The Aiko Dashboard plug-in page for a Display Actor — a live
  mirror of the panel through the leased frame feed, the shared state with
  editable settings, the process log, and the same keys as the console,
  sent to the Actor's own key map
type: concept
audience: [developers, end-users]
status: draft
ste: adapted
source:
  - src/aiko_services/actors/display/dashboard_plugin.py
  - src/aiko_services/actors/display/display.py
  - src/aiko_services/actors/display/outputs.py
related: [display, display_protocol, design, testing, dashboard,
  dashboard_plugin, share]
version: "0.8-dev"
last_updated: 2026-09-28
---

# Dashboard page for the Display Actor (dashboard_plugin.py)

## Overview

The Aiko [Dashboard](../../concepts/dashboard.md) shows every Service's
shared state and log. A [plug-in page](../../concepts/dashboard_plugin.md)
adds what a Display Actor needs: the panel itself. `dashboard_plugin.py`
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

The plug-in is in the wheel, in the actors tier. Any `-p` replaces the
Dashboard's default plug-ins, so give both:

```bash
aiko_dashboard -p aiko_services.main.dashboard_plugins \
               -p aiko_services.actors.display.dashboard_plugin
```

`AIKO_DISPLAY_MIRROR` sets the mirror when the page starts: `on` (the
default), `off`, or `ascii` for plain ASCII characters.

Select the Display Actor in the Services list and press `S`. The page
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
more. A terminal that is not Unicode aware (`LC_ALL=C`, for example)
shows the mirror in plain ASCII: `'`, `.` and `:` for each pair of
pixels, or ` .:#` for each 2x4 cell by the number of lit pixels. The
service bar's right end says `mirror 5 Hz  fps 30  key 95 ms`, or
`mirror: waiting for frames`, `mirror: no frames N s`, `mirror: off (M)`,
`mirror: not supported by this Actor` (an Actor before Epic 1, or the
simple example) or `MQTT down`. `key N ms` is the time from the last key
sent to the next frame.
`last_error` shows red for five seconds after it changes.

**Keys.** Every letter, digit and symbol of the Actor's key map is sent as
`(key K tap)`. An arrow key is held (see below). The Actor runs a mapped key's
preset, or changes its setting, and passes any other key to the running
applet. Four keys differ from the console, because the Dashboard reserves
them on every page:

| Key | On the page | Why |
|-----|-------------|-----|
| `m` | `(key D tap)`: the demo applet | `D` is back to the Dashboard |
| `K` | Stop the Actor, after a confirmation | `X` quits the Dashboard |
| `H` | This page's help | `?` is the Dashboard's help. `h` still shows the help applet on the panel |
| `Esc`, `Backspace`, `q` | Back to the Dashboard | `x` quits the Dashboard |
| `M` | The mirror off, or on again | A page key: the Actor has no `M` |

Page-only keys: `Enter` on a state row edits it, when the row is a
setting. The pop-up shows the setting's values, and a bad value converges
back with `last_error` telling why. `L` opens the log level pop-up.

**The arrow keys are held.** A terminal sends a key press and then its
auto-repeats, but never a release. So the page sends `(key NAME down)`
on the first press and ignores the repeats. When no repeat arrives for
0.25 s, it sends `(key NAME up)`. The Actor lets go of a `down` after
2 s, so while the key is held, the page sends `down` again each second.
Leaving the page lets go of every arrow. A terminal that waits more than
0.25 s before its first repeat gives one short gap at the start of a
hold.

### Public API

The page has no wire protocol of its own. It uses the display protocol
([display_protocol](display_protocol.md)):

- `(mirror TOPIC 30)` on the `in` topic asks for the feed on the
  Dashboard's own topic, `NAMESPACE/HOST/PID/0/display/mirror`, and a
  timer extends it every 10 seconds. Leaving the page sends
  `(mirror TOPIC 0)`. A page that quits without leaving, or crashes,
  costs the Actor at most 30 seconds of frames.
- `(key NAME tap)` for every key, and `(key NAME down)` and
  `(key NAME up)` for the arrow keys.
- `(mirror TOPIC 0)` for `M`, when it turns the mirror off.
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
| `DisplayPage` | The page's model: what a key does, the aliases, the arrow hold and release, the latency measure, the mirror switch, the feed status, the error flash, the rendered rows | `render_mirror` |
| `render_mirror` | Rows of text and colors from a frame and the shared state, in Unicode or ASCII | `Appearance`, `text_lines`, `ascii_lines`, `xterm_color` |
| `MirrorWidget` | Prints the rows on the page's canvas | `DisplayPage` |
| `DisplayFrame` | The page: layouts, the Service's start and stop, the feed lease, the keys, the pop-ups, the state table, the log | `ServiceFrame`, `LogUI`, `LogLevelPopupMenu`, the `Canvas`, `Screen`, `Interaction` and `Display` proxies |

## Current limitations and roadmap

- Text entry for the canvas is not on the page. Use `aiko_display text`.
- The latency from an arrow key to the next mirrored frame, measured on
  the forklift game at `mirror_rate 10` from a Mac to the Linux SBC: 54
  to 196 ms over 12 samples, median about 95 ms. This includes the
  100 ms limit of the mirror.
- The terminal test (`test_terminal_matrix`) runs the page in a
  pseudo-terminal for each `TERM` of `xterm-256color`, `xterm`, `linux`
  and `vt100`, with three locales and two sizes. `LC_ALL=C` gives the
  ASCII mirror. `vt100` cannot hide the cursor, so no Dashboard starts
  there. The [design record](design.md) gives the table.
- A person must still try the page in the macOS Terminal, iTerm2, the
  Linux console (its font has no Braille), ssh and tmux. The
  [test guide](testing.md) lists these checks.
- Two Dashboards mirroring one Actor cost it two publishes per frame. The
  Actor caps holders at four.

## Related concepts

- [display](display.md) — the Actor
- [display_protocol](display_protocol.md) — the wire protocol, the mirror rows
- [design](design.md) — the Dashboard plug-in pattern and the terminals
- [testing](testing.md) — the step-by-step test guide, section 8
- [Dashboard](../../concepts/dashboard.md),
  [Dashboard plug-in](../../concepts/dashboard_plugin.md)
- [Share](../../concepts/share.md) — the shared state the page reads and
  writes
