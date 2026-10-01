#!/usr/bin/env python3
#
# Install, in a Python virtual environment:
#   Raspberry Pi with the OLED on I2C:            pip install luma.oled click psutil
#     The OLED library is "luma.oled" (which brings luma.core, smbus2 and Pillow).
#     Not "luma": that's an unrelated command line tool for the Lumavate platform.
#   macOS or Linux desktop, emulating the OLED:   pip install click pillow psutil pygame
#     pygame is optional: without it, the OLED is emulated in the terminal.
"""SSD1306 128x64 OLED test tool: screen control, test pattern, text, drawings, games and system status.

On a Raspberry Pi the OLED is driven over I2C; on macOS or a Linux desktop it is emulated in a window or the terminal.

\b
Examples:
  oled_test.py screen on                  # light every pixel (hardware test)
  oled_test.py -a 0x3D pattern            # display at I2C address 0x3D
  oled_test.py -fs 10 text hello          # a message in a 10 pixel font
  oled_test.py draw --no-shade            # outline drawings only
  oled_test.py game invaders
  oled_test.py system -r 2                # status, updated twice a second
  oled_test.py demo                       # a random tour of everything
  oled_test.py -o terminal game pong      # emulate the OLED in the terminal
  oled_test.py -c 'yellow navy' draw      # yellow on navy (emulated displays)
  oled_test.py --preview p.png pattern    # save a PNG instead of using the display
"""

import functools
import importlib.util
import itertools
import math
import os
import random
import re
import select
import shutil
import socket
import sys
import textwrap
import time
from datetime import datetime
from pathlib import Path

import click
from PIL import Image, ImageChops, ImageColor, ImageDraw, ImageFilter, ImageFont

WIDTH, HEIGHT = 128, 64
I2C_BUS = 1
ADDRESSES = (0x3C, 0x3D)  # the two addresses an SSD1306 can have (set by its SA0 pin)
SANS_FONTS = ("DejaVuSans.ttf", "Verdana.ttf", "Arial.ttf", "Helvetica.ttc")  # Linux first, then macOS
MONO_FONTS = ("DejaVuSansMono.ttf", "Menlo.ttc", "Monaco.ttf", "Courier New.ttf")
INK = 255

# Keys that switch to a subcommand (run with its default options) while any subcommand is running
KEY_COMMANDS = {"D": "demo", "d": "draw", "F": "forklift", "g": "game", "p": "pattern", "S": "screen", "s": "system",
                "t": "text"}
QUIT_KEYS, HELP_KEY, FONT_KEY, RESET_KEY = "xq", "h", "f", "R"  # R: back to the starting colors, font and speed
COLOR_KEYS = "cC"  # next foreground, next background color (emulated displays only)
FOREGROUNDS = ("white", "deepskyblue", "yellow", "lime", "orange", "hotpink")
BACKGROUNDS = ("black", "midnightblue", "darkslategray", "maroon", "dimgray", "white")
FONT_SIZES = ("5x7", 8, 10, 12, 16, 20, 24)  # what "f" steps through
SPEED_KEYS = "0123456789"  # 0 fastest ... 4 normal ... 9 slowest
ARROWS = {"A": "up", "B": "down", "C": "right", "D": "left"}  # the last letters of the terminal's arrow key codes
ARROW_HOLD = 0.1  # seconds that a typed arrow key counts as held: key repeat keeps it held (terminals have no key up)
HELP_LINES = ["h help    x,q quit", "D demo    d draw", "F forklift g game", "p pattern S screen", "s system  t text",
              "again: next options", "0-9 speed  R reset", "c,C color  f font"]

# Classic 5x7 font for " " to "~": 5 columns per character, bit 0 is the top row
FONT_5X7 = bytes.fromhex("""
    0000000000 00005f0000 0007000700 147f147f14 242a7f2a12 2313086462 3649552250 0005030000
    001c224100 0041221c00 082a1c2a08 08083e0808 0050300000 0808080808 0060600000 2010080402
    3e5149453e 00427f4000 4261514946 2141454b31 1814127f10 2745454539 3c4a494930 0171090503
    3649494936 064949291e 0036360000 0056360000 0008142241 1414141414 4122140800 0201510906
    324979413e 7e1111117e 7f49494936 3e41414122 7f4141221c 7f49494941 7f09090101 3e41415132
    7f0808087f 00417f4100 2040413f01 7f08142241 7f40404040 7f0204027f 7f0408107f 3e4141413e
    7f09090906 3e4151215e 7f09192946 4649494931 01017f0101 3f4040403f 1f2040201f 7f2018207f
    6314081463 0304780403 6151494543 00007f4141 0204081020 41417f0000 0402010204 4040404040
    0001020400 2054545478 7f48444438 3844444420 384444487f 3854545418 087e090102 081454543c
    7f08040478 00447d4000 2040443d00 007f102844 00417f4000 7c04180478 7c08040478 3844444438
    7c14141408 081414187c 7c08040408 4854545420 043f444020 3c4040207c 1c2040201c 3c4030403c
    4428102844 0c5050503c 4464544c44 0008364100 00007f0000 0041360800 0804040804
""")

# Raw commands, sent directly so the display memory (the current image) is left alone
SCREEN_COMMANDS = {
    "on": [0xAE, 0xD5, 0x80, 0x8D, 0x14, 0xAF, 0xA5],  # light every pixel, ignoring display memory
    "off": [0xA4, 0xAE],  # display off (sleep); display memory is kept
    "show": [0x8D, 0x14, 0xAF, 0xA4],  # display on, showing display memory again
    "invert": [0xA7],
    "normal": [0xA6],
}


def find_truetype(size, mono):
    """The first of the fonts that is installed (Pillow searches the system's font folders), else Pillow's own."""
    for name in MONO_FONTS if mono else SANS_FONTS:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default(size)


class Font:
    """The built-in 5x7 bitmap font, or a TrueType font (DejaVu Sans on Linux) at a size in pixels."""

    def __init__(self, size, mono=False):
        self.size = size
        self.truetype = None
        if size != "5x7":
            self.truetype = find_truetype(size, mono)
        # The rows that letters use, from the top of capitals to the bottom of descenders
        _, self.top, _, self.bottom = (0, 0, 0, 7) if size == "5x7" else self.render("Ajgy").getbbox()
        self.line_height = self.bottom - self.top

    def mono(self):
        """This font with every character the same width."""
        return self if self.truetype is None else Font(self.size, mono=True)

    def render(self, text):
        """Image of the text, as wide as the text and as high as the font."""
        if self.truetype is None:
            image = Image.new("1", (max(1, 6 * len(text) - 1), 7))
            for i, char in enumerate(text):
                code = ord(char if " " <= char <= "~" else "?") - 32
                for column, bits in enumerate(FONT_5X7[5 * code:5 * code + 5]):
                    for row in range(7):
                        if bits >> row & 1:
                            image.putpixel((6 * i + column, row), INK)
            return image
        ascent, descent = self.truetype.getmetrics()
        image = Image.new("1", (max(1, math.ceil(self.truetype.getlength(text))), ascent + descent))
        ImageDraw.Draw(image).text((0, 0), text, font=self.truetype, fill=INK)
        return image

    def render_line(self, text):
        """Image of the text, trimmed to the rows that letters use, for laying out lines."""
        image = self.render(text)
        return image.crop((0, self.top, image.width, self.bottom))


class OledNotFound(OSError):
    """The OLED doesn't answer at its I2C address."""


class TimeUp(Exception):
    """The display's deadline has passed (it ends each step of the demo)."""


class FontChange(Exception):
    """The font was changed ("f" or "R") while a finished picture was on view: draw it again in the new font."""


class KeyPress(Exception):
    """A command key was typed: stop what's running and act on the key."""

    def __init__(self, key):
        super().__init__(key)
        self.key = key


class Keyboard:
    """Keys typed in the terminal, read as they're typed without waiting (stdin in cbreak mode)."""

    def __init__(self):
        import termios
        import tty
        self.termios = termios
        self.saved = termios.tcgetattr(sys.stdin)
        tty.setcbreak(sys.stdin)  # no Enter needed and no echo; Ctrl-C still works

    @classmethod
    def open(cls):
        """A Keyboard, or None when stdin isn't a terminal (e.g. a command run over ssh without -t)."""
        return cls() if sys.stdin.isatty() else None

    def read(self):
        """The keys typed since the last read: characters, or "up", "down", "left" or "right" for arrow keys."""
        typed = b""
        while select.select([sys.stdin], [], [], 0)[0] and (byte := os.read(sys.stdin.fileno(), 1)):
            typed += byte
        keys = []
        for key in re.findall(r"\x1b(?:\[[0-9;]*[A-Za-z~]|O[A-Za-z])?|.", typed.decode(errors="ignore"), re.DOTALL):
            if not key.startswith("\x1b"):
                keys.append(key)
            elif len(key) > 1 and key[-1] in ARROWS:  # (other escape codes, e.g. function keys, are dropped)
                keys.append(ARROWS[key[-1]])
        return keys

    def close(self):
        self.termios.tcsetattr(sys.stdin, self.termios.TCSADRAIN, self.saved)


