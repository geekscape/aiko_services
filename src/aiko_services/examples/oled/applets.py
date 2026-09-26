#!/usr/bin/env python3
#
# Aiko Services: OLED applets
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# The higher-level features of the OLED Actor: an applet is a source
# of 128x64 frames that the Actor steps from its event-loop timer at the
# applet's frame rate (times the "speed" setting).  Applets never
# sleep, never block and never touch the Actor: they get a Host with just
# what they may use.  Keys reach interactive applets through key().
#
# Wire form:  (applet NAME [WORDS ...] [key=value ...])
#             (applet none)
#
# Applets
# ~~~~~~~~~~~~
#   status [rate=1]   the host's status: IP address, date, time and uptime,
#                     CPU and memory, disk and network, temperature, load,
#                     and the last (log ...) lines.  The default, and the
#                     main purpose of the Actor: a display for headless hosts
#   help              the wire commands and settings, on the display
#   pattern           the test pattern: shifted, missing or stretched rows show
#   text [WORDS]      the words centred; without words a screen full of digits
#   blink [rate=2]    the panel's power off and on: a hardware test
#   demo [random=on] [count=N] [seed=N]
#                     a tour of the applets and settings, a few seconds
#                     each, at random or the fixed TOUR
#   games.py: pong asteroids invaders games forklift forklift_game
#   drawings.py: draw
#
# Not part of the Interface composition pattern (see ADR-022): plain
# presentation classes owned by the Actor, not Services.
#
# To Do
# ~~~~~
# - None, yet !

from datetime import datetime
import itertools
import math
import os
import random
import socket
import time

from PIL import Image, ImageDraw

from aiko_services.examples.oled.graphics import (
    HEIGHT, INK, WIDTH, blank, paste_centred, pixels, stamp,
)

__all__ = [
    "APPLETS", "OPTION_LENGTH_MAXIMUM", "TOUR", "Applet",
    "AppletDone", "BlinkApplet", "DemoApplet", "HelpApplet",
    "Host", "PatternApplet", "StatusApplet", "TextApplet",
    "parse_applet_args", "pattern_image", "random_steps",
]

OPTION_LENGTH_MAXIMUM = 64  # characters per word or option value (P9 bound)

class AppletDone(Exception):
    """The applet finished: the Actor goes back to its default"""

class Host:
    """What an applet may use.  The Actor implements this; tests can
    pass a plain one"""

    width, height = WIDTH, HEIGHT
    name = "oled"

    def __init__(self, font, rng=None, speed=1.0):
        self.font = font
        self.rng = rng or random.Random()
        self.speed = speed

    def title_rows(self):
        """Pixel rows at the top that the Actor's title row covers (0: none)"""

        return 0

    def connection(self):
        """The Actor's connection state: NONE, NETWORK, TRANSPORT, REGISTRAR"""

        return "NONE"

    def log_lines(self):
        """The most recent (log ...) lines, oldest first"""

        return []

    def log_seen(self):
        """The log lines have been shown (clears the "L" annunciator)"""

    def keys_held(self):
        """The keys held down now: "up", "down", "left", "right", characters"""

        return set()

    def status(self, token):
        """Tell observers what the applet is doing (share
        "applet_detail"); one token, no spaces"""

    def setting(self, name):
        """The current value of a setting, e.g. setting("font")"""

        return None

    def control(self, name, value):
        """Change a display setting, e.g. control("power", "off")"""

class Applet:
    """A source of frames.  Subclasses set "name", "fps" (frames per second
    at speed 1) and "OPTIONS" (key: type), and implement step()"""

    name = "base"
    fps = 30
    wants_title = False  # True: the title row is drawn over the frame
    OPTIONS = {}         # option name: type, e.g. {"seed": int}
    description = ""     # one token for observers

    def __init__(self, host, words=(), options=None):
        self.host = host
        self.words = list(words)
        self.options = options or {}

    def step(self):
        """The next frame (a 128x64 "1" PIL image), or None for no change.
        Raise AppletDone when finished"""

        return None

    def key(self, name, state):
        """A key event: name "up", "down", "left", "right" or a character;
        state "tap", "down" or "up" """

    def stop(self):
        """The applet is being replaced: undo any settings it changed"""

    def frame(self):
        """A blank frame to draw on"""

        return Image.new("1", (self.host.width, self.host.height))

    def write_lines(self, lines, top=None):
        """A frame with the lines of text, one per text row, from the top
        (below the title row) down; lines that don't fit are dropped"""

        frame = self.frame()
        font = self.host.font
        y = self.host.title_rows() if top is None else top
        for line in lines:
            if y + font.line_height > self.host.height:
                break
            stamp(frame, font.render_line(line), 0, y)
            y += font.cell_height
        return frame

