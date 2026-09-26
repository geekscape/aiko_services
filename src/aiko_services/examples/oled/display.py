#!/usr/bin/env python3
#
# Aiko Services: OLED display backends
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# Where the OLED Actor's frames go: the SSD1306 on the Raspberry Pi's I2C
# bus (luma.oled), or an emulated OLED in a desktop window (pygame), in the
# terminal (Unicode half blocks), in a PNG file, nowhere (none), or a fake
# that records everything (tests).  The emulated displays imitate the
# panel's contrast, invert, power and all-pixels-on settings by changing
# the picture they show.
#
# Every backend is driven from the Actor's event-loop thread: show() is
# bounded work (an I2C frame is ~25 ms at 400 kHz), and pygame must be
# pumped from the main thread, which the event loop is.
#
# Not part of the Interface composition pattern (see ADR-022): a
# presentation seam injected into the Actor through parameters["display"],
# like StoreForwardMessage.  Hardware libraries are imported lazily in
# open() (P9): pip install luma.oled (Raspberry Pi) or pygame (desktop).
#
# To Do
# ~~~~~
# - Display worker thread for the SSD1306, if frame_ms measurements demand
# - Second panel (0x3C and 0x3D), one Actor per panel

import importlib.util
import os
from pathlib import Path
import shutil
import sys
import time

from PIL import Image, ImageChops, ImageColor, ImageDraw

from aiko_services.examples.oled.graphics import HEIGHT, INK, WIDTH, blank

__all__ = [
    "ADDRESSES", "OUTPUTS", "Display", "DisplayNotFound", "FakeDisplay",
    "NullDisplay", "PngDisplay", "Ssd1306Display", "TerminalDisplay",
    "WindowDisplay", "choose_display", "parse_colors", "scan_i2c",
]

ADDRESSES = (0x3C, 0x3D)  # the two addresses an SSD1306 can have (SA0 pin)
OUTPUTS = ("auto", "oled", "window", "terminal", "png", "none")
PNG_PERIOD = 1.0  # seconds between PNG files, at most

# SSD1306 raw commands, sent directly so the display memory is left alone
_INVERT, _NORMAL = 0xA7, 0xA6
_ALL_ON, _ALL_OFF = 0xA5, 0xA4

class DisplayNotFound(OSError):
    """The display can't be opened: no OLED at the I2C address, a library
    isn't installed, no desktop for a window, ..."""

# --------------------------------------------------------------------------- #

class Display:
    """A place to show 128x64 one-bit frames.  The base class keeps the
    emulated appearance (invert, power, all pixels on, brightness, colors)
    and renders nothing: subclasses render()"""

    name = "base"
    device = "-"  # what was opened, e.g. "ssd1306@0x3C/i2c1"

    def __init__(self):
        self.frame = blank()
        self.powered, self.all_lit, self.inverted = True, False, False
        self.brightness = 255
        self.foreground, self.background = (255, 255, 255), (0, 0, 0)

    def open(self):
        """Acquire the device; raises DisplayNotFound"""

    def show(self, image):
        self.frame = image
        self.render(self.appearance())

    def contrast(self, value):
        self.brightness = value
        self.render(self.appearance())

    def invert(self, on):
        self.inverted = on
        self.render(self.appearance())

    def power(self, on):
        self.powered = on
        self.render(self.appearance())

    def all_on(self, on):
        self.all_lit = on
        self.render(self.appearance())

    def set_colors(self, foreground=None, background=None):
        """Colors of lit and unlit pixels (RGB tuples): emulated displays"""

        self.foreground = foreground or self.foreground
        self.background = background or self.background
        self.render(self.appearance())

    def poll(self):
        """Window events since the last poll: "quit" or (state, key)"""

        return []

    def message(self, text):
        """A status line beside the picture, where there is room for one"""

    def close(self, blank_first=True):
        """Release the device; blank the panel first, unless told not to"""

    # Emulation helpers --------------------------------------------------- #

    def appearance(self):
        """The frame as the panel would show it"""

        if not self.powered:
            return blank()
        if self.all_lit:
            return blank(INK)
        return ImageChops.invert(self.frame) if self.inverted else self.frame

    def render(self, image):
        """Put the image on view"""

    def colored(self, image):
        """An RGB image of lit and unlit pixels in the display's colors,
        dimmed by the contrast"""

        lit = Image.new("RGB", image.size, self.lit_color())
        unlit = Image.new("RGB", image.size, self.background)
        return Image.composite(lit, unlit, image)

    def lit_color(self):
        """The foreground color, dimmed towards the background by the
        contrast (as far as a quarter)"""

        level = 0.25 + 0.75 * self.brightness / 255
        return tuple(round(back + (fore - back) * level)
            for fore, back in zip(self.foreground, self.background))