class Display:
    """Where the images go: subclasses show them on the OLED, in a desktop window, in the terminal or in a PNG file.

    Commands draw 128x64 one-bit images and show() them; screen() and contrast() change how the screen shows them.
    The emulated displays (all but the OLED) imitate those settings by changing the picture they show.
    """

    live = True  # False when only the final image matters (a PNG file)
    keeps_image = False  # True when the image stays on the display after the program ends (the OLED)
    stays_open = False  # True when the display goes when the program ends, so hold() keeps it open
    deadline = None  # when set, show(), wait() and hold() raise TimeUp once time.monotonic() passes it
    keyboard = None  # the Keyboard, when stdin is a terminal
    time_scale = 1.0  # set by the speed keys: multiplies drawing times, frame intervals and update intervals
    foreground, background = (255, 255, 255), (0, 0, 0)  # RGB colors of lit and unlit pixels (emulated displays)

    def __init__(self, font):
        self.font = self.base_font = self.starting_font = font  # base: from -fs, "f" or "R"; commands can override it
        self.starting_colors = (self.foreground, self.background)  # what "R" goes back to
        self.frame = blank()
        self.color_turns = {}  # how far each color key has stepped through its list
        self.holding = False  # True while hold() shows a finished picture
        self.arrow_until = {}  # arrow key: until when it counts as held
        self.powered, self.all_lit, self.inverted, self.brightness = True, False, False, 255

    def show(self, image):
        self.frame = image
        self.put(image)
        self.poll()
        if self.deadline and time.monotonic() >= self.deadline:
            raise TimeUp

    def put(self, image):
        """Send a new image to the screen."""
        self.render(self.appearance())

    def screen(self, action):
        """Imitate the OLED's screen commands (see SCREEN_COMMANDS), or clear the image."""
        if action == "clear":
            self.frame = blank()
        elif action in ("on", "off", "show"):
            self.powered, self.all_lit = action != "off", action == "on"
        else:
            self.inverted = action == "invert"
        self.render(self.appearance())

    def contrast(self, value):
        self.brightness = value
        self.render(self.appearance())

    def appearance(self):
        """The image as the screen shows it."""
        if not self.powered:
            return blank()
        if self.all_lit:
            return blank(INK)
        return ImageChops.invert(self.frame) if self.inverted else self.frame

    def render(self, image):
        """Put the image on view."""

    def status(self, message):
        click.echo(message)

    def set_colors(self, foreground=None, background=None):
        """Change the colors of lit and/or unlit pixels (RGB tuples)."""
        self.foreground, self.background = foreground or self.foreground, background or self.background
        self.render(self.appearance())

    def colored(self, image):
        """An RGB image of lit and unlit pixels in the display's colors, dimmed by the contrast."""
        return Image.composite(Image.new("RGB", image.size, self.lit_color()), Image.new("RGB", image.size, self.background), image)

    def lit_color(self):
        """The foreground color, dimmed towards the background by the contrast (as far as a quarter)."""
        level = 0.25 + 0.75 * self.brightness / 255
        return tuple(round(back + (fore - back) * level) for fore, back in zip(self.foreground, self.background))

    def poll(self):
        """Act on typed keys: raise KeyPress for a command key."""
        for key in self.read_keys():
            if key in ARROWS.values():
                self.arrow_until[key] = time.monotonic() + ARROW_HOLD
            elif key in SPEED_KEYS:
                self.time_scale = 2 ** ((int(key) - 4) / 2)  # 0: a quarter of the time, 4: normal, 9: 5.7 times
                words = {"0": "fastest", "4": "normal", "9": "slowest"}.get(key, f"time x{self.time_scale:.2g}")
                self.status(f"Speed {key} ({words})")
            elif key in COLOR_KEYS:
                names = FOREGROUNDS if key == "c" else BACKGROUNDS
                self.color_turns[key] = (self.color_turns.get(key, -1) + 1) % len(names)
                name = names[self.color_turns[key]]
                self.set_colors(**{"foreground" if key == "c" else "background": ImageColor.getrgb(name)})
                if not self.keeps_image:  # the OLED says instead that its color is fixed
                    self.status(f"Color {key}: {'foreground' if key == 'c' else 'background'} {name}")
            elif key == FONT_KEY:
                sizes = [str(size) for size in FONT_SIZES]
                turn = sizes.index(str(self.base_font.size)) + 1 if str(self.base_font.size) in sizes else 0
                self.status(f"Key f: font size {FONT_SIZES[turn % len(FONT_SIZES)]}")
                self.change_font(Font(FONT_SIZES[turn % len(FONT_SIZES)]))
            elif key == RESET_KEY:
                if not self.keeps_image:  # (the OLED's color is fixed)
                    self.set_colors(*self.starting_colors)
                self.color_turns, self.time_scale = {}, 1.0
                self.status(f"Key R: reset to the starting colors, font size {self.starting_font.size} and speed 4")
                self.change_font(self.starting_font)
            elif key in KEY_COMMANDS or key in QUIT_KEYS + HELP_KEY:
                raise KeyPress(key)

    def change_font(self, font):
        """Use this font from now on.  Running animations pick it up as they go; a finished picture is redrawn."""
        self.font = self.base_font = font
        if self.holding:
            raise FontChange

    def read_keys(self):
        return self.keyboard.read() if self.keyboard else []

    def arrows_held(self):
        """The arrow keys held down now ("up", "down", "left", "right")."""
        now = time.monotonic()
        return {key for key, until in self.arrow_until.items() if until > now}

    def reset(self):
        """Undo any screen settings: display on, not inverted, full contrast."""
        for action in ("show", "normal"):
            self.screen(action)
        self.contrast(255)

    def wait(self, seconds):
        end = time.monotonic() + seconds if self.deadline is None else min(time.monotonic() + seconds, self.deadline)
        while (left := end - time.monotonic()) > 0:
            time.sleep(min(left, 0.02))
            self.poll()
        if self.deadline and time.monotonic() >= self.deadline:
            raise TimeUp

    def hold(self):
        """After a one-off command: wait for the deadline, if there is one, or else, when keys can be typed or the
        display would go when the program ends, wait for a key, the window to close or Ctrl-C."""
        self.holding = True
        try:
            while self.deadline or self.stays_open or self.keyboard:  # with a keyboard, wait for keys
                self.wait(3600)
        finally:
            self.holding = False

    def close(self):
        pass


class Oled(Display):
    """The SSD1306 on the Raspberry Pi's I2C bus, driven by luma.oled."""

    keeps_image = True

    def __init__(self, font, address):
        super().__init__(font)
        self.address = address
        self._device = None

    def put(self, image):
        if self._device is None:
            from luma.core.error import DeviceNotFoundError
            from luma.core.interface.serial import i2c
            from luma.oled.device import ssd1306
            try:
                self._device = ssd1306(i2c(port=I2C_BUS, address=self.address), width=WIDTH, height=HEIGHT)
            except DeviceNotFoundError as error:
                raise OledNotFound(str(error)) from error
            self._device.persist = True  # leave the last image on screen at exit
        self._device.display(image)

    def screen(self, action):
        if action == "clear":
            self.show(blank())
        else:
            self.command(*SCREEN_COMMANDS[action])

    def contrast(self, value):
        self.command(0x81, value)

    def set_colors(self, foreground=None, background=None):
        self.status("Colors only change emulated displays: the OLED's color is fixed")

    def command(self, *commands):
        from smbus2 import SMBus
        try:
            with SMBus(I2C_BUS) as bus:
                for command in commands:
                    bus.write_byte_data(self.address, 0x00, command)
        except OSError as error:
            raise OledNotFound(f"No reply from address 0x{self.address:02X}: {error}") from error


class Window(Display):
    """An emulated OLED in a desktop window (pygame), with dark gaps between the pixels.  Esc closes it."""

    stays_open = True
    SCALE = 5

    def __init__(self, font):
        super().__init__(font)
        os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
        if sys.platform.startswith("linux") and os.environ.get("DISPLAY", ":").split(":")[0] not in ("", "unix"):
            # A remote X display (ssh -X or -Y, e.g. to XQuartz on macOS): SDL's GLX and shared memory (MIT-SHM)
            # don't work over the network, but OpenGL through EGL (Mesa's software renderer) does
            os.environ.setdefault("SDL_VIDEO_X11_FORCE_EGL", "1")
            os.environ.setdefault("EGL_LOG_LEVEL", "fatal")  # (no warning that it isn't accelerated)
        import pygame
        self.pygame = pygame
        pygame.display.init()
        pygame.display.set_caption("SSD1306 128x64 OLED")
        size = (WIDTH * self.SCALE, HEIGHT * self.SCALE)
        self.window = pygame.display.set_mode(size)
        self.grid = Image.new("1", size, INK)  # where lit pixels show: each pixel less a 1 pixel gap
        draw = ImageDraw.Draw(self.grid)
        for x in range(0, size[0], self.SCALE):
            draw.line((x, 0, x, size[1]), fill=0)
        for y in range(0, size[1], self.SCALE):
            draw.line((0, y, size[0], y), fill=0)
        self.render(blank())

    def render(self, image):
        size = self.grid.size
        lit = ImageChops.logical_and(image.resize(size, Image.NEAREST), self.grid)
        picture = self.colored(lit)
        self.window.blit(self.pygame.image.frombytes(picture.tobytes(), size, "RGB"), (0, 0))
        self.pygame.display.flip()
        self.poll()

    def read_keys(self):
        keys = super().read_keys()
        for event in self.pygame.event.get():
            if event.type == self.pygame.QUIT or (event.type == self.pygame.KEYDOWN and event.key == self.pygame.K_ESCAPE):
                raise KeyboardInterrupt
            if event.type == self.pygame.KEYDOWN:
                keys += [self.arrow_keys()[event.key]] if event.key in self.arrow_keys() else list(event.unicode)
        return keys

    def arrow_keys(self):
        return {self.pygame.K_UP: "up", self.pygame.K_DOWN: "down", self.pygame.K_LEFT: "left", self.pygame.K_RIGHT: "right"}

    def arrows_held(self):  # a window knows which keys are down
        pressed = self.pygame.key.get_pressed()
        return super().arrows_held() | {name for code, name in self.arrow_keys().items() if pressed[code]}

    def close(self):
        self.pygame.quit()


BRAILLE_DOTS = {(0, 0): 0x01, (0, 1): 0x02, (0, 2): 0x04, (1, 0): 0x08, (1, 1): 0x10, (1, 2): 0x20, (0, 3): 0x40, (1, 3): 0x80}


class Terminal(Display):
    """An emulated OLED in the terminal, drawn with Unicode half blocks: 2 pixel rows per character, so it needs
    128x34 characters; smaller terminals get Braille dots, 2x4 pixels per character (64x18 characters)."""

    stays_open = True
    def __init__(self, font):
        super().__init__(font)
        columns, rows = shutil.get_terminal_size()
        self.blocks = columns >= WIDTH and rows >= HEIGHT // 2 + 2
        self.message = ""
        sys.stdout.write("\x1b[2J\x1b[?25l")  # clear the screen and hide the cursor
        self.render(blank())

    def render(self, image):
        lit = image.load()
        if self.blocks:
            lines = ["".join(" ▀▄█"[(lit[x, y] > 0) + 2 * (lit[x, y + 1] > 0)] for x in range(WIDTH))
                     for y in range(0, HEIGHT, 2)]
        else:
            lines = ["".join(chr(0x2800 + sum(bit for (dx, dy), bit in BRAILLE_DOTS.items() if lit[x + dx, y + dy]))
                             for x in range(0, WIDTH, 2)) for y in range(0, HEIGHT, 4)]
        colors = f"38;5;{xterm_color(self.lit_color())};48;5;{xterm_color(self.background)}"
        sys.stdout.write(f"\x1b[H\x1b[{colors}m" + "\n".join(lines) + f"\x1b[0m\n\x1b[K{self.message}")
        sys.stdout.flush()

    def status(self, message):
        self.message = message
        self.render(self.appearance())

    def close(self):
        sys.stdout.write("\x1b[0m\x1b[?25h\n")  # restore the colours and the cursor


def xterm_color(rgb):
    """The nearest of the xterm 256 colors (the 6x6x6 color cube or the grey scale), which most terminals show."""
    levels = (0, 95, 135, 175, 215, 255)
    cube = [min(range(6), key=lambda i: abs(levels[i] - value)) for value in rgb]
    grey = min(range(24), key=lambda i: abs(8 + 10 * i - sum(rgb) / 3))
    def distance(color):
        return sum((a - b) ** 2 for a, b in zip(color, rgb))
    if distance([levels[i] for i in cube]) <= distance([8 + 10 * grey] * 3):
        return 16 + 36 * cube[0] + 6 * cube[1] + cube[2]
    return 232 + grey


class Png(Display):
    """The final image, saved as a PNG file at 4 times the size."""

    live = False

    def __init__(self, font, path):
        super().__init__(font)
        self.path = path

    def close(self):
        self.colored(self.appearance().resize((WIDTH * 4, HEIGHT * 4), Image.NEAREST)).save(self.path)

def blank(fill=0):
    return Image.new("1", (WIDTH, HEIGHT), fill)


def pixels(lit):
    """Image with the pixels lit where lit(x, y) is true."""
    image = blank()
    image.putdata([INK if lit(x, y) else 0 for y in range(HEIGHT) for x in range(WIDTH)])
    return image


def sprite(rows):
    """Image from rows of "#" (lit) and "." (unlit)."""
    image = Image.new("1", (len(rows[0]), len(rows)))
    image.putdata([INK if char == "#" else 0 for row in rows for char in row])
    return image


def stamp(image, mask, x, y):
    image.paste(INK, (round(x), round(y)), mask)


def paste_centred(image, text, font):
    """Draw text with its actual lit pixels centred on the screen, on a cleared background."""
    ink = font.render(text)
    ink = ink.crop(ink.getbbox())
    x, y = (WIDTH - ink.width) // 2, (HEIGHT - ink.height) // 2
    ImageDraw.Draw(image).rectangle((x - 2, y - 2, x + ink.width + 1, y + ink.height + 1), fill=0)
    stamp(image, ink, x, y)


def frames(interval, wait=time.sleep):
    """Yield once per frame, every interval() seconds at most, waiting with wait(seconds)."""
    due = time.monotonic()
    while True:
        yield
        due += interval()
        delay = due - time.monotonic()
        if delay > 0:
            wait(delay)
        else:
            due = time.monotonic()


