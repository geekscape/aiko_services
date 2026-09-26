---
title: OLED Actor test guide
description: Step-by-step instructions for a technical lead to exercise
  every part of the OLED display Actor example — on macOS with an emulated
  display and on a Linux Single Board Computer (SBC) with the SSD1306 panel —
  the unit tests, the command line and its help, raw S-expressions, the
  shared state, the Aiko Dashboard, the applets, the keys console, failure
  behavior and systemd
type: guide
audience: [developers]
status: draft
ste: adapted
source:
  - src/aiko_services/examples/oled
related: [oled, oled_protocol, dashboard, share, discovery]
version: "0.8-dev"
last_updated: 2026-09-26
---

# OLED Actor test guide

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
  `aiko_oled` command needs an editable install, because `examples/` is
  not in the wheel:

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
  is "No OLED Actors found" although the Actor runs. Clear it, then
  restart the Registrar:

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
  Actor: `aiko_oled list`, then `aiko_oled -n SBC_HOSTNAME keys`.

## 2. Unit tests and lint

```bash
pytest src/aiko_services/tests/unit/test_oled.py \
       src/aiko_services/tests/unit/test_oled_cli.py \
       src/aiko_services/tests/unit/test_oled_applets.py
flake8 . --select=E9,F63,F7,F82
```

Expect: `86 passed`, and no flake8 output. No broker and no panel are
needed. Run them on the SBC too (Python 3.13 there). One test asserts
that `oled_test.py`, the original spike, is never imported.

## 3. The help

```bash
aiko_oled --help
aiko_oled run --help
aiko_oled applet --list
aiko_oled keys --help
```

Expect: the group help ends with a reference built from the code's own
tables. It lists the applets, the settings, the shared state keys, the
wire commands and the console keys with their presets. Every subcommand's `--help` explains it in
full. `applet --list` needs no Actor. Nothing is wider than 80 columns.

## 4. Run the Actor

Terminal 1:

```bash
aiko_registrar &
aiko_oled run -o terminal                  # [mac] emulated in the terminal
aiko_oled run -o window                    # [mac] emulated in a pygame window
aiko_oled run -o png --png /tmp/oled.png   # [mac] the newest frame as a PNG
aiko_oled run                              # [sbc] the panel at 0x3C (-a 0x3D for SA0 high)
```

Expect: a line `OLED Actor NAME: aiko/HOST/PID/1/in`, where NAME is the
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
| 5.1 | `aiko_oled list` | `HOST  aiko/HOST/PID/1  ec=true`, exit status 0 |
| 5.2 | `aiko_oled text 0 0 hello world` | The status display stops. `hello world` on the bottom row (origin bottom-left) |
| 5.3 | `aiko_oled text 0 8 second row` | One text row above it |
| 5.4 | `aiko_oled log Hello from the lead` | The canvas scrolls up one row, and the line is on the bottom row. The title row shows `L` |
| 5.5 | `aiko_oled pixels 0 0 127 63` | The bottom-left pixel lights. The top-right pixel lights unless the title row covers it |
| 5.6 | `aiko_oled line 0 0 127 63` | A diagonal |
| 5.7 | `aiko_oled clear` | Only the title row remains |
| 5.8 | `aiko_oled set contrast 32` | Dim. `aiko_oled set contrast 255` restores |
| 5.9 | `aiko_oled set invert on`, then `off` | Inverse video, and back |
| 5.10 | `aiko_oled set power off`, then `on` | The display off (blank), and back |
| 5.11 | `aiko_oled set title Aiko_Services` | The title row reads `Aiko Serv`: the title has 9 columns with the 5x7 font. The annunciators and the clock follow |
| 5.12 | `aiko_oled set title off`, then `aiko_oled set title on` | The row disappears, so the canvas and the applets have the whole panel. Then it returns with the same text |
| 5.13 | `aiko_oled applet pong`, then `aiko_oled log one`, `aiko_oled log two`, then `aiko_oled applet log` | Pong keeps running while the lines arrive (no title row over a game). The `log` applet shows both lines and clears `L` |
| 5.14 | `aiko_oled set font 12` | Text drawn from now on is larger. `set font 5x7` restores |
| 5.15 | `aiko_oled applet status` | The status display again, in the current font: IP, uptime, `CPU 12.3% Mem 34.5%`, `Disk 61.2% Load 0.42`, `Rx 111k Tx 1.1k`, `Temp 45.1C` on an SBC, and the newest log line. `aiko_oled log again` replaces that line |
| 5.16 | `aiko_oled applet status date=on` | The date row is added |
| 5.17 | `aiko_oled applet pong` | Pong plays itself. `aiko_oled set speed 2` doubles the pace, and `set speed 1` restores |
| 5.18 | `aiko_oled applet forklift_game`, then `aiko_oled key right`, `aiko_oled key up` | The forklift drives right a little, and lifts its forks a little, per key |
| 5.19 | `aiko_oled stop` | The canvas from 5.7 is shown again |
| 5.20 | `aiko_oled set bogus 1` | A usage error, exit status 2. The key is checked locally |
| 5.21 | `aiko_oled exit` | The display blanks, the Actor process ends, exit status 0 |
| 5.22 | `aiko_oled -t 2 exit`, with nothing running | `Timeout after 2 s: no OLED Actor named HOST`, exit status 1 |