def parse_applet_args(args, spec):
    """Split wire arguments into plain words and key=value options, coercing
    each option with the type in spec.  Raises ValueError for an unknown
    option, a bad value or an over-long argument"""

    words, options = [], {}
    for arg in args:
        if not isinstance(arg, str):
            raise ValueError(f"argument {arg!r} isn't a string")
        if len(arg) > OPTION_LENGTH_MAXIMUM:
            raise ValueError(f"argument longer than {OPTION_LENGTH_MAXIMUM}")
        if "=" in arg:
            key, value = arg.split("=", 1)
            if key not in spec:
                raise ValueError(f"unknown option {key!r}")
            try:
                options[key] = spec[key](value)
            except (TypeError, ValueError):
                raise ValueError(f"bad value for {key}: {value!r}")
        else:
            words.append(arg)
    return words, options

# --------------------------------------------------------------------------- #

def ip_address():
    """The address of the interface that reaches the network, else "none" """

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
        try:
            udp.connect(("10.254.254.254", 1))  # sends nothing: picks the route
            return udp.getsockname()[0]
        except OSError:
            return "none"

def per_second(count):
    """Short human readable rate, e.g. 950, 12k, 3.4M"""

    for unit in ("", "k", "M", "G"):
        if count < 999.5:
            return f"{count:.1f}{unit}" if unit and count < 9.95 else f"{count:.0f}{unit}"
        count /= 1000
    return f"{count:.0f}T"

class StatusApplet(Applet):
    """The host's status, one item per text row, refreshed "rate" times a
    second (default once).  With the 5x7 font and the title row, seven
    rows: IP address; date; time and uptime; CPU and memory; disk and
    network traffic; temperature and CPU speed (or load); then the last
    (log ...) lines.  Without the title row the first line is the host
    name and the connection state.  Sampling uses non-blocking psutil calls"""

    name = "status"
    fps = 1
    wants_title = True
    OPTIONS = {"rate": float}
    description = "status"

    def __init__(self, host, words=(), options=None):
        super().__init__(host, words, options)
        self.fps = max(0.1, min(10.0, self.options.get("rate", 1.0)))
        import psutil
        self.psutil = psutil
        psutil.cpu_percent(interval=None)  # starts the measurement
        self._before = (time.monotonic(), self._network_bytes())

    def _network_bytes(self):
        counters = [counter for name, counter
            in self.psutil.net_io_counters(pernic=True).items()
            if not name.startswith("lo")]
        return (sum(counter.bytes_recv for counter in counters),
                sum(counter.bytes_sent for counter in counters))

    def _cpu_speed(self):
        try:
            frequency = self.psutil.cpu_freq()
            return f"{frequency.current:.0f}MHz" if frequency else ""
        except (AttributeError, NotImplementedError, OSError, RuntimeError):
            return ""

    def _temperature(self):
        try:
            sensors = self.psutil.sensors_temperatures()  # Linux only
        except (AttributeError, NotImplementedError, OSError):
            return None
        for readings in sensors.values():
            if readings:
                return readings[0].current
        return None

    def lines(self):
        psutil = self.psutil
        now = (time.monotonic(), self._network_bytes())
        seconds = max(now[0] - self._before[0], 1e-6)
        received, sent = ((b - a) / seconds for a, b in zip(self._before[1], now[1]))
        self._before = now
        up = int(time.time() - psutil.boot_time())
        days, hours, minutes = up // 86400, up // 3600 % 24, up // 60 % 60
        uptime = f"{days}d{hours:02d}h" if days else f"{hours}h{minutes:02d}m"
        clock = datetime.now()
        temperature = self._temperature()
        try:
            load = "Load {:.2f} {:.2f} {:.2f}".format(*os.getloadavg())
        except (AttributeError, OSError):
            load = ""
        lines = []
        if not self.host.title_rows():
            lines.append(f"{self.host.name} {self.host.connection()}"[:21])
        lines += [
            f"IP {ip_address()}",
            f"{clock:%a %d %b %Y}",
            f"{clock:%H:%M:%S} up {uptime}",
            f"CPU {psutil.cpu_percent(interval=None):.0f}% "
            f"Mem {psutil.virtual_memory().percent:.0f}%",
            f"Disk {psutil.disk_usage(os.path.expanduser('~')).percent:.0f}% "
            f"Rx{per_second(received)} Tx{per_second(sent)}",
            (f"Temp {temperature:.1f}C {self._cpu_speed()}".rstrip()
             if temperature is not None else load),
        ]
        lines += self.host.log_lines()
        return [line for line in lines if line]

    def step(self):
        frame = self.write_lines(self.lines())
        self.host.log_seen()
        return frame

