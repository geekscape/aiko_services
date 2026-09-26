#!/usr/bin/env python3
#
# Aiko Services: OLED keys console
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# "aiko_oled keys": an interactive console in the terminal for a running
# OLED Actor.  Keys typed here become wire commands: letters switch
# applets (the same letter again: the next preset, e.g. g steps through
# pong, asteroids, invaders and all three in turn; p, t and s through the
# fonts; t through messages; d through styles and subjects), arrow keys
# go to the running applet, digits set the speed, and other keys
# change settings through the shared state, exactly as the Dashboard does.
# A status line shows the Actor's shared state as it changes.
#
# Keys
# ~~~~
#   s status  l log  p pattern  t text  d draw  g games  F forklift game
#   A forklift  D demo  b blink  C clock  e eyes  h help (again: next page)
#   arrows: (key left|right|up|down)   0-9 speed (0 fastest, 4 normal, 9 slowest)
#   f next font   T title on/off   i invert   o power   a all pixels on
#   + - contrast
#   c clear   R reset   ? this list   x q quit the console   X exit the Actor
#
# The console runs on the Aiko Services event loop: the keyboard is polled
# by a timer (no thread), and the Actor is found by discovery.
#
# Not part of the Interface composition pattern (see ADR-022): a CLI shell.

import os
import re
import select
import sys

import click

import aiko_services as aiko
from aiko_services.main.utilities import get_hostname

from aiko_services.examples.oled.drawings import SUBJECTS
from aiko_services.examples.oled.graphics import FONT_SIZES
from aiko_services.examples.oled.oled import (
    OLED, OLEDApplets, _service_filter,
)

__all__ = ["KEY_APPLETS", "PRESETS", "Keyboard", "KeysConsole", "applet", "key_command", "update"]

ARROWS = {"A": "up", "B": "down", "C": "right", "D": "left"}  # the terminal's codes
def applet(name, *arguments):
    return ("applet", (name, *arguments))

def update(key, value):
    return ("update", key, value)

# What each applet key sends; the same key again: the next preset (as the
# original oled_test.py stepped through each subcommand's options).  A
# preset without its own font goes back to the base font (see key_command)
PRESETS = {
    "s": [[applet("status")], [applet("status", "rate=4")],
          [update("font", "5x7"), applet("status")],
          [update("font", "10"), applet("status")],
          [update("font", "12"), applet("status")]],
    "l": [[applet("log")]],
    "h": [[applet("help", f"page={page}")] for page in range(1, 7)],
    "p": [[applet("pattern")], [update("font", "5x7"), applet("pattern")],
          [update("font", "10"), applet("pattern")],
          [update("font", "16"), applet("pattern")]],
    "t": [[applet("text")], [update("font", "5x7"), applet("text")],
          [update("font", "10"), applet("text")],
          [update("font", "16"), applet("text")],
          [update("font", "10"), applet("text", "Hello!")],
          [update("font", "24"), applet("text", "OLED")],
          [update("font", "16"), applet("text", "128x64")]],
    "b": [[applet("blink")], [applet("blink", "rate=8")]],
    "d": [[applet("draw")], [applet("draw", "shade=off")],
          [applet("draw", "style=hatch")], [applet("draw", "style=stipple")]]
         + [[applet("draw", f"subject={subject}")] for subject in sorted(SUBJECTS)],
    "g": [[applet("pong")], [applet("asteroids")], [applet("invaders")], [applet("games")]],
    "F": [[applet("forklift_game")]],
    "A": [[applet("forklift")]],
    "D": [[applet("demo")], [applet("demo", "random=off")]],
    "C": [[applet("clock")], [applet("clock", "title=on")], [applet("clock", "seconds=off")]],
    "e": [[applet("eyes")]] + [[applet("eyes", f"emotion={emotion}")]
                               for emotion in ("happy", "sad", "angry", "surprised",
                                               "sleepy", "suspicious", "curious", "loving")],
}
KEY_APPLETS = {key: presets[0][-1][1][0] for key, presets in PRESETS.items()}
RESET = {"contrast": "255", "invert": "off", "power": "on", "all_on": "off",
         "font": "5x7", "speed": "1"}