Start the Actor again (step 4) before you continue.

## 6. Raw S-expressions (what an aiko_engine_mp client sends)

```bash
mosquitto_pub -t $TOPIC/in -m "(oled:text 0 0 hello)"        # the bottom row
mosquitto_pub -t $TOPIC/in -m "(oled:log This is a test !)"  # scrolls, the bottom row
mosquitto_pub -t $TOPIC/in -m "(oled:pixels 0 0 127 63)"     # two corners
mosquitto_pub -t $TOPIC/in -m "(text 0 16 native form)"      # the same command, no prefix
mosquitto_pub -t $TOPIC/in -m '(text 0 24 "quoted text is one word")'
```

Expect: the same effects as the `aiko_oled` commands. Now the
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
[oled_protocol](oled_protocol.md). For example `backend oled`,
`device ssd1306@0x3C/i2c1` on the SBC, `connection REGISTRAR`,
`applet draw`, `contrast 64`, `heartbeat N`,
`last_error set_contrast_not_int@...`, `log_pending off` and
`metrics.frames N`. Then `(update heartbeat N)` once a second, and
`(update metrics.* N)` every two seconds while something changes, for
ten seconds. Every value is one token: no spaces.

## 8. The Aiko Dashboard

```bash
aiko_dashboard
```

1. The Services list shows the OLED Actor: protocol `.../oled:0`, tag
   `ec=true`. Move to its row with the arrow keys, and press `s` to
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
   `x` exits the Dashboard. The Service page (`S`) has no OLED plug-in
   yet: that is Epic 1.

## 9. The applets

```bash
aiko_oled applet pattern           # the test pattern: border, ticks, diagonals, circle, blocks, "centre"
aiko_oled applet text              # a screen full of digits, each row offset by one
aiko_oled applet text Hello lead   # the words in the center
aiko_oled applet blink rate=4      # the power off and on, four times a second (the next applet stops it)
aiko_oled applet log               # the last eight (log ...) lines, oldest first
aiko_oled applet help              # the help pages, turning every 8 s; page=2 holds one
aiko_oled applet help page=5       # the wire commands; the arrow keys turn the pages
aiko_oled applet clock             # the clock face; title=on keeps the title row; seconds=off
aiko_oled applet eyes              # the eyes; emotion=angry holds one; blink=off
aiko_oled applet asteroids seed=1  # the same game every time with the same seed
aiko_oled applet games duration=10 # pong, asteroids and invaders in turn
aiko_oled applet forklift          # the forklift moves the pallet by itself
aiko_oled applet draw subject=cat style=hatch speed=4
aiko_oled applet draw shade=off count=1   # one outlined drawing, then back to the default applet
aiko_oled applet demo random=off   # the fixed tour of the applets and settings
aiko_oled applet demo              # the random tour
aiko_oled applet status            # back to the status display
```