def parse_address(ctx, param, value):
    try:
        return int(value, 0)
    except ValueError:
        raise click.BadParameter(f"{value!r} is not a number, e.g. 0x3D")


def parse_font_size(ctx, param, value):
    if value == "5x7":
        return Font(value)
    if not value.isdigit() or not 6 <= int(value) <= 64:
        raise click.BadParameter(f"{value!r} is neither 5x7 nor a size from 6 to 64")
    return Font(int(value))


def parse_color(ctx, param, value):
    if value is None:
        return None
    names = value.replace(",", " ").split()
    try:
        if not 1 <= len(names) <= 2:
            raise ValueError
        return [ImageColor.getrgb(name)[:3] for name in names]
    except ValueError:
        raise click.BadParameter(f"{value!r}: give a foreground color and optionally a background color, "
                                 "as names like yellow or navy, or #rrggbb, e.g. -c yellow or -c 'yellow navy'")


OUTPUTS = ("auto", "oled", "window", "terminal")


def open_display(address, font, output, preview, color):
    display = choose_display(address, font, output, preview)
    if color:
        display.set_colors(*color)
        display.starting_colors = (display.foreground, display.background)
    return display


def choose_display(address, font, output, preview):
    if preview:
        return Png(font, preview)
    if output == "auto":
        has_desktop = sys.platform == "darwin" or os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
        if Path(f"/dev/i2c-{I2C_BUS}").exists():
            output = "oled"
        elif has_desktop and importlib.util.find_spec("pygame"):
            output = "window"
        else:
            output = "terminal"
    return {"oled": lambda: Oled(font, address), "window": lambda: Window(font), "terminal": lambda: Terminal(font)}[output]()


def with_display(command):
    """Pass the command its display, opened (only when the command runs) from the global options.

    While it runs, typed keys (see KEY_COMMANDS) switch to other subcommands on the same display.
    """
    @functools.wraps(command)
    def wrapper(*args, **kwargs):
        ctx = click.get_current_context()
        display = open_display(**ctx.obj)
        ctx.call_on_close(display.close)
        display.keyboard = Keyboard.open()
        if display.keyboard:
            ctx.call_on_close(display.keyboard.close)
            display.status("Keys: h help, x or q quit")
        run = functools.partial(command, display, *args, **kwargs)
        current, choice = ctx.info_name, 0  # the subcommand running and which of its key_options() it's using
        while True:
            try:
                return run()
            except FontChange:
                continue  # the same subcommand again, in the new font
            except KeyPress as press:
                display.reset()
                if press.key in QUIT_KEYS:
                    return None
                if press.key == HELP_KEY:
                    run = functools.partial(show_help, display)
                    continue
                name = KEY_COMMANDS[press.key]
                options = key_options(name)
                choice = (choice + 1) % len(options) if name == current else 0
                current = name
                font_size, arguments = options[choice]
                display.font = display.base_font if font_size is None else Font(font_size)
                command_line = (["-fs", str(font_size)] if font_size else []) + [name, *arguments]
                display.status(f"Key {press.key}: oled_test.py {' '.join(command_line)}")
                subcommand = cli.commands[name]
                params = subcommand.make_context(name, arguments, parent=ctx).params
                run = functools.partial(subcommand.callback.__wrapped__, display, **params)
    return wrapper


def key_options(name):
    """The (font size or None for -fs, arguments) that a subcommand's key steps through, one per press."""
    return {
        "demo": [(None, []), (None, ["--no-random"])],
        "draw": [(None, []), (None, ["--no-shade"]), (None, ["--style", "hatch"]), (None, ["--style", "stipple"]),
                 *[(None, ["--subject", subject]) for subject in sorted(SUBJECTS)]],
        "forklift": [(None, []), (None, ["--auto", "--duration", "0"])],
        "game": [(None, [name]) for name in GAMES] + [(None, [])],
        "pattern": [(None, []), ("5x7", []), (10, []), (16, [])],
        "screen": [(None, [action]) for action in ("on", "blink", "invert", "off")]
                  + [(None, ["show", "--contrast", "16"]), (None, ["blink", "-r", "8"])],
        "system": [(None, []), (None, ["-r", "4"]), ("5x7", []), (10, []), (12, [])],
        "text": [(None, []), ("5x7", []), (10, []), (16, []), (10, ["Hello!"]), (24, ["OLED"]), (16, ["128x64"])],
    }[name]


def show_help(display):
    """The keyboard commands, on the display and as status messages."""
    image = blank()
    for i, line in enumerate(HELP_LINES):
        y = 1 + i * (display.font.line_height + 1)
        if y + display.font.line_height <= HEIGHT:
            stamp(image, display.font.render_line(line), 2, y)
    display.show(image)
    display.status(" | ".join(HELP_LINES))
    display.hold()


@click.group(help=__doc__)
@click.option("-a", "--address", default="0x3C", callback=parse_address, help="I2C address.  [default: 0x3C]")
@click.option("-fs", "--font_size", "font", default="5x7", callback=parse_font_size,
              help="Font: the 5x7 bitmap font, or a TrueType font at a size in pixels, e.g. 10.  [default: 5x7]")
@click.option("-o", "--output", type=click.Choice(OUTPUTS), default="auto", show_default=True,
              help="Where to show the images: the OLED, or an emulated OLED in a desktop window (pygame) or the "
                   "terminal.  auto: the OLED if there is an I2C bus, else a window if pygame is installed, "
                   "else the terminal.")
@click.option("-c", "--color", callback=parse_color, metavar="'FOREGROUND [BACKGROUND]'",
              help="Colors of lit and unlit pixels on an emulated display (the OLED's color is fixed): "
                   "names like yellow or navy, or #rrggbb.  [default: white black]")
@click.option("--preview", type=click.Path(dir_okay=False), help="Save the final image as a PNG file instead.")
@click.pass_context
def cli(ctx, address, font, output, color, preview):
    ctx.obj = {"address": address, "font": font, "output": output, "preview": preview, "color": color}


@cli.command()
@click.argument("action", type=click.Choice(list(SCREEN_COMMANDS) + ["blink", "clear"]))
@click.option("-r", "--rate", default=2.0, show_default=True, help="Blink: changes per second.")
@click.option("--contrast", type=click.IntRange(0, 255), help="Also set the brightness (0-255).")
@with_display
def screen(display, action, rate, contrast):
    """Control the screen directly.

    \b
    on      light every pixel, ignoring the image (hardware test)
    off     turn the display off (sleep); the image is kept
    blink   alternate between "on" and "off" until Ctrl-C
    show    turn the display on showing the image (undoes "on" and "off")
    invert  swap lit and unlit pixels
    normal  undo "invert"
    clear   erase the image

    An emulated display has no image of its own, so it shows the effect on the test pattern.
    """
    if not display.keeps_image:
        display.show(pattern_image(display.font))
    if contrast is not None:
        display.contrast(contrast)
    if action == "blink":
        if not display.live:
            raise click.UsageError("blink needs a live display, not --preview")
        try:
            for state in itertools.cycle(("on", "off")):
                display.screen(state)
                display.wait(display.time_scale / rate)
        finally:
            display.screen("show")
    else:
        display.screen(action)
        display.hold()


def pattern_image(font):
    """The test pattern (see the pattern command)."""
    image = blank()
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, WIDTH - 1, HEIGHT - 1), outline=INK)
    for x in range(8, WIDTH, 8):
        draw.line((x, 1, x, 4 if x % 32 == 0 else 2), fill=INK)
    for y in range(8, HEIGHT, 8):
        draw.line((1, y, 4 if y % 32 == 0 else 2, y), fill=INK)
    draw.line((0, 0, WIDTH - 1, HEIGHT - 1), fill=INK)
    draw.line((0, HEIGHT - 1, WIDTH - 1, 0), fill=INK)
    draw.ellipse((40, 8, 87, 55), outline=INK)
    blocks = [
        (8, 18, lambda x, y: y % 2 == 0),
        (8, 34, lambda x, y: y % 2 == 1),
        (104, 18, lambda x, y: True),
        (104, 34, lambda x, y: (x + y) % 2 == 0),
    ]
    for left, top, lit in blocks:
        image.paste(pixels(lit).crop((left, top, left + 16, top + 12)), (left, top))
    paste_centred(image, "centre", font)
    return image


@cli.command()
@with_display
def pattern(display):
    """Test pattern that shows any shifted, missing, stretched or interleaved rows and columns.

    \b
    - Border: all four edges, so nothing is shifted or cut off
    - Ruler ticks every 8 pixels (longer every 32) along the top and left
    - Corner-to-corner diagonals: straight and unbroken if the rows are in order
    - Circle: round, not squashed or stretched
    - Left blocks: even rows only (upper) and odd rows only (lower); both must show
    - Right blocks: solid (upper) and a 1-pixel checkerboard (lower)
    - "centre" exactly in the middle
    """
    display.show(pattern_image(display.font))
    display.hold()


@cli.command("text")
@click.argument("message", required=False)
@with_display
def text_command(display, message):
    """Show MESSAGE centred, or without one, fill the screen with digits.

    Each row counts 0123456789012... across every column, starting one digit later than the row above.
    """
    image = blank()
    if message:
        paste_centred(image, message, display.font)
    else:
        font = display.font.mono()
        digits = [font.render_line(str(digit)) for digit in range(10)]
        _, top, _, bottom = font.render("0123456789").getbbox()
        digits = [digit.crop((0, top - font.top, digit.width, bottom - font.top)) for digit in digits]
        cell = 6 if font.truetype is None else round(font.truetype.getlength("0"))
        pitch = bottom - top + 1
        for row in range(math.ceil(HEIGHT / pitch)):
            for column in range(math.ceil(WIDTH / cell)):
                stamp(image, digits[(row + column) % 10], column * cell, row * pitch)
    display.show(image)
    display.hold()


def oval(cx, cy, rx, ry):
    n = max(12, round(math.pi * (rx + ry)))
    return [(cx + rx * math.cos(2 * math.pi * k / n), cy + ry * math.sin(2 * math.pi * k / n)) for k in range(n)]


def spokes(cx, cy, r):
    return [("line", [(cx + r * math.cos(a), cy + r * math.sin(a)), (cx - r * math.cos(a), cy - r * math.sin(a))])
            for a in (0.3, 0.3 + math.pi / 3, 0.3 + 2 * math.pi / 3)]


