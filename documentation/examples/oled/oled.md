---
title: OLED display Actor (oled.py)
description: An SSD1306 128x64 OLED as an Aiko Services Actor — a status
  display for headless hosts, a canvas that any client draws on with
  aiko_engine_mp compatible S-expressions, settings that the Dashboard
  reads and writes, applications that run on the display, and emulated
  displays for a desktop
type: concept
audience: [developers, end-users]
status: draft
ste: false
source:
  - src/aiko_services/examples/oled/oled.py
  - src/aiko_services/examples/oled/display.py
  - src/aiko_services/examples/oled/graphics.py
  - src/aiko_services/examples/oled/applications.py
related: [actor, service, share, discovery, event, dashboard,
  dashboard_plugin, oled_protocol]
version: "0.8-dev"
last_updated: 2026-09-26
---

# OLED display Actor (oled.py)

## Overview

A small OLED on a headless Raspberry Pi or server can show the host's own
status: hostname, IP address, whether it is connected to the MQTT broker
and the Registrar, the time, load, and the last log lines.  `oled.py`
makes such a display an Aiko Services [Actor](../../concepts/actor.md)
with protocol `oled:0`.

The Actor owns one 128x64 one-bit image.  Remote one-way commands draw on
it (`clear`, `text`, `pixel`, `pixels`, `line`, `log`), or choose an
*application*: a source of frames that the Actor steps at the
application's frame rate.  Everything else about the display — contrast,
invert, power, title row, font, speed, blanking — is
[shared state](../../concepts/share.md) that the Aiko Dashboard, or any
client, writes with `(update KEY VALUE)`.  The wire commands are the same
ones the MicroPython [aiko_engine_mp](https://github.com/geekscape/aiko_engine_mp)
OLED accepts: `(oled:text 0 0 hello)` and `(text 0 0 hello)` are one
command.

Without the panel, the same Actor shows its frames in a desktop window
(pygame), in the terminal, or in a PNG file.  The original standalone
spike, `oled_test.py`, stays in the directory unchanged for reference.

## For application developers

### Command-line usage

`aiko_oled` (registered in `pyproject.toml`; the example directory is not
in the wheel, so it needs `pip install -e .`).  `run` starts the Actor in
the foreground; every other subcommand discovers the running Actor by
name and protocol and sends it one command.

| Subcommand | Arguments and options | What it does |
|------------|----------------------|--------------|
| `run` | `-n NAME` (default: hostname), `-o auto\|oled\|window\|terminal\|png\|none`, `-a 0x3C`, `-b 1`, `--application NAME`, `-fs 5x7\|6..64`, `--title TEXT\|off`, `-c 'FG [BG]'`, `--png FILE`, `--standalone`, `--strict` | Run the Actor.  `auto` picks the OLED when `/dev/i2c-N` exists, else a window when there is a desktop and pygame, else the terminal.  `--standalone` runs without a broker.  `--strict` exits when the display can't be opened, instead of retrying every 10 s |
| `exit` | `-n`, `-t 5`, `--all` | `(exit)`: blank the display and terminate.  `-n '*'` needs `--all` |
| `list` | `-t 2` | Every `oled:0` Actor on the broker: name, topic path, tags |
| `clear` | `-n`, `-t` | `(clear)` |
| `log WORDS...` | `-n`, `-t` | `(log WORDS ...)` |
| `text X Y WORDS...` | `-n`, `-t` | `(text X Y WORDS ...)`, origin bottom-left |
| `pixels X Y ...` | `-n`, `-t` | `(pixels X Y ...)` |
| `line X0 Y0 X1 Y1` | `-n`, `-t` | `(line X0 Y0 X1 Y1)` |
| `set KEY VALUE` | `-n`, `-t` | `(update KEY VALUE)` on the Actor's control topic, exactly what the Dashboard does |
| `application NAME [ARGS...]` | `-n`, `-t` | `(application NAME ARGS ...)`; `stop` is `(application none)` |
| `key NAME [tap\|down\|up]` | `-n`, `-t` | `(key NAME STATE)` for the running application |

Every remote subcommand gives up with exit status 1 after `-t` seconds
when no Actor answers (the framework's `do_command()` would wait for
ever).  A session on the desktop:

    $ export AIKO_MQTT_HOST=localhost
    $ aiko_registrar &
    $ aiko_oled run -o png --png /tmp/oled.png -n oledit --title Aiko_v0.8 &
    OLED Actor oledit: aiko/nomad/92920/1/in
    $ mosquitto_pub -t aiko/nomad/92920/1/in -m "(oled:text 0 0 hello)"
    $ aiko_oled text -n oledit 0 8 second row
    $ aiko_oled set -n oledit contrast 32
    $ aiko_oled list
    oledit  aiko/nomad/92920/1  ec=true
    $ aiko_oled exit -n oledit
    $ aiko_oled exit -n oledit -t 2
    Timeout after 2 s: no OLED Actor named oledit
    $ echo $?
    1

On the Raspberry Pi: `aiko_oled run -a 0x3D`.  Append `&` to run it in
the background, or start it with `aiko_process create`.

### Public API

**Interface `OLED`** (`aiko.Actor`, protocol
`github.com/geekscape/aiko_services/protocol/oled:0`).  Every method is
one-way; outcomes are observed in the shared state.  Coordinates: x
0..127 left to right, y 0..63 bottom to top.

| Method | Wire form | Effect |
|--------|-----------|--------|
| `clear()` | `(clear)`, `(oled:clear)` | Erase the canvas; the title row stays |
| `log(*words)` | `(log WORDS ...)`, `(oled:log ...)` | Scroll the canvas up one text row, write the words on the bottom row; keep the line (8 lines) for the status application |
| `pixel(x, y)` | `(pixel X Y)`, `(oled:pixel X Y)` | Light one pixel |
| `pixels(*coordinates)` | `(pixels X Y X Y ...)`, `(oled:pixels ...)` | Light pixels, at most 256 pairs, all or nothing |
| `line(x0, y0, x1, y1)` | `(line X0 Y0 X1 Y1)` | Draw a line |
| `text(x, y, *words)` | `(text X Y WORDS ...)`, `(oled:text ...)` | Write the words with the text cell's bottom-left at (X, Y) |
| `exit()` | `(exit)` | Blank the display and terminate |

**Interface `OLEDApplications`**.

| Method | Wire form | Effect |
|--------|-----------|--------|
| `application(name, *args)` | `(application NAME [WORDS ...] [key=value ...])` | Run an application, replacing the running one; `none` shows the canvas |
| `key(name, state="tap")` | `(key NAME [tap\|down\|up])` | A key for the running application |

Drawing on the canvas stops a running application, so that the drawing
is seen; `log` does not, because the status application shows the log
lines itself.  Anything else on the `in` topic — including the
framework's `(run)` — is rejected: the Actor dispatches only the
methods of its Interfaces, plus `(stop)` and `(set_log_level LEVEL)`.

**Shared state** (all values are single tokens).  RW keys are settings:
write them with `(update KEY VALUE)` on the control topic, or edit them
in the Dashboard.  A bad value is rejected and the value in force is
published again, so an observer converges back.

| Key | Values | RW | Meaning |
|-----|--------|----|---------|
| `backend` / `device` | `oled\|window\|terminal\|png\|none\|fake` / `ssd1306@0x3D/i2c1`, `pygame`, `tty`, `png:NAME`, `absent` | R | The display in use; `absent` while it can't be opened |
| `size` / `origin` | `128x64` / `bottom` | R | The panel; the coordinate origin |
| `connection` | `NONE\|NETWORK\|TRANSPORT\|REGISTRAR` | R | The Actor's connection state |
| `applications` | comma-separated names | R | The applications this Actor can run |
| `application` | name or `none` | RW | The running application; writing it starts one (`NAME[,ARG,...]`) |
| `application_detail` | token | R | What the application says it is doing |
| `fps` | frames per second shown, measured | R | |
| `speed` | `0.1`..`10` | RW | Multiplies every application's frame rate |
| `font` | `5x7` or `6`..`64` | RW | The canvas font: the 5x7 bitmap font or a TrueType size |
| `contrast` | `0`..`255` | RW | Panel brightness |
| `invert` / `power` / `all_on` | `on\|off` | RW | Inverse video; display sleep; every pixel lit (a hardware test) |
| `title` | token (`_` shown as a space) or `off` | RW | The inverse-video title row with annunciators and the clock |
| `blank_after` | seconds, `0` = never | RW | Sleep the display after this long without a new frame; any command wakes it |
| `heartbeat` | seconds since start | R | Updated every second: proof the event loop is not blocked |
| `last_error` | `WHAT@UTC` or `-` | R | The last rejection or failure, e.g. `pixel_x_range@2026-09-26T04:21:00Z` |
| `log_count` | count | R | Lines received by `log` |
| `metrics.commands` `.rejected` `.frames` `.frame_ms` `.errors` | counts | R | Accepted and rejected commands, frames shown, the last frame's render time, errors caught in timers; published every 2 s when changed |

## For framework developers (internals)

### Design

    MQTT thread ──on_message──► event queue ──► event-loop thread (main)
                                                 │
       ┌─────────────────────────────────────────┴────────────────────────┐
       │ OLEDImpl                                                          │
       │  _topic_in_handler: parse guard → oled: aliases → allow-list      │
       │  wire methods ─► Canvas (PIL "1" 128x64, wire coordinates)        │
       │  _tick 30 Hz  ─► application.step() → frame                       │
       │  _present(frame): + title row, skip if unchanged ─► Display.show  │
       │  settings ◄── ec_producer change handler ◄── (update K V)         │
       │  _heartbeat 1 s, _metrics_flush 2 s, _reopen 10 s                 │
       └───────────────────────────────────────────────────────────────────┘
                                                 │
                        Display: Ssd1306 (luma) | Window (pygame) | Terminal | Png | Null | Fake

- **One thread.** All Actor state is touched only on the event-loop
  thread.  Rendering is bounded work inside the frame timer (an I2C frame
  is about 25 ms at 400 kHz, measured and published as `metrics.frame_ms`),
  and pygame must be pumped from the main thread, which the event loop is.
  A display worker thread stays a roadmap item, to be added only if
  measurements demand it.
- **Coalescing.** A frame is shown only when its bytes changed, and at
  most once per tick, so a flood of `pixels` commands costs microseconds
  each and one device write.
- **Deny by default (P12).** `_topic_in_handler` replaces the framework's:
  the parser is guarded (a token such as `12:30` raises inside it), the
  `oled:` names are aliased, and only `WIRE_COMMANDS` — the abstract
  methods of the two Interfaces plus `stop` and `set_log_level` — reach
  the mailbox.  Inherited public methods such as `run` are unreachable.
- **Settings through shared state (P3).** The change handler applies a
  written setting through the same setter the Actor uses itself; an
  `_applied` table stops the Actor's own updates from re-entering.
- **Bounds (P9).** Log ring 8 lines (oldest dropped); 256 pixel pairs per
  command; 128 characters of text; 64 characters per application argument;
  5 keys held.
- **Every timer body is guarded.** The framework's event loop does not
  catch exceptions in timer handlers, so `_guarded()` logs, counts
  `metrics.errors`, sets `last_error` and stops the application, and the
  process lives on.
- **Failure behavior.** A display that can't be opened, or that fails, is
  reported (`device` `absent`, `last_error`) and retried every 10 s; the
  Actor keeps working meanwhile.  A rejected command changes nothing but
  `metrics.rejected` and `last_error`.

### Implementation notes

- `Canvas._device_y()` in `graphics.py` is the only place the bottom-left
  wire coordinates meet PIL's top-left rows.  Applications draw PIL frames
  directly.
- `ec_producer.add_handler()` replays the whole share synchronously, so
  the share and every attribute a handler touches are seeded before the
  handler is added.
- Callbacks from other threads (the connection state handler) only
  `_post_message()` to the mailbox.
- The CLI's `run` installs a SIGTERM handler and blanks the display in a
  `finally` block: Ctrl-C, `(exit)`, `aiko_oled exit` and `systemctl stop`
  all leave the panel blank.
- With `-o terminal`, console logging would scribble on the picture:
  `run` sets `AIKO_LOG_MQTT=true` unless it is already set.
- Share values must be single tokens: the framework publishes incremental
  updates unencoded.  `_token()` reduces free text, and never lets a value
  start with digits followed by a colon.

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `OLED` (Interface) | The `oled:0` canvas commands and `exit` | `OLEDImpl` |
| `OLEDApplications` (Interface) | Running applications, keys | `OLEDImpl` |
| `OLEDImpl` | Dispatch guard, validation, the canvas, settings, timers, metrics, display failure and recovery, shutdown | `Canvas`, `Display`, `Application`, `ECProducer`, `aiko.event` |
| `Canvas` | The frame buffer in wire coordinates; text, pixels, lines, scrolling log, title rows | `Font` |
| `Font` | 5x7 bitmap or TrueType glyph rendering, cell metrics | Pillow |
| `Display` and backends | Show a frame; contrast, invert, power, all-on; window events; blank on close | luma.oled, pygame, the terminal, Pillow |
| `Application`, `Host` | A source of frames and what it may use of the Actor | `OLEDImpl` |
| `main` (click) | `run`, and discovery-plus-one-command subcommands with a timeout | `aiko.do_command`, `aiko.do_discovery` |

## Current limitations and roadmap

- Applications: the status display (the main goal), then pattern, text,
  blink, the games, the forklift, drawings and the demo from
  `oled_test.py`, and an `aiko_oled keys` console — the next two phases.
- The 5x7 font gives 21 characters per row; aiko_engine_mp's 8x8 font
  gives 16.  An 8x8 bitmap font for pixel parity is on the roadmap.
- One panel per Actor.  aiko_engine_mp spreads text across two panels.
- `(oled:log a   b)` collapses runs of spaces, because the framework
  parser tokenises; aiko_engine_mp keeps them.
- `aiko_oled` is a console script only for editable installs, because the
  example directory is not in the wheel.  Promotion into
  `src/aiko_services/main/oled/` would fix that.
- A Dashboard plug-in for the `oled` protocol, and convergence with
  aiko_engine_mp (which could register protocol `oled:0` and accept both
  `text` and `oled:text`), are stretch goals.

## Related concepts

- [Actor](../../concepts/actor.md), [Service](../../concepts/service.md)
- [Share](../../concepts/share.md): the shared state and `(update ...)`
- [Discovery](../../concepts/discovery.md): how the CLI finds the Actor
- [Event](../../concepts/event.md): timers on the event-loop thread
- [Dashboard](../../concepts/dashboard.md),
  [Dashboard plug-in](../../concepts/dashboard_plugin.md)
- [oled_protocol](oled_protocol.md): the wire protocol specification
