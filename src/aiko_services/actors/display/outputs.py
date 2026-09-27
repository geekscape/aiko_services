#!/usr/bin/env python3
#
# Aiko Services: OLED display outputs
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# Where the Display Actor's frames go: the output seam.  Two Interfaces,
# Output (open, show, close, pump, add_handler, message) and OutputControls
# (contrast, invert, power, all_on, set_colors), and one Impl per backend:
# the SSD1306 on the I2C bus (luma.oled), an emulated panel in a desktop
# window (pygame), in the terminal (Unicode half blocks or Braille), in a
# PNG file, nowhere (none), or a fake that records everything (tests).
# choose_output() composes the one that -o names.  The emulated outputs
# imitate the panel's contrast, invert, power and all-pixels-on settings
# with an Appearance (a value type) that changes the picture they show.
#
# Composed per ADR-022 decision 1 (a test double and alternative backends
# must compose): NullOutputImpl is the default Impl of both Interfaces, so
# a backend that lacks a method (the SSD1306 has no window events) gets a
# no-op.  Hardware libraries are imported lazily in open() (P9):
# pip install luma.oled (the SBC) or pygame (a desktop).
#
# Every output is driven from the Actor's event-loop thread: show() is
# bounded work (an I2C frame is ~25 ms at 400 kHz), pump() delivers window
# events to the Actor's handler there, and pygame must be pumped from the
# main thread, which the event loop is.
#
# To Do
# ~~~~~
# - Output worker thread for the SSD1306, if frame_ms measurements demand
# - PanelsOutputImpl: both panels as one display (Epic 1 phase 4)

from abc import abstractmethod
from dataclasses import dataclass
import importlib.util
import os
from pathlib import Path
import shutil
import sys
import time

from PIL import Image, ImageChops, ImageColor, ImageDraw

import aiko_services as aiko

from aiko_services.actors.display.graphics import HEIGHT, INK, WIDTH, blank

__all__ = [
    "ADDRESSES", "OUTPUTS", "Appearance", "DisplayNotFound", "FakeOutputImpl",
    "NullOutputImpl", "Output", "OutputControls", "PngOutputImpl",
    "Ssd1306OutputImpl", "TerminalOutputImpl", "WindowOutputImpl",
    "choose_output", "fake_output", "output_args", "parse_colors", "scan_i2c",
    "text_lines", "xterm_color",
]

ADDRESSES = (0x3C, 0x3D)  # the two addresses an SSD1306 can have (SA0 pin)
OUTPUTS = ("auto", "oled", "window", "terminal", "png", "none")
PNG_PERIOD = 1.0  # seconds between PNG files, at most

# SSD1306 raw commands, sent directly so the display memory is left alone
_INVERT, _NORMAL = 0xA7, 0xA6
_ALL_ON, _ALL_OFF = 0xA5, 0xA4

class DisplayNotFound(OSError):
    """The output can't be opened: no OLED at the I2C address, a library
    isn't installed, no desktop for a window, ..."""

# The emulation ------------------------------------------------------------ #

@dataclass
class Appearance:
    """How an emulated panel looks: the settings that change the picture.
    A value type (ADR-022 category Value and data types)"""

    powered: bool = True
    all_lit: bool = False
    inverted: bool = False
    brightness: int = 255
    foreground: tuple = (255, 255, 255)
    background: tuple = (0, 0, 0)

    def apply(self, frame):
        """The frame as the panel would show it"""

        if not self.powered:
            return blank(width=frame.width, height=frame.height)
        if self.all_lit:
            return blank(INK, width=frame.width, height=frame.height)
        return ImageChops.invert(frame) if self.inverted else frame

    def lit_color(self):
        """The foreground color, dimmed towards the background by the
        contrast (as far as a quarter)"""

        level = 0.25 + 0.75 * self.brightness / 255
        return tuple(round(back + (fore - back) * level)
            for fore, back in zip(self.foreground, self.background))

    def colored(self, image):
        """An RGB image of lit and unlit pixels in the colors, dimmed by
        the contrast"""

        lit = Image.new("RGB", image.size, self.lit_color())
        unlit = Image.new("RGB", image.size, self.background)
        return Image.composite(lit, unlit, image)

BRAILLE_DOTS = {(0, 0): 0x01, (0, 1): 0x02, (0, 2): 0x04, (1, 0): 0x08,
                (1, 1): 0x10, (1, 2): 0x20, (0, 3): 0x40, (1, 3): 0x80}