Expect: each applet runs until the next command. `aiko_oled applet
nosuch` and `aiko_oled applet draw subject=unicorn` change nothing, and
they set `last_error` (`set_applet_unknown@...`, `set_applet_args@...`).

## 10. The keys console

```bash
aiko_oled keys
```

Expect: `OLED Actor HOST: $TOPIC  (? for the keys)`, and a status line
that follows the shared state. Then type, without Enter:

| Key | Expect |
|-----|--------|
| `?` | The key list |
| `p` | The test pattern. The status line shows `applet pattern` |
| `p` again, three times | The test pattern in the 5x7, 10 and 16 pixel fonts. The same key again gives the next preset |
| `t`, seven times | The digit grid in the current font, then in the 5x7, 10 and 16 pixel fonts, then `Hello!`, `OLED` and `128x64` in larger fonts |
| `g`, four times | Pong, asteroids, invaders, then the three in turn |
| `d`, repeatedly | A drawing, then outlined, hatched, stippled, then each subject |
| `F`, then the arrow keys | The forklift game: left and right drive, up and down lift. A tapped key moves a little, and a held key moves more |
| `0` … `9` | The speed: `0` fastest, `4` normal, `9` slowest (`speed` in the status line) |
| `f`, repeatedly | The next font size |
| `i`, `o`, `a` | Invert, power and all-pixels-on toggles |
| `+`, `-` | Contrast up and down by 16 |
| `c` | Clear the canvas |
| `l` | The log lines |
| `h`, six times | The help pages, one per press |
| `C`, three times | The clock face, then with the title row, then without the seconds hand |
| `e`, repeatedly | The eyes, then held at `happy`, and on through the emotions |
| `T` | The title row off, then on again |
| `s`, repeatedly | The status display, then at 4 updates a second, then in the 5x7, 10 and 12 pixel fonts |
| `R` | Reset the settings, and show the status display |
| `x` | Quit the console. The Actor keeps running |

`X` then `y` would exit the Actor.

## 11. Failure behavior

| Step | Do | Expect |
|------|----|--------|
| 11.1 **[sbc]** | `aiko_oled run -a 0x3D`, an address without a panel | A WARNING `no SSD1306 at 0x3D`. The Actor runs. The shared state shows `device absent` and `last_error display_not_found@...`, and every 10 s it retries. `aiko_oled exit` ends it |
| 11.2 **[sbc]** | `aiko_oled run -a 0x3D --strict` | The Actor exits at once with the error |
| 11.3 | `aiko_oled run --standalone`, with the broker stopped or `AIKO_MQTT_HOST` wrong | The status display works without a broker. The title row shows no `M` and no `R` |
| 11.4 | With the Actor running: `kill -TERM PID` | The display blanks, and the process ends with exit status 0 |
| 11.5 | Ctrl-C in the Actor's terminal | The same |
| 11.6 | `aiko_oled set blank_after 5`, then wait 5 s | The display goes off. Any command, for example `aiko_oled log wake`, brings it back. `set blank_after 0` disables it |
| 11.7 | `aiko_oled applet pong`, then `mosquitto_pub -t $TOPIC/in -m "(text 0 0 stop)"` | A drawing command stops the applet and shows the text. `aiko_oled log x` while an applet runs does not stop it |
| 11.8 | `aiko_oled -n nosuch -t 2 applet pong` | `Timeout after 2 s: no OLED Actor named nosuch`, exit status 1 |

## 12. systemd on the SBC (optional)

Edit `src/aiko_services/examples/oled/aiko_oled.service` for the user,
the paths and the address. Then:

```bash
sudo cp aiko_oled.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now aiko_oled
journalctl -u aiko_oled -f
```

Expect: the status display at boot. `sudo systemctl stop aiko_oled`
blanks it.

## 13. Clean up

```bash
aiko_oled exit
kill %1            # the Registrar started in step 4, if it was yours
```

## Related concepts

- [oled](oled.md), [oled_protocol](oled_protocol.md)
- [Dashboard](../../concepts/dashboard.md),
  [Share](../../concepts/share.md),
  [Discovery](../../concepts/discovery.md)
