---
title: OLED Actor test guide
description: Step-by-step instructions for a technical lead to exercise
  every part of the OLED display Actor example — on macOS with an emulated
  display and on a Linux Single Board Computer (SBC) with the SSD1306 panel —
  the command line, raw S-expressions, the shared state, the Aiko
  Dashboard, the applets, the keys console, failure behavior and the tests
type: guide
audience: [developers]
status: draft
ste: false
source:
  - src/aiko_services/examples/oled
related: [oled, oled_protocol, dashboard, share]
version: "0.8-dev"
last_updated: 2026-09-26
---

# OLED Actor test guide

Each step says what to do and what to expect.  Steps marked **[mac]** run
on macOS (or any desktop) with an emulated display; steps marked **[sbc]**
run on the Linux SBC with the panel; unmarked steps run on both.  Two
terminals per host are useful: one for the Actor, one for commands.

## 1. What you need

- An MQTT broker (mosquitto) on the host, and `AIKO_MQTT_HOST` pointing at
  it.  Every terminal below starts with:

      export AIKO_MQTT_HOST=localhost
      export AIKO_LOG_MQTT=false        # log to the console, not the broker

- The repository installed editable in a virtual environment (the
  `aiko_oled` command needs an editable install: `examples/` is not in the
  wheel):

      cd <repository>; pip install -e .

- **[sbc]** the SSD1306 driver: `pip install luma.oled`.  **[mac]** the
  window emulation: `pip install pygame` (optional).