def text_lines(image, blocks=True):
    """A one-bit picture as rows of text: Unicode half blocks (2 pixel rows
    per character) or Braille dots (2x4 pixels per character)"""

    lit = image.load()
    if blocks:
        return ["".join(" ▀▄█"[(lit[x, y] > 0) + 2 * (lit[x, y + 1] > 0)]
            for x in range(image.width)) for y in range(0, image.height, 2)]
    return ["".join(chr(0x2800 + sum(bit
        for (dx, dy), bit in BRAILLE_DOTS.items() if lit[x + dx, y + dy]))
        for x in range(0, image.width, 2)) for y in range(0, image.height, 4)]

def xterm_color(rgb):
    """The nearest of the xterm 256 colors (the 6x6x6 color cube or the
    grey scale), which most terminals show"""

    levels = (0, 95, 135, 175, 215, 255)
    cube = [min(range(6), key=lambda i: abs(levels[i] - value)) for value in rgb]
    grey = min(range(24), key=lambda i: abs(8 + 10 * i - sum(rgb) / 3))

    def distance(color):
        return sum((a - b) ** 2 for a, b in zip(color, rgb))

    if distance([levels[i] for i in cube]) <= distance([8 + 10 * grey] * 3):
        return 16 + 36 * cube[0] + 6 * cube[1] + cube[2]
    return 232 + grey

# The Interfaces ----------------------------------------------------------- #

class Output(aiko.Interface):
    """
    Where frames go.  open() acquires the device and raises DisplayNotFound
    when it can't; show(image) puts a one-bit frame on it; pump() delivers
    the window's events ("quit" or (state, key)) to the handlers added with
    add_handler(); message(text) shows a status line where there is room;
    close(blank_first) releases the device.  Every method is local, called
    from the Actor's event-loop thread.  The attributes "name" (what -o
    names) and "device" (what was opened) are the share's backend and
    device.
    """

    aiko.Interface.default("Output", "aiko_services.actors.display.outputs.NullOutputImpl")

    @abstractmethod
    def open(self):
        """Acquire the device; raises DisplayNotFound"""

    @abstractmethod
    def show(self, image):
        """Show a one-bit PIL frame"""

    @abstractmethod
    def close(self, blank_first=True):
        """Release the device; blank the panel first, unless told not to"""

    @abstractmethod
    def pump(self):
        """Deliver the window's events since the last pump to the handlers"""

    @abstractmethod
    def add_handler(self, handler):
        """handler(event): "quit", or (state, key) with state "down", "up"
        or "tap" """

    @abstractmethod
    def message(self, text):
        """A status line beside the picture, where there is room for one"""

class OutputControls(aiko.Interface):
    """
    The glass: the panel's own settings.  An emulated output imitates them
    by changing the picture it shows; the SSD1306 sends its commands.
    """

    aiko.Interface.default(
        "OutputControls", "aiko_services.actors.display.outputs.NullOutputImpl")

    @abstractmethod
    def contrast(self, value):
        """Brightness 0..255"""

    @abstractmethod
    def invert(self, on):
        """Inverse video"""

    @abstractmethod
    def power(self, on):
        """Display sleep when off"""

    @abstractmethod
    def all_on(self, on):
        """Every pixel lit: a hardware test"""

    @abstractmethod
    def set_colors(self, foreground=None, background=None):
        """Colors of lit and unlit pixels (RGB tuples): emulated outputs"""

# The Impls ---------------------------------------------------------------- #

class NullOutputImpl(Output, OutputControls):
    """No output at all: the Actor still works (share, applets).  The
    default Impl of both Interfaces, so a backend that lacks a method gets
    a no-op.  Every no-op here must work without this __init__, because a
    composed backend runs its own.  The Appearance is kept, so the
    settings are still tracked"""

    name = "none"
    device = "none"

    def __init__(self, context, **_):
        self.appearance = Appearance()
        self.frame = blank()

    def open(self):
        pass

    def show(self, image):
        self.frame = image

    def close(self, blank_first=True):
        pass

    def pump(self):
        pass

    def add_handler(self, handler):
        pass  # no events ever: the handler is never called

    def message(self, text):
        pass

    def contrast(self, value):
        self.appearance.brightness = value

    def invert(self, on):
        self.appearance.inverted = on

    def power(self, on):
        self.appearance.powered = on

    def all_on(self, on):
        self.appearance.all_lit = on

    def set_colors(self, foreground=None, background=None):
        self.appearance.foreground = foreground or self.appearance.foreground
        self.appearance.background = background or self.appearance.background