POLL_PERIOD = 0.05
STATUS_KEYS = ("applet", "applet_detail", "fps", "speed", "font",
               "contrast", "invert", "power", "all_on", "last_error")

class Keyboard:
    """Keys typed in the terminal, read as they're typed without waiting
    (stdin in cbreak mode)"""

    def __init__(self):
        import termios
        import tty
        self.termios = termios
        self.saved = termios.tcgetattr(sys.stdin)
        tty.setcbreak(sys.stdin)  # no Enter needed and no echo; Ctrl-C works

    @classmethod
    def open(cls):
        """A Keyboard, or None when stdin isn't a terminal"""

        return cls() if sys.stdin.isatty() else None

    def read(self):
        """The keys typed since the last read: characters, or "up", "down",
        "left" or "right" for the arrow keys"""

        typed = b""
        while select.select([sys.stdin], [], [], 0)[0]:
            byte = os.read(sys.stdin.fileno(), 1)
            if not byte:
                break
            typed += byte
        keys = []
        pattern = r"\x1b(?:\[[0-9;]*[A-Za-z~]|O[A-Za-z])?|."
        for key in re.findall(pattern, typed.decode(errors="ignore"), re.DOTALL):
            if not key.startswith("\x1b"):
                keys.append(key)
            elif len(key) > 1 and key[-1] in ARROWS:  # (other codes are dropped)
                keys.append(ARROWS[key[-1]])
        return keys

    def close(self):
        self.termios.tcsetattr(sys.stdin, self.termios.TCSADRAIN, self.saved)

def key_command(key, state):
    """The commands a console key sends: a list of ("applet", arguments),
    ("key", arguments), ("clear", ()) or ("update", key, value); [] for a
    key that means nothing.  "state" holds the preset turns, the current
    key, the Actor's settings and the base font.  Pure, for tests"""

    if key in ARROWS.values():
        return [("key", (key, "tap"))]
    if key in PRESETS:
        presets = PRESETS[key]
        turn = state["turns"].get(key, -1) + 1 if state.get("current") == key else 0
        turn %= len(presets)
        state["turns"][key] = turn
        state["current"] = key
        commands = list(presets[turn])
        base = state.get("base_font")
        if base and not any(command[:2] == ("update", "font") for command in commands)  \
                and state["settings"].get("font", base) != base:
            commands.insert(0, update("font", base))     # back to the base font
        return commands
    if key.isdigit():
        return [update("speed", f"{2 ** ((4 - int(key)) / 2):.3g}")]
    if key == "T":
        current = state["settings"].get("title", "on")
        return [update("title", "on" if current == "off" else "off")]
    if key == "f":
        sizes = [str(size) for size in FONT_SIZES]
        current = state["settings"].get("font", "5x7")
        turn = (sizes.index(current) + 1) % len(sizes) if current in sizes else 0
        state["base_font"] = sizes[turn]
        return [update("font", sizes[turn])]
    if key in ("i", "o", "a"):
        name = {"i": "invert", "o": "power", "a": "all_on"}[key]
        current = state["settings"].get(name, "on" if name == "power" else "off")
        return [update(name, "off" if current == "on" else "on")]
    if key in ("+", "-"):
        try:
            contrast = int(state["settings"].get("contrast", "255"))
        except ValueError:
            contrast = 255
        contrast = max(0, min(255, contrast + (16 if key == "+" else -16)))
        return [update("contrast", str(contrast))]
    if key == "c":
        return [("clear", ())]
    return []