class HelpApplet(Applet):
    """The wire commands and settings, on the display"""

    name = "help"
    fps = 0.2
    wants_title = True
    description = "help"
    LINES = [
        "(text X Y WORDS)",
        "(log WORDS)",
        "(pixels X Y ...)",
        "(clear) (exit)",
        "(applet NAME)",
        "set contrast|invert",
        "set title|font|speed",
        "aiko_oled --help",
    ]

    def step(self):
        return self.write_lines(self.LINES)

# --------------------------------------------------------------------------- #

def pattern_image(font):
    """The test pattern: a border on all four edges; ruler ticks every 8
    pixels (longer every 32) along the top and left; corner-to-corner
    diagonals; a circle; blocks of even rows only and odd rows only (left),
    a solid block and a 1-pixel checkerboard (right); "centre" in the middle"""

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

def digits_image(font):
    """A screen full of digits: each row counts 0123456789012... across every
    column, starting one digit later than the row above"""

    image = blank()
    font = font.mono()
    digits = [font.render_line(str(digit)) for digit in range(10)]
    _, top, _, bottom = font.render("0123456789").getbbox()
    digits = [digit.crop((0, top - font.top, digit.width, bottom - font.top))
              for digit in digits]
    cell = 6 if font.truetype is None else round(font.truetype.getlength("0"))
    pitch = bottom - top + 1
    for row in range(math.ceil(HEIGHT / pitch)):
        for column in range(math.ceil(WIDTH / cell)):
            stamp(image, digits[(row + column) % 10], column * cell, row * pitch)
    return image

class StillApplet(Applet):
    """One picture, drawn again only when the font changes"""

    fps = 2

    def __init__(self, host, words=(), options=None):
        super().__init__(host, words, options)
        self._font = None

    def picture(self):
        return self.frame()

    def step(self):
        if self._font is self.host.font:
            return None
        self._font = self.host.font
        return self.picture()

class PatternApplet(StillApplet):
    """The test pattern, to check a panel for shifted, missing, stretched or
    interleaved rows and columns"""

    name = "pattern"
    description = "pattern"

    def picture(self):
        return pattern_image(self.host.font)

class TextApplet(StillApplet):
    """WORDS centred in the current font, or without words the screen full
    of digits"""

    name = "text"

    def __init__(self, host, words=(), options=None):
        super().__init__(host, words, options)
        self.description = "message" if self.words else "digits"

    def picture(self):
        if not self.words:
            return digits_image(self.host.font)
        frame = self.frame()
        paste_centred(frame, " ".join(self.words), self.host.font)
        return frame

class BlinkApplet(Applet):
    """The panel's power switched off and on, "rate" times a second, over
    the test pattern: a hardware test.  Stopping it leaves the power on"""

    name = "blink"
    fps = 2
    OPTIONS = {"rate": float}
    description = "blink"

    def __init__(self, host, words=(), options=None):
        super().__init__(host, words, options)
        self.fps = max(0.5, min(10.0, self.options.get("rate", 2.0)))
        self._on = True
        self._shown = False

    def step(self):
        self._on = not self._on
        self.host.control("power", "on" if self._on else "off")
        if self._shown:
            return None
        self._shown = True
        return pattern_image(self.host.font)

    def stop(self):
        self.host.control("power", "on")

# The fixed tour: (seconds, applet, arguments, settings for the step)
TOUR = [
    (3, "blink", ["rate=4"], {}),
    (4, "pattern", [], {}),
    (3, "pattern", [], {"invert": "on"}),
    (3, "pattern", [], {"contrast": "16"}),
    (4, "text", [], {}),
    (4, "text", [], {"font": "10"}),
    (3, "text", ["Hello!"], {"font": "20"}),
    (5, "status", [], {}),
    (4, "status", [], {"font": "12"}),
    (13, "draw", ["subject=forklift", "count=1", "hold=3"], {}),
    (8, "draw", ["shade=off", "speed=4", "count=1", "hold=2"], {}),
    (13, "draw", ["style=hatch", "count=1", "hold=3"], {}),
    (10, "pong", [], {}),
    (10, "asteroids", [], {}),
    (10, "invaders", [], {}),
    (25, "forklift", [], {}),
]

