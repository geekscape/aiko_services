# Aiko Services example: OLED display Actor

An SSD1306 128x64 OLED as an Aiko Services Actor (protocol `oled:0`).
The main use is a status display for a headless Raspberry Pi or server:
hostname, IP address, connection state, time, load and the last log lines.
Any Aiko Services client can also draw on it, with the same S-expressions
that the MicroPython [aiko_engine_mp](https://github.com/geekscape/aiko_engine_mp)
OLED accepts, and the Aiko Dashboard reads and writes its settings.
Without the panel, the OLED is emulated in a desktop window (pygame), in
the terminal or in a PNG file.

Documentation: [documentation/examples/oled/ReadMe.md](../../../../documentation/examples/oled/ReadMe.md)

## Hardware

- Raspberry Pi 4B (or any Linux host with an I2C bus)
- SSD1306 128x64 OLED module on I2C bus 1: SDA pin 3, SCL pin 5, VCC 3.3 V
  pin 1, GND pin 6.  Address 0x3C (default) or 0x3D (SA0 pin high)
- Enable I2C: `sudo raspi-config nonint do_i2c 0`, then reboot.  Faster
  frames: add `dtparam=i2c_arm_baudrate=400000` to `/boot/firmware/config.txt`
- Check: `/usr/sbin/i2cdetect -y 1` shows `3c` or `3d`

## Install

The example lives in `src/aiko_services/examples/`, which the Aiko
Services wheel does not ship, so the `aiko_oled` command needs an editable
install of the repository:

    pip install -e .              # aiko_services, in your virtual environment
    pip install luma.oled         # the SSD1306 driver (Raspberry Pi only)
    pip install pygame            # optional: the desktop window emulation

## Run

    export AIKO_MQTT_HOST=localhost
    aiko_registrar &
    aiko_oled run -a 0x3D         # on the Raspberry Pi
    aiko_oled run -o terminal     # or emulated, on any host

From another terminal or host on the same broker:

    aiko_oled text 0 0 hello      # origin bottom-left: the bottom row
    aiko_oled log Hello from nomad
    aiko_oled set contrast 64     # settings are shared state: the Dashboard edits them too
    aiko_oled list
    aiko_oled exit

aiko_engine_mp style, with `mosquitto_pub` on the Actor's `in` topic:

    mosquitto_pub -t aiko/HOST/PID/1/in -m "(oled:text 0 0 hello)"

## Files

| File | Purpose |
|------|---------|
| `oled.py` | The `OLED` and `OLEDApplications` Interfaces, `OLEDImpl` and the `aiko_oled` command line |
| `display.py` | Display backends: SSD1306 (luma.oled), pygame window, terminal, PNG, none, fake |
| `graphics.py` | 5x7 font, image helpers, the bottom-left `Canvas`, the title row |
| `applications.py` | Applications: sources of frames the Actor runs — `status` (the default), `help` |
| `aiko_oled.service` | systemd unit for a Raspberry Pi: the display comes up with the host |
| `oled_test.py` | The original standalone spike (click, no Aiko Services): kept unchanged for reference |