# Cartoon subjects: (box size, shapes in drawing order), coordinates in the box with y downwards.
#   poly, oval:  outlined, shaded, and hide whatever was drawn before them underneath
#   line: open stroke;  ring: outline only;  dot, blob: small solid oval or polygon
SUBJECTS = {
    "house": (60, [
        ("poly", [(38, 24), (38, 10), (45, 10), (45, 24)]),
        ("ring", (42, 6, 3, 2)), ("ring", (47, 2, 2, 1.5)),
        ("poly", [(10, 30), (50, 30), (50, 58), (10, 58)]),
        ("poly", [(5, 31), (30, 11), (55, 31)]),
        ("poly", [(25, 58), (25, 42), (35, 42), (35, 58)]), ("dot", (33, 50, 1, 1)),
        ("poly", [(14, 36), (22, 36), (22, 44), (14, 44)]), ("line", [(18, 36), (18, 44)]), ("line", [(14, 40), (22, 40)]),
        ("poly", [(38, 36), (46, 36), (46, 44), (38, 44)]), ("line", [(42, 36), (42, 44)]), ("line", [(38, 40), (46, 40)]),
    ]),
    "tree": (60, [
        ("poly", [(26, 58), (28, 36), (33, 36), (35, 58)]),
        ("oval", (30, 24, 21, 17)),
        ("line", [(30, 40), (30, 30)]), ("line", [(30, 34), (23, 27)]), ("line", [(30, 31), (37, 24)]),
        ("dot", (19, 20, 1.5, 1.5)), ("dot", (39, 15, 1.5, 1.5)), ("dot", (42, 30, 1.5, 1.5)),
    ]),
    "pine": (60, [
        ("poly", [(27, 58), (27, 50), (33, 50), (33, 58)]),
        ("poly", [(10, 51), (30, 30), (50, 51)]),
        ("poly", [(14, 40), (30, 18), (46, 40)]),
        ("poly", [(18, 28), (30, 4), (42, 28)]),
    ]),
    "cat": (60, [
        ("line", [(42, 54), (50, 52), (54, 45), (53, 38), (56, 33)]),
        ("oval", (30, 45, 13, 13)),
        ("oval", (24, 57, 4, 2)), ("oval", (36, 57, 4, 2)),
        ("poly", [(21, 19), (21, 6), (28, 13)]), ("poly", [(32, 13), (39, 6), (39, 19)]),
        ("oval", (30, 22, 11, 10)),
        ("dot", (26, 21, 1.5, 2)), ("dot", (34, 21, 1.5, 2)),
        ("blob", [(29, 25), (31, 25), (30, 27)]), ("line", [(27, 29), (30, 27), (33, 29)]),
        ("line", [(25, 26), (14, 24)]), ("line", [(25, 27), (14, 30)]),
        ("line", [(35, 26), (46, 24)]), ("line", [(35, 27), (46, 30)]),
    ]),
    "dog": (60, [
        ("line", [(12, 36), (6, 30), (5, 23)]),
        ("line", [(16, 44), (15, 58)]), ("line", [(21, 45), (21, 58)]),
        ("line", [(33, 45), (33, 58)]), ("line", [(38, 44), (39, 58)]),
        ("oval", (26, 38, 16, 9)),
        ("oval", (45, 25, 9, 8)),
        ("oval", (53, 29, 6, 4)),
        ("poly", [(39, 19), (35, 32), (41, 33), (44, 20)]),
        ("dot", (47, 23, 1.3, 1.3)), ("dot", (58, 27, 1.8, 1.5)),
    ]),
    "bicycle": (60, [
        ("ring", (14, 46, 12, 12)), ("ring", (46, 46, 12, 12)),
        *spokes(14, 46, 11), *spokes(46, 46, 11),
        ("line", [(14, 46), (28, 46), (24, 30), (14, 46)]), ("line", [(24, 30), (41, 29), (28, 46)]),
        ("line", [(41, 29), (46, 46)]),
        ("line", [(24, 30), (24, 28)]), ("line", [(20, 28), (28, 28)]),
        ("line", [(41, 29), (39, 23), (45, 22)]),
        ("line", [(25, 50), (31, 42)]), ("line", [(23, 50), (27, 50)]), ("line", [(29, 42), (33, 42)]),
        ("dot", (14, 46, 1.5, 1.5)), ("dot", (46, 46, 1.5, 1.5)),
    ]),
    "forklift": (60, [
        ("poly", [(41, 56), (41, 6), (46, 6), (46, 56)]),
        ("line", [(15, 30), (15, 12)]), ("line", [(31, 30), (29, 12)]), ("line", [(12, 12), (34, 12)]),
        ("ring", (23, 18, 2.5, 2.5)), ("line", [(23, 21), (22, 28)]), ("line", [(23, 24), (28, 25)]),
        ("line", [(18, 30), (18, 23)]), ("line", [(31, 20), (27, 26)]),
        ("poly", [(6, 48), (6, 36), (10, 30), (36, 30), (39, 36), (39, 48)]),
        ("oval", (14, 51, 6, 6)), ("oval", (33, 51, 6, 6)),
        ("dot", (14, 51, 1.5, 1.5)), ("dot", (33, 51, 1.5, 1.5)),
        ("line", [(46, 39), (48, 39), (48, 52), (59, 52)]),
        ("poly", [(49, 51), (49, 38), (59, 38), (59, 51)]), ("line", [(49, 38), (59, 51)]), ("line", [(59, 38), (49, 51)]),
    ]),
    "flower": (60, [
        ("line", [(30, 58), (31, 48), (29, 38), (30, 28)]),
        ("poly", [(31, 48), (37, 42), (45, 40), (42, 46)]), ("poly", [(29, 42), (23, 36), (15, 35), (18, 40)]),
        *[("oval", (30 + 9 * math.cos(a), 18 + 9 * math.sin(a), 5.5, 5.5)) for a in (k * math.pi / 3 + 0.5 for k in range(6))],
        ("oval", (30, 18, 5, 5)),
    ]),
}
SUN = (24, [("oval", (12, 12, 5, 5)),
            *[("line", [(12 + 7 * math.cos(a), 12 + 7 * math.sin(a)), (12 + 10 * math.cos(a), 12 + 10 * math.sin(a))])
              for a in (k * math.pi / 4 for k in range(8))]])
STYLES = ("outline", "hatch", "stipple")
GROUND = HEIGHT - 2
DRAW_SECONDS = 8.0  # default time for one drawing
SHADING_WEIGHT = 0.3  # shading strokes are drawn this much faster than outlines, relative to their length
SOLID_LENGTH = 4  # a solid dot takes as long to draw as a line this long


class Pencil:
    """Draws strokes a little at a time, like watching someone sketch."""

    def __init__(self, display):
        self.display = display
        self.paper = blank()

    def sketch(self, strokes, seconds):
        """Draw (points, visible mask, solid, weight) strokes, finishing in about the given seconds.

        Only the pixels lit in each stroke's visible mask are drawn; weight scales the time a stroke takes.
        """
        total = sum(weight * (SOLID_LENGTH if solid else sum(map(math.dist, points, points[1:])))
                    for points, _, solid, weight in strokes)
        rate = max(total, 1) / seconds  # weighted pixels per second
        self.elapsed, self.last, done = 0.0, time.monotonic(), 0.0
        for points, visible, solid, weight in strokes:
            layer = blank()
            draw = ImageDraw.Draw(layer)
            if solid:
                draw.polygon(points, fill=INK, outline=INK)
                done += weight * SOLID_LENGTH
                self.pace(layer, visible, done / rate)
                points = []
            for (x0, y0), (x1, y1) in zip(points, points[1:]):
                steps = max(1, math.ceil(math.dist((x0, y0), (x1, y1)) / 2))
                for i in range(steps):
                    a, b = i / steps, (i + 1) / steps
                    draw.line((x0 + (x1 - x0) * a, y0 + (y1 - y0) * a, x0 + (x1 - x0) * b, y0 + (y1 - y0) * b), fill=INK)
                    done += weight * math.dist((x0, y0), (x1, y1)) / steps
                    self.pace(layer, visible, done / rate)
            self.paper = self.compose(layer, visible)
        self.display.show(self.paper)

    def pace(self, layer, visible, due):
        """Show the drawing so far, once the clock reaches due seconds into the drawing.

        The clock runs slower or faster by the display's time_scale (the speed keys).
        """
        now = time.monotonic()
        self.elapsed, self.last = self.elapsed + (now - self.last) / self.display.time_scale, now
        ahead = due - self.elapsed
        if ahead > 0 and self.display.live:
            self.display.wait(ahead * self.display.time_scale)
            self.display.show(self.compose(layer, visible))

    def compose(self, layer, visible):
        return ImageChops.logical_or(self.paper, ImageChops.logical_and(layer, visible))

    def erase(self):
        """Sweep an eraser across the drawing."""
        for x in range(0, WIDTH + 8, 8):
            frame = self.paper.copy()
            ImageDraw.Draw(frame).rectangle((0, 0, x, HEIGHT), fill=0)
            self.display.show(frame)
        self.paper = blank()


def place(subject, left, top, flip):
    """Screen shapes for a subject: (kind, points) in drawing order."""
    size, shapes = subject
    placed = []
    for kind, data in shapes:
        points = oval(*data) if kind in ("oval", "ring", "dot") else data
        points = [(left + (size - x if flip else x), top + y) for x, y in points]
        placed.append((kind, points if kind == "line" else points + [points[0]]))
    return placed


def filled(points):
    mask = blank()
    ImageDraw.Draw(mask).polygon(points, fill=INK, outline=INK)
    return mask


def thicken(mask, size):
    """Grow (size > 0) or shrink (size < 0) the lit area of a mask by a pixel."""
    image_filter = ImageFilter.MaxFilter(3) if size > 0 else ImageFilter.MinFilter(3)
    return mask.convert("L").filter(image_filter).convert("1", dither=Image.Dither.NONE)


def shading_strokes(region, style, rng):
    """Hatch lines or stipple rows covering the lit pixels of region, as [start, end] strokes."""
    lit = region.load()
    if style == "hatch":
        slope = rng.choice((1, -1))
        lines = [[(c + slope * y, y) for y in range(HEIGHT) if 0 <= c + slope * y < WIDTH]
                 for c in range(-HEIGHT, WIDTH + HEIGHT, 3)]
    else:
        lines = [[(x, y) for x in range(WIDTH)] for y in range(0, HEIGHT, 2)]
    strokes = []
    for cells in lines:
        run = []
        for cell in cells + [None]:
            if cell and lit[cell]:
                run.append(cell)
            elif run:
                strokes.append([run[0], run[-1]] if len(strokes) % 2 else [run[-1], run[0]])
                run = []
    return strokes


def scene_strokes(shapes, style, rng):
    """Strokes for a scene: every shape's outline, the ground, then shading for the closed shapes."""
    masks = [filled(points) if kind in ("poly", "oval") else None for kind, points in shapes]
    details = []  # the eyes, whiskers, etc., widened by a pixel, so that shading keeps clear of them
    for kind, points in shapes:
        detail = filled(points) if kind in ("dot", "blob") else blank()
        if kind in ("line", "ring"):
            ImageDraw.Draw(detail).line(points, fill=INK)
        details.append(thicken(detail, 1))
    visibles = []
    for i in range(len(shapes)):
        hidden = blank()
        for mask in masks[i + 1:]:
            if mask:
                hidden = ImageChops.logical_or(hidden, mask)
        visibles.append(ImageChops.invert(hidden))
    strokes = [(points, visible, kind in ("dot", "blob"), 1) for (kind, points), visible in zip(shapes, visibles)]
    strokes.append(([(0, GROUND), (WIDTH - 1, GROUND)], blank(INK), False, 1))
    if style != "outline":
        texture = blank(INK) if style == "hatch" else pixels(lambda x, y: x % 2 == 0 and y % 2 == 0)
        for i, (mask, visible) in enumerate(zip(masks, visibles)):
            if mask:
                region = ImageChops.logical_and(thicken(mask, -1), visible)
                for detail in details[i + 1:]:
                    region = ImageChops.logical_and(region, ImageChops.invert(detail))
                shading = ImageChops.logical_and(region, texture)
                strokes += [(points, shading, False, SHADING_WEIGHT) for points in shading_strokes(region, style, rng)]
    return strokes


@cli.command("draw")
@click.option("--subject", "subjects", multiple=True, type=click.Choice(sorted(SUBJECTS)),
              help="Only draw these subjects (repeatable).  [default: all]")
@click.option("--shade/--no-shade", "-s/-S", default=True, show_default=True,
              help="Randomly shade drawings (hatched or stippled) or outline them; --no-shade for outlines only.")