def random_steps(rng):
    """Endless demo steps like those in TOUR, chosen at random; never the
    same kind twice in a row"""

    def font():
        return {"font": rng.choice(["5x7", "10", "12", "16"])}

    def seed():
        return [f"seed={rng.randrange(1000000)}"]

    def screen():
        return rng.choice([
            (3, "pattern", [], {"invert": "on"}),
            (3, "blink", [f"rate={rng.choice('248')}"], {}),
            (3, "pattern", [], {"contrast": rng.choice(["8", "64", "160"])}),
        ])

    def draw():
        speed = rng.choice((4, 6, 8))
        options = rng.choice([[], ["shade=off"], [f"style={rng.choice(('outline', 'hatch', 'stipple'))}"]])
        subject = [f"subject={rng.choice(('house', 'tree', 'pine', 'cat', 'dog', 'bicycle', 'flower', 'forklift'))}"]  \
            if rng.random() < 0.5 else []
        return (speed + 5, "draw", ["count=1", f"speed={speed}", "hold=3", *options, *subject, *seed()], {})

    makers = [
        screen,
        lambda: (4, "pattern", [], font()),
        lambda: (4, "text", [], font()),
        lambda: (3, "text", [rng.choice(["Hello!", "SSD1306", "128x64", "OLED", "Pi 4B"])],
                 {"font": rng.choice(["10", "16", "24"])}),
        lambda: (5, "status", [f"rate={rng.choice('124')}"], font()),
        draw,
        lambda: (10, rng.choice(["pong", "asteroids", "invaders"]), seed(), font()),
        lambda: (25, "forklift", seed(), font()),
    ]
    previous = None
    while True:
        maker = rng.choice([maker for maker in makers if maker is not previous])
        previous = maker
        yield maker()

class DemoApplet(Applet):
    """A tour of the applets and settings, a few seconds each: at
    random (default) or the fixed TOUR ("random=off"); "count" steps, 0 for
    ever.  Settings a step changes are put back after it"""

    name = "demo"
    fps = 30
    OPTIONS = {"random": lambda text: text not in ("off", "false", "0", "no"),
               "count": int, "seed": int}
    description = "demo"

    def __init__(self, host, words=(), options=None):
        super().__init__(host, words, options)
        rng = host.rng if "seed" not in self.options  \
            else random.Random(self.options["seed"])
        steps = random_steps(rng) if self.options.get("random", True)  \
            else itertools.cycle(TOUR)
        count = self.options.get("count", 0)
        self._steps = itertools.islice(steps, count) if count else steps
        self._sub = None
        self._saved = {}
        self._left = 0

    @property
    def wants_title(self):
        return self._sub.wants_title if self._sub else False

    def _restore(self):
        if self._sub is not None:
            self._sub.stop()
            self._sub = None
        for key, value in self._saved.items():
            if value is not None:
                self.host.control(key, value)
        self._saved = {}

    def _next_step(self):
        self._restore()
        while True:
            seconds, name, args, settings = next(self._steps)  # StopIteration: done
            applet_class = APPLETS.get(name)
            if applet_class is None:
                continue
            try:
                words, options = parse_applet_args(args, applet_class.OPTIONS)
                self._sub = applet_class(self.host, words, options)
                break
            except ValueError:
                continue
        for key, value in settings.items():
            self._saved.setdefault(key, self.host.setting(key))
            self.host.control(key, value)
        self._left = round(seconds * self.fps)
        self._every = max(1, round(self.fps / max(self._sub.fps, 0.001)))
        self._tick = 0
        self.description = f"demo_{name}"
        self.host.status(self.description)

    def step(self):
        if self._sub is None or self._left <= 0:
            try:
                self._next_step()
            except StopIteration:
                self._restore()
                raise AppletDone
            return self._sub.step()
        self._left -= 1
        self._tick += 1
        if self._tick % self._every:
            return None
        try:
            return self._sub.step()
        except AppletDone:
            self._left = 0
            return None

    def stop(self):
        self._restore()

APPLETS = {applet.name: applet for applet in (
    StatusApplet, HelpApplet, PatternApplet, TextApplet,
    BlinkApplet, DemoApplet)}
