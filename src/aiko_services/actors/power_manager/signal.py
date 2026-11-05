#!/usr/bin/env python3
#
# Aiko Services: the power manager's signals
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# One short sound for each thing that an operator must know without a
# screen: the host is up and holding, a Pipeline runs, the host is stopping,
# and a button press has been accepted.
#
# A pattern is data: durations in seconds, where the first is "on", the next
# is "off", and so on.  Therefore a test compares a list, with no hardware
# and no sound, and a new pattern is a table entry rather than code.
#
# The buzzer is driven from a worker thread.  A pattern sleeps between its
# edges, and the event-loop thread must never sleep (P2).  One lock keeps
# two patterns from interleaving into a sound that means nothing.
#
# **The buzzer does not use the GPIO character device**, for the same
# reason the hold does not, reached from the other direction.
#
# gpiozero, lgpio and libgpiod all claim a line, and the claim is held for
# the life of the process.  A close does not free it: gpiozero re-claims
# the line as an input with no pull and leaves the claim in place, which
# its own source says in as many words (gpiozero/pins/lgpio.py).  Two other
# writers reach this same pad -- the start-up unit and the shutdown hook,
# which use the platform's pin utility because neither can import Python --
# and a claim refuses them, and the command line too.
#
# Measured on 2026-11-05: "aiko_power_manager signal" was refused with
# "GPIO busy" by an Actor that had claimed the line once at start-up, and
# lgpio named the Actor's library as the consumer while the pin read as an
# input.  Claiming for each pattern instead of once, which was the first
# attempt at this, changes nothing another process can see.
#
# So the pad is driven and nothing is claimed, exactly as hold.py does it.
# One subprocess for each edge, which the shutdown hook's own 50 ms chirps
# show is quick enough.
#
# These classes are internal collaborators of the module Implementation,
# and not a public API: the one public Interface is PowerManager (ADR-028
# decision 1).  _Emulated in the display outputs is the same shape.
#
# gpiozero is imported in open(), and nowhere else (P9).
#
# To Do
# ~~~~~
# * The RGB LED as a second signal device, after the library study (the
#   plan's phase 7).  play() already takes a name and not a sound

import threading
import time

from aiko_services.actors.power_manager.hold import hold_tool, run_tool

__all__ = [
    "BUZZER_GPIO", "FakeBuzzer", "GpioBuzzer", "PATTERNS", "choose_buzzer",
    "pattern_seconds",
]

BUZZER_GPIO = 4                    # BCM, active high

# Durations in seconds: on, off, on, off ...
#
# A buzzer has one pitch, so a pattern tells them apart by its rhythm and
# by its length.  Two rules come from that.  A sound an operator waits for
# ends on a long note, which is the part that carries across a room.  And a
# sound that reports a fault, or a loss, is fast and repeated.
PATTERNS = {
    # Short, then long: "rea-dy".  An operator holds a soft power button
    # for ten seconds or more before this plays, and the first version of
    # it was 300 ms of two chirps, which the lead found easy to miss
    "booted": (0.15, 0.10, 0.50),
    # Three quick taps and a note that resolves them: the cheerful one.
    # It reports that an application does its work, and it must not sound
    # like any of the others
    "pipeline": (0.07, 0.06, 0.07, 0.06, 0.07, 0.06, 0.35),
    "shutdown": (0.05, 0.05, 0.05, 0.05, 0.05),     # Three fast chirps
    "accepted": (0.5,),              # The press reached its three seconds
    # "pipeline" turned around: the long note first, then taps trailing
    # away.  It reports that the work an application was doing has stopped,
    # so it must be heard as the opposite of the cheerful one, and must not
    # be mistaken for "shutdown", which means the host itself is going.
    # Exactly reversing "pipeline" gave it the same total length, which
    # the rule below forbids and the tests caught: two sounds are told
    # apart by rhythm AND by length
    "lost": (0.45, 0.08, 0.06, 0.08, 0.06, 0.08),
}

def pattern_seconds(name):
    """How long the pattern takes.  A caller that must wait for a sound to
    finish, such as the shutdown hook, needs this and not a guess"""

    return round(sum(PATTERNS[name]), 3)

class FakeBuzzer:
    """No buzzer: the test double, and what a platform without one gets.
    Every play() is recorded, with the pattern that was asked for"""

    device = "none"

    def __init__(self, **_):
        self.played = []
        self.opened = False
        self.closed = False

    def open(self):
        self.opened = True

    def play(self, name):
        self.played.append(name)

    def close(self):
        self.closed = True

class GpioBuzzer:
    """A buzzer on one output line, driven by the platform's pin utility.

    Nothing is claimed, so the start-up unit, the shutdown hook and the
    command line can all sound this pad while this Actor runs.  The module
    header says why that matters and what was measured.

    play() returns at once and the pattern runs on a worker thread, because
    a pattern sleeps and the event-loop thread must not (P2)"""

    device = "gpio"

    def __init__(self, gpio=BUZZER_GPIO, thread=True, sleeper=time.sleep,
        runner=None, **_):

        self.gpio = gpio
        self._thread = bool(thread)
        self._sleep = sleeper
        # The pin utility, injected so a test asserts the exact arguments
        # with no subprocess and no hardware, as hold.py does
        self._runner = runner or run_tool
        self._lock = threading.Lock()
        self.played = []
        self.opened = False

    def open(self):
        """Leave the line low, and hold nothing.

        It drives the pad once, so a platform with no pin utility raises
        here and reports no "signal" property, rather than failing at the
        first sound"""

        self._set(False)
        self.opened = True

    def play(self, name):
        """Sound one pattern.  An unknown name is refused, so that a typo is
        silent rather than a long note"""

        if name not in PATTERNS:
            raise ValueError(
                f'unknown pattern "{name}": one of {sorted(PATTERNS)}')
        self.played.append(name)
        if self._thread:
            worker = threading.Thread(
                target=self._run, args=(name,), daemon=True,
                name=f"buzzer_{name}")
            worker.start()
            return worker
        self._run(name)
        return None

    def close(self):
        """Leave the line low.  There is nothing to give back, because
        nothing was claimed"""

        try:
            self._set(False)
        except Exception:                            # noqa: BLE001
            pass                       # A close must not raise
        self.opened = False

    def _run(self, name):
        """The pattern, on its own thread.  The lock keeps two patterns from
        interleaving.  A failing buzzer must never raise into a caller that
        is shutting a host down"""

        with self._lock:
            try:
                for index, seconds in enumerate(PATTERNS[name]):
                    self._set(index % 2 == 0)
                    self._sleep(seconds)
            finally:
                self._set(False)

    def _set(self, on):
        """One edge, through the pin utility"""

        level = "dh" if on else "dl"
        code, output = self._runner(["set", str(self.gpio), "op", level])
        if code != 0:
            raise OSError(
                f"set {self.gpio} op {level} failed: {output.strip()[:80]}")

def choose_buzzer(buzzer="auto", **parameters):
    """The buzzer for "buzzer": "gpio", "none", or "auto", which is the real
    one where gpiozero can be imported and the fake one everywhere else.
    Nothing is acquired here"""

    if buzzer == "auto":
        # The pin utility, and not a library: that is what drives this pad
        buzzer = "gpio" if hold_tool() else "none"
    buzzers = {"gpio": GpioBuzzer, "none": FakeBuzzer}
    if buzzer not in buzzers:
        raise ValueError(
            f'unknown buzzer "{buzzer}": one of {sorted(buzzers)}')
    return buzzers[buzzer](**parameters)

# --------------------------------------------------------------------------- #