@click.option("--style", type=click.Choice(STYLES), help="Always use this style.")
@click.option("--speed", default=DRAW_SECONDS, show_default=True, help="Seconds to draw each picture.")
@click.option("--hold", default=3.0, show_default=True, help="Seconds to show each finished drawing.")
@click.option("--count", default=0, help="Number of drawings.  [default: forever]")
@click.option("--seed", type=int, help="Random seed, to repeat the same drawings.")
@with_display
def draw_command(display, subjects, shade, style, speed, hold, count, seed):
    """Pencil-draw random cartoon scenes: house, tree, pine, cat, dog, bicycle, flower and forklift."""
    rng = random.Random(seed)
    pencil = Pencil(display)
    choices = sorted(subjects or SUBJECTS)
    drawn = 0
    while not count or drawn < count:
        names = rng.sample(choices, k=min(rng.choice((1, 2)), len(choices)))
        scene_style = style or (rng.choice(STYLES) if shade else "outline")
        if len(names) == 2:
            shapes = place(SUBJECTS[names[0]], 2, 3, rng.random() < 0.5) + place(SUBJECTS[names[1]], 66, 3, rng.random() < 0.5)
        else:
            left = rng.randint(4, WIDTH - 64)
            shapes = place(SUBJECTS[names[0]], left, 3, rng.random() < 0.5)
            gap_left, gap_right = left, WIDTH - left - 60
            if max(gap_left, gap_right) >= 28:
                sun_left = (gap_left - 24) // 2 if gap_left > gap_right else left + 60 + (gap_right - 24) // 2
                shapes += place(SUN, sun_left, 2, False)
        display.status(f"Drawing {' and '.join(names)} ({scene_style})")
        pencil.sketch(scene_strokes(shapes, scene_style, rng), speed)
        drawn += 1
        if not display.live:
            break
        display.wait(hold * display.time_scale)
        if not count or drawn < count:
            pencil.erase()
    display.hold()


