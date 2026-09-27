---
title: Display Actor test guide
description: Step-by-step instructions for a technical lead to exercise
  every part of the Display Actor — on macOS with an emulated display and
  on a Linux Single Board Computer (SBC) with the SSD1306 panel — the unit
  tests, the command line and its help, raw S-expressions, the shared
  state, the Aiko Dashboard, the applets, the keys console, the simple
  example, the terminals, failure behavior and systemd
type: guide
audience: [developers]
status: draft
ste: adapted
source:
  - src/aiko_services/actors/display
related: [display, display_protocol, display_dashboard, dashboard, share,
  discovery]
version: "0.8-dev"
last_updated: 2026-09-28
---

# Display Actor test guide

Each step says what to do and what to expect. A step marked **[mac]**
runs on macOS, or any desktop, with an emulated display. A step marked
**[sbc]** runs on the Linux SBC with the panel. A step without a mark
runs on both. Two terminals per host are useful: one for the Actor, one
for the commands. The whole guide takes about an hour.

## 1. What you need

- An MQTT broker (mosquitto) on the host, and `AIKO_MQTT_HOST` pointing
  at it. Every terminal below starts with:

  ```bash
  export AIKO_MQTT_HOST=localhost
  export AIKO_LOG_MQTT=false        # log to the console, not to the broker
  ```

- The repository installed editable in a virtual environment. The
  wheel also has the `aiko_display` command, but the tests and the simple
  example are in the repository:

  ```bash
  cd <repository>
  pip install -e .
  ```

- **[sbc]** The SSD1306 driver: `pip install luma.oled`.
- **[mac]** The window emulation: `pip install pygame` (optional).
- **[sbc]** I2C enabled, and the panel visible: `/usr/sbin/i2cdetect -y 1`
  shows `3c`, the default address, or `3d` when the module's SA0 pin is
  high.

Two deployment traps:

- A stale retained Registrar announcement stops discovery. The symptom
  is "No Display Actors found" although the Actor runs. A Registrar with
  the liveness probe (branch `andyg/registrar-liveness`) replaces the
  stale announcement by itself, in about 5 s. With an older Registrar,
  clear it, then restart the Registrar:

  ```bash
  mosquitto_pub -t aiko/service/registrar -r -n
  ```

- A broker that listens on 127.0.0.1 only, the Debian default, cannot be
  reached from another host. To drive the SBC's Actor from a desktop, let
  its broker listen on every interface. Any host on the LAN can then
  publish, so keep this to a trusted network:

  ```bash
  printf "listener 1883 0.0.0.0\nallow_anonymous true\n" | sudo tee /etc/mosquitto/conf.d/aiko.conf
  sudo systemctl restart mosquitto
  ```

  Then, on the desktop, `export AIKO_MQTT_HOST=SBC_HOSTNAME` and name the
  Actor: `aiko_display list`, then `aiko_display -n SBC_HOSTNAME keys`.

## 2. Unit tests and lint

```bash
pytest src/aiko_services/tests/unit/test_display.py \
       src/aiko_services/tests/unit/test_display_cli.py \
       src/aiko_services/tests/unit/test_display_applets.py \
       src/aiko_services/tests/unit/test_display_dashboard_plugin.py \
       src/aiko_services/tests/unit/test_example_oled.py
flake8 . --select=E9,F63,F7,F82
```

Expect: `140 passed, 6 xfailed`, and no flake8 output. The 6 expected
failures are the `vt100` terminal cases (see step 14). No broker and no
panel are needed. Run them on the SBC too (Python 3.13 there). One test
asserts that `oled_test.py`, the original spike, is never imported.

## 3. The help

```bash
aiko_display --help
aiko_display run --help
aiko_display applet --list
aiko_display keys --help
```

Expect: the group help ends with a reference built from the code's own
tables. It lists the applets, the settings, the shared state keys, the
wire commands and the console keys with their presets. Every subcommand's `--help` explains it in
full. `applet --list` needs no Actor. Nothing is wider than 80 columns.

## 4. Run the Actor

Terminal 1:

