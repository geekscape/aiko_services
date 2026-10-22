# Aiko Services actors: the WhisPlay Actor

The WhisPlay HAT as an Aiko Services Actor. It shows the camera on the panel, and
a long button press performs an action, which is a clean shutdown by default. It
replaces the vendor demonstration that `/etc/rc.local` used to start.

Shared variables, changed while it runs:

| Name | Default | Meaning |
|---|---|---|
| `action` | `power_off` | What a long button press does: `power_off` or `none` |
| `rate` | `8.0` | Frames each second, 0.1 to 30.0 |
| `resolution` | `240x180` | What is read from the camera |

## The screen layout

`240x180` fills the 240 pixel width of the panel exactly, so there is no
horizontal scaling, and it leaves **240x100 underneath for text**: the host name,
the address, the frame count and the time. The panel is an image area above a
text area, not a full screen image.

The glass has **rounded corners with no pixels**, so the text is inset from
the sides and nothing important goes in a corner. The font size is derived
from the text area and the line count, so four lines fill the 100 pixels.

## The camera needs a virtual environment with system packages

`picamera2` needs the `libcamera` Python bindings. On Raspberry Pi OS they are
the operating system package `python3-libcamera`, at
`/usr/lib/python3/dist-packages/libcamera`, and **they are not on PyPI**:
`pip index versions libcamera` reports no distribution. `picamera2`, `spidev`
and `gpiozero` are on PyPI, but `picamera2` without the bindings is of no use.

So an isolated virtual environment cannot reach the camera. Make it with
system packages:

```bash
python3 -m venv --system-site-packages ~/venvs/venv_3.13
~/venvs/venv_3.13/bin/pip install -e .
```

Packages installed into the environment still take precedence, except where the
system already satisfies the requirement. On a Raspberry Pi 5 that leaves numpy
at the system version, which is what `picamera2` was built against. Without
`--system-site-packages` the failure is an `ImportError` a long way from its
cause, which is why it is written here.

## Install

```bash
pip install -e .          # "aiko_whisplay" is then on the PATH
aiko_whisplay --help
```

## Run

On the Raspberry Pi, with the HAT:

```bash
aiko_whisplay run                       # the panel, camera and button it finds
aiko_whisplay run --action none         # a long press then does nothing
aiko_whisplay run --rate 1.0 --rotate 180
```

On a laptop, with no HAT at all:

```bash
aiko_whisplay run --panel window --camera none --button none
```

`--panel window` opens a desktop window through pygame, in the way a window
stands in for the OLED of the [Display Actor](../display/ReadMe.md). The whole
Actor runs, so the frame composition and the handlers are exercised without
hardware.

Change a setting while it runs. These are shared variables, not wire commands:

```bash
mosquitto_pub -t TOPIC_PATH/control -m "(update rate 1.0)"
mosquitto_pub -t TOPIC_PATH/control -m "(update action none)"
```

## What it does not accept

The Actor adds **no wire command of its own**. The allow-list is
`set_log_level` and `stop`, and dispatch refuses everything else (P12,
ADR-023). That is deliberate: `action` decides whether a button press halts the
host, so nothing on the bus reaches it directly. A refused command is logged and
recorded in the `last_error` shared variable.

## Threads

Read this before changing the Actor. It follows P11 (ADR-027):

* State, `self.share` included, is mutated **only** on the event-loop thread.
* The worker thread and the button thread **never** touch shared state. They
  post work with `_post_message()`.
* Settings go the other way, into the worker thread, through a `Queue`.
* There are no locks.

The worker thread owns the camera and the panel, because a capture and a 134,400
byte write over SPI must not run on the event-loop thread.

## The panel, and Epic 4

This Actor drives the 240x280 ST7789 panel **directly**, in colour. Going
through `display:0` is not possible today: its `Canvas` is vector and text only
— `clear`, `log`, `pixel`, `pixels`, `line`, `text` — at one bit and 128x64,
with no image command. CP-F also says that bulk pixels belong out of band.

When `display:0` gains a real `depth`, the Display Actor absorbs this panel. Two
things must never drive the panel at once, so that work starts by retiring
whichever duplicate survives. The route the design anticipates is an **applet**,
because applets produce frames directly and bypass the FrameBuffer.

## `power_off` halts the host only

A long press stops Aiko Services cleanly, then halts the Raspberry Pi. **It does
not cut the battery output.** A PiSugar keeps supplying power to a halted
Raspberry Pi, so the battery drains until it cuts out. Cutting the output needs
an I2C write that the power Actor will bring, and `action` is a shared variable,
so that becomes a change of default rather than a rewrite.

## Tests

```bash
pytest -q src/aiko_services/tests/unit/test_whisplay.py
```

Expect `45 passed`. No hardware and no broker. The frame composition and the
press rule are pure functions, tested directly. The Actor is composed with the
fake panel, camera and button. One test runs the event loop for a moment, to
show that the worker thread's frame count reaches shared state through the
mailbox.

## Files

| File | Contents |
|---|---|
| `whisplay.py` | The Actor: shared variables, the worker thread, the handlers and the allow-list |
| `frame.py` | The frame: the camera image above the text, and RGB565 |
| `panel.py` | `Panel`: the ST7789, a desktop window, and nothing |
| `camera.py` | `Camera`: a Raspberry Pi camera, and a test pattern |
| `button.py` | `Button`: the GPIO button, and the press rule |
| `cli.py` | The `aiko_whisplay` command |