def pong(rng, display):
    """Two computer players, each of which misjudges the ball now and then."""
    paddle_height, xs = 12, (2, WIDTH - 4)
    faces = (xs[0] + 2, xs[1] - 2)  # ball x (its left edge) where it touches each paddle
    paddles, aims, scores = [26.0, 26.0], [0.0, 0.0], [0, 0]

    def serve(direction):
        return [WIDTH / 2, rng.uniform(16, 48)], [direction * 4.8, rng.uniform(-3, 3)]

    ball, velocity = serve(rng.choice((-1, 1)))
    while True:
        for side in (0, 1):
            coming = (velocity[0] < 0) == (side == 0)
            # Where the ball will reach this paddle, allowing for bounces off the top and bottom
            bounce = (ball[1] + velocity[1] * (faces[side] - ball[0]) / velocity[0]) % (2 * (HEIGHT - 2))
            arrival = min(bounce, 2 * (HEIGHT - 2) - bounce)
            target = arrival + 1 + aims[side] - paddle_height / 2 if coming else (HEIGHT - paddle_height) / 2
            paddles[side] += max(-3.6, min(3.6, target - paddles[side]))
            paddles[side] = max(0.0, min(HEIGHT - paddle_height, paddles[side]))
        previous_x = ball[0]
        ball[0] += velocity[0]
        ball[1] += velocity[1]
        if not 0 <= ball[1] <= HEIGHT - 2:
            velocity[1] = -velocity[1]
            ball[1] = max(0.0, min(HEIGHT - 2, ball[1]))
        for side, face in enumerate(faces):
            crossed = (previous_x - face) * (ball[0] - face) <= 0  # moved onto or past the paddle's face
            if (velocity[0] < 0) == (side == 0) and crossed and paddles[side] - 2 <= ball[1] <= paddles[side] + paddle_height:
                ball[0] = face
                velocity[0] = -max(-9.0, min(9.0, velocity[0] * 1.05))
                velocity[1] = max(-6.0, min(6.0, velocity[1] + 3 * (ball[1] + 1 - paddles[side] - paddle_height / 2) / 4))
                aims[1 - side] = rng.uniform(-8, 8)
        if not -2 <= ball[0] <= WIDTH:
            scores[ball[0] < 0] += 1
            ball, velocity = serve(1 if ball[0] < 0 else -1)
        image = blank()
        draw = ImageDraw.Draw(image)
        for y in range(0, HEIGHT, 4):
            draw.line((WIDTH // 2 - 1, y, WIDTH // 2 - 1, y + 1), fill=INK)
        for side, x in enumerate(xs):
            draw.rectangle((x, round(paddles[side]), x + 1, round(paddles[side]) + paddle_height - 1), fill=INK)
            label = display.font.render_line(str(scores[side]))
            stamp(image, label, WIDTH // 2 - 8 - label.width if side == 0 else WIDTH // 2 + 6, 1)
        draw.rectangle((round(ball[0]), round(ball[1]), round(ball[0]) + 1, round(ball[1]) + 1), fill=INK)
        yield image


def asteroids(rng, display):
    """A ship turns, aims and fires at the nearest rock; big rocks split into smaller ones."""
    cx, cy = WIDTH / 2, HEIGHT / 2
    points_for = {9: 20, 5: 50, 3: 100}
    angle, cooldown, respawn, score, lives = 0.0, 0, 0, 0, 3
    bullets, sparks = [], []

    def rock(x, y, size):
        heading, speed = rng.uniform(0, 2 * math.pi), rng.uniform(0.25, 0.8)
        return {"x": x, "y": y, "vx": speed * math.cos(heading), "vy": speed * math.sin(heading), "r": size,
                "turn": 0.0, "spin": rng.uniform(-0.05, 0.05), "shape": [rng.uniform(0.7, 1.15) for _ in range(9)]}

    def explode(x, y, count):
        for _ in range(count):
            heading, speed = rng.uniform(0, 2 * math.pi), rng.uniform(0.3, 1.5)
            sparks.append([x, y, speed * math.cos(heading), speed * math.sin(heading), rng.randint(8, 20)])

    rocks = []
    while True:
        if not rocks:
            rocks = [rock(rng.choice((0, WIDTH - 1)), rng.uniform(0, HEIGHT), 9) for _ in range(4)]
        for r in rocks:
            r["x"], r["y"], r["turn"] = (r["x"] + r["vx"]) % WIDTH, (r["y"] + r["vy"]) % HEIGHT, r["turn"] + r["spin"]
        if respawn:
            respawn -= 1
        else:
            target = min(rocks, key=lambda r: math.dist((cx, cy), (r["x"], r["y"])))
            lead = math.dist((cx, cy), (target["x"], target["y"])) / 3
            aim = math.atan2(target["y"] + target["vy"] * lead - cy, target["x"] + target["vx"] * lead - cx)
            turn = (aim - angle + math.pi) % (2 * math.pi) - math.pi
            angle += max(-0.12, min(0.12, turn))
            cooldown = max(0, cooldown - 1)
            if abs(turn) < 0.1 and not cooldown:
                bullets.append([cx + 6 * math.cos(angle), cy + 6 * math.sin(angle), 3 * math.cos(angle), 3 * math.sin(angle), 30])
                cooldown = 7
        for bullet in bullets:
            bullet[0], bullet[1], bullet[4] = (bullet[0] + bullet[2]) % WIDTH, (bullet[1] + bullet[3]) % HEIGHT, bullet[4] - 1
        for bullet in list(bullets):
            hit = next((r for r in rocks if math.dist(bullet[:2], (r["x"], r["y"])) < r["r"] + 1), None)
            if hit:
                bullets.remove(bullet)
                rocks.remove(hit)
                score += points_for[hit["r"]]
                explode(hit["x"], hit["y"], hit["r"])
                if hit["r"] > 3:
                    rocks += [rock(hit["x"], hit["y"], 5 if hit["r"] == 9 else 3) for _ in range(2)]
        bullets = [bullet for bullet in bullets if bullet[4] > 0]
        crash = None if respawn else next((r for r in rocks if math.dist((cx, cy), (r["x"], r["y"])) < r["r"] + 3), None)
        if crash:
            rocks.remove(crash)
            explode(cx, cy, 20)
            respawn, lives = 50, lives - 1
            if not lives:
                score, lives = 0, 3
        for spark in sparks:
            spark[0], spark[1], spark[4] = spark[0] + spark[2], spark[1] + spark[3], spark[4] - 1
        sparks = [spark for spark in sparks if spark[4] > 0]
        image = blank()
        draw = ImageDraw.Draw(image)
        for r in rocks:
            draw.polygon([(r["x"] + r["r"] * m * math.cos(r["turn"] + 2 * math.pi * k / 9),
                           r["y"] + r["r"] * m * math.sin(r["turn"] + 2 * math.pi * k / 9)) for k, m in enumerate(r["shape"])],
                         outline=INK)
        if not respawn:
            draw.polygon([(cx + 5 * math.cos(angle + a), cy + 5 * math.sin(angle + a)) if a == 0 else
                          (cx + 4 * math.cos(angle + a), cy + 4 * math.sin(angle + a)) for a in (0, 2.5, math.pi, -2.5)],
                         outline=INK)
        for x, y, *_ in bullets + sparks:
            draw.point((x, y), fill=INK)
        stamp(image, display.font.render_line(str(score)), 1, 1)
        for i in range(lives):
            x = WIDTH - 5 - 6 * i
            draw.polygon([(x, 1), (x - 2, 6), (x + 2, 6)], outline=INK)
        yield image


INVADERS = [  # (points, two animation frames), top row first
    (30, [sprite(["...##...", "..####..", ".##..##.", "########", "..#..#..", ".#.##.#."]),
          sprite(["...##...", "..####..", ".##..##.", "########", ".#.##.#.", "#......#"])]),
    (20, [sprite(["..#..#..", "#.####.#", "##.##.##", "########", ".#....#.", "#......#"]),
          sprite(["..#..#..", "..####..", ".#.##.#.", "########", "#.#..#.#", ".#....#."])]),
    (10, [sprite(["..####..", ".######.", "##.##.##", "########", ".##..##.", "##....##"]),
          sprite(["..####..", ".######.", "##.##.##", "########", "..#..#..", ".#.##.#."])]),
]
CANNON = sprite(["...#...", "..###..", "#######", "#######"])
SAUCER = sprite(["..####..", ".######.", "#.#.#.#.", ".##..##."])
BLAST = sprite(["#..#..#.", ".#.#.#..", "#......#", "..#.#.#.", ".#..#..#"])
BUNKER = sprite(["..########..", ".##########.", "############", "############", "####....####", "###......###"])


def invaders(rng, display):
    """Marching invaders, a cannon that picks them off, bombs, crumbling bunkers and a passing saucer."""
    cannon_y, bunker_y = HEIGHT - 6, HEIGHT - 17
    score = 0
    while True:
        alive = {(row, column) for row in range(3) for column in range(8)}
        score_height = display.font.line_height + 2
        grid_x, grid_y, direction, tick, pose = 10.0, score_height + 6.0, 1, 0, 0
        bunkers = blank()
        for x in (18, 58, 98):
            stamp(bunkers, BUNKER, x, bunker_y)
        cannon_x, cannon_hit, target, shot, saucer = 60.0, 0, None, None, None
        bombs, blasts = [], []

        def position(row, column):
            return grid_x + 12 * column, grid_y + 9 * row

        while alive and max(position(*invader)[1] for invader in alive) + 6 < bunker_y:
            tick += 1
            if tick >= 2 + len(alive) // 3:  # the fewer that are left, the faster they march
                tick, pose = 0, 1 - pose
                xs = [position(*invader)[0] for invader in alive]
                if min(xs) + 2 * direction < 1 or max(xs) + 8 + 2 * direction > WIDTH - 1:
                    grid_y, direction = grid_y + 2, -direction
                else:
                    grid_x += 2 * direction
            if cannon_hit:
                cannon_hit -= 1
            else:
                if target not in alive:
                    column = rng.choice(sorted({column for _, column in alive}))
                    target = max(invader for invader in alive if invader[1] == column)
                aim = position(*target)[0] + 4 - 3
                cannon_x += max(-1.5, min(1.5, aim - cannon_x))
                if shot is None and abs(aim - cannon_x) < 2:
                    shot = [cannon_x + 3, cannon_y - 3]
            if shot:
                for _ in range(3):
                    shot[1] -= 1
                    x, y = round(shot[0]), round(shot[1])
                    hit = next((invader for invader in alive if 0 <= x - position(*invader)[0] < 8
                                and 0 <= y - position(*invader)[1] < 6), None)
                    if y < score_height:
                        shot = None
                    elif hit:
                        alive.remove(hit)
                        score += INVADERS[hit[0]][0]
                        blasts.append([*position(*hit), 8])
                        shot = None
                    elif saucer and 0 <= x - saucer[0] < 8 and 0 <= y - score_height < 4:
                        score += 100
                        blasts.append([saucer[0], score_height, 12])
                        saucer, shot = None, None
                    elif bunkers.getpixel((x, y)):
                        ImageDraw.Draw(bunkers).rectangle((x - 1, y - 2, x + 1, y), fill=0)
                        shot = None
                    if shot is None:
                        break
            if alive and rng.random() < 0.04:
                column = rng.choice(sorted({column for _, column in alive}))
                x, y = position(*max(invader for invader in alive if invader[1] == column))
                bombs.append([x + 4, y + 6])
            for bomb in list(bombs):
                bomb[1] += 1.2
                x, y = round(bomb[0]), round(bomb[1])
                if y >= HEIGHT - 1:
                    bombs.remove(bomb)
                elif bunkers.getpixel((x, y)):
                    ImageDraw.Draw(bunkers).rectangle((x - 1, y, x + 1, y + 2), fill=0)
                    bombs.remove(bomb)
                elif not cannon_hit and 0 <= x - cannon_x < 7 and y >= cannon_y:
                    blasts.append([cannon_x, cannon_y - 1, 12])
                    bombs.remove(bomb)
                    cannon_hit = 40
            if saucer is None and rng.random() < 0.004:
                saucer = [-8.0, 0.8] if rng.random() < 0.5 else [float(WIDTH), -0.8]
            if saucer:
                saucer[0] += saucer[1]
                if not -8 <= saucer[0] <= WIDTH:
                    saucer = None
            for blast in blasts:
                blast[2] -= 1
            blasts = [blast for blast in blasts if blast[2] > 0]
            image = bunkers.copy()
            draw = ImageDraw.Draw(image)
            for row, column in alive:
                stamp(image, INVADERS[row][1][pose], *position(row, column))
            if not cannon_hit or cannon_hit % 8 < 4:
                stamp(image, CANNON, cannon_x, cannon_y)
            if shot:
                draw.line((shot[0], shot[1], shot[0], shot[1] + 2), fill=INK)
            for x, y in bombs:
                draw.line([(x, y), (x + 1, y + 1), (x, y + 2)], fill=INK)
            if saucer:
                stamp(image, SAUCER, saucer[0], score_height)
            for x, y, _ in blasts:
                stamp(image, BLAST, x, y)
            draw.line((0, HEIGHT - 1, WIDTH - 1, HEIGHT - 1), fill=INK)
            stamp(image, display.font.render_line(f"SCORE {score}"), 0, 0)
            yield image


GAMES = {"pong": pong, "asteroids": asteroids, "invaders": invaders}


@cli.command()
@click.argument("name", required=False, type=click.Choice(list(GAMES)))
@click.option("--duration", default=20.0, show_default=True, help="Seconds for each game when they take turns.")
@click.option("--fps", default=30, show_default=True, help="Maximum frames per second.")
@click.option("--seed", type=int, help="Random seed, to repeat the same play.")
@with_display
def game(display, name, duration, fps, seed):
    """Self-playing demos of the classics: pong, asteroids and (space) invaders.

    Without NAME, the games take turns, each for --duration seconds.
    """
    rng = random.Random(seed)
    for game_name in itertools.cycle([name] if name else GAMES):
        display.status(f"Playing {game_name}")
        play = GAMES[game_name](rng, display)
        if not display.live:
            display.show(next(itertools.islice(play, 200, None)))
            return
        end = time.monotonic() + duration
        for image, _ in zip(play, frames(lambda: display.time_scale / fps, display.wait)):
            display.show(image)
            if not name and time.monotonic() > end:
                break


# Forklift: the forklift from "draw" (at 80%), a pallet and a racking bay with 3 levels: 0 its floor, 1 and 2 (the
# top) on beams.  Screen rows: the ground line is GROUND; things standing on the ground have their bottom on the row
# above it.  Pallets are (left column, bottom row).
LIFT_SCALE = 0.8


def shape_points(kind, data):
    return oval(*data) if kind in ("oval", "ring", "dot") else data


LIFT_BODY = [(kind, data) for kind, data in SUBJECTS["forklift"][1]  # without its mast, forks and crate (drawn here)
             if max(x for x, _ in shape_points(kind, data)) <= 46 and min(x for x, _ in shape_points(kind, data)) != 41]
LIFT_MAST = (41 * LIFT_SCALE, 46 * LIFT_SCALE)  # the mast's columns, from the forklift's left
LIFT_MAST_TOP = round(GROUND - 1 - (57 - 6) * LIFT_SCALE) + 4  # (4 rows shorter than drawn, so the inner mast shows)
LIFT_CARRIAGE = 48 * LIFT_SCALE  # the carriage (the forks' upright) from the forklift's left
FORK_LENGTH, CARRIAGE_HEIGHT, INNER_MAST_ABOVE = 9, 10, 5  # (the inner mast rises this far above the carriage)
PALLET_WIDTH, PALLET_HEIGHT = 13, 13
RACK_X, RACK_WIDTH, RACK_TOP = 107, 18, 8  # the racking bay's front upright, its width and its top bar's row
LEVELS = {0: GROUND - 1, 1: 43, 2: 25}  # rack level: the row a pallet there has its bottom on
BEAMS = {1: 44, 2: 26}  # the top rows of the beams (2 rows deep) that levels 1 and 2 stand on
FORKS_DOWN, FORKS_TOP = GROUND - 1, 18  # the forks' lowest and highest rows
FORKS_CARRY = FORKS_DOWN - 4  # forks when driving with a pallet
PALLET_SLOTS = 1  # a pallet rests on the forks with its bottom this many rows below them
GROUND_SPOTS = (32, RACK_X - PALLET_WIDTH - 4)  # where a pallet can stand on the open ground (its left column)
LIFT_X_MAX = RACK_X - 1 - LIFT_MAST[1]  # the forklift's furthest x: its mast just short of the rack


def draw_pallet(draw, left, bottom):
    """A pallet with a crate on it, like the one in the forklift drawing."""
    right, top = left + PALLET_WIDTH - 1, bottom - PALLET_HEIGHT + 1
    for (x0, y0), (x1, y1) in pallet_lines(left, bottom):
        if y0 == y1 == bottom - 1:  # the blocks, with the fork slots between them
            draw.rectangle((x0, y0, x1, y1), fill=INK)
    draw.rectangle((left + 1, top, right - 1, bottom - 3), fill=0, outline=INK)
    draw.rectangle((left, bottom - 2, right, bottom), fill=0)
    for (x0, y0), (x1, y1) in pallet_lines(left, bottom):
        if not y0 == y1 == bottom - 1:
            draw.line((x0, y0, x1, y1), fill=INK)
    for x in (left, (left + right) // 2 - 1, right - 1):
        draw.rectangle((x, bottom - 1, x + 1, bottom - 1), fill=INK)


def pallet_lines(left, bottom):
    """The lines a pallet and its crate are made of (the pieces it breaks into)."""
    right, top = left + PALLET_WIDTH - 1, bottom - PALLET_HEIGHT + 1
    return [((left + 1, top), (right - 1, top)), ((left + 1, bottom - 3), (right - 1, bottom - 3)),
            ((left + 1, top), (left + 1, bottom - 3)), ((right - 1, top), (right - 1, bottom - 3)),
            ((left + 1, top), (right - 1, bottom - 3)), ((right - 1, top), (left + 1, bottom - 3)),
            ((left, bottom - 2), (right, bottom - 2)), ((left, bottom), (right, bottom))]


def draw_forklift(draw, x, forks):
    """The forklift with its left at column x and its forks at row forks."""
    def screen(points):
        return [(x + px * LIFT_SCALE, GROUND - 1 - (57 - py) * LIFT_SCALE) for px, py in points]

    draw.rectangle((x + LIFT_MAST[0], LIFT_MAST_TOP, x + LIFT_MAST[1], GROUND - 1), fill=0, outline=INK)
    for kind, data in LIFT_BODY:
        points = screen(shape_points(kind, data))
        if kind == "line":
            draw.line(points, fill=INK)
        else:  # outlines filled black, so later parts hide earlier ones; small dots solid
            draw.polygon(points, fill=INK if kind in ("dot", "blob") else 0, outline=INK)
    carriage, top = x + LIFT_CARRIAGE, forks - CARRIAGE_HEIGHT
    if top - INNER_MAST_ABOVE < LIFT_MAST_TOP:  # the inner mast slides up out of the outer mast
        draw.rectangle((x + 42 * LIFT_SCALE, top - INNER_MAST_ABOVE, x + 45 * LIFT_SCALE, LIFT_MAST_TOP), fill=0, outline=INK)
    draw.line((carriage, top, carriage, forks), fill=INK)
    draw.line((carriage, forks, carriage + FORK_LENGTH, forks), fill=INK)


def draw_warehouse(x, forks, pallet, pieces=()):
    """The ground, racking bay, forklift and pallet (if any), and the pieces of a broken pallet."""
    image = blank()
    draw = ImageDraw.Draw(image)
    draw.line((0, GROUND, WIDTH - 1, GROUND), fill=INK)
    for post in (RACK_X, RACK_X + RACK_WIDTH):
        draw.line((post, RACK_TOP, post, GROUND - 1), fill=INK)
    for row in (RACK_TOP, *BEAMS.values()):
        draw.rectangle((RACK_X, row, RACK_X + RACK_WIDTH, row + 1), outline=INK)
    draw_forklift(draw, x, round(forks))
    if pallet:
        draw_pallet(draw, round(pallet[0]), round(pallet[1]))
    for x0, y0, x1, y1, *_ in pieces:
        draw.line((x0, y0, x1, y1), fill=INK)
    return image


def forklift_work(rng, display):
    """Frames of the forklift moving the pallet between the ground and random rack levels by itself, for ever."""
    drive, lift = 1.4, 1.0  # pixels per frame
    at_rack = RACK_X + 1 - LIFT_CARRIAGE  # the forklift's x with its pallet in the rack
    before_rack = RACK_X - PALLET_WIDTH - 2 - LIFT_CARRIAGE  # its x with the pallet just clear of the rack
    mirrored = rng.random() < 0.5  # the rack on the left instead
    state = {"x": 0.0, "forks": float(FORKS_CARRY), "carried": False, "pallet": None, "level": None, "moves": 0}
    if rng.random() < 0.5:
        state["level"] = rng.choice(list(LEVELS))
        state["pallet"] = [RACK_X + 2, LEVELS[state["level"]]]
        state["x"] = rng.uniform(-4, before_rack - 10)
    else:
        left = rng.randint(*GROUND_SPOTS)
        state["pallet"] = [left, GROUND - 1]
        state["x"] = rng.uniform(-4, left - 14 - LIFT_CARRIAGE)

    def frame():
        if state["carried"]:
            state["pallet"] = [round(state["x"] + LIFT_CARRIAGE) + 1, round(state["forks"]) + PALLET_SLOTS]
        image = draw_warehouse(state["x"], state["forks"], state["pallet"])
        if mirrored:
            image = image.transpose(Image.FLIP_LEFT_RIGHT)
        label = display.font.render_line(f"Moves {state['moves']}")
        stamp(image, label, WIDTH - label.width - 1 if mirrored else 1, 0)
        return image

    def go(key, target, speed):
        """Frames moving the forklift ("x") or its forks ("forks") to the target, at speed pixels per frame."""
        while state[key] != target:
            step = target - state[key]
            state[key] = target if abs(step) <= speed else state[key] + math.copysign(speed, step)
            yield frame()

    def pause(frames):
        for _ in range(frames):
            yield frame()

    while True:
        if state["level"] is None:  # the pallet is on the ground: take it to a random rack level
            level = rng.choice(list(LEVELS))
            display.status(f"Forklift: pallet on the ground to rack level {level}")
            left = state["pallet"][0]
            yield from go("forks", FORKS_DOWN, lift)
            yield from go("x", left - 1 - LIFT_CARRIAGE, drive)
            yield from go("forks", GROUND - 1 - PALLET_SLOTS, lift)
            state["carried"] = True
            yield from go("forks", FORKS_CARRY, lift)
            yield from go("x", before_rack, drive)
            resting = LEVELS[level] - PALLET_SLOTS  # forks with the pallet standing on its level
            yield from go("forks", min(resting - 3, FORKS_CARRY), lift)
            yield from go("x", at_rack, drive / 2)
            yield from go("forks", resting, lift / 2)
            state["carried"], state["level"] = False, level
            yield from go("forks", min(resting + 1, FORKS_DOWN), lift)
            yield from pause(10)
            yield from go("x", before_rack, drive)
            yield from go("forks", FORKS_CARRY, lift)
        else:  # the pallet is in the rack: fetch it and set it down on the ground somewhere
            display.status(f"Forklift: pallet at rack level {state['level']} to the ground")
            resting = LEVELS[state["level"]] - PALLET_SLOTS
            yield from go("x", before_rack, drive)
            yield from go("forks", min(resting + 1, FORKS_DOWN), lift)
            yield from go("x", at_rack, drive / 2)
            yield from go("forks", resting, lift / 2)
            state["carried"], state["level"] = True, None
            yield from go("forks", min(resting - 3, FORKS_CARRY), lift / 2)
            yield from go("x", before_rack, drive / 2)
            yield from go("forks", FORKS_CARRY, lift)
            left = rng.randint(*GROUND_SPOTS)
            yield from go("x", left - 1 - LIFT_CARRIAGE, drive)
            yield from go("forks", GROUND - 1 - PALLET_SLOTS, lift / 2)
            state["carried"] = False
            yield from go("forks", FORKS_DOWN, lift)
            yield from pause(10)
            yield from go("x", max(-4.0, state["x"] - rng.uniform(8, 20)), drive)  # (-4: its back on screen)
        state["moves"] += 1
        yield from pause(15)


def overlap(start, end, other_start, other_end):
    """How far two ranges of columns or rows (ends included) overlap: 0 or more when they touch or overlap."""
    return min(end, other_end) - max(start, other_start)


class ForkliftGame:
    """The forklift game: drive and lift with the arrow keys to put the pallet where the top line says.

    The pallet's "physics": it rests on the highest thing under it - the forks, a beam or the ground.  Resting only on
    the forks, it goes where they go; touching a beam or the ground, that holds it (so the forks can slide out).  A
    pallet whose middle isn't over its beam falls when the forks leave it, and breaks if it falls far.  The forklift,
    forks and a pallet can't go through the racking bay's beams, or the forks and forklift through a pallet, except
    the forks into the slots at its bottom.
    """

    DRIVE, LIFT, GRAVITY = 1.4, 1, 0.35  # pixels per frame, rows per frame, rows per frame per frame
    TARGETS = ("ground", "bay 0", "bay 1", "bay 2")

    def __init__(self, rng, display):
        self.rng, self.display = rng, display
        self.x, self.forks = rng.uniform(-4, 20), FORKS_CARRY
        self.pallet = [float(rng.randint(GROUND_SPOTS[0] + 20, GROUND_SPOTS[1])), GROUND - 1]
        self.falling = None  # (speed, the row it fell from) while the pallet falls
        self.pieces = []  # a broken pallet's pieces: [x0, y0, x1, y1, speed across, speed down]
        self.new_pallet_at = None  # when a broken pallet gets replaced
        self.placed, self.broken = 0, 0
        self.message, self.message_until = "", 0.0
        self.new_target()

    # Where things are

    def pallet_box(self, left=None, bottom=None):
        left, bottom = self.pallet[0] if left is None else left, self.pallet[1] if bottom is None else bottom
        return left, left + PALLET_WIDTH - 1, bottom - PALLET_HEIGHT + 1, bottom

    def forks_in_slots(self, x=None, forks=None):
        """Whether the forks are in the pallet's slots (in far enough, at its bottom rows)."""
        carriage = (self.x if x is None else x) + LIFT_CARRIAGE
        forks = self.forks if forks is None else forks
        left, right, _, bottom = self.pallet_box()
        return overlap(carriage, carriage + FORK_LENGTH, left, right) >= 4 and bottom - PALLET_SLOTS <= forks <= bottom

    def on_forks(self):
        return self.pieces == [] and self.falling is None and self.forks_in_slots()

    def support(self, left=None, bottom=None):
        """What the pallet stands on: "ground", a beam's level (1 or 2), or None."""
        left, right, _, bottom = self.pallet_box(left, bottom)
        if bottom >= GROUND - 1:
            return "ground"
        return next((level for level, row in BEAMS.items()
                     if bottom + 1 == row and overlap(left, right, RACK_X, RACK_X + RACK_WIDTH) >= 0), None)

    def balanced(self):
        """Whether the pallet's middle is over what it stands on (anything is steady on the ground)."""
        middle = self.pallet[0] + PALLET_WIDTH / 2
        return self.support() == "ground" or RACK_X <= middle <= RACK_X + RACK_WIDTH

    def location(self):
        """Where the pallet has been put: one of TARGETS, or None."""
        if self.pieces or self.falling is not None or not self.balanced():
            return None
        support = self.support()
        in_bay = RACK_X <= self.pallet[0] + PALLET_WIDTH / 2 <= RACK_X + RACK_WIDTH
        if support == "ground":
            return "bay 0" if in_bay else "ground" if self.pallet[0] + PALLET_WIDTH <= RACK_X else None
        return f"bay {support}" if support else None

    @staticmethod
    def hits_rack(left, right, top, bottom):
        return any(overlap(left, right, RACK_X, RACK_X + RACK_WIDTH) >= 0 and overlap(top, bottom, row, row + 1) >= 0
                   for row in (RACK_TOP, *BEAMS.values()))

    # Moving

    def try_move(self, x, forks):
        """Move the forklift to x and its forks to row forks, with the pallet if it goes too, unless that's blocked."""
        if not (-4 <= x <= LIFT_X_MAX and FORKS_TOP <= forks <= FORKS_DOWN):
            return False
        left, bottom = self.pallet
        new_left, new_bottom = left, bottom
        if self.on_forks():
            if not self.support():  # riding only on the forks: it goes where they go
                new_left, new_bottom = left + (x - self.x), bottom + (forks - self.forks)
            elif forks < self.forks:  # the forks lift it off the beam or ground (once they're up in its slots)
                new_bottom = min(bottom, forks + PALLET_SLOTS)
            # otherwise the beam or ground holds it, while the forks lower or slide out
        carriage = x + LIFT_CARRIAGE
        if self.hits_rack(carriage, carriage + FORK_LENGTH, forks, forks) or \
                self.hits_rack(carriage, carriage, forks - CARRIAGE_HEIGHT, forks):
            return False
        if not self.pieces:
            box = self.pallet_box(new_left, new_bottom)
            if (new_left, new_bottom) != (left, bottom):
                if self.hits_rack(*box):
                    return False
            else:  # the forks, carriage and mast against the pallet standing still
                p_left, p_right, p_top, p_bottom = box
                if overlap(carriage, carriage + FORK_LENGTH, p_left, p_right) >= 0 and p_top <= forks <= p_bottom \
                        and not p_bottom - PALLET_SLOTS <= forks <= p_bottom:
                    return False
                if overlap(carriage, carriage, p_left, p_right) >= 0 and \
                        overlap(forks - CARRIAGE_HEIGHT, forks, p_top, p_bottom) >= 0:
                    return False
                if overlap(x + LIFT_MAST[0], x + LIFT_MAST[1], p_left, p_right) >= 0 and \
                        overlap(LIFT_MAST_TOP, GROUND - 1, p_top, p_bottom) >= 0:
                    return False
        self.x, self.forks, self.pallet = x, forks, [new_left, new_bottom]
        return True

    def step(self, held):
        """One frame: move as the arrow keys say, then let the pallet fall, break or be placed."""
        if "up" in held or "down" in held:
            self.try_move(self.x, self.forks + (1 if "down" in held else -1) * self.LIFT)
        if "left" in held or "right" in held:
            self.try_move(self.x + (1 if "right" in held else -1) * self.DRIVE, self.forks)
        if self.pieces:
            self.shatter()
        elif self.falling is not None:
            self.fall()
        elif not self.on_forks() and not (self.support() and self.balanced()):
            self.falling = (0.0, self.pallet[1])  # nothing under it now, or it tips off its beam
            self.show_message("Whoops!")
        elif self.location() == self.target and not self.forks_in_slots():
            seconds = time.monotonic() - self.started
            self.placed += 1
            self.show_message(f"Done in {seconds:.1f}s!")
            self.display.status(f"Forklift: pallet put on {self.target} in {seconds:.1f} seconds "
                                f"({self.placed} placed, {self.broken} broken)")
            self.new_target()

    def fall(self):
        speed, start = self.falling
        speed += self.GRAVITY
        self.pallet[1] += speed
        self.falling = (speed, start)
        if self.pallet[1] >= GROUND - 1:
            self.pallet[1], self.falling = GROUND - 1, None
            if GROUND - 1 - start > 6:
                self.break_pallet()

    def break_pallet(self):
        self.broken += 1
        self.pieces = [[x0, y0, x1, y1, self.rng.uniform(-1.5, 1.5), self.rng.uniform(-2.5, -0.5)]
                       for (x0, y0), (x1, y1) in pallet_lines(*self.pallet)]
        self.new_pallet_at = time.monotonic() + 2.5
        self.show_message("Broken!")
        self.display.status(f"Forklift: the pallet fell and broke ({self.placed} placed, {self.broken} broken)")

    def shatter(self):
        """Move the broken pieces, bouncing on the ground; then bring a new pallet."""
        for piece in self.pieces:
            piece[4] *= 0.97
            piece[5] += self.GRAVITY
            piece[0] += piece[4]
            piece[2] += piece[4]
            piece[1] += piece[5]
            piece[3] += piece[5]
            below = max(piece[1], piece[3]) - (GROUND - 1)
            if below > 0:
                piece[1], piece[3] = piece[1] - below, piece[3] - below
                piece[4], piece[5] = piece[4] * 0.5, -piece[5] * 0.3 if piece[5] > 1 else 0
        if time.monotonic() >= self.new_pallet_at:
            carriage = self.x + LIFT_CARRIAGE
            spots = [left for left in range(*GROUND_SPOTS) if left > carriage + FORK_LENGTH + 3 or left + PALLET_WIDTH < self.x]
            self.pieces, self.pallet = [], [float(self.rng.choice(spots or [GROUND_SPOTS[1]])), GROUND - 1]
            self.new_target()

    def new_target(self):
        self.target = self.rng.choice([target for target in self.TARGETS if target != self.location()])
        self.started = time.monotonic()
        self.display.status(f"Forklift: put the pallet on {self.target}")

    def show_message(self, message):
        self.message, self.message_until = message, time.monotonic() + 2

    def frame(self):
        image = draw_warehouse(self.x, self.forks, None if self.pieces else self.pallet, self.pieces)
        now = time.monotonic()
        line = self.message if now < self.message_until else f"To {self.target}  {now - self.started:.1f}s"
        stamp(image, self.display.font.render_line(line), 1, 0)
        return image


@cli.command("forklift")
@click.option("--auto", is_flag=True, help="Watch the forklift work by itself, even when keys can be typed.")
@click.option("--duration", default=60.0, show_default=True, help="--auto: seconds of work (0: until stopped).")
@click.option("--fps", default=30, show_default=True, help="Maximum frames per second.")
@click.option("--seed", type=int, help="Random seed, to repeat the same start.")
@with_display
def forklift_command(display, auto, duration, fps, seed):
    """Forklift game: put the pallet where the top line says, in the racking bay or on the ground.

    \b
    Arrow keys: left and right drive, up and down raise and lower the forks.
    The bay has 3 levels: 0 its floor, 1 and 2 (the top) on beams.
    To pick up the pallet, lower the forks, drive them into its slots and lift.
    To put it in the bay, lift it above the level, drive in, lower it until the
    beam (or floor) holds it, lower the forks a little more, and back out.
    A pallet with its middle not over the beam falls, and breaks if it falls far.

    Without keys to play with (or with --auto), the forklift works by itself until the time runs out: a pallet on
    the ground goes to a random level of the bay, and a pallet in the bay comes back to a random place on the ground.
    """
    rng = random.Random(seed)
    playing = not auto and display.live and (display.keyboard is not None or isinstance(display, Window))
    if playing:
        display.status("Forklift: arrow keys drive (left, right) and lift (up, down)")
        game = ForkliftGame(rng, display)
        for _ in frames(lambda: display.time_scale / fps, display.wait):
            game.step(display.arrows_held())
            display.show(game.frame())
    work = forklift_work(rng, display)
    if not display.live:
        display.show(next(itertools.islice(work, 150, None)))
        return
    end = time.monotonic() + duration
    for image, _ in zip(work, frames(lambda: display.time_scale / fps, display.wait)):
        display.show(image)
        if duration and time.monotonic() >= end:
            break
    display.status("Forklift: time's up")
    display.hold()


def ip_address():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
        try:
            udp.connect(("10.254.254.254", 1))  # UDP connect sends nothing; it just picks the outgoing interface
            return udp.getsockname()[0]
        except OSError:
            return "none"


def per_second(count):
    """Short human readable rate, e.g. 950, 12k, 3.4M."""
    for unit in ("", "k", "M", "G"):
        if count < 999.5:
            return f"{count:.1f}{unit}" if unit and count < 9.95 else f"{count:.0f}{unit}"
        count /= 1000
    return f"{count:.0f}T"


@cli.command()
@click.option("-r", "--rate", default=1.0, show_default=True, help="Updates per second.")
@with_display
def system(display, rate):
    """Live system status, one item per line.

    \b
    host name; IP address; date; time and uptime; CPU and memory use;
    disk use and network traffic (received/sent bytes per second);
    temperature and CPU speed (where available); load average (1, 5 and 15 minutes)
    """
    import psutil

    def network_bytes():
        counters = [c for name, c in psutil.net_io_counters(pernic=True).items() if not name.startswith("lo")]
        return sum(c.bytes_recv for c in counters), sum(c.bytes_sent for c in counters)

    def cpu_speed():
        try:
            return f"{psutil.cpu_freq().current:.0f}MHz"
        except (AttributeError, NotImplementedError, OSError, RuntimeError):
            return ""

    psutil.cpu_percent()  # starts the measurement that the first reading uses
    before = (time.monotonic(), network_bytes())
    display.wait(0.2)
    for _ in frames(lambda: display.time_scale / rate, display.wait):
        now = (time.monotonic(), network_bytes())
        received, sent = ((b - a) / (now[0] - before[0]) for a, b in zip(before[1], now[1]))
        before = now
        up = int(time.time() - psutil.boot_time())
        days, hours, minutes = up // 86400, up // 3600 % 24, up // 60 % 60
        sensors = next(iter(getattr(psutil, "sensors_temperatures", dict)().values()), None)  # Linux only
        clock = datetime.now()
        lines = [
            socket.gethostname(),
            f"IP {ip_address()}",
            f"{clock:%a %d %b %Y}",
            f"{clock:%H:%M:%S} up " + (f"{days}d{hours:02d}h" if days else f"{hours}h{minutes:02d}m"),
            f"CPU {psutil.cpu_percent():.0f}% Mem {psutil.virtual_memory().percent:.0f}%",
            f"Disk {psutil.disk_usage(str(Path.home())).percent:.0f}% Rx{per_second(received)} Tx{per_second(sent)}",
            f"Temp {f'{sensors[0].current:.1f}C' if sensors else 'n/a'} {cpu_speed()}",
            "Load {:.2f} {:.2f} {:.2f}".format(*os.getloadavg()),
        ]
        image = blank()
        font = display.font
        for i, line in enumerate(lines):
            y = i * (font.line_height + 1)
            if y + font.line_height > HEIGHT:
                break
            stamp(image, font.render_line(line), 0, y)
        display.show(image)
        if not display.live:
            return


# The fixed tour for "demo --no-random": (seconds, font size or None for -fs, command line)
TOUR = [
    (3, None, ["screen", "on"]),
    (3, None, ["screen", "blink", "-r", "4"]),
    (4, None, ["pattern"]),
    (3, None, ["screen", "invert"]),
    (3, None, ["screen", "show", "--contrast", "16"]),
    (4, "5x7", ["text"]),
    (4, 10, ["text"]),
    (3, 20, ["text", "Hello!"]),
    (5, "5x7", ["system"]),
    (4, 12, ["system"]),
    (13, None, ["draw", "--subject", "forklift", "--count", "1", "--hold", "3"]),
    (8, None, ["draw", "--no-shade", "--speed", "4", "--count", "1", "--hold", "2"]),
    (13, None, ["draw", "--style", "hatch", "--count", "1", "--hold", "3"]),
    (10, None, ["game", "pong"]),
    (10, None, ["game", "asteroids"]),
    (10, None, ["game", "invaders"]),
    (25, None, ["forklift", "--auto", "--duration", "0"]),
]


def random_steps(rng):
    """Endless demo steps like those in TOUR, with subcommands and options chosen at random."""
    def font():
        return rng.choice(["5x7", 10, 12, 16])

    def seed():
        return ["--seed", str(rng.randrange(1_000_000))]

    def screen():
        return 3, None, rng.choice([["screen", "on"], ["screen", "invert"], ["screen", "blink", "-r", rng.choice("248")],
                                    ["screen", "show", "--contrast", rng.choice(["8", "64", "160"])]])

    def draw():
        speed = rng.choice((4, 6, 8))
        options = rng.choice([[], ["--no-shade"], ["--style", rng.choice(STYLES)]])
        subject = ["--subject", rng.choice(sorted(SUBJECTS))] if rng.random() < 0.5 else []
        return speed + 5, None, ["draw", "--count", "1", "--speed", str(speed), "--hold", "3", *options, *subject, *seed()]

    makers = [
        screen,
        lambda: (4, font(), ["pattern"]),
        lambda: (4, font(), ["text"]),
        lambda: (3, rng.choice([10, 16, 24]), ["text", rng.choice(["Hello!", "SSD1306", "128x64", "OLED", "Pi 4B"])]),
        lambda: (5, font(), ["system", "-r", rng.choice("124")]),
        draw,
        lambda: (10, font(), ["game", rng.choice(list(GAMES)), *seed()]),
        lambda: (25, font(), ["forklift", "--auto", "--duration", "0", *seed()]),
    ]
    previous = None
    while True:
        maker = rng.choice([maker for maker in makers if maker is not previous])  # never the same kind twice
        previous = maker
        yield maker()


@cli.command()
@click.option("--random/--no-random", "-r/-R", "shuffle", default=True, show_default=True,
              help="Choose subcommands and their options at random; --no-random runs a fixed tour of them all.")
@click.option("--count", default=0, help="Number of steps.  [default: forever]")
@click.option("--seed", type=int, help="Random seed, to repeat the same steps.")
@with_display
def demo(display, shuffle, count, seed):
    """Run through the subcommands with various options, a few seconds each.

    Each step shows the equivalent command line.
    """
    if not display.live:
        raise click.UsageError("demo needs a live display, not --preview")
    ctx = click.get_current_context()
    steps = random_steps(random.Random(seed)) if shuffle else itertools.cycle(TOUR)
    for seconds, font_size, args in itertools.islice(steps, count or None):
        command = cli.commands[args[0]]
        params = command.make_context(args[0], list(args[1:]), parent=ctx).params
        display.font = display.base_font if font_size is None else Font(font_size)
        display.status("demo: oled_test.py " + " ".join((["-fs", str(font_size)] if font_size else []) + args))
        display.deadline = time.monotonic() + seconds * display.time_scale
        try:
            while True:
                try:
                    command.callback.__wrapped__(display, **params)  # the command itself, on this display
                    display.hold()
                except FontChange:
                    continue  # the same step again, in the new font, for the rest of its time
        except TimeUp:
            pass
        finally:
            display.deadline = None
            display.reset()  # undo any screen settings for the next step


def responds(address):
    from smbus2 import SMBus
    with SMBus(I2C_BUS) as bus:
        try:
            bus.write_quick(address)
            return True
        except OSError:
            return False


def keys_help():
    """The keys, for the end of --help.  Made from the key tables, so it's always up to date."""
    def wrapped(label, text):  # (click indents the epilog by 2 more)
        return textwrap.fill(text, width=77, initial_indent=f"  {label:11}", subsequent_indent=" " * 13)

    lines = [textwrap.fill("Keys, while a subcommand runs in a terminal or in the emulator window.  With keys "
                           "available, subcommands that show one picture wait for the next key instead of ending.",
                           width=77), "",
             wrapped("h", "help: show these keys on the display"),
             wrapped("x q", "quit (Esc or closing the window also quits the emulator; Ctrl-C always works)"),
             "",
             "  Switch subcommand; press the same key again for its next options, in turn:"]
    for key, name in KEY_COMMANDS.items():
        options = [" ".join((["-fs", str(size)] if size else []) + arguments)
                   or ("(all, taking turns)" if name == "game" else "(default)") for size, arguments in key_options(name)]
        lines.append(wrapped(f"{key} {name}", " | ".join(options)))
    lines += ["",
              wrapped("0-9", "speed: 0 fastest (a quarter of the time), 4 normal, 9 slowest (5.7 times as long)"),
              wrapped("c", "next foreground color: " + " ".join(FOREGROUNDS) + " (emulated displays only)"),
              wrapped("C", "next background color: " + " ".join(BACKGROUNDS) + " (emulated displays only)"),
              wrapped("f", "next font size: " + " ".join(map(str, FONT_SIZES))),
              wrapped("R", "reset the colors, font size and speed to how the program started")]
    return "\n\n".join("\b\n" + paragraph for paragraph in "\n".join(lines).split("\n\n"))


def main():
    try:
        cli.main(standalone_mode=False)
    except click.exceptions.Abort:
        pass  # Ctrl-C, or the emulator window closed
    except click.ClickException as error:
        error.show()
        sys.exit(error.exit_code)
    except OledNotFound as error:
        found = [f"0x{address:02X}" for address in ADDRESSES if responds(address)]
        hint = f"An SSD1306 answers at {' and '.join(found)}: use -a" if found else \
            "No SSD1306 answers at 0x3C or 0x3D: check the wiring and that I2C is enabled"
        sys.exit(f"Error: {error}\n{hint}")


cli.epilog = keys_help()  # (made here, once the subjects, games and key tables all exist)

if __name__ == "__main__":
    main()