class _Emulated:
    """The shared emulation for the outputs that draw a picture: the
    settings change the Appearance and the picture is rendered again.  A
    mixin of concrete methods, not an Impl: subclasses implement render()"""

    def _emulate(self):
        self.appearance = Appearance()
        self.frame = blank()
        self._handlers = []

    def show(self, image):
        self.frame = image
        self.render(self.appearance.apply(image))

    def _rerender(self):
        self.render(self.appearance.apply(self.frame))

    def render(self, image):
        """Put the image on view"""

    def contrast(self, value):
        self.appearance.brightness = value
        self._rerender()

    def invert(self, on):
        self.appearance.inverted = on
        self._rerender()

    def power(self, on):
        self.appearance.powered = on
        self._rerender()

    def all_on(self, on):
        self.appearance.all_lit = on
        self._rerender()

    def set_colors(self, foreground=None, background=None):
        self.appearance.foreground = foreground or self.appearance.foreground
        self.appearance.background = background or self.appearance.background
        self._rerender()

    def add_handler(self, handler):
        self._handlers.append(handler)

    def _deliver(self, events):
        for event in events:
            for handler in self._handlers:
                handler(event)

class FakeOutputImpl(_Emulated, Output, OutputControls):
    """Records every frame and control call: the test double.  "show_delay"
    imitates a slow device; "events" is what the next pump() delivers"""

    name = "fake"
    device = "fake"

    def __init__(self, context, show_delay=0.0, fail_open=False, **_):
        self._emulate()
        self.frames = []     # every frame shown, in order
        self.controls = []   # ("contrast", 128), ("power", False), ...
        self.show_delay = show_delay
        self.fail_open = fail_open
        self.opened = self.closed = False
        self.blanked = False
        self.events = []     # what pump() delivers next, e.g. ("tap", "g")

    def open(self):
        if self.fail_open:
            raise DisplayNotFound("fake output told to fail")
        self.opened = True

    def show(self, image):
        if self.show_delay:
            time.sleep(self.show_delay)
        self.frames.append(image.copy())
        super().show(image)

    def contrast(self, value):
        self.controls.append(("contrast", value))
        super().contrast(value)

    def invert(self, on):
        self.controls.append(("invert", on))
        super().invert(on)

    def power(self, on):
        self.controls.append(("power", on))
        super().power(on)

    def all_on(self, on):
        self.controls.append(("all_on", on))
        super().all_on(on)

    def set_colors(self, foreground=None, background=None):
        self.controls.append(("colors", foreground, background))
        super().set_colors(foreground, background)

    def pump(self):
        events, self.events = self.events, []
        self._deliver(events)

    def message(self, text):
        self.text = text

    def close(self, blank_first=True):
        self.closed, self.blanked = True, blank_first

    @property
    def foreground(self):
        return self.appearance.foreground

    @property
    def background(self):
        return self.appearance.background

class Ssd1306OutputImpl(Output, OutputControls):
    """The SSD1306 on an I2C bus, driven by luma.oled.  No window events
    and no message: the default Impl's no-ops"""

    name = "oled"
    device = "-"

    def __init__(self, context, address=ADDRESSES[0], bus=1, width=WIDTH,
                 height=HEIGHT, **_):
        self.address, self.bus = address, bus
        self.width, self.height = width, height
        self.appearance = Appearance()   # tracked, though the glass shows it
        self._device = None

    def open(self):
        try:
            from luma.core.error import DeviceNotFoundError
            from luma.core.interface.serial import i2c
            from luma.oled.device import ssd1306
        except ImportError as error:
            raise DisplayNotFound(
                f"luma.oled isn't installed ({error}): pip install luma.oled")
        try:
            serial = i2c(port=self.bus, address=self.address)
            self._device = ssd1306(serial, width=self.width, height=self.height)
        except (DeviceNotFoundError, OSError) as error:
            self._device = None
            raise DisplayNotFound(
                f"no SSD1306 at 0x{self.address:02X} on I2C bus {self.bus}: "
                f"{error}")
        self.device = f"ssd1306@0x{self.address:02X}/i2c{self.bus}"

    def show(self, image):
        self._device.display(image)

    def contrast(self, value):
        self.appearance.brightness = value
        self._device.contrast(value)

    def invert(self, on):
        self.appearance.inverted = on
        self._device.command(_INVERT if on else _NORMAL)

    def power(self, on):
        self.appearance.powered = on
        if on:
            self._device.show()
        else:
            self._device.hide()

    def all_on(self, on):
        self.appearance.all_lit = on
        self._device.command(_ALL_ON if on else _ALL_OFF)

    def set_colors(self, foreground=None, background=None):
        pass  # the panel's color is fixed in the glass

    def close(self, blank_first=True):
        if self._device is not None:
            if blank_first:
                self._device.display(blank(width=self.width, height=self.height))
                self._device.hide()
            self._device = None