```bash
aiko_registrar &
aiko_display run -o terminal                  # [mac] emulated in the terminal
aiko_display run -o window                    # [mac] emulated in a pygame window
aiko_display run -o png --png /tmp/oled.png   # [mac] the newest frame as a PNG
aiko_display run                              # [sbc] the panel at 0x3C (-a 0x3D for SA0 high)
```

Expect: a line `Display Actor NAME: aiko/HOST/PID/1/in`, where NAME is the
hostname. Then the status display: an inverse-video title row with the
name, the annunciators and the clock (hh:mm:ss). The annunciators are
`M` (the broker) and `R` (the Registrar). Below the title row: the IP
address, the uptime, CPU and memory, disk and load, the network traffic,
and the temperature where the host has a sensor. In the terminal, the
picture is drawn with half-block characters (Braille dots in a small
terminal). With `-o png`, open the file after each command below to see
the display.

Note the topic path. The steps below use `$TOPIC` for `aiko/HOST/PID/1`.

## 5. The command line

Terminal 2, on the same host. To command an Actor with another name, or
on another host, put `-n NAME` before the subcommand.

| Step | Command | Expect |
|------|---------|--------|
| 5.1 | `aiko_display list` | `HOST  aiko/HOST/PID/1  ec=true device=oled canvas=0 screen=0 interaction=0`, exit status 0. The tags name the display backend and the three aspects |
| 5.2 | `aiko_display text 0 0 hello world` | The status display stops. `hello world` on the bottom row (origin bottom-left) |
| 5.3 | `aiko_display text 0 8 second row` | One text row above it |
| 5.4 | `aiko_display log Hello from the lead` | The canvas scrolls up one row, and the line is on the bottom row. The title row shows `L` |
| 5.5 | `aiko_display pixels 0 0 127 63` | The bottom-left pixel lights. The top-right pixel lights unless the title row covers it |
| 5.6 | `aiko_display line 0 0 127 63` | A diagonal |
| 5.7 | `aiko_display clear` | Only the title row remains |
| 5.8 | `aiko_display set contrast 32` | Dim. `aiko_display set contrast 255` restores |
| 5.9 | `aiko_display set invert on`, then `off` | Inverse video, and back |
| 5.10 | `aiko_display set power off`, then `on` | The display off (blank), and back |
| 5.11 | `aiko_display set title Aiko_Services` | The title row reads `Aiko Serv`: the title has 9 columns with the 5x7 font. The annunciators and the clock follow |
| 5.12 | `aiko_display set title off`, then `aiko_display set title on` | The row disappears, so the canvas and the applets have the whole panel. Then it returns with the same text |
| 5.13 | `aiko_display applet pong`, then `aiko_display log one`, `aiko_display log two`, then `aiko_display applet log` | Pong keeps running while the lines arrive (no title row over a game). The `log` applet shows both lines and clears `L` |
| 5.14 | `aiko_display set font 12` | Text drawn from now on is larger. `set font 5x7` restores |
| 5.14a **[mac]** | `aiko_display set foreground yellow`, then `aiko_display set background navy` | Lit pixels turn yellow, then the rest turns navy. On the panel nothing changes, but the values are published. `set foreground default` and `set background default` restore the colors from `-c`, or white on black |
| 5.15 | `aiko_display applet status` | The status display again, in the current font: IP, `CPU 12% Mem 34%`, `Dsk 61% R 111k T 1.1k`, `Load 0.42 0.38 0.35`, `Temp 45C F 1 1500MHz` on an SBC, the uptime, then the newest log line last. `aiko_display log again` replaces the log line |
| 5.15a | `aiko_display applet status view=cpu_mem` | A chart: a heading with a solid sample and `CPU 12%`, a dotted sample and `Mem 34%`, then the traces growing from the right, one column a second |
| 5.15b **[sbc]** | `aiko_display applet status screen=wifi` | The Wi-Fi link: `SSID`, `Ch` with the band and bandwidth, `RSSI`, the `Tx` and `Rx` bit rates, `AP`, the traffic and the interface. Then `view=rssi` for its chart |
| 5.16 | `aiko_display applet status date=on` | The date row is added |
| 5.17 | `aiko_display applet pong` | Pong plays itself. `aiko_display set speed 2` doubles the pace, and `set speed 1` restores |
| 5.18 | `aiko_display applet forklift_game`, then `aiko_display key right`, `aiko_display key up` | The forklift drives right a little, and lifts its forks a little, per key. `aiko_display key right down` drives it for 2 s: a `down` holds a key for 2 s at most |
| 5.18a | `aiko_display key g`, then `aiko_display key 5` | The Actor's key map runs the preset: pong starts, then runs at `speed 0.707`. `aiko_display key R` resets and shows the status display |
| 5.18b | `aiko_display mirror aiko/probe/mirror 20`, then `mosquitto_sub -t aiko/probe/mirror -C 3 \| wc -c` | 3072: three frames of 1024 bytes, one for each change of the panel (the clock changes it once a second). `aiko_display mirror aiko/probe/mirror 0` stops the feed, and `mirrors` in the shared state reads `0` |
| 5.19 | `aiko_display stop` | The canvas from 5.7 is shown again |
| 5.20 | `aiko_display set bogus 1` | A usage error, exit status 2. The key is checked locally |
| 5.21 | `aiko_display exit` | The display blanks, the Actor process ends, exit status 0. On the wire `(exit)` is an alias of `(stop)` |
| 5.22 | `aiko_display -t 2 exit`, with nothing running | `Timeout after 2 s: no Display Actor named HOST`, exit status 1 |

