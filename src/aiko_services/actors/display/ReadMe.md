# Aiko Services actors: the Display Actor

An SSD1306 128x64 OLED as an Aiko Services Display Actor (protocol
`display:0`: the composite of the Canvas, Screen and Interaction aspects).
The main use is a status display for a headless Linux Single Board
Computer (SBC) or server: hostname, IP address, connection state, time,
load and the newest log line.  Any Aiko Services client can also draw on
it, with the same S-expressions that the MicroPython
[aiko_engine_mp](https://github.com/geekscape/aiko_engine_mp) OLED
accepts, and the Aiko Dashboard reads and writes its settings.  Without
the panel, the OLED is emulated in a desktop window (pygame), in the
terminal or in a PNG file.

Documentation: [documentation/actors/display/ReadMe.md](../../../../documentation/actors/display/ReadMe.md)
(the Actor, the `display:0` protocol, the design record and the step-by-step
[test guide](../../../../documentation/actors/display/testing.md)).
`aiko_display --help` is the complete command reference.

## Hardware

- A Linux SBC with an I2C bus, for example a Raspberry Pi
- An SSD1306 128x64 OLED module on I2C bus 1: SDA pin 3, SCL pin 5,
  VCC 3.3 V pin 1, GND pin 6.  Address 0x3C (the default) or 0x3D (the
  SA0 pin high)
- Enable I2C: `sudo raspi-config nonint do_i2c 0`, then reboot.  For
  faster frames, add `dtparam=i2c_arm_baudrate=400000` to
  `/boot/firmware/config.txt`
- Check: `/usr/sbin/i2cdetect -y 1` shows `3c` or `3d`

## Install

The package ships in the Aiko Services wheel, in the actors tier, with
the `aiko_display` command:

```bash
pip install aiko_services     # or "pip install -e ." in a clone
pip install luma.oled         # the SSD1306 driver (the SBC only)
pip install pygame            # optional: the desktop window emulation
```

## Run

```bash
export AIKO_MQTT_HOST=localhost
aiko_registrar &
aiko_display run -a 0x3C         # on the SBC with the OLED
aiko_display run -o terminal     # or emulated, on any host
```

From another terminal or host on the same broker:

```bash
aiko_display text 0 0 hello      # origin bottom-left: the bottom row
aiko_display log Hello from nomad
aiko_display set contrast 64     # settings are shared state: the Dashboard edits them too
aiko_display applet pong         # or draw, clock, eyes, forklift_game, demo ...
aiko_display applet --list       # the applets and their options
aiko_display key g               # the key map lives on the Actor: pong
aiko_display keys                # interactive: every key goes to the Actor (the window too)
aiko_display mirror aiko/probe 20 # a leased feed of raw frames to a topic, 20 s
aiko_dashboard -p aiko_services.main.dashboard_plugins -p aiko_services.actors.display.dashboard_plugin
aiko_display list
aiko_display exit
```

From another host, point `AIKO_MQTT_HOST` at the SBC's broker and name
the Actor: `aiko_display -n HOSTNAME keys`.  The SBC's mosquitto must listen
on every interface (`listener 1883 0.0.0.0` and `allow_anonymous true` in
`/etc/mosquitto/conf.d/aiko.conf`; the Debian default is 127.0.0.1 only).

aiko_engine_mp style, with `mosquitto_pub` on the Actor's `in` topic:

```bash
mosquitto_pub -t aiko/HOST/PID/1/in -m "(oled:text 0 0 hello)"
```

For a display that comes up with the host, install `aiko_display.service`
with systemd (the instructions are in the file).

## Tests

```bash
pytest src/aiko_services/tests/unit/test_display.py \
       src/aiko_services/tests/unit/test_display_cli.py \
       src/aiko_services/tests/unit/test_display_applets.py \
       src/aiko_services/tests/unit/test_display_dashboard_plugin.py
```

142 tests (6 of them expected failures: the `vt100` terminal cases); no
broker and no panel needed.

## Files

| File | Purpose |
|------|---------|
| `display.py` | The `Canvas`, `Screen` and `Interaction` aspects, the `Display` composite, `DisplayImpl`, `SETTINGS_SPEC` and `service_filter()` |
| `cli.py` | The `aiko_display` command line |
| `outputs.py` | The output seam: `Output` and `OutputControls` Interfaces, one Impl per backend (SSD1306 with luma.oled, pygame window, terminal, PNG, none, fake), the `Appearance` emulation, the frame as Unicode or ASCII text |
| `graphics.py` | 5x7 font, image helpers, the bottom-left `FrameBuffer`, the title row |
| `applets.py` | Applets: sources of frames the Actor runs — `log`, `help`, `pattern`, `text`, `blink`, `demo` |
| `status.py` | `status`, the default: the host and Wi-Fi screens, as text or as charts of the newest samples, one per column |
| `games.py` | `pong`, `asteroids`, `invaders`, `games`, `forklift`, `forklift_game` (arrow keys over the wire) |
| `drawings.py` | `draw`: pencil-sketched cartoon scenes |
| `faces.py` | `clock`: an analog or a digital clock face; `eyes`: animated eyes showing emotions |
| `keys.py` | The key map, run on the Actor by `(key K)`: what each key does, and the `keys.*` legend |
| `console.py` | `aiko_display keys`: an interactive console for the running Actor |
| `dashboard_plugin.py` | The Aiko Dashboard page: a live mirror of the panel (Unicode or ASCII, `M` turns it off), the shared state, the log, the keys, held arrows |
| `aiko_display.service` | systemd unit for a Linux SBC: the display comes up with the host |

The one-file example of the same protocol, `oled_actor.py`, and the
original standalone spike, `oled_test.py`, are in `src/aiko_services/examples/oled/`.