class KeysConsole:
    """The interactive console for one OLED Actor"""

    def __init__(self, name, timeout):
        self.name = name or get_hostname()
        self.timeout = timeout
        self.keyboard = None
        self.topic_path = None
        self.oled = self.applets = None
        self.cache = {}                  # the Actor's shared state, kept by an ECConsumer
        self.state = {"turns": {}, "current": None, "settings": self.cache}
        self.status = ""
        self.confirm_exit = False

    def run(self):
        self.keyboard = Keyboard.open()
        if self.keyboard is None:
            raise click.UsageError("keys needs a terminal (stdin isn't one)")
        try:
            aiko.event.add_timer_handler(self._timed_out, self.timeout)
            aiko.do_discovery(OLEDApplets, _service_filter(self.name),
                self._found, self._lost)
            aiko.process.run()
        finally:
            self.keyboard.close()
            click.echo()

    # Discovery ------------------------------------------------------------ #

    def _timed_out(self):
        aiko.event.remove_timer_handler(self._timed_out)
        if self.topic_path is None:
            click.echo(f"Timeout after {self.timeout:g} s: no OLED Actor named {self.name}", err=True)
            aiko.process.terminate(1)

    def _found(self, service_details, service):
        if self.topic_path is not None:
            return
        self.topic_path = service_details[0]
        self.applets = service
        self.oled = aiko.get_service_proxy(f"{self.topic_path}/in", OLED)
        aiko.compose_instance(aiko.ECConsumerImpl, aiko.ec_consumer_args(
            aiko.process, 0, self.cache, f"{self.topic_path}/control"))
        click.echo(f"OLED Actor {service_details[1]}: {self.topic_path}  (? for the keys)")
        aiko.event.add_timer_handler(self._poll, POLL_PERIOD)

    def _lost(self, service_details):
        if service_details[0] == self.topic_path:
            click.echo(f"\r\nOLED Actor {self.name} has gone")
            aiko.process.terminate()

    # Keys ----------------------------------------------------------------- #

    def _poll(self):
        if "base_font" not in self.state and "font" in self.cache:
            self.state["base_font"] = self.cache["font"]   # the font at the start
        for key in self.keyboard.read():
            self._key(key)
        self._show_status()

    def _key(self, key):
        if self.confirm_exit:
            self.confirm_exit = False
            if key == "y":
                self.oled.exit()
                click.echo("\r\nexit sent")
                aiko.process.terminate()
            return
        if key in ("x", "q"):
            aiko.process.terminate()
        elif key == "X":
            self.confirm_exit = True
            click.echo("\r\nExit the OLED Actor?  y to confirm", nl=False)
        elif key == "?":
            click.echo("\r\n" + self._help())
        elif key == "R":
            for name, value in RESET.items():
                self._update(name, value)
            self.applets.applet("status")
            self.state["current"] = "s"
            self.state["base_font"] = RESET["font"]
        else:
            for command in key_command(key, self.state):
                if command[0] == "update":
                    self._update(command[1], command[2])
                else:
                    getattr(self.applets if command[0] in ("applet", "key")
                            else self.oled, command[0])(*command[1])

    def _update(self, name, value):
        aiko.process.message.publish(f"{self.topic_path}/control", f"(update {name} {value})")

    def _show_status(self):
        status = "  ".join(f"{key} {self.cache[key]}" for key in STATUS_KEYS if key in self.cache)
        if status != self.status:
            self.status = status
            click.echo(f"\r\x1b[K{status}", nl=False)

    @staticmethod
    def _help():
        return "\r\n".join([
            "s status  l log  p pattern  t text  d draw  g games  F forklift game",
            "A forklift  D demo  b blink  C clock  e eyes  h help (again: the next page)",
            "(the same key again: the next preset, e.g. g: pong, asteroids, invaders, all;",
            " p, t, s: the fonts; t: messages; d: styles, subjects; e: emotions)",
            "arrows: keys for the applet   0-9 speed (4 normal)   f next font   T title",
            "i invert  o power  a all on  + - contrast  c clear  R reset",
            "? this list   x q quit the console   X exit the OLED Actor",
        ])