- **[sbc]** I2C enabled and the panel visible: `/usr/sbin/i2cdetect -y 1`
  shows `3c` (the default address; `3d` if the module's SA0 is high).

Two deployment traps to know about:

- A stale retained Registrar announcement stops discovery ("No OLED Actors
  found" although the Actor runs).  Clear it and restart the Registrar:
  `mosquitto_pub -t aiko/service/registrar -r -n`.
- A broker that listens on 127.0.0.1 only (the Debian default) cannot be
  reached from another host.  To drive the SBC's Actor from a desktop, let
  its broker listen on every interface (any host on the LAN can then
  publish, so keep this to a trusted network):

      printf "listener 1883 0.0.0.0\nallow_anonymous true\n" | sudo tee /etc/mosquitto/conf.d/aiko.conf
      sudo systemctl restart mosquitto

  Then, on the desktop, `export AIKO_MQTT_HOST=SBC_HOSTNAME` and use the
  Actor's name: `aiko_oled list`, `aiko_oled -n SBC_HOSTNAME keys`.

## 2. Unit tests and lint

    pytest src/aiko_services/tests/unit/test_oled.py \
           src/aiko_services/tests/unit/test_oled_cli.py \
           src/aiko_services/tests/unit/test_oled_applets.py
    flake8 . --select=E9,F63,F7,F82

Expect: 82 passed; no flake8 output.  No broker or panel is needed.  Run
them on the SBC too (Python 3.13 there).

## 3. Run the Actor

Terminal 1:

    aiko_registrar &
    aiko_oled run -o terminal            # [mac] emulated in the terminal
    aiko_oled run -o window              # [mac] emulated in a pygame window
    aiko_oled run -o png --png /tmp/oled.png   # [mac] the latest frame as a PNG
    aiko_oled run                        # [sbc] the panel at 0x3C (-a 0x3D for SA0 high)

Expect: a line `OLED Actor NAME: aiko/HOST/PID/1/in` (NAME is the
hostname), then the status display: an inverse-video title row with the
name, the annunciators `M` (broker) and `R` (Registrar) and the clock
(hh:mm:ss), and below it the IP address, uptime, CPU and memory, disk and
load, network traffic, and the temperature where the host has a sensor.  In
the terminal the picture is drawn with
half-block characters (Braille dots in a small terminal).  With `-o png`,
open the file after each command below to see the display.

Note the topic path: the steps below use `$TOPIC` for
`aiko/HOST/PID/1`.

## 4. The command line

Terminal 2 (same host; to command an Actor with another name or on
another host, put `-n NAME` before the subcommand):

| Step | Command | Expect |
|------|---------|--------|
| 4.1 | `aiko_oled list` | `HOST  aiko/HOST/PID/1  ec=true`, exit status 0 |
| 4.2 | `aiko_oled text 0 0 hello world` | The status display stops; `hello world` on the bottom row (origin bottom-left) |
| 4.3 | `aiko_oled text 0 8 second row` | One text row above it |
| 4.4 | `aiko_oled log Hello from the lead` | The canvas scrolls up one row; the line is on the bottom row |
| 4.5 | `aiko_oled pixels 0 0 127 63` | The bottom-left pixel and, unless the title row covers it, the top-right pixel light |
| 4.6 | `aiko_oled line 0 0 127 63` | A diagonal |
| 4.7 | `aiko_oled clear` | Only the title row remains |
| 4.8 | `aiko_oled set contrast 32` | Dim; `aiko_oled set contrast 255` restores |
| 4.9 | `aiko_oled set invert on`, then `off` | Inverse video and back |
| 4.10 | `aiko_oled set power off`, then `on` | Display off (blank) and back |
| 4.11 | `aiko_oled set title Aiko_Services` | The title row reads `Aiko Services` with the annunciators (`L` log lines pending, `M` broker, `R` Registrar) and the clock `hh:mm:ss` |
| 4.11a | `aiko_oled set title off`, then `aiko_oled set title on` | The row disappears (the whole panel for the canvas and applets), then returns with `Aiko Services` |
| 4.11b | `aiko_oled applet pong`, then `aiko_oled log one`, `aiko_oled log two`, then `aiko_oled applet log` | `L` is not visible during pong (no title row over a game); the `log` applet shows both lines and, with the title row on, clears `L` |
| 4.12 | `aiko_oled set font 12` | Text drawn from now on is larger (`set font 5x7` restores) |
| 4.13 | `aiko_oled applet status` | The status display again (its rows use the current font): IP, uptime, `CPU 12.3% Mem 34.5%`, `Disk 61.2% Load 0.42`, `Rx 111k Tx 1.1k`, `Temp 45.1C` on an SBC, and the newest log line — `aiko_oled log again` replaces it |
| 4.13a | `aiko_oled applet --list` | The applets with a summary and their options, no Actor needed |
| 4.14 | `aiko_oled applet pong` | Pong plays itself; `aiko_oled set speed 2` doubles the pace, `set speed 1` restores |
| 4.15 | `aiko_oled applet forklift_game` then `aiko_oled key right`, `aiko_oled key up` | The forklift drives right a little and lifts its forks a little per key |
| 4.16 | `aiko_oled stop` | The canvas (from 4.7) is shown again |
| 4.17 | `aiko_oled set bogus 1` | Usage error, exit status 2 (the key is checked locally) |
| 4.18 | `aiko_oled exit` | The display blanks, the Actor process ends, exit status 0 |
| 4.19 | `aiko_oled -t 2 exit` (nothing running) | `Timeout after 2 s: no OLED Actor named HOST`, exit status 1 |

Start the Actor again (step 3) before continuing.

## 5. Raw S-expressions (what an aiko_engine_mp client sends)

    mosquitto_pub -t $TOPIC/in -m "(oled:text 0 0 hello)"        # bottom row
    mosquitto_pub -t $TOPIC/in -m "(oled:log This is a test !)"  # scrolls, bottom row
    mosquitto_pub -t $TOPIC/in -m "(oled:pixels 0 0 127 63)"     # two corners
    mosquitto_pub -t $TOPIC/in -m "(text 0 16 native form)"      # the same command, no prefix
    mosquitto_pub -t $TOPIC/in -m '(text 0 24 "quoted text is one word")'

Expect: the same effects as the `aiko_oled` commands.  Now the rejections:

    mosquitto_pub -t $TOPIC/in -m "(run)"                # not a wire command
    mosquitto_pub -t $TOPIC/in -m "(pixel 200 0)"        # out of range
    mosquitto_pub -t $TOPIC/in -m "(log 12:30 lunch)"    # unquoted digits:colon
    mosquitto_pub -t $TOPIC/in -m '(log "12:30" lunch)'  # quoted: accepted

Expect: the first three change nothing on the display; the Actor's console
logs a WARNING for each (`dispatch rejected: unknown_command (run)`,
`pixel rejected: x_range`, `dispatch rejected: parse_error`), and the
process keeps running.  The fourth writes `12:30 lunch`.

Settings, the way the Dashboard writes them:

    mosquitto_pub -t $TOPIC/control -m "(update contrast 64)"
    mosquitto_pub -t $TOPIC/control -m "(update contrast abc)"   # rejected, converges back to 64
    mosquitto_pub -t $TOPIC/control -m "(update applet invaders)"

## 6. The shared state

The Actor publishes its state to consumers that hold a lease.  Watch it
with a lease of ten seconds:

    mosquitto_sub -v -t aiko/probe &
    mosquitto_pub -t $TOPIC/control -m "(share aiko/probe 10 *)"

Expect: a snapshot `(add KEY VALUE)` of every key in the table in
[oled](oled.md) (`backend oled`, `device ssd1306@0x3C/i2c1` on the SBC,
`connection REGISTRAR`, `applet invaders`, `contrast 64`, `heartbeat N`,
`last_error set_contrast_not_int@...`, `metrics.frames N` ...), then
`(update heartbeat N)` once a second and `(update metrics.* N)` every two
seconds while something changes, for ten seconds.  Every value is one
token: no spaces.

## 7. The Aiko Dashboard

    aiko_dashboard

1. The Services list shows the OLED Actor (protocol `.../oled:0`, tag
   `ec=true`).  Move to its row with the arrow keys and press `s` to
   select it.  Expect: the Variables section fills with the shared state
   (`applet`, `contrast`, `heartbeat` counting, `metrics.*` ...).
2. Press `Tab` to move to the Variables section, move to `contrast`,
   press `Enter`, type `16` and confirm.  Expect: the display dims; the
   variable shows `16`.
3. The same for `invert` → `on` (inverse video), `applet` → `pong` (the
   game starts), `font` → `10`, `title` → `Hello_lead` (underscores are
   spaces on the display), `speed` → `2`.
4. Enter a bad value, e.g. `contrast` → `abc`.  Expect: the value returns
   to what it was, and `last_error` shows `set_contrast_not_int@...`.
5. `?` shows the Dashboard's help; `l` changes the Actor's log level;
   `x` exits the Dashboard.  (`S`, the Service page, has no OLED plug-in
   yet: that is Epic 1.)

## 8. The applets

    aiko_oled applet pattern           # the test pattern: border, ticks, diagonals, circle, blocks, "centre"
    aiko_oled applet text              # a screen full of digits, each row offset by one
    aiko_oled applet text Hello lead   # the words centred
    aiko_oled applet blink rate=4      # the power off and on four times a second (stop with the next applet)
    aiko_oled applet log               # the last eight (log ...) lines, oldest first
    aiko_oled applet help              # help pages turning every 8 s; page=2 holds one
    aiko_oled applet clock             # the clock face; title=on keeps the title row
    aiko_oled applet eyes              # the eyes; emotion=angry holds one; blink=off
    aiko_oled applet asteroids seed=1  # the same game every time with the same seed
    aiko_oled applet games duration=10 # pong, asteroids and invaders in turn
    aiko_oled applet forklift          # the forklift moves the pallet by itself
    aiko_oled applet draw subject=cat style=hatch speed=4
    aiko_oled applet draw shade=off count=1   # one outlined drawing, then back to the default applet
    aiko_oled applet demo random=off   # the fixed tour: blink, pattern, invert, dim, digits, fonts, status, drawings, games, forklift
    aiko_oled applet demo              # the random tour
    aiko_oled applet status            # back to the status display

Expect: each runs until the next command.  `aiko_oled applet nosuch`
and `aiko_oled applet draw subject=unicorn` change nothing and set
`last_error` (`set_applet_unknown@...`, `set_applet_args@...`).

## 9. The keys console

    aiko_oled keys

Expect: `OLED Actor HOST: $TOPIC  (? for the keys)` and a status line that
follows the shared state.  Then type, without Enter:

| Key | Expect |
|-----|--------|
| `?` | The key list |
| `p` | The test pattern; the status line shows `applet pattern` |
| `t` repeatedly | The digit grid in the current font, then in the 5x7, 10 and 16 pixel fonts, then `Hello!`, `OLED` and `128x64` in larger fonts (the same key again: the next preset) |
| `g` repeatedly | Pong, asteroids, invaders, then the three in turn |
| `p` repeatedly | The test pattern in the 5x7, 10 and 16 pixel fonts |
| `d` repeatedly | A drawing; outlined; hatched; stippled; then each subject |
| `F`, then the arrow keys | The forklift game: left and right drive, up and down lift (a tapped key moves a little; hold it for more) |
| `0` … `9` | Speed: `0` fastest, `4` normal, `9` slowest (`speed` in the status line) |
| `f` (repeat) | The next font size |
| `i`, `o`, `a` | Invert, power and all-pixels-on toggles |
| `+`, `-` | Contrast up and down by 16 |
| `c` | Clear the canvas |
| `l` | The log lines |
| `h`, again, again | The help pages, one per press |
| `C` | The clock face |
| `e`, then `e` again | The eyes, then held at `happy` (and on through the emotions) |
| `T` | The title row off, then on again |
| `s` | The status display |
| `R` | Reset the settings and show the status display |
| `x` | Quit the console (the Actor keeps running) |

`X` then `y` would exit the Actor.

## 10. Failure behavior

| Step | Do | Expect |
|------|----|--------|
| 10.1 **[sbc]** | `aiko_oled run -a 0x3D` (an address without a panel) | A WARNING `no SSD1306 at 0x3D`; the Actor runs; the shared state shows `device absent` and `last_error display_not_found@...`; every 10 s it retries.  `aiko_oled exit` ends it |
| 10.2 | `aiko_oled run --standalone` with the broker stopped (or `AIKO_MQTT_HOST` wrong) | The status display works without a broker: the title shows no `M` or `R` |
| 10.3 | With the Actor running: `kill -TERM PID` | The display blanks and the process ends (exit status 0) |
| 10.4 | Ctrl-C in the Actor's terminal | The same |
| 10.5 | `aiko_oled set blank_after 5`, wait 5 s | The display goes off; any command (e.g. `aiko_oled log wake`) brings it back; `set blank_after 0` disables it |
| 10.6 | `aiko_oled applet pong` then `mosquitto_pub -t $TOPIC/in -m "(text 0 0 stop)"` | Drawing on the canvas stops the applet and shows the text; `aiko_oled log x` while an applet runs does not stop it |

## 11. systemd on the SBC (optional)

Edit `src/aiko_services/examples/oled/aiko_oled.service` for the user,
paths and address, then:

    sudo cp aiko_oled.service /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable --now aiko_oled
    journalctl -u aiko_oled -f

Expect: the status display at boot; `sudo systemctl stop aiko_oled`
blanks it.

## 12. Clean up

    aiko_oled exit
    kill %1            # the Registrar started in step 3, if it was yours

## Related concepts

- [oled](oled.md), [oled_protocol](oled_protocol.md)
- [Dashboard](../../concepts/dashboard.md), [Share](../../concepts/share.md)
