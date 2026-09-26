#!/usr/bin/env python3
#
# Aiko Services: OLED keys console
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# "aiko_oled keys": an interactive console in the terminal for a running
# OLED Actor.  Keys typed here become wire commands and settings updates,
# through the key map in keys.py (which the emulator window shares):
# letters switch applets (the same letter again: the next preset, e.g. g
# steps through pong, asteroids, invaders and all three in turn; p, t and
# s through the fonts; t through messages; d through styles and subjects),
# arrow keys go to the running applet, digits set the speed, and other
# keys change settings through the shared state, exactly as the Dashboard
# does.  A status line shows the Actor's shared state as it changes.
#
# Keys
# ~~~~
#   s status  l log  p pattern  t text  d draw  D demo  S blink  C clock
#   e eyes  g games: pong, asteroids, invaders, forklift  G forklift game
#   h ? help (again: the next page)
#   arrows: (key left|right|up|down)   0-9 speed (0 fastest, 4 normal, 9 slowest)
#   f F next / previous font   T title on/off   i invert   o power
#   a all pixels on   + - contrast   b B next foreground / background color
#   c clear   R reset the settings and colors   x q quit the console
#   X exit the Actor
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

from aiko_services.examples.oled.keys import (        # the key map, shared
    ARROWS, KEY_APPLETS, PRESETS, RESET, applet, key_command, reset_commands,
    update,
)
from aiko_services.examples.oled.oled import (
    OLED, OLEDApplets, _service_filter,
)

__all__ = ["KEY_APPLETS", "PRESETS", "RESET", "Keyboard", "KeysConsole", "applet",
           "key_command", "reset_commands", "update"]

POLL_PERIOD = 0.05
STATUS_KEYS = ("applet", "applet_detail", "fps", "speed", "font", "contrast",
               "invert", "power", "all_on", "foreground", "background", "last_error")

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
        else:
            commands = reset_commands(self.state) if key == "R"  \
                else key_command(key, self.state)
            for command in commands:
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
