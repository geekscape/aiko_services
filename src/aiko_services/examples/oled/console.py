#!/usr/bin/env python3
#
# Aiko Services: OLED keys console
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# "aiko_oled keys": an interactive console in the terminal for a running
# OLED Actor.  Keys typed here become wire commands: letters switch
# applications (the same letter again: its next option preset), arrow keys
# go to the running application, digits set the speed, and other keys
# change settings through the shared state, exactly as the Dashboard does.
# A status line shows the Actor's shared state as it changes.
#
# Keys
# ~~~~
#   s status  p pattern  t text  d draw  g games  F forklift game
#   A forklift  D demo  b blink  h help
#   arrows: (key left|right|up|down)   0-9 speed (0 fastest, 4 normal, 9 slowest)
#   f next font   i invert   o power   a all pixels on   + - contrast
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
    OLED, OLEDApplications, _service_filter,
)

__all__ = ["KEY_APPLICATIONS", "PRESETS", "Keyboard", "KeysConsole", "key_command"]

ARROWS = {"A": "up", "B": "down", "C": "right", "D": "left"}  # the terminal's codes
KEY_APPLICATIONS = {"s": "status", "p": "pattern", "t": "text", "d": "draw",
                    "g": "games", "F": "forklift_game", "A": "forklift",
                    "D": "demo", "b": "blink", "h": "help"}
PRESETS = {  # the same key again: the next argument list
    "status": [[], ["rate=4"]],
    "pattern": [[]],
    "text": [[], ["Hello!"], ["OLED"], ["128x64"]],
    "draw": [[], ["shade=off"], ["style=hatch"], ["style=stipple"]]
            + [[f"subject={subject}"] for subject in sorted(SUBJECTS)],
    "games": [[], ["duration=10"]],
    "forklift_game": [[]],
    "forklift": [[]],
    "demo": [[], ["random=off"]],
    "blink": [[], ["rate=8"]],
    "help": [[]],
}
RESET = {"contrast": "255", "invert": "off", "power": "on", "all_on": "off",
         "font": "5x7", "speed": "1"}
POLL_PERIOD = 0.05
STATUS_KEYS = ("application", "application_detail", "fps", "speed", "font",
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
    """The (method, arguments) or ("update", key, value) that a console key
    sends, given the console's state (presets, settings); None for keys
    that only change the console itself.  Pure, for tests"""

    if key in ARROWS.values():
        return ("key", (key, "tap"))
    if key in KEY_APPLICATIONS:
        name = KEY_APPLICATIONS[key]
        presets = PRESETS[name]
        turn = state["turns"].get(name, -1) + 1 if state.get("current") == name else 0
        state["turns"][name] = turn % len(presets)
        state["current"] = name
        return ("application", (name, *presets[turn % len(presets)]))
    if key.isdigit():
        return ("update", "speed", f"{2 ** ((4 - int(key)) / 2):.3g}")
    if key == "f":
        sizes = [str(size) for size in FONT_SIZES]
        current = state["settings"].get("font", "5x7")
        turn = (sizes.index(current) + 1) % len(sizes) if current in sizes else 0
        return ("update", "font", sizes[turn])
    if key in ("i", "o", "a"):
        name = {"i": "invert", "o": "power", "a": "all_on"}[key]
        current = state["settings"].get(name, "on" if name == "power" else "off")
        return ("update", name, "off" if current == "on" else "on")
    if key in ("+", "-"):
        try:
            contrast = int(state["settings"].get("contrast", "255"))
        except ValueError:
            contrast = 255
        contrast = max(0, min(255, contrast + (16 if key == "+" else -16)))
        return ("update", "contrast", str(contrast))
    if key == "c":
        return ("clear", ())
    return None

class KeysConsole:
    """The interactive console for one OLED Actor"""

    def __init__(self, name, timeout):
        self.name = name or get_hostname()
        self.timeout = timeout
        self.keyboard = None
        self.topic_path = None
        self.oled = self.applications = None
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
            aiko.do_discovery(OLEDApplications, _service_filter(self.name),
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
        self.applications = service
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
            self.applications.application("status")
            self.state["current"] = "status"
        else:
            command = key_command(key, self.state)
            if command is None:
                return
            if command[0] == "update":
                self._update(command[1], command[2])
            else:
                getattr(self.applications if command[0] in ("application", "key")
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
            "s status  p pattern  t text  d draw  g games  F forklift game  A forklift",
            "D demo  b blink  h help   (the same key again: the next options)",
            "arrows: keys for the application   0-9 speed (4 normal)   f next font",
            "i invert  o power  a all on  + - contrast  c clear  R reset",
            "? this list   x q quit the console   X exit the OLED Actor",
        ])