Start the Actor again (step 4) before you continue.

## 6. Raw S-expressions (what an aiko_engine_mp client sends)

```bash
mosquitto_pub -t $TOPIC/in -m "(oled:text 0 0 hello)"        # the bottom row
mosquitto_pub -t $TOPIC/in -m "(oled:log This is a test !)"  # scrolls, the bottom row
mosquitto_pub -t $TOPIC/in -m "(oled:pixels 0 0 127 63)"     # two corners
mosquitto_pub -t $TOPIC/in -m "(text 0 16 native form)"      # the same command, no prefix
mosquitto_pub -t $TOPIC/in -m '(text 0 24 "quoted text is one word")'
mosquitto_pub -t $TOPIC/in -m "(key g tap)"                    # the key map: pong
```

Expect: the same effects as the `aiko_display` commands. Now the
rejections:

```bash
mosquitto_pub -t $TOPIC/in -m "(run)"                # not a wire command
mosquitto_pub -t $TOPIC/in -m "(pixel 200 0)"        # out of range
mosquitto_pub -t $TOPIC/in -m "(log 12:30 lunch)"    # unquoted digits and a colon
mosquitto_pub -t $TOPIC/in -m '(log "12:30" lunch)'  # quoted: accepted
```

Expect: the first three change nothing on the display. The Actor's
console logs a WARNING for each: `dispatch rejected: unknown_command
(run)`, `pixel rejected: x_range` and `dispatch rejected: parse_error
(...)`. The process keeps running. The fourth writes `12:30 lunch`.

Settings, the way the Dashboard writes them:

```bash
mosquitto_pub -t $TOPIC/control -m "(update contrast 64)"
mosquitto_pub -t $TOPIC/control -m "(update contrast abc)"   # rejected, converges back to 64
mosquitto_pub -t $TOPIC/control -m "(update applet invaders)"
mosquitto_pub -t $TOPIC/control -m "(update applet draw,subject=cat)"
```

## 7. The shared state

The Actor publishes its state to the consumers that hold a lease. Watch
it with a lease of ten seconds:

```bash
mosquitto_sub -v -t aiko/probe &
mosquitto_pub -t $TOPIC/control -m "(share aiko/probe 10 *)"
```

Expect: a snapshot `(add KEY VALUE)` of every key in the table of
[display_protocol](display_protocol.md). For example `backend oled`,
`device ssd1306@0x3C/i2c1` on the SBC, `connection REGISTRAR`,
`applet draw`, `contrast 64`, `heartbeat N`,
`last_error set_contrast_not_int@...`, `log_pending off`,
`settings applet,contrast,...`, `keys.g pong|asteroids|invaders|forklift`
and `metrics.frames N`. Then `(update heartbeat N)` once a second, and
`(update metrics.* N)` every two seconds while something changes, for
ten seconds. Every value is one token: no spaces.