class FakeDisplay(Display):
    """Records every frame and control call: the test double.  "show_delay"
    imitates a slow device"""

    name = "fake"
    device = "fake"

    def __init__(self, show_delay=0.0, fail_open=False):
        super().__init__()
        self.frames = []     # every frame shown, in order
        self.controls = []   # ("contrast", 128), ("power", False), ...
        self.show_delay = show_delay
        self.fail_open = fail_open
        self.opened = self.closed = False
        self.blanked = False

    def open(self):
        if self.fail_open:
            raise DisplayNotFound("fake display told to fail")
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

    def close(self, blank_first=True):
        self.closed, self.blanked = True, blank_first

class NullDisplay(Display):
    """No display at all: the Actor still works (share, applets)"""

    name = "none"
    device = "none"

# --------------------------------------------------------------------------- #

class Ssd1306Display(Display):
    """The SSD1306 on an I2C bus, driven by luma.oled"""

    name = "oled"

    def __init__(self, address=ADDRESSES[0], bus=1, width=WIDTH, height=HEIGHT):
        super().__init__()
        self.address, self.bus = address, bus
        self.width, self.height = width, height
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
        self.frame = image
        self._device.display(image)

    def contrast(self, value):
        self.brightness = value
        self._device.contrast(value)

    def invert(self, on):
        self.inverted = on
        self._device.command(_INVERT if on else _NORMAL)

    def power(self, on):
        self.powered = on
        if on:
            self._device.show()
        else:
            self._device.hide()

    def all_on(self, on):
        self.all_lit = on
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

# --------------------------------------------------------------------------- #

class WindowDisplay(Display):
    """An emulated OLED in a desktop window (pygame), with dark gaps between
    the pixels.  Esc or closing the window is reported by poll() as "quit";
    other keys as ("down"|"up", name).  Must be driven from the main thread"""

    name = "window"
    device = "pygame"
    SCALE = 5

    def __init__(self):
        super().__init__()
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
            pygame.display.set_caption("Aiko Services: OLED 128x64")
            size = (WIDTH * self.SCALE, HEIGHT * self.SCALE)
            self._window = pygame.display.set_mode(size)
        except pygame.error as error:
            raise DisplayNotFound(f"no window: {error}")
        self.pygame = pygame
        self._grid = Image.new("1", size, INK)  # lit pixels, less a 1 px gap
        draw = ImageDraw.Draw(self._grid)
        for x in range(0, size[0], self.SCALE):
            draw.line((x, 0, x, size[1]), fill=0)
        for y in range(0, size[1], self.SCALE):
            draw.line((0, y, size[0], y), fill=0)
        self.render(blank())

    def render(self, image):
        if self.pygame is None:
            return
        size = self._grid.size
        lit = ImageChops.logical_and(image.resize(size, Image.NEAREST), self._grid)
        picture = self.colored(lit)
        surface = self.pygame.image.frombytes(picture.tobytes(), size, "RGB")
        self._window.blit(surface, (0, 0))
        self.pygame.display.flip()
        self._pump()

    def _pump(self):
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

    def poll(self):
        if self.pygame is not None:
            self._pump()
        events, self._events = self._events, []
        return events

    def close(self, blank_first=True):
        if self.pygame is not None:
            self.pygame.quit()
            self.pygame = None

# --------------------------------------------------------------------------- #

