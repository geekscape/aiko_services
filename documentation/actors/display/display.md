---
title: Display Actor (display.py)
description: An SSD1306 128x64 OLED as a Display Actor (protocol display:0,
  the composite of the Canvas, Screen and Interaction aspects) — a status
  display for headless hosts, a canvas that any client draws on with
  aiko_engine_mp compatible S-expressions, settings declared once and
  edited through the shared state, applets that run on the display, a key
  map on the device, a keys console, and emulated displays for a desktop
type: concept
audience: [developers, end-users]
status: draft
ste: adapted
source:
  - src/aiko_services/actors/display/display.py
  - src/aiko_services/actors/display/outputs.py
  - src/aiko_services/actors/display/cli.py
  - src/aiko_services/actors/display/graphics.py
  - src/aiko_services/actors/display/applets.py
  - src/aiko_services/actors/display/status.py
  - src/aiko_services/actors/display/games.py
  - src/aiko_services/actors/display/drawings.py
  - src/aiko_services/actors/display/faces.py
  - src/aiko_services/actors/display/console.py
  - src/aiko_services/actors/display/keys.py
  - src/aiko_services/actors/display/dashboard_plugin.py
related: [actor, service, share, discovery, event, process, connection,
  dashboard, dashboard_plugin, parameters, stream, display_protocol,
  display_dashboard, design, testing]
version: "0.8-dev"
last_updated: 2026-09-28
---

# Display Actor (display.py)

## Overview

A small OLED on a headless Linux Single Board Computer (SBC) or server
shows the host's own status. The rows give the hostname, the IP address,
the broker and Registrar connections, the clock, the load and the newest
log line. `display.py` makes such a display an Aiko Services
[Actor](../../concepts/actor.md) with protocol `display:0`: the composite
of three aspects, drawing on a *canvas*, controlling the *screen*, and
controlling what runs on the display (*interaction*).

The Actor owns one 128x64 one-bit image, the *canvas*. Remote one-way
commands draw on it: `clear`, `text`, `pixel`, `pixels`, `line` and
`log`. A command can also start an *applet*: a source of frames that the
Actor steps at the applet's frame rate. The status display is the default
applet. Everything else about the display is
[shared state](../../concepts/share.md): the contrast, inverse video,
power, the title row, the font, the speed and the blanking. The Aiko
[Dashboard](../../concepts/dashboard.md), or any client, writes a
setting with `(update KEY VALUE)`.