## 8. The Aiko Dashboard

```bash
aiko_dashboard
```

The Dashboard's own pages first, then the display page (step 6 on).

1. The Services list shows the Display Actor: protocol `.../display:0`,
   tags `ec=true device=... canvas=0 screen=0 interaction=0`. Move to its row with the arrow keys, and press `s` to
   select it. Expect: the Variables section fills with the shared state
   (`applet`, `contrast`, `heartbeat` counting, `metrics.*` and more).
2. Press `Tab` to move to the Variables section. Move to `contrast`,
   press `Enter`, type `16` and confirm. Expect: the display dims, and
   the variable shows `16`.
3. Do the same for `invert` → `on` (inverse video), `applet` → `pong`
   (the game starts), `font` → `10`, `title` → `Hello_lead` (underscores
   are spaces on the display), and `speed` → `2`.
4. Enter a bad value, for example `contrast` → `abc`. Expect: the value
   returns to what it was, and `last_error` shows
   `set_contrast_not_int@...`.
5. `?` shows the Dashboard's help. `l` changes the Actor's log level.
   `x` exits the Dashboard.
6. Start the Dashboard with the display page, in a terminal of at least
   132x48 for the half-block mirror (80x24 gives the Braille mirror):

   ```bash
   aiko_dashboard -p aiko_services.main.dashboard_plugins -p aiko_services.actors.display.dashboard_plugin
   ```

   Select the Actor and press `S`. Expect: the mirror shows the status
   display within a second, and the service bar reads `mirror 5 Hz  fps
   N`. The state table lists every key, the legend names the keys, and
   the log pane shows the Actor's lines.
7. Press `g`: pong plays in the mirror. `i`: the mirror inverts. `o`: it
   goes dark, and again lights. `+` and `-`: it dims and brightens. `b`:
   the lit pixels change color (a 256-color terminal). `m`: the demo.
8. Press `Enter` on the `contrast` row, type `abc`, `OK`. Expect:
   `last_error` turns red with `set_contrast_not_int@...`, and the value
   snaps back. Type `32`: the mirror dims.
9. `H` shows the page's help. `L` opens the log level pop-up. `K` asks to
   stop the Actor: `Cancel`.
10. Press `D` (or `Esc`). Expect: the Dashboard. In another terminal,
    `mosquitto_sub -v -t 'aiko/+/+/+/control'` shows no `(mirror ...)`
    renewal after 10 s, and `mirrors` in the shared state reads `0`.
11. Press `S` again. Press `M`. Expect: the page and the service bar
    read `mirror: off (M)`, and the Actor's `mirrors` falls by one. Press
    `M` again: the mirror returns within 10 s.
12. Press `G`, then hold the right arrow key for three seconds. Expect:
    the forklift drives right all the time that the key is held, and
    stops within a quarter of a second after you let go. The service
    bar shows `key N ms`, the time from the key to the next frame. With
    `aiko_display set mirror_rate 10` first, expect about 50 to 200 ms
    from a desktop to the SBC.
13. Press `x` to quit the Dashboard. Expect: within 30 s the Actor's
    `mirrors` reads `0` (the lease expired).
14. Start the page again with `AIKO_DISPLAY_MIRROR=ascii`, and then with
    `LC_ALL=C` instead. Expect: both show the mirror in plain ASCII
    (`'`, `.` and `:`). `AIKO_DISPLAY_MIRROR=off` starts with the mirror
    off.

## 9. The applets

