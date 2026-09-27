#!/usr/bin/env python3
#
# Aiko Services: OLED keys console
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# "aiko_oled keys": an interactive console in the terminal for a running
# display Actor.  Every key typed here is sent as "(key K tap)": the key
# map lives on the Actor (keys.py), which runs a mapped key's preset (g
# steps through pong, asteroids, invaders and the forklift; s and S the
# status screens and views; digits set the speed; other keys change
# settings) and passes any other key, the arrows above all, to the running
# applet.  Thus the console, the emulator window and the Dashboard plug-in
# behave the same.  Only x, q (quit the console) and X (stop the Actor)
# are the console's own.  A status line shows the Actor's shared state.
#
# Keys
# ~~~~
#   s status screens: host, wifi   S the next view of that screen: text, charts
#   l log  p pattern  t text  d draw  D demo  P blink  C clock  e eyes
#   g games: pong, asteroids, invaders, forklift   G forklift game
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

from aiko_services.examples.oled.keys import ARROWS
from aiko_services.examples.oled.oled import (
    Display, Interaction, _service_filter,
)

__all__ = ["Keyboard", "KeysConsole"]

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
        self.display = self.interaction = None
        self.cache = {}                  # the Actor's shared state, kept by an ECConsumer
        self.status = ""
        self.confirm_exit = False

    def run(self):
        self.keyboard = Keyboard.open()
        if self.keyboard is None:
            raise click.UsageError("keys needs a terminal (stdin isn't one)")
        try:
            aiko.event.add_timer_handler(self._timed_out, self.timeout)
            aiko.do_discovery(Interaction, _service_filter(self.name),
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
        self.interaction = service
        self.display = aiko.get_service_proxy(f"{self.topic_path}/in", Display)
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
                self.display.stop()
                click.echo("\r\nstop sent")
                aiko.process.terminate()
            return
        if key in ("x", "q"):
            aiko.process.terminate()
        elif key == "X":
            self.confirm_exit = True
            click.echo("\r\nExit the OLED Actor?  y to confirm", nl=False)
        else:
            self.interaction.key(key, "tap")    # the Actor's key map decides

    def _show_status(self):
        status = "  ".join(f"{key} {self.cache[key]}" for key in STATUS_KEYS if key in self.cache)
        if status != self.status:
            self.status = status
            click.echo(f"\r\x1b[K{status}", nl=False)
