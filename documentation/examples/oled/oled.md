---
title: OLED display Actor (oled.py)
description: An SSD1306 128x64 OLED as an Aiko Services Actor — a status
  display for headless hosts, a canvas that any client draws on with
  aiko_engine_mp compatible S-expressions, settings that the Dashboard
  reads and writes, applets that run on the display, and emulated
  displays for a desktop
type: concept
audience: [developers, end-users]
status: draft
ste: false
source:
  - src/aiko_services/examples/oled/oled.py
  - src/aiko_services/examples/oled/display.py
  - src/aiko_services/examples/oled/graphics.py
  - src/aiko_services/examples/oled/applets.py
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
*applet*: a source of frames that the Actor steps at the
applet's frame rate.  Everything else about the display — contrast,
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
in the wheel, so it needs `pip install -e .`).  Two options come before
the subcommand: `-n NAME` names the Actor, the one to run or the one to
command (default: the local hostname), and `-t SECONDS` is how long to
wait for it (default 5; for `list`, how long to collect).  `run` starts
the Actor in the foreground; every other subcommand discovers the running
Actor by name and protocol and sends it one command.  `aiko_oled --help`
ends with a reference made from the code's own tables — the applets and
their options, the settings, the shared state keys, the wire commands and
the console keys with their preset cycles — and every subcommand's
`--help` explains it in full.

| Subcommand | Arguments and options | What it does |
|------------|----------------------|--------------|
| `run` | `-o auto\|oled\|window\|terminal\|png\|none`, `-a 0x3C`, `-b 1`, `--applet NAME`, `-fs 5x7\|6..64`, `--title TEXT\|off`, `-c 'FG [BG]'`, `--png FILE`, `--standalone`, `--strict` | Run the Actor.  `auto` picks the OLED when `/dev/i2c-N` exists, else a window when there is a desktop and pygame, else the terminal.  `--standalone` runs without a broker.  `--strict` exits when the display can't be opened, instead of retrying every 10 s |
| `exit` | `--all` | `(exit)`: blank the display and terminate.  `-n '*'` needs `--all` |
| `list` | | Every `oled:0` Actor on the broker (or the one named with `-n`): name, topic path, tags |
| `clear` | | `(clear)` |
| `log WORDS...` | | `(log WORDS ...)` |
| `text X Y WORDS...` | | `(text X Y WORDS ...)`, origin bottom-left |
| `pixels X Y ...` | | `(pixels X Y ...)` |
| `line X0 Y0 X1 Y1` | | `(line X0 Y0 X1 Y1)` |
| `set KEY VALUE` | | `(update KEY VALUE)` on the Actor's control topic, exactly what the Dashboard does |
| `applet NAME [ARGS...]` | `-l` | `(applet NAME ARGS ...)`; `stop` is `(applet none)`; `applet -l` lists the applets and their options without an Actor |
| `key NAME [tap\|down\|up]` | | `(key NAME STATE)` for the running applet |
| `keys` | | Interactive console: letters switch applets and the same letter again steps through the presets (`g`: pong, asteroids, invaders, all in turn; `p`, `t`, `s`: the fonts; `t`: messages; `d`: styles and subjects; `e`: emotions; `h`: the help pages), arrows send keys, digits set the speed, `f` `T` `i` `o` `a` `+` `-` change settings, `R` resets, `x` quits, `X` exits the Actor; a status line follows the shared state |

Every remote subcommand gives up with exit status 1 after `-t` seconds
when no Actor answers (the framework's `do_command()` would wait for
ever).  A session on the desktop:

    $ export AIKO_MQTT_HOST=localhost
    $ aiko_registrar &
    $ aiko_oled -n oledit run -o png --png /tmp/oled.png --title Aiko_v0.8 &
    OLED Actor oledit: aiko/nomad/92920/1/in
    $ mosquitto_pub -t aiko/nomad/92920/1/in -m "(oled:text 0 0 hello)"
    $ aiko_oled -n oledit text 0 8 second row
    $ aiko_oled -n oledit set contrast 32
    $ aiko_oled list
    oledit  aiko/nomad/92920/1  ec=true
    $ aiko_oled -n oledit exit
    $ aiko_oled -n oledit -t 2 exit
    Timeout after 2 s: no OLED Actor named oledit
    $ echo $?
    1