def scan_i2c(bus=1, addresses=ADDRESSES):
    """The addresses that answer on the bus, for a hint when the OLED isn't
    found; [] when smbus2 isn't installed"""

    try:
        from smbus2 import SMBus
    except ImportError:
        return []
    found = []
    try:
        with SMBus(bus) as smbus:
            for address in addresses:
                try:
                    smbus.write_quick(address)
                    found.append(address)
                except OSError:
                    pass
    except OSError:
        pass
    return found

class WindowOutputImpl(_Emulated, Output, OutputControls):
    """An emulated panel in a desktop window (pygame), with dark gaps
    between the pixels.  Esc or closing the window is delivered as "quit";
    other keys as ("down"|"up", arrow) or ("tap", character).  Must be
    driven from the main thread"""

    name = "window"
    device = "pygame"

    def __init__(self, context, scale=5, **_):
        self._emulate()
        self.scale = scale
        self.pygame = None
        self._events = []

    def open(self):
        os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
        display = os.environ.get("DISPLAY", ":").split(":")[0]
        if sys.platform.startswith("linux") and display not in ("", "unix"):
            # A remote X display (ssh -X or -Y, e.g. to XQuartz on macOS):
            # SDL's GLX and shared memory don't work over the network, but
            # OpenGL through EGL (Mesa's software renderer) does
            os.environ.setdefault("SDL_VIDEO_X11_FORCE_EGL", "1")
            os.environ.setdefault("EGL_LOG_LEVEL", "fatal")
        try:
            import pygame
        except ImportError as error:
            raise DisplayNotFound(
                f"pygame isn't installed ({error}): pip install pygame")
        try:
            pygame.display.init()
            pygame.display.set_caption(
                f"Aiko Services: OLED {self.frame.width}x{self.frame.height}")
            size = (self.frame.width * self.scale, self.frame.height * self.scale)
            self._window = pygame.display.set_mode(size)
        except pygame.error as error:
            raise DisplayNotFound(f"no window: {error}")
        self.pygame = pygame
        self._grid = Image.new("1", size, INK)  # lit pixels, less a 1 px gap
        draw = ImageDraw.Draw(self._grid)
        for x in range(0, size[0], self.scale):
            draw.line((x, 0, x, size[1]), fill=0)
        for y in range(0, size[1], self.scale):
            draw.line((0, y, size[0], y), fill=0)
        self.render(self.frame)

    def render(self, image):
        if self.pygame is None:
            return
        size = self._grid.size
        lit = ImageChops.logical_and(image.resize(size, Image.NEAREST), self._grid)
        picture = self.appearance.colored(lit)
        surface = self.pygame.image.frombytes(picture.tobytes(), size, "RGB")
        self._window.blit(surface, (0, 0))
        self.pygame.display.flip()
        self._collect()

    def _collect(self):
        pygame = self.pygame
        arrows = {pygame.K_UP: "up", pygame.K_DOWN: "down",
                  pygame.K_LEFT: "left", pygame.K_RIGHT: "right"}
        for event in pygame.event.get():
            if event.type == pygame.QUIT or (
                    event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                self._events.append("quit")
            elif event.type in (pygame.KEYDOWN, pygame.KEYUP):
                state = "down" if event.type == pygame.KEYDOWN else "up"
                if event.key in arrows:
                    self._events.append((state, arrows[event.key]))
                elif state == "down" and len(event.unicode) == 1  \
                        and event.unicode.isprintable():
                    self._events.append(("tap", event.unicode))

    def pump(self):
        if self.pygame is not None:
            self._collect()
        events, self._events = self._events, []
        self._deliver(events)

    def close(self, blank_first=True):
        if self.pygame is not None:
            self.pygame.quit()
            self.pygame = None

class TerminalOutputImpl(_Emulated, Output, OutputControls):
    """An emulated panel in the terminal, drawn with Unicode half blocks:
    2 pixel rows per character, so 128x64 needs 128x34 characters; smaller
    terminals get Braille dots, 2x4 pixels per character (64x18)"""

    name = "terminal"
    device = "tty"

    def __init__(self, context, stream=None, **_):
        self._emulate()
        self._stream = stream
        self._message = ""
        self.blocks = True
        self._opened = False

    @property
    def stream(self):
        return self._stream or sys.stdout

    def open(self):
        columns, rows = shutil.get_terminal_size()
        self.blocks = columns >= self.frame.width and rows >= self.frame.height // 2 + 2
        self.stream.write("\x1b[2J\x1b[?25l")  # clear, hide the cursor
        self._opened = True
        self.render(self.frame)

    def lines(self, image):
        """The picture as lines of text (see text_lines)"""

        return text_lines(image, self.blocks)

    def render(self, image):
        if not self._opened:
            return
        colors = f"38;5;{xterm_color(self.appearance.lit_color())};"  \
                 f"48;5;{xterm_color(self.appearance.background)}"
        self.stream.write(f"\x1b[H\x1b[{colors}m" + "\n".join(self.lines(image))
            + f"\x1b[0m\n\x1b[K{self._message}")
        self.stream.flush()

    def pump(self):
        pass

    def message(self, text):
        self._message = text
        self._rerender()

    def close(self, blank_first=True):
        if self._opened:
            self.stream.write("\x1b[0m\x1b[?25h\n")  # colors and cursor back
            self.stream.flush()
            self._opened = False

class PngOutputImpl(_Emulated, Output, OutputControls):
    """The latest frame, saved as a PNG file at 4 times the size (at most
    once a second, and on close)"""

    name = "png"

    def __init__(self, context, path="oled.png", **_):
        self._emulate()
        self.path = str(path)
        self.device = f"png:{os.path.basename(self.path)}"
        self._saved_at = 0.0
        self._pending = None

    def open(self):
        pass

    def render(self, image):
        self._pending = image
        if time.monotonic() - self._saved_at >= PNG_PERIOD:
            self._save()

    def _save(self):
        if self._pending is not None:
            picture = self._pending.resize(
                (self._pending.width * 4, self._pending.height * 4), Image.NEAREST)
            self.appearance.colored(picture).save(self.path)
            self._saved_at = time.monotonic()
            self._pending = None

    def pump(self):
        pass

    def message(self, text):
        pass

    def close(self, blank_first=True):
        self._save()

# Composition -------------------------------------------------------------- #

def output_args(**parameters):
    """init_args for composing an output Impl (like ec_consumer_args)"""

    return {"context": aiko.Context(), **parameters}

def fake_output(**parameters):
    """A composed FakeOutputImpl: the test double"""

    return aiko.compose_instance(FakeOutputImpl, output_args(**parameters))

def parse_colors(text):
    """(foreground, background) RGB tuples from "yellow", "yellow navy" or
    "yellow,#101828"; background None when only one color is given.
    Raises ValueError"""

    names = str(text).replace(",", " ").split()
    if not 1 <= len(names) <= 2:
        raise ValueError(
            "give a foreground color and optionally a background color")
    colors = [ImageColor.getrgb(name)[:3] for name in names]
    return colors[0], (colors[1] if len(colors) == 2 else None)

def choose_output(output="auto", address=ADDRESSES[0], bus=1, png_path=None):
    """The composed output for an --output choice.  "auto": the OLED when
    the I2C bus exists, else a window when there is a desktop and pygame,
    else the terminal.  Nothing is imported or opened here: see open()"""

    if output == "auto":
        has_desktop = sys.platform == "darwin" or os.environ.get("DISPLAY")  \
            or os.environ.get("WAYLAND_DISPLAY")
        if Path(f"/dev/i2c-{bus}").exists():
            output = "oled"
        elif has_desktop and importlib.util.find_spec("pygame"):
            output = "window"
        else:
            output = "terminal"
    impls = {
        "oled": (Ssd1306OutputImpl, {"address": address, "bus": bus}),
        "window": (WindowOutputImpl, {}),
        "terminal": (TerminalOutputImpl, {}),
        "png": (PngOutputImpl, {"path": png_path or "oled.png"}),
        "none": (NullOutputImpl, {}),
        "fake": (FakeOutputImpl, {}),
    }
    if output not in impls:
        raise ValueError(f"unknown output {output!r}: one of {OUTPUTS}")
    impl, parameters = impls[output]
    return aiko.compose_instance(impl, output_args(**parameters))