```bash
aiko_display applet pattern           # the test pattern: border, ticks, diagonals, circle, blocks, "centre"
aiko_display applet text              # a screen full of digits, each row offset by one
aiko_display applet text Hello lead   # the words in the center
aiko_display applet blink rate=4      # the power off and on, four times a second (the next applet stops it)
aiko_display applet log               # the last eight (log ...) lines, oldest first
aiko_display applet help              # the help pages, turning every 8 s; page=2 holds one
aiko_display applet help page=5       # the wire commands; the arrow keys turn the pages
aiko_display applet clock             # the analog clock face; title=on keeps the title row; seconds=off
aiko_display applet clock face=digital   # the weekday, the date and the time under the title row
aiko_display applet eyes              # the eyes; emotion=angry holds one; blink=off
aiko_display applet asteroids seed=1  # the same game every time with the same seed
aiko_display applet games duration=10 # pong, asteroids and invaders in turn
aiko_display applet forklift          # the forklift moves the pallet by itself
aiko_display applet draw subject=cat style=hatch speed=4
aiko_display applet draw shade=off count=1   # one outlined drawing, then back to the default applet
aiko_display applet demo random=off   # the fixed tour of the applets and settings
aiko_display applet demo              # the random tour
aiko_display applet status screen=wifi view=rx_tx   # the Wi-Fi interface's traffic chart
aiko_display applet status            # back to the status display
```

Expect: each applet runs until the next command. `aiko_display applet
nosuch` and `aiko_display applet draw subject=unicorn` change nothing, and
they set `last_error` (`set_applet_unknown@...`, `set_applet_args@...`).

## 10. The keys console

```bash
aiko_display keys
```

Expect: `Display Actor HOST: $TOPIC  (? for the keys)`, and a status line
that follows the shared state. Every key is sent to the Actor as
`(key K tap)`, and the Actor's key map decides. Then type, without Enter:

| Key | Expect |
|-----|--------|
| `?` | The help applet on the display, page 1: the same as `h` |
| `p` | The test pattern. The status line shows `applet pattern` |
| `p` again, three times | The test pattern in the 5x7, 10 and 16 pixel fonts. The same key again gives the next preset |
| `t`, seven times | The digit grid in the current font, then in the 5x7, 10 and 16 pixel fonts, then `Hello!`, `OLED` and `128x64` in larger fonts |
| `g`, four times | Pong, asteroids, invaders, then the forklift working by itself |
| `d`, repeatedly | A drawing, then outlined, hatched, stippled, then each subject |
| `G`, then the arrow keys | The forklift game: left and right drive, up and down lift. A tapped key moves a little, and a held key moves more |
| `0` … `9` | The speed: `0` fastest, `4` normal, `9` slowest (`speed` in the status line) |
| `f`, then `F` | The next font size, then the previous one again |
| `i`, `o`, `a` | Invert, power and all-pixels-on toggles |
| `+`, `-` | Contrast up and down by 16 |
| `b`, repeatedly **[mac]** | The next foreground color: deepskyblue, yellow, lime, orange, hotpink, white |
| `B`, repeatedly **[mac]** | The next background color: midnightblue, darkslategray, maroon, dimgray, white, black |
| `c` | Clear the canvas |
| `P`, twice | The panel's power off and on, twice a second, then eight times a second |
| `l` | The log lines |
| `h`, six times | The help pages, one per press |
| `C`, four times | The clock face, then with the title row, then without the seconds hand, then the digital face |
| `e`, repeatedly | The eyes, then held at `happy`, and on through the emotions |
| `T` | The title row off, then on again |
| `s`, twice | The host status, then the Wi-Fi screen |
| `S`, three times | The views of the screen shown: its first chart, its second chart, then the text again |
| `R` | Reset the settings and the colors, and show the status display |
| `x` | Quit the console. The Actor keeps running |

`X` then `y` would exit the Actor.

**[mac]** The emulator window takes the same keys. Start
`aiko_display run -o window`, click the window, and type `g`, `g`, `b`, `5`
and `R`: pong, then asteroids, a blue foreground, a slower pace, then the
status display with the colors reset. The arrow keys drive the forklift
game (`G`). `x`, `q` or `Esc` closes the window and exits the Actor.

## 11. Failure behavior