On the SBC with the OLED: `aiko_oled run -a 0x3C`.  Append `&` to run it in
the background, or start it with `aiko_process create`.  For a display
that comes up with the host, install `aiko_oled.service` (in the source
directory) with systemd: `systemctl stop` sends SIGTERM and the Actor
blanks the panel.  With `--standalone` the status display works before,
or without, the MQTT broker.

**The status display.**  The default applet, `status`, refreshes
once a second (`applet status rate=2` for twice).  With the 5x7 font
the title row shows the Actor's name, three annunciators and the clock:

| Annunciator | Meaning | Cleared |
|---|---|---|
| `L` | `(log ...)` lines arrived that no applet has shown yet (`log_pending on`) | When the `status` or `log` applet shows them |
| `M` | Connected to the MQTT broker (connection `TRANSPORT` or better) | When the connection drops |
| `R` | Registered with the Registrar (connection `REGISTRAR`) | When the Registrar goes |

Below the title row, the status rows keep every number a fixed width, so
nothing jumps:

    ▮w3029f1   LMR 14:26:45▮
    IP 192.168.0.137
    Up 3d04h
    CPU 12.3% Mem 34.5%
    Disk 61.2% Load 0.42
    Rx 111k Tx 1.1k           bytes per second: three digits and a unit
    Temp 45.1C 1500MHz        only where the host has a sensor (an SBC does)
    Hello from nomad          the newest (log ...) line; a new one replaces it

The date is not shown (`applet status date=on` adds it) and the time only
when the title row is off: then the first line is the name and the
connection state, and the time precedes the uptime.  `set title off` gives
an applet the whole panel; `set title on` brings the row back.

The `log` applet shows the last eight `(log ...)` lines, oldest first, as
they arrive, and clears `L`; the lines are kept whatever applet runs, so
`applet log` shows them after a game.  `help` lists the wire commands on
the display; `aiko_oled applet --list` lists the applets and their options.

### Public API

**Interface `OLED`** (`aiko.Actor`, protocol
`github.com/geekscape/aiko_services/protocol/oled:0`).  Every method is
one-way; outcomes are observed in the shared state.  Coordinates: x
0..127 left to right, y 0..63 bottom to top.

| Method | Wire form | Effect |
|--------|-----------|--------|
| `clear()` | `(clear)`, `(oled:clear)` | Erase the canvas; the title row stays |
| `log(*words)` | `(log WORDS ...)`, `(oled:log ...)` | Scroll the canvas up one text row, write the words on the bottom row; keep the line (8 lines) for the status applet |
| `pixel(x, y)` | `(pixel X Y)`, `(oled:pixel X Y)` | Light one pixel |
| `pixels(*coordinates)` | `(pixels X Y X Y ...)`, `(oled:pixels ...)` | Light pixels, at most 256 pairs, all or nothing |
| `line(x0, y0, x1, y1)` | `(line X0 Y0 X1 Y1)` | Draw a line |
| `text(x, y, *words)` | `(text X Y WORDS ...)`, `(oled:text ...)` | Write the words with the text cell's bottom-left at (X, Y) |
| `exit()` | `(exit)` | Blank the display and terminate |

**Interface `OLEDApplets`**.

| Method | Wire form | Effect |
|--------|-----------|--------|
| `applet(name, *args)` | `(applet NAME [WORDS ...] [key=value ...])` | Run an applet, replacing the running one; `none` shows the canvas |
| `key(name, state="tap")` | `(key NAME [tap\|down\|up])` | A key for the running applet |

**Applets** (`(applet NAME [WORDS ...] [key=value ...])`):