BRAILLE_DOTS = {(0, 0): 0x01, (0, 1): 0x02, (0, 2): 0x04, (1, 0): 0x08,
                (1, 1): 0x10, (1, 2): 0x20, (0, 3): 0x40, (1, 3): 0x80}

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

class TerminalDisplay(Display):
    """An emulated OLED in the terminal, drawn with Unicode half blocks:
    2 pixel rows per character, so it needs 128x34 characters; smaller
    terminals get Braille dots, 2x4 pixels per character (64x18)"""

    name = "terminal"
    device = "tty"

    def __init__(self, stream=None):
        super().__init__()
        self._stream = stream
        self._message = ""
        self.blocks = True
        self._opened = False

    @property
    def stream(self):
        return self._stream or sys.stdout

    def open(self):
        columns, rows = shutil.get_terminal_size()
        self.blocks = columns >= WIDTH and rows >= HEIGHT // 2 + 2
        self.stream.write("\x1b[2J\x1b[?25l")  # clear, hide the cursor
        self._opened = True
        self.render(blank())

    def lines(self, image):
        """The picture as lines of text"""

        lit = image.load()
        if self.blocks:
            return ["".join(" ▀▄█"[(lit[x, y] > 0) + 2 * (lit[x, y + 1] > 0)]
                for x in range(image.width)) for y in range(0, image.height, 2)]
        return ["".join(chr(0x2800 + sum(bit
            for (dx, dy), bit in BRAILLE_DOTS.items() if lit[x + dx, y + dy]))
            for x in range(0, image.width, 2)) for y in range(0, image.height, 4)]

    def render(self, image):
        if not self._opened:
            return
        colors = f"38;5;{xterm_color(self.lit_color())};"  \
                 f"48;5;{xterm_color(self.background)}"
        self.stream.write(f"\x1b[H\x1b[{colors}m" + "\n".join(self.lines(image))
            + f"\x1b[0m\n\x1b[K{self._message}")
        self.stream.flush()

    def message(self, text):
        self._message = text
        self.render(self.appearance())

    def close(self, blank_first=True):
        if self._opened:
            self.stream.write("\x1b[0m\x1b[?25h\n")  # colors and cursor back
            self.stream.flush()
            self._opened = False

class PngDisplay(Display):
    """The latest frame, saved as a PNG file at 4 times the size (at most
    once a second, and on close)"""

    name = "png"

    def __init__(self, path):
        super().__init__()
        self.path = str(path)
        self.device = f"png:{os.path.basename(self.path)}"
        self._saved_at = 0.0
        self._pending = None

    def render(self, image):
        self._pending = image
        if time.monotonic() - self._saved_at >= PNG_PERIOD:
            self._save()

    def _save(self):
        if self._pending is not None:
            picture = self._pending.resize((WIDTH * 4, HEIGHT * 4), Image.NEAREST)
            self.colored(picture).save(self.path)
            self._saved_at = time.monotonic()
            self._pending = None

    def close(self, blank_first=True):
        self._save()

# --------------------------------------------------------------------------- #

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

def choose_display(output="auto", address=ADDRESSES[0], bus=1,
    png_path=None, colors=None):
    """The backend for an --output choice.  "auto": the OLED when the I2C
    bus exists, else a window when there is a desktop and pygame, else the
    terminal.  Nothing is imported or opened here: see Display.open()"""

    if output == "auto":
        has_desktop = sys.platform == "darwin" or os.environ.get("DISPLAY")  \
            or os.environ.get("WAYLAND_DISPLAY")
        if Path(f"/dev/i2c-{bus}").exists():
            output = "oled"
        elif has_desktop and importlib.util.find_spec("pygame"):
            output = "window"
        else:
            output = "terminal"
    if output == "oled":
        display = Ssd1306Display(address, bus)
    elif output == "window":
        display = WindowDisplay()
    elif output == "terminal":
        display = TerminalDisplay()
    elif output == "png":
        display = PngDisplay(png_path or "oled.png")
    elif output == "none":
        display = NullDisplay()
    elif output == "fake":
        display = FakeDisplay()
    else:
        raise ValueError(f"unknown output {output!r}: one of {OUTPUTS}")
    if colors:
        display.set_colors(*colors)
    return display