The wire commands are the ones that the MicroPython
[aiko_engine_mp](https://github.com/geekscape/aiko_engine_mp) OLED
accepts. `(oled:text 0 0 hello)` and `(text 0 0 hello)` are one command,
and the origin is the bottom-left corner on both:

```bash
mosquitto_pub -t $TOPIC_PATH/in -m "(oled:text 0 0 hello)"
```

Without the panel, the same Actor shows its frames in a desktop window
(pygame), in the terminal or in a PNG file. Thus every part of the
Actor runs on a desktop, and the unit tests need no hardware.

The package is in `src/aiko_services/actors/display/`, the actors tier
of the wheel. `examples/oled/` has a small one-file example of the same
protocol, `oled_actor.py`, for a newcomer. It also keeps the original
standalone spike, `oled_test.py`, unchanged, for reference.

**Why to use it**: a headless host tells you at a glance that it is up,
connected and registered, without a monitor or a login. The same panel
is a remote canvas for any Aiko Services client, and the Dashboard
controls it like any other Service.

## For application developers

### Command-line usage

The console script is `aiko_display`, defined in `pyproject.toml` as
`aiko_services.actors.display.cli:main`. The package is in the wheel:

```bash
pip install aiko_services     # or "pip install -e ." for a clone
pip install luma.oled         # the SSD1306 driver (the SBC only)
pip install pygame            # optional: the desktop window emulation
```

The source `ReadMe.md` covers the wiring and the I2C setup. Two options
come before the subcommand, because every subcommand uses them:

| Option | Meaning | Default |
|--------|---------|---------|
| `-n NAME`, `--name` | The Display Actor: the one to run, or the one to command | The local hostname |
| `-t SECONDS`, `--timeout` | How long to wait for the Actor. For `list`, how long to collect the Actors | 5 |

`run` starts the Actor in the foreground. Every other subcommand
discovers the running Actor by name and protocol, sends it one command
and exits. `aiko_display --help` ends with a reference that the code builds
from its own tables: the applets and their options, the settings, the
shared state keys, the wire commands and the console keys with their
preset cycles. Every subcommand's `--help` explains it in full.

| Subcommand | Arguments and options | What it does |
|------------|----------------------|--------------|
| `run` | The table below | Run the Actor |
| `exit` | `--all` | `(exit)`, an alias of the framework's `(stop)`: the Actor terminates and the display blanks. `-n '*'` needs `--all` |
| `list` | | Every `display:0` Actor on the broker, or the one named with `-n`: name, topic path, tags |
| `clear` | | `(clear)` |
| `log WORDS...` | | `(log WORDS ...)` |
| `text X Y WORDS...` | | `(text X Y WORDS ...)`, origin bottom-left |
| `pixels X Y ...` | | `(pixels X Y ...)` |
| `line X0 Y0 X1 Y1` | | `(line X0 Y0 X1 Y1)` |
| `set KEY VALUE` | | `(update KEY VALUE)` on the Actor's control topic, exactly what the Dashboard does. The key is checked locally |
| `applet NAME [ARGS...]` | `-l`, `--list` | `(applet NAME ARGS ...)`. `applet -l` lists the applets and their options without an Actor |
| `stop` | | `(applet none)`: the canvas is shown again |
| `key NAME [tap\|down\|up]` | | `(key NAME STATE)`: a key in the Actor's key map runs its preset, any other key goes to the running applet. `down` holds a key for 2 s at most |
| `keys` | | The interactive console, see below |
| `mirror TOPIC [SECONDS]` | | `(mirror TOPIC SECONDS)`: a leased feed of raw frames to TOPIC, 30 s by default, 0 stops. `mosquitto_sub -t TOPIC` shows the bytes |

The options of `run`:

| Option | Meaning | Default |
|--------|---------|---------|
| `-o`, `--output` | `oled`: the SSD1306 over I2C. `window`: a pygame window, 5x with pixel gaps. The console keys work in it, and `Esc`, `x` or `q` exits the Actor. `terminal`: half-block characters, 128x34 (Braille dots, 64x18, in a smaller terminal). `png`: the newest frame in a file, at most once a second. `none`: no display, the Actor still runs. `auto`: `oled` when `/dev/i2c-N` exists, else `window` on a desktop with pygame, else `terminal` | `auto` |
| `-a`, `--address` | The I2C address: `0x3C`, or `0x3D` with the module's SA0 pin high | `0x3C` |
| `-b`, `--bus` | The I2C bus number | `1` |
| `--applet NAME` | The applet at start. `none` shows the canvas | `status` |
| `-fs`, `--font_size` | The text font: `5x7`, the bitmap font, or a TrueType size 6..64 | `5x7` |
| `--title TEXT\|off` | The title row text, `_` for a space, or `off` | The Actor name |
| `-c 'FG [BG]'`, `--color` | The colors of an emulated display, for example `'yellow navy'`: the settings `foreground` and `background`, which the keys `b` and `B` step through | White on black |
| `--png FILE` | The file for `-o png` | `oled.png` |
| `--standalone` | Run without an MQTT broker. The status display works before, or without, the broker | |
| `--strict` | Exit when the display cannot be opened. Without it, the Actor reports `device` `absent` and retries every 10 s | |

Every remote subcommand gives up with exit status 1 after `-t` seconds
when no Actor answers. The framework's `do_command()` would wait for
ever. A session on a desktop:

```bash
export AIKO_MQTT_HOST=localhost
aiko_registrar &
aiko_display -n oledit run -o png --png /tmp/oled.png --title Aiko_v0.8 &
# Display Actor oledit: aiko/nomad/92920/1/in
mosquitto_pub -t aiko/nomad/92920/1/in -m "(oled:text 0 0 hello)"
aiko_display -n oledit text 0 8 second row
aiko_display -n oledit set contrast 32
aiko_display list
# oledit  aiko/nomad/92920/1  ec=true
aiko_display -n oledit exit
aiko_display -n oledit -t 2 exit
# Timeout after 2 s: no Display Actor named oledit  (exit status 1)
```

On the SBC with the panel, run `aiko_display run -a 0x3C`. Append `&` to
run it in the background, or start it with `aiko_process create`. For a
display that comes up with the host, install `aiko_display.service` from
the source directory with systemd. `systemctl stop` sends SIGTERM, and
the Actor blanks the panel. With `--standalone`, the status display
works without the MQTT broker.

To drive the SBC's Actor from a desktop, point `AIKO_MQTT_HOST` at the
SBC's broker and name the Actor: `aiko_display -n HOSTNAME keys`. The
SBC's broker must listen on every interface. The
[test guide](testing.md) gives the mosquitto configuration and the two
discovery traps.

**The Dashboard page.** `aiko_dashboard -p aiko_services.main.dashboard_plugins
-p aiko_services.actors.display.dashboard_plugin`, then `S` on the Actor.
The page shows a live mirror of the panel through the leased frame feed,
and the shared state with editable settings. It shows the process log,
and it takes the same keys as the console. In a terminal that is not
Unicode aware, the mirror uses plain ASCII. The
[Dashboard page](display_dashboard.md) document describes it.

### The status display

The default applet, `status`, refreshes once a second
(`applet status rate=2` for twice). It has two screens, the host and the
Wi-Fi link, and each screen shows its values as text or as a chart. With
the 5x7 font, the title row shows the Actor's name, three annunciators
and the clock:

| Annunciator | Meaning | Cleared |
|-------------|---------|---------|
| `L` | `(log ...)` lines arrived that no applet has shown yet (shared state `log_pending` `on`) | When the `status` or the `log` applet shows them |
| `M` | Connected to the MQTT broker (connection `TRANSPORT` or better) | When the connection drops |
| `R` | Registered with the Registrar (connection `REGISTRAR`) | When the Registrar goes |

The title row has a fixed layout of 21 columns: 9 for the title, 3 for
the annunciators, a space and 8 for the clock. Below it, every number
keeps a fixed width, so nothing jumps:

```text
▮w3029f1   LMR 14:26:45▮   the title row, inverse video
IP 192.168.0.137
CPU 12% Mem 34%
Dsk 61% R 111k T 1.1k      received and sent, bytes per second: three digits and a unit
Load 0.42 0.38 0.35        the 1, 5 and 15 minute load averages
Temp 45C F 1 1500MHz       where the host has a sensor: the fan's GPIO14 level, 1 or 0
Up 3d04h                   the uptime
Hello from nomad           the newest (log ...) line, last; a new one replaces it
```

The date is not shown, and `applet status date=on` adds it. When the
rows do not all fit, the last row, the log line, is dropped. The time is
shown only when the title row is off. Then the first row is the
name and the connection state, and the time precedes the uptime.
`set title off` gives an applet the whole panel, and `set title on`
brings the row back with its last text.

**The Wi-Fi screen.** `applet status screen=wifi` shows the link of the
strongest wireless interface:

```text
SSID geekscape_n
Ch 132 5GHz BW 80MHz       the channel, the band and the bandwidth
RSSI -37dBm Q 70/70        the signal and the link quality
Tx 867 Rx 780 Mb/s         the bit rates (with NetworkManager: its rate and signal percent)
AP a6:91:b1:75:16:82       the access point
R 4.6k T 950               the interface's traffic, bytes per second
IF wlxc03a55a6afeb         the interface
```

**The charts.** `view=` plots a screen's values over the last 128
refreshes, one column each, the newest at the right. A heading row shows
a sample of each trace, solid or dotted, with its name and current
value. The host screen has `view=cpu_mem` (CPU solid, memory dotted, 0
to 100 percent) and `view=rx_tx` (received solid, sent dotted, scaled to
the largest value shown, which the heading gives). The Wi-Fi screen has
`view=rssi` (-90 to -30 dBm) and `view=rx_tx` for the interface. The
samples are kept while the process runs, so a change of view keeps the
chart. In the console and the window, `s` steps through the screens, and
`S` steps through the views of the screen shown: text, then the charts.

**The readings.** The psutil calls do not block. The signal comes from
`/proc/net/wireless` at every refresh. The fan level comes from
`pinctrl get 14` every 2 seconds, about 3 milliseconds. The Wi-Fi details
come from `iw dev IF link` and `iw dev IF info`, about 6 milliseconds
together, every 10 seconds while the Wi-Fi text screen shows. Without
`iw`, one `nmcli` call gives them, about 50 milliseconds. The tools are
looked for in `/usr/sbin` and `/sbin` as well as the PATH. Without Linux,
`iw` or NetworkManager, or a wireless interface, the rows say so.

The `log` applet shows the last eight `(log ...)` lines, oldest first,
as they arrive, and it clears `L`. The lines are kept whatever applet
runs, so `applet log` shows them after a game. The `help` applet shows
six pages on the display: the console keys, the Dashboard settings and
state, and the wire commands. The pages turn by themselves, with the
arrow keys, or with `h` in the console.

### The keys console

`aiko_display keys` sends every key typed in a terminal to the Actor as
`(key K tap)`, and a status line follows the Actor's shared state. The
key map lives on the Actor: a mapped key runs its preset, or changes its
setting, and the same key again steps to the next preset. Any other key
goes to the running applet. Only `x` and `q` (quit the console) and `X`
(stop the Actor) are the console's own. The emulator window (`-o window`)
and `aiko_display key K` go through the same `key()`, so all three behave
the same. In the window, `Esc`, `x` and `q` exit the Actor, as the
original spike did.

| Key | Presets, in turn |
|-----|------------------|
| `s` | status (the host screen), status screen=wifi |
| `S` | The next view of the status screen shown: text, then its charts. Host: CPU and memory, then received and sent. Wi-Fi: RSSI, then received and sent |
| `l` | log |
| `h`, `?` | help page 1 to 6 |
| `p` | pattern, then in the 5x7, 10 and 16 pixel fonts |
| `t` | text (a screen full of digits), then in the 5x7, 10 and 16 pixel fonts, then `Hello!`, `OLED` and `128x64` in larger fonts |
| `d` | draw, then shade=off, style=hatch, style=stipple, then each subject: bicycle, cat, dog, flower, forklift, house, pine, tree |
| `g` | pong, asteroids, invaders, forklift: the self-playing games |
| `G` | forklift_game: the interactive one |
| `P` | blink, blink rate=8 |
| `D` | demo, demo random=off |
| `C` | clock, clock title=on, clock seconds=off, clock face=digital |
| `e` | eyes, then each emotion: happy, sad, angry, surprised, sleepy, suspicious, curious, loving |
| arrows | `(key left\|right\|up\|down)` for the applet: the forklift game and the help pages |
| `0`..`9` | The speed: `0` fastest (x4), `4` normal, `9` slowest |
| `f`, `F` | The next, or the previous, font size |
| `T`, `i`, `o`, `a` | Title on or off, invert, power, all pixels on |
| `+`, `-` | Contrast up or down by 16 |
| `b` | The next foreground color of an emulated display: white, deepskyblue, yellow, lime, orange, hotpink |
| `B` | The next background color: black, midnightblue, darkslategray, maroon, dimgray, white |
| `c` | Clear the canvas |
| `R` | Reset the settings and the colors, and show the status display |
| `x`, `q`, `X` | Quit the console. `X` then `y` exits the Actor |

A preset with a font of its own sets that font, and the next preset
without one reverts to the base font. `f` and `R` set the base font.

### Public API

**The idea.** A Display Actor registers protocol `display:0`. Clients
draw with `(text X Y ...)`, `(pixels ...)`, `(line ...)`, `(clear)` and
`(log ...)`. They set its appearance with `(update KEY VALUE)`. They
start a mode with `(applet NAME ...)` and send it keys with `(key NAME)`.
The Actor publishes what it is (`size`, `origin`, `depth`, `panels`,
`applets`, `settings`, `keys.*`) and what it does (`applet`,
`applet_detail`, `fps`, `last_error`), so a client adapts without code.
A client of any display, in thirty lines:

```python
import aiko_services as aiko
from aiko_services.actors.display import PROTOCOL, Display

cache = {}

def found(details, display):
    topic_path = details[0]
    aiko.compose_instance(aiko.ECConsumerImpl, aiko.ec_consumer_args(
        aiko.process, 0, cache, f"{topic_path}/control"))
    aiko.event.add_timer_handler(lambda: draw(topic_path, display), 1.0)

def draw(topic_path, display):
    if "size" not in cache:
        return                                   # wait for the first snapshot
    width, height = map(int, cache["size"].split("x"))
    display.clear()
    display.line(0, 0, width - 1, 0)             # a bottom rule, any size
    display.text(0, 8, "hello", cache.get("backend", "?"))
    aiko.process.message.publish(f"{topic_path}/control", "(update contrast 64)")
    display.applet("clock", "face=digital")      # a mode ...
    display.key("right")                         # ... and a key for it
    aiko.process.terminate()

aiko.do_discovery(Display,
    aiko.ServiceFilter("*", "*", PROTOCOL, "*", "*", "*"), found)
aiko.process.run()
```

**The aspects.** The protocol is the composite of three Interfaces, each
with a contract id. Because the Registrar matches one protocol string per
Service, the aspects are advertised as tags: `ec=true device=oled
canvas=0 screen=0 interaction=0`. Every method is one-way, and the
outcome is observed in the shared state. Coordinates: x 0..127 left to
right, y 0..63 bottom to top. The decisions are recorded in
[ADR-025](../../../constitution/adr/ADR-025_RemoteDisplayAbstraction.md).

| Aspect | Contract id | Methods | Owns in the share |
|--------|-------------|---------|-------------------|
| `Canvas` — drawing on a canvas | `.../canvas:0` | `clear()`, `log(*words)`, `pixel(x, y)`, `pixels(*coordinates)`, `line(x0, y0, x1, y1)`, `text(x, y, *words)` | RW `font`, `title`. R `size`, `origin`, `depth`, `log_count`, `log_pending` |
| `Screen` — controlling the screen | `.../screen:0` | `mirror(topic, seconds)` | RW `contrast`, `invert`, `power`, `all_on`, `blank_after`, `foreground`, `background`, `mirror_rate`. R `backend`, `device`, `panels`, `fps`, `mirrors` |
| `Interaction` — what runs on the display | `.../interaction:0` | `applet(name, *args)`, `key(name, state="tap")` | RW `applet`, `speed`. R `applets`, `applet_detail`, `keys.*` |
| `Display` — the composite | `.../display:0`, registered | the framework's `stop` (`exit` is its alias), `set_log_level` | R `settings`, `connection`, `heartbeat`, `last_error`, `metrics.*` |

| Method | Wire form | Effect |
|--------|-----------|--------|
| `clear()` | `(clear)`, `(oled:clear)` | Erase the canvas. The title row stays |
| `log(*words)` | `(log WORDS ...)`, `(oled:log ...)` | Scroll the canvas up one text row and write the words on the bottom row. Keep the line (the last eight) for the status and log applets |
| `pixel(x, y)` | `(pixel X Y)`, `(oled:pixel X Y)` | Light one pixel |
| `pixels(*coordinates)` | `(pixels X Y X Y ...)`, `(oled:pixels ...)` | Light pixels, at most 256 pairs, all or nothing |
| `line(x0, y0, x1, y1)` | `(line X0 Y0 X1 Y1)` | Draw a line |
| `text(x, y, *words)` | `(text X Y WORDS ...)`, `(oled:text ...)` | Write the words with the text cell's bottom-left at (X, Y) |
| `applet(name, *args)` | `(applet NAME [WORDS ...] [key=value ...])` | Run an applet, which replaces the running one. `none` shows the canvas |
| `key(name, state="tap")` | `(key NAME [tap\|down\|up])` | A key in the key map runs its preset, or changes its setting, on `tap` or `down`. Any other key goes to the running applet. `down` holds the key for 2 s at most, so a client that holds a key sends `down` again |
| `mirror(topic, seconds)` | `(mirror TOPIC SECONDS)` | Create or extend a leased feed of the panel's frames to TOPIC, raw bytes on change at most `mirror_rate` a second. 0 destroys it. At most 4 holders |
| `stop()` | `(stop)`, `(exit)` | Terminate the process. The display blanks on the way out |

**The control model.** "Control" means four things, and every client
speaks one vocabulary. The last column names the framework concept each
one follows. Thus the coming extraction of Parameters and Streams from
`pipeline.py` finds the display already in shape. The
[shape document](parameters_streams_shape.md) proposes that extraction.

| Kind | Mechanism | Wire | Confirm | Framework analogue |
|------|-----------|------|---------|--------------------|
| Settings | share updates, one setter each, declared once in `SETTINGS_SPEC` | `(update KEY VALUE)` on `control` | observe the key | [Parameters](../../concepts/parameters.md): declared names with defaults, overridden live through the share |
| Commands | `Canvas` methods | `(text ...)` on `in` | `metrics.commands`, `last_error` | remote method calls |
| Interaction | the applet is the *mode*; keys go to it | `(applet NAME [key=value ...])`, `(key NAME)` | `applet`, `applet_detail` | a [Stream](../../concepts/stream.md) bound to a graph path, with per-Stream parameters |
| Presets | the key map on the device | `(key K tap)` for a mapped key | `applet`, settings | — |

**Applets** (`(applet NAME [WORDS ...] [key=value ...])`):

| Name | Options | What it shows |
|------|---------|---------------|
| `status` | `rate=` updates per second (1), `date=on`, `screen=host\|wifi`, `view=text\|cpu_mem\|rx_tx\|rssi` | The host's status, the default, or the Wi-Fi link, as text or as a chart |
| `log` | | The last eight `(log ...)` lines as they arrive |
| `help` | `page=N`, `hold=` seconds (8) | Help in pages that fit the display: console keys (applets, actions), Dashboard settings and state, wire commands and notes |
| `clock` | `face=analog\|digital`, `title=on\|off`, `seconds=off` | Analog: hour, minute and second hands, the day of the month in a window, the weekday and the month, full screen unless `title=on`. Digital: the title row, then the weekday, the date and the time, each on a row in the largest font that fits, spaced evenly |
| `eyes` | `seed=`, `emotion=neutral\|happy\|sad\|angry\|surprised\|sleepy\|suspicious\|curious\|loving`, `blink=off` | Animated eyes (iris, pupil, lids, brows, smile lines) that look around, blink and show a random range of emotions |
| `pattern` | | The test pattern for a panel: border, ruler ticks, diagonals, a circle, even and odd row blocks, a checkerboard, "centre" |
| `text [WORDS]` | | The words in the center. Without words, a screen full of digits |
| `blink` | `rate=` changes per second (2) | The panel's power off and on: a hardware test |
| `pong`, `asteroids`, `invaders` | `seed=` | Self-playing classics |
| `games` | `duration=` seconds each (20), `seed=` | The three games in turn |
| `forklift` | `duration=` seconds (0: for ever), `seed=` | A forklift moving a pallet between the ground and a racking bay |
| `forklift_game` | `seed=` | The forklift game: `(key left\|right\|up\|down)` drive and lift. Put the pallet where the top line says |
| `draw` | `subject=`, `style=outline\|hatch\|stipple`, `shade=on\|off`, `speed=` seconds per drawing (8), `hold=` (3), `count=` (0: for ever), `seed=` | Pencil-sketched cartoon scenes |
| `demo` | `random=on\|off`, `count=`, `seed=` | A tour of the applets and settings, a few seconds each |

Every applet is deterministic for a given `seed=`. No applet uses a
clock, only frame counts. A drawing command stops a running applet, so
that the drawing is seen. `log` does not stop it, because the status
applet shows the log lines itself. Anything else on the `in` topic is
rejected, including the framework's `(run)`. The Actor dispatches only
the methods of its three aspects, plus `(stop)` and
`(set_log_level LEVEL)`.

**Settings**: the writable shared state, declared once in
`SETTINGS_SPEC` (name, kind, default, range, description). The `settings`
share key, the setters, the rejection reasons, the help texts and the
tests all derive from that table. Write a setting with `aiko_display set`,
with `(update KEY VALUE)` on the control topic, or in the Dashboard. A
bad value is rejected, and the value in force is published again, so an
observer converges back. All values are single tokens.

| Key | Values | Meaning |
|-----|--------|---------|
| `applet` | `NAME[,ARG,...]` or `none` | The running applet. Writing it starts one, and `none` shows the canvas |
| `contrast` | `0`..`255` | The panel brightness |
| `invert` | `on`, `off` | Inverse video |
| `power` | `on`, `off` | Display sleep when `off` |
| `all_on` | `on`, `off` | Every pixel lit: a hardware test |
| `title` | text (`_` shown as a space), `on` or `off` | The inverse-video title row: the text, the annunciators and the clock (hh:mm:ss). `off` hides it, so the canvas and the applets have the whole panel. `on` shows it again with the last text. The default is the Actor name |
| `font` | `5x7` or `6`..`64` | The canvas font: the 5x7 bitmap font or a TrueType size |
| `speed` | `0.1`..`10` | Multiplies every applet's frame rate |
| `blank_after` | seconds, `0` = never | Sleep the display after this long without a new frame. Any command wakes it |
| `mirror_rate` | `1`..`10` | Frames a second to each mirror holder, at most |
| `foreground`, `background` | A color name, `#rrggbb`, or `default` | The colors of lit and unlit pixels on an emulated display. The OLED's color is fixed, but the value is kept. `default` is the color from `-c`, or white on black |

**Observations**: the read-only shared state.

| Key | Values | Meaning |
|-----|--------|---------|
| `backend`, `device`, `panels` | `oled\|window\|terminal\|png\|none\|fake` and `ssd1306@0x3C/i2c1`, `pygame`, `tty`, `png:NAME` or `absent` | The display in use. `absent` while it cannot be opened. `panels` lists every panel from Epic 1 phase 4 |
| `size`, `origin`, `depth` | `128x64`, `bottom`, `1` | The panel, the coordinate origin, the bits per pixel |
| `settings` | comma-separated names | The writable keys, from `SETTINGS_SPEC` |
| `keys.KEY` | `pong\|asteroids\|invaders\|forklift`, `speed`, `title` ... | The key map: the applets a key steps through, or the setting it changes |
| `mirrors` | count | The holders of the frame feed, at most 4 |
| `connection` | `NONE\|NETWORK\|TRANSPORT\|REGISTRAR` | The Actor's [connection](../../concepts/connection.md) state |
| `applets` | comma-separated names | The applets this Actor can run |
| `applet_detail` | token or `-` | What the applet says it is doing, for example `to_bay_2` |
| `fps` | frames per second | The frame rate shown, measured |
| `log_pending` | `on`, `off` | The `L` annunciator: log lines arrived that no applet has shown yet |
| `log_count` | count | The lines received by `log`. The last eight are kept |
| `heartbeat` | seconds since start | Updated every second: the proof that the event loop is not blocked |
| `last_error` | `WHAT@UTC` or `-` | The last rejection or failure, for example `pixel_x_range@2026-09-26T04:21:00Z` |
| `metrics.commands`, `.rejected`, `.frames`, `.frame_ms`, `.errors`, `.mirrored` | counts | Accepted and rejected commands, frames shown, the last frame's render time, errors caught in timers, frames mirrored. Published every 2 s when changed |

The [protocol](display_protocol.md) document gives the grammar of every
value and the rejection reasons.

## For framework developers (internals)

### Design

```text
MQTT thread ──on_message──► event queue ──► event-loop thread (main)
                                             │
   ┌─────────────────────────────────────────┴────────────────────────┐
   │ DisplayImpl                                                       │
   │  _topic_in_handler: parse guard → oled: aliases → allow-list      │
   │  wire methods ─► FrameBuffer (PIL "1", canvas size, wire coords)  │
   │  _tick 30 Hz  ─► applet.step() → frame (centered if smaller)      │
   │  _present(frame): + title row, skip if unchanged ─► Output.show   │
   │  settings ◄── ec_producer change handler ◄── (update K V)         │
   │  _heartbeat 1 s, _metrics_flush 2 s, _reopen 10 s                 │
   └───────────────────────────────────────────────────────────────────┘
                                             │
      Output + OutputControls: Ssd1306 (luma) | Window (pygame) | Terminal | Png | Null | Fake
```

- **One thread.** All Actor state is touched only on the event-loop
  thread. Rendering is bounded work inside the frame timer. An I2C frame
  takes about 25 ms at 400 kHz, measured and published as
  `metrics.frame_ms`. The pygame window must be pumped from the main
  thread, which the event loop is. A display worker thread stays a roadmap item, to be
  added only if measurements demand it.
- **The output seam is composed (ADR-022).** Where frames go is two
  Interfaces in `outputs.py`: `Output` (open, show, close, pump,
  add_handler, message) and `OutputControls` (contrast, invert, power,
  all_on, set_colors). One Impl serves each backend, and `NullOutputImpl`
  is the default Impl of both. Thus a backend that lacks a method gets a
  no-op. `choose_output()` composes the one that `-o` names, and the
  Actor receives it as the parameter `output`. The window's events reach
  the Actor through `pump()` and a handler, on the event-loop thread. An
  `Appearance` value type emulates the panel's settings for the window,
  the terminal, the PNG file and the Dashboard mirror.
- **Applets are portable.** An applet draws frames of its Host's size
  (`host.width`, `host.height`, `host.depth`) and cuts text rows at
  `host.columns()`. The games and the drawings are composed for a fixed
  128x64 field, and they declare `MIN_SIZE`. On a wider canvas the Actor
  centers the field. On a smaller canvas `applet` is rejected with
  `applet_too_small`, and `applets` lists only the applets that fit.
  Every Host call takes and returns S-expression values (tokens,
  integers, words). Thus a sandboxed evaluator could expose the same
  surface to applets written in LISP. That is a direction, not Epic 1
  work.
- **Coalescing.** A frame is shown only when its bytes changed, and at
  most once per tick. Thus a flood of `pixels` commands costs
  microseconds each and one device write.
- **Deny by default (P12).** `_topic_in_handler` replaces the
  framework's. The parser is guarded, because a token such as `12:30`
  raises inside it. The `oled:` names and `exit` are aliased. Only
  `WIRE_COMMANDS` reach the mailbox: the abstract methods of the three
  aspects, plus `stop` and `set_log_level`. Inherited public methods
  such as `run` are unreachable.
- **The key map on the device.** `key()` runs a mapped key's preset, or
  changes its setting, and passes any other key to the running applet.
  Thus the console, the emulator window, `aiko_display key` and the
  Dashboard plug-in send the same `(key K tap)`. The legend `keys.*` in
  the share lets a client of a foreign display build its own.
- **Settings through shared state (P3).** The change handler applies a
  written setting through the same setter the Actor uses itself. An
  `_applied` table stops the Actor's own updates from re-entering.
- **Bounds (P9).** The log ring keeps 8 lines, and the oldest is
  dropped. One command lights at most 256 pixel pairs. A text or log
  line has at most 128 characters, a title 32, an applet argument 64.
  At most 5 keys are held. A `down` holds a key for 2 s at most
  (`KEY_DOWN_MAXIMUM`). Thus a lost `up` cannot hold a key for ever.
- **Every timer body is guarded.** The framework's event loop does not
  catch exceptions in timer handlers. `_guarded()` logs the exception,
  counts `metrics.errors`, sets `last_error` and stops the applet, and
  the process lives on.
- **Failure behavior.** A display that cannot be opened, or that fails,
  is reported (`device` `absent`, `last_error`) and retried every 10 s.
  The Actor keeps working meanwhile. A rejected command changes nothing
  but `metrics.rejected` and `last_error`.

### Implementation notes

- `FrameBuffer._device_y()` in `graphics.py` is the only place where the
  bottom-left wire coordinates meet PIL's top-left rows. Applets draw
  PIL frames directly.
- `ec_producer.add_handler()` replays the whole share synchronously.
  Thus the share, and every attribute a handler touches, are seeded
  before the handler is added.
- A callback from another thread, such as the connection state handler,
  only posts a message to the mailbox.
- The CLI's `run` installs a SIGTERM handler and blanks the display in a
  `finally` block. Ctrl-C, `(exit)`, `aiko_display exit` and
  `systemctl stop` all leave the panel blank.
- With `-o terminal`, console logging would scribble on the picture.
  `run` sets `AIKO_LOG_MQTT=true` unless it is already set.
- Share values must be single tokens, because the framework publishes
  incremental updates unencoded. `_token()` reduces free text, and it
  never lets a value start with digits followed by a colon.
- A key typed in the emulator window reaches `_step()` as a display
  event and goes through `key()` like a key from the wire. The map reads
  the shared state to decide, for example `applet_detail` for `S`. The
  window's own exit keys, `x`, `q` and `X`, call `stop()`. The window
  sends `down` again each second for an arrow that is still held.
- `--applet` takes the applet's options after commas, as the `applet`
  share key does: `--applet status,screen=wifi`.
- The remote-X trap: a pygame window over `ssh -Y` fails with a GLX
  error. `WindowOutputImpl` sets `SDL_VIDEO_X11_FORCE_EGL=1` when the X
  display is remote.

### CRC card

| Class | Responsibilities | Collaborators |
|-------|------------------|---------------|
| `Canvas`, `Screen`, `Interaction` (aspect Interfaces), `Display` (the composite, protocol `display:0`) | The wire contract: drawing, the screen's settings, what runs on the display | `DisplayImpl` |
| `DisplayImpl` | The dispatch guard, validation, the canvas, the settings from `SETTINGS_SPEC`, the key map, timers, metrics, output failure and recovery, applet fit and centering, shutdown | `FrameBuffer`, `Output`, `OutputControls`, `Applet`, `keys.py`, `ECProducer`, `aiko.event` |
| `FrameBuffer` (graphics.py) | The frame buffer in wire coordinates: text, pixels, lines, the scrolling log, the title rows | `Font` |
| `Font` | 5x7 bitmap or TrueType glyph rendering, cell metrics | Pillow |
| `Output`, `OutputControls` (outputs.py) and the Impls `Ssd1306OutputImpl`, `WindowOutputImpl`, `TerminalOutputImpl`, `PngOutputImpl`, `NullOutputImpl` (the default), `FakeOutputImpl` | Show a frame. Contrast, invert, power, all-on, colors. Window events through `pump()`. Blank on close | luma.oled, pygame, the terminal, Pillow, `Appearance` |
| `Appearance`, `text_lines()`, `ascii_lines()` (outputs.py) | The emulated panel: power, all-on, invert and contrast applied to a frame, the colors, the frame as half blocks or Braille, or as plain ASCII | Pillow, the Dashboard page |
| `Applet`, `Host` | A source of frames of the Host's size, or of a fixed `MIN_SIZE` field. What an applet may use of the Actor: geometry, font, settings, log lines, keys | `DisplayImpl` |
| `status.py`: `StatusApplet`, `HISTORY`, the readers | The host and Wi-Fi screens, their text rows and charts, the sample history; the fan, signal and link readers | `Host`, psutil, `pinctrl`, `iw`, `nmcli` |
| `LogApplet`, `HelpApplet`, `PatternApplet`, `TextApplet`, `BlinkApplet`, `DemoApplet` | The built-in applets. The demo runs the others in turn and restores the settings it changed | `Host`, `APPLETS` |
| `games.py`: `pong`, `asteroids`, `invaders`, `forklift_work`, `ForkliftGame` | Frame generators on the fixed 128x64 field, and the forklift game's pallet physics, counted in frames | `Host` |
| `drawings.py`: `SUBJECTS`, `scene_strokes`, `sketch_frames`, `DrawApplet` | Cartoon subjects, stroke planning, the pencil sketch as a frame generator | `Host` |
| `faces.py`: `ClockApplet`, `EyesApplet` | The clock face. The eyes' lens shapes, gaze, blinks and eased emotions | `Host` |
| `keys.py`: `PRESETS`, `key_command`, `reset_commands`, `legend` | The key map, run on the Actor by `key()`: what each key does, and the `keys.*` legend | `DisplayImpl` |
| `KeysConsole` (console.py) | Every key typed in a terminal becomes `(key K tap)`. `x`, `q` and `X` are its own. An ECConsumer shows the shared state | `aiko.do_discovery`, `ECConsumerImpl` |
| `main` (cli.py, click) | `run`, and the discovery-plus-one-command subcommands with a timeout | `aiko.do_command`, `aiko.do_discovery` |

## Current limitations and roadmap

**Implemented.** Epic 0 (complete 2026-09-26): everything above but the
aspects. Epic 1 (2026-09-27 and 2026-09-28) added:

- the `display:0` composite of three aspects, with their tags (phase 1)
- the settings declared once in `SETTINGS_SPEC`, the key map on the
  device, and the parity tests (phase 1)
- the leased frame mirror and the [Dashboard page](display_dashboard.md)
  (phase 2)
- the composed output seam and the portable applets (phase 3)
- the move to the actors tier, `actors/display/`, and the
  `aiko_display` command (phase 9)
- the ASCII mirror, the mirror switch, the arrow hold, the limit on
  `down` and the terminal tests (phase 10)
- the [Parameters and Streams shape](parameters_streams_shape.md) and
  the [design record](design.md) (phase 13)
- the simple example `examples/oled/oled_actor.py` (phase 14)

The 142 display tests and the 4 example tests run on Python 3.12
(macOS) and 3.13 (the SBC). They need no broker and no panel.

**Sharp edges in the implemented code:**

- The status readings run on the event-loop thread. The psutil calls
  take well under 5 ms. The `pinctrl` reading takes about 3 ms every
  2 s. The `iw` reading takes about 6 ms every 10 s while the Wi-Fi text
  screen shows, and `nmcli` about 50 ms. If a host proves slow, move
  them to a worker that posts the readings to the mailbox.
- The fan level, the signal and the Wi-Fi details are Linux readings, and
  the details need `iw` or NetworkManager. Elsewhere the rows say so.
- The 5x7 font gives 21 characters per row. The aiko_engine_mp 8x8 font
  gives 16.
- One panel per Actor. aiko_engine_mp spreads text across two panels.
- `(oled:log a   b)` collapses runs of spaces, because the framework
  parser tokenizes. aiko_engine_mp keeps them.
- A mapped letter cannot reach a running applet, because the key map
  runs first. Games use the arrow keys, which are never mapped.
- A client that holds a key must send `down` again within 2 s. The
  Dashboard page and the window do this. A client written before
  2026-09-28 that sends one `down` and waits sees the key released
  after 2 s.

**Only when the lead says "Do it":**

- Phase 4: one Actor for both panels as one 256x64 display
  (`-a 0x3C,0x3D`), text flowing across as on the firmware.
- Phase 8: the flood measurement, which decides whether a worker thread
  is necessary, and the review pack.

**Deferred:** the 8x8 font (phase 5) and the extras (phase 7) to Epic 2
or 3. The `logs` applet and the services screen (phase 6) wait for the
Recorder roadmap.

**Candidates for later Epics:** aiko_engine_mp registers `display:0` and
passes the Canvas conformance trace (Epic 2). Events on the `out` topic
(Epic 3). The [design record](design.md) gives all the directions.

## Related concepts

- [Actor](../../concepts/actor.md), [Service](../../concepts/service.md)
  — the Actor and its protocol
- [Share](../../concepts/share.md) — the shared state and
  `(update ...)`
- [Discovery](../../concepts/discovery.md) — how the CLI finds the
  Actor
- [Event](../../concepts/event.md) — timers on the event-loop thread
- [Process](../../concepts/process.md) — `aiko.process.run()` with or
  without a broker, and `terminate()`
- [Connection](../../concepts/connection.md) — the `M` and `R`
  annunciators
- [Dashboard](../../concepts/dashboard.md),
  [Dashboard plug-in](../../concepts/dashboard_plugin.md) — editing the
  settings, and the plug-in page
- [S-expression parser](../../concepts/utilities/parser.md) — the wire
  format and its quoting rules
- [Parameters](../../concepts/parameters.md), [Stream](../../concepts/stream.md)
  — the shapes the settings and the mirror follow
- [ADR-025](../../../constitution/adr/ADR-025_RemoteDisplayAbstraction.md)
  — the decisions behind the abstraction
- [display_protocol](display_protocol.md) — the wire protocol specification
- [display_dashboard](display_dashboard.md) — the Dashboard page
- [design](design.md) — the design record and the future directions
- [parameters_streams_shape](parameters_streams_shape.md) — the proposed
  Parameters and Streams aspects
- [testing](testing.md) — the step-by-step test guide