| Name | Options | What it shows |
|------|---------|---------------|
| `status` | `rate=` updates per second (1), `date=on` | The host's status; the default |
| `log` | | The last eight `(log ...)` lines as they arrive |
| `help` | `page=N`, `hold=` seconds (8) | Help in pages that fit the display: console keys (applets, actions), Dashboard settings and state, LISP commands and notes; the pages turn by themselves, with the arrow keys, or with `h` in the console |
| `clock` | `title=on`, `seconds=off` | An analog clock face: hour, minute and second hands, the day of the month in a window, weekday and month |
| `eyes` | `seed=`, `emotion=neutral\|happy\|sad\|angry\|surprised\|sleepy\|suspicious\|curious\|loving`, `blink=off` | Animated eyes (iris, pupil, lids, brows, smile lines) that look around, blink and show a random range of emotions |
| `pattern` | | The test pattern for a panel: border, ruler ticks, diagonals, a circle, even and odd row blocks, a checkerboard, "centre" |
| `text [WORDS]` | | The words centred; without words a screen full of digits |
| `blink` | `rate=` changes per second (2) | The panel's power off and on: a hardware test |
| `pong`, `asteroids`, `invaders` | `seed=` | Self-playing classics |
| `games` | `duration=` seconds each (20), `seed=` | The three games in turn |
| `forklift` | `duration=` seconds (0: for ever), `seed=` | A forklift moving a pallet between the ground and a racking bay |
| `forklift_game` | `seed=` | The forklift game: `(key left\|right\|up\|down)` drive and lift; put the pallet where the top line says |
| `draw` | `subject=`, `style=outline\|hatch\|stipple`, `shade=on\|off`, `speed=` seconds per drawing (8), `hold=` (3), `count=` (0: for ever), `seed=` | Pencil-sketched cartoon scenes |
| `demo` | `random=on\|off`, `count=`, `seed=` | A tour of the applets and settings, a few seconds each |

Every applet is deterministic for a given `seed=`: no applet
uses a clock, only frame counts.  Drawing on the canvas stops a running
applet, so that the drawing is seen; `log` does not, because the
status applet shows the log lines itself.  Anything else on the `in` topic — including the
framework's `(run)` — is rejected: the Actor dispatches only the
methods of its Interfaces, plus `(stop)` and `(set_log_level LEVEL)`.

**Shared state** (all values are single tokens).  RW keys are settings:
write them with `(update KEY VALUE)` on the control topic, or edit them
in the Dashboard.  A bad value is rejected and the value in force is
published again, so an observer converges back.

| Key | Values | RW | Meaning |
|-----|--------|----|---------|
| `backend` / `device` | `oled\|window\|terminal\|png\|none\|fake` / `ssd1306@0x3C/i2c1`, `pygame`, `tty`, `png:NAME`, `absent` | R | The display in use; `absent` while it can't be opened |
| `size` / `origin` | `128x64` / `bottom` | R | The panel; the coordinate origin |
| `connection` | `NONE\|NETWORK\|TRANSPORT\|REGISTRAR` | R | The Actor's connection state |
| `applets` | comma-separated names | R | The applets this Actor can run |
| `applet` | name or `none` | RW | The running applet; writing it starts one (`NAME[,ARG,...]`) |
| `applet_detail` | token | R | What the applet says it is doing |
| `fps` | frames per second shown, measured | R | |
| `speed` | `0.1`..`10` | RW | Multiplies every applet's frame rate |
| `font` | `5x7` or `6`..`64` | RW | The canvas font: the 5x7 bitmap font or a TrueType size |
| `contrast` | `0`..`255` | RW | Panel brightness |
| `invert` / `power` / `all_on` | `on\|off` | RW | Inverse video; display sleep; every pixel lit (a hardware test) |
| `title` | text (`_` shown as a space), `off` or `on`; default: the Actor name | RW | The inverse-video title row: the text, the annunciators and the clock (hh:mm:ss).  `off` hides it, so the canvas and applets have the whole panel; `on` shows it again with the last text |
| `log_pending` | `on\|off` | R | The `L` annunciator: `(log ...)` lines arrived that no applet has shown yet |
| `blank_after` | seconds, `0` = never | RW | Sleep the display after this long without a new frame; any command wakes it |
| `heartbeat` | seconds since start | R | Updated every second: proof the event loop is not blocked |
| `last_error` | `WHAT@UTC` or `-` | R | The last rejection or failure, e.g. `pixel_x_range@2026-09-26T04:21:00Z` |
| `log_count` | count | R | Lines received by `log` (the last eight are kept) |
| `metrics.commands` `.rejected` `.frames` `.frame_ms` `.errors` | counts | R | Accepted and rejected commands, frames shown, the last frame's render time, errors caught in timers; published every 2 s when changed |

