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
# Not part of the Interface composition pattern (see ADR-022): plain
# presentation classes owned by the Actor, not Services.
#
# To Do
# ~~~~~
# - Phase 1: status (the main goal), help
# - Phase 2: pattern, text, blink, games, forklift, draw, demo

import random

from PIL import Image

from aiko_services.examples.oled.graphics import HEIGHT, WIDTH

__all__ = [
    "APPLICATIONS", "OPTION_LENGTH_MAXIMUM", "Application", "ApplicationDone",
    "Host", "parse_application_args",
]

OPTION_LENGTH_MAXIMUM = 64  # characters per word or option value (P9 bound)

class ApplicationDone(Exception):
    """The application finished: the Actor goes back to its default"""

class Host:
    """What an application may use.  The Actor implements this; tests can
    pass a plain one"""

    width, height = WIDTH, HEIGHT

    def __init__(self, font, rng=None, speed=1.0):
        self.font = font
        self.rng = rng or random.Random()
        self.speed = speed

    def connection(self):
        """The Actor's connection state: NONE, NETWORK, TRANSPORT, REGISTRAR"""

        return "NONE"

    def log_lines(self):
        """The most recent (log ...) lines, oldest first"""

        return []

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

APPLICATIONS = {}  # name: Application subclass (filled in Phases 1 and 2)
