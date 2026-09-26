#!/usr/bin/env python3
#
# Aiko Services: OLED applications
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# The higher-level features of the OLED Actor: an application is a source
# of 128x64 frames that the Actor steps from its event-loop timer at the
# application's frame rate (times the "speed" setting).  Applications never
# sleep, never block and never touch the Actor: they get a Host with just
# what they may use.  Keys reach interactive applications through key().
#
# Wire form:  (application NAME [WORDS ...] [key=value ...])
#             (application none)
#
# Applications
# ~~~~~~~~~~~~
#   status [rate=1]   the host's status: IP address, date, time and uptime,
#                     CPU and memory, disk and network, temperature, load,
#                     and the last (log ...) lines.  The default, and the
#                     main purpose of the Actor: a display for headless hosts
#   help              the wire commands and settings, on the display
#
# Not part of the Interface composition pattern (see ADR-022): plain
# presentation classes owned by the Actor, not Services.
#
# To Do
# ~~~~~
# - Phase 2: pattern, text, blink, games, forklift, draw, demo

from datetime import datetime
import os
import random
import socket
import time

from PIL import Image

from aiko_services.examples.oled.graphics import HEIGHT, WIDTH, stamp

__all__ = [
    "APPLICATIONS", "OPTION_LENGTH_MAXIMUM", "Application", "ApplicationDone",
    "HelpApplication", "Host", "StatusApplication", "parse_application_args",
]

OPTION_LENGTH_MAXIMUM = 64  # characters per word or option value (P9 bound)

class ApplicationDone(Exception):
    """The application finished: the Actor goes back to its default"""

class Host:
    """What an application may use.  The Actor implements this; tests can
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
        """Tell observers what the application is doing (share
        "application_detail"); one token, no spaces"""

    def control(self, name, value):
        """Change a display setting, e.g. control("power", "off")"""

class Application:
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
        Raise ApplicationDone when finished"""

        return None

    def key(self, name, state):
        """A key event: name "up", "down", "left", "right" or a character;
        state "tap", "down" or "up" """

    def stop(self):
        """The application is being replaced: undo any settings it changed"""

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

def parse_application_args(args, spec):
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

class StatusApplication(Application):
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

class HelpApplication(Application):
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
        "(application NAME)",
        "set contrast|invert",
        "set title|font|speed",
        "aiko_oled --help",
    ]

    def step(self):
        return self.write_lines(self.LINES)

APPLICATIONS = {
    StatusApplication.name: StatusApplication,
    HelpApplication.name: HelpApplication,
}