| Step | Do | Expect |
|------|----|--------|
| 11.1 **[sbc]** | `aiko_display run -a 0x3D`, an address without a panel | A WARNING `no SSD1306 at 0x3D`. The Actor runs. The shared state shows `device absent` and `last_error display_not_found@...`, and every 10 s it retries. `aiko_display exit` ends it |
| 11.2 **[sbc]** | `aiko_display run -a 0x3D --strict` | The Actor exits at once with the error |
| 11.3 | `aiko_display run --standalone`, with the broker stopped or `AIKO_MQTT_HOST` wrong | The status display works without a broker. The title row shows no `M` and no `R` |
| 11.4 | With the Actor running: `kill -TERM PID` | The display blanks, and the process ends with exit status 0 |
| 11.5 | Ctrl-C in the Actor's terminal | The same |
| 11.6 | `aiko_display set blank_after 5`, then wait 5 s | The display goes off. Any command, for example `aiko_display log wake`, brings it back. `set blank_after 0` disables it |
| 11.7 | `aiko_display applet pong`, then `mosquitto_pub -t $TOPIC/in -m "(text 0 0 stop)"` | A drawing command stops the applet and shows the text. `aiko_display log x` while an applet runs does not stop it |
| 11.8 | `aiko_display -n nosuch -t 2 applet pong` | `Timeout after 2 s: no Display Actor named nosuch`, exit status 1 |

## 12. systemd on the SBC (optional)

Edit `src/aiko_services/actors/display/aiko_display.service` for the user,
the paths and the address. Then:

```bash
sudo cp aiko_display.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now aiko_display
journalctl -u aiko_display -f
```

Expect: the status display at boot. `sudo systemctl stop aiko_display`
blanks it.

## 13. The simple example

`examples/oled/oled_actor.py` is a second, much smaller Actor for the
same protocol. It accepts `clear`, `log` and `text` only. Stop the
Display Actor first (`aiko_display exit`) when both would use the same
panel.

```bash
cd src/aiko_services/examples/oled
./oled_actor.py -a 0x3C -n example      # [sbc] the panel
./oled_actor.py -a none -n example      # [mac] drawn in the terminal
```

| Step | Command | Expect |
|------|---------|--------|
| 13.1 | `aiko_display -n example list` | `example  aiko/HOST/PID/1  ec=true device=ssd1306 canvas=0` (`device=terminal` with `-a none`) |
| 13.2 | `aiko_display -n example text 0 56 Aloha` | `Aloha` on the top row |
| 13.3 | `aiko_display -n example log hello world`, twice | The picture scrolls up one row each time, and the line is on the bottom row |
| 13.4 | The Dashboard page on `example` | `mirror: not supported by this Actor`. A key typed on the page is logged as an ERROR, `Function not found`, on the Actor's log topic |
| 13.5 | `aiko_display -n example exit` | The panel blanks and the example ends. `aiko_display stop` stops an applet, so the example does not accept it |

## 14. Terminals (a person must look)

The terminal test (`test_terminal_matrix`) finds what asciimatics
decides in a pseudo-terminal, but it cannot see the glyphs. Start the
display page (step 8.6) in each of these, at 132x48 and at 80x24:

| Terminal | Expect |
|----------|--------|
| macOS Terminal | The half-block and the Braille mirror, in the panel's colors |
| iTerm2 | The same |
| The Linux console of the SBC (no desktop) | The half-block mirror. The console font has no Braille, so at 80x24 use `AIKO_DISPLAY_MIRROR=ascii` |
| ssh from the desktop to the SBC | The same as the local terminal. The arrow keys hold, with one short gap at the start when the first repeat is slow |
| tmux, in any of the above | The same, with 256 colors when `TERM` in tmux is `tmux-256color` |
| `TERM=vt100` | No Dashboard: asciimatics cannot hide the cursor. The 6 expected failures in step 2 record this |

## 15. Clean up

```bash
aiko_display exit
kill %1            # the Registrar started in step 4, if it was yours
```

## Related concepts

- [display](display.md), [display_protocol](display_protocol.md),
  [display_dashboard](display_dashboard.md), [design](design.md)
- [Dashboard](../../concepts/dashboard.md),
  [Share](../../concepts/share.md),
  [Discovery](../../concepts/discovery.md)