## For framework developers (internals)

### Design

    MQTT thread ──on_message──► event queue ──► event-loop thread (main)
                                                 │
       ┌─────────────────────────────────────────┴────────────────────────┐
       │ OLEDImpl                                                          │
       │  _topic_in_handler: parse guard → oled: aliases → allow-list      │
       │  wire methods ─► Canvas (PIL "1" 128x64, wire coordinates)        │
       │  _tick 30 Hz  ─► applet.step() → frame                       │
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
  command; 128 characters of text; 64 characters per applet argument;
  5 keys held.
- **Every timer body is guarded.** The framework's event loop does not
  catch exceptions in timer handlers, so `_guarded()` logs, counts
  `metrics.errors`, sets `last_error` and stops the applet, and the
  process lives on.
- **Failure behavior.** A display that can't be opened, or that fails, is
  reported (`device` `absent`, `last_error`) and retried every 10 s; the
  Actor keeps working meanwhile.  A rejected command changes nothing but
  `metrics.rejected` and `last_error`.

### Implementation notes

- `Canvas._device_y()` in `graphics.py` is the only place the bottom-left
  wire coordinates meet PIL's top-left rows.  Applets draw PIL frames
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
| `OLEDApplets` (Interface) | Running applets, keys | `OLEDImpl` |
| `OLEDImpl` | Dispatch guard, validation, the canvas, settings, timers, metrics, display failure and recovery, shutdown | `Canvas`, `Display`, `Applet`, `ECProducer`, `aiko.event` |
| `Canvas` | The frame buffer in wire coordinates; text, pixels, lines, scrolling log, title rows | `Font` |
| `Font` | 5x7 bitmap or TrueType glyph rendering, cell metrics | Pillow |
| `Display` and backends | Show a frame; contrast, invert, power, all-on; window events; blank on close | luma.oled, pygame, the terminal, Pillow |
| `Applet`, `Host` | A source of frames and what it may use of the Actor | `OLEDImpl` |
| `StatusApplet`, `PatternApplet`, `TextApplet`, `BlinkApplet`, `HelpApplet`, `DemoApplet` | The built-in applets; the demo runs the others in turn and restores the settings it changed | `Host`, `APPLETS` |
| `games.py`: `pong`, `asteroids`, `invaders`, `forklift_work`, `ForkliftGame` | Frame generators and the forklift game's pallet physics, counted in frames | `Host` |
| `drawings.py`: `SUBJECTS`, `scene_strokes`, `sketch_frames`, `DrawApplet` | Cartoon subjects, stroke planning, the pencil sketch as a frame generator | `Host` |
| `faces.py`: `ClockApplet`, `EyesApplet` | The clock face; the eyes' lens shapes, gaze, blinks and eased emotions | `Host` |
| `KeysConsole` (console.py) | Keys typed in a terminal become wire commands and settings updates; an ECConsumer shows the shared state | `aiko.do_discovery`, `ECConsumerImpl` |
| `main` (click) | `run`, and discovery-plus-one-command subcommands with a timeout | `aiko.do_command`, `aiko.do_discovery` |

## Current limitations and roadmap

- The status sampling (psutil) runs on the event-loop thread: well under
  5 ms on a Linux Single Board Computer (SBC).  If a host proves slow, move it to a worker
  that posts the readings to the mailbox.
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
