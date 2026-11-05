#!/usr/bin/env python3
#
# Aiko Services: the power button and the dock line
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# Two input lines on the power management module: a button that an operator
# holds to stop the host, and a line that says whether the host is docked.
#
# The button is **active LOW**: the line is at 0 V while it is held, and the
# board pulls it up when it is not.  So gpiozero needs pull_up=True, which
# is the opposite of the WhisPlay panel's button.  The cost of getting this
# wrong is silent: every event arrives inverted, so a press reports a
# release and the press itself is never seen.
#
# The dock line is active LOW as well: low means docked.
#
# A press that reaches its hold time fires while the button is still down,
# and not when it comes up.  Therefore the operator hears the "accepted"
# signal at the moment the press counted and can let go, rather than
# guessing how long three seconds is.
#
# **Dock changes need a dwell of seconds, not a debounce of milliseconds.**
# An external supply glitches, and a dock that flickers must not start a
# shutdown.  The dwell is the Actor's, on its own timer, because it belongs
# to the rule and not to the wire (policy.py).
#
# Every callback here runs on the gpiozero thread and only hands the value
# to a handler.  It never touches Actor state (P11).
#
# These classes are internal collaborators of the module Implementation,
# and not a public API: the one public Interface is PowerManager (ADR-028
# decision 1).  signal.py has the same shape.
#
# To Do
# ~~~~~
# * A short press, for the Display's next page, and a double press.
#   classify() returns the kind already

import time

__all__ = [
    "BUTTON_ACTIVE_LOW", "BUTTON_GPIO", "DOCK_ACTIVE_LOW", "DOCK_GPIO",
    "FakePowerInputs", "GpioPowerInputs", "HOLD_TIME_S", "choose_power_inputs",
    "classify",
]

BUTTON_GPIO = 6                    # BCM, low while held
DOCK_GPIO = 7                      # BCM, low while docked
HOLD_TIME_S = 3.0

# The board pulls both lines up, and each one goes low to mean something.
# Named here so that the reason survives, because the cost of getting it
# wrong is silent: with pull_up=False every event arrives inverted
BUTTON_ACTIVE_LOW = True
DOCK_ACTIVE_LOW = True

def classify(seconds, hold_time_s=HOLD_TIME_S):
    """"long" when the press lasted at least hold_time_s, else "short".

    A pure function of one duration, so the rule that stops a host is
    tested without a button"""

    return "long" if seconds >= hold_time_s else "short"

class FakePowerInputs:
    """No lines: the test double, and what a platform without them gets.

    press() and set_docked() report what a real button and a real dock line
    would report"""

    device = "none"

    def __init__(self, docked=True, hold_time_s=HOLD_TIME_S, **_):
        self._docked = bool(docked)
        self.hold_time_s = float(hold_time_s)
        self._handlers = []
        self.opened = False
        self.closed = False

    def open(self):
        self.opened = True

    def add_handler(self, handler):
        self._handlers.append(handler)

    def docked(self):
        return self._docked

    def press(self, seconds=None, kind=None):
        """Report a press.  With "seconds" it is classified, and a press
        that reaches the hold time reports "held" as a real one does"""

        if kind is None:
            seconds = self.hold_time_s if seconds is None else float(seconds)
            kind = "held" if classify(seconds, self.hold_time_s) == "long"  \
                else "short"
        self._report("button", kind)
        return kind

    def set_docked(self, docked):
        """Report a dock change, as the line would"""

        self._docked = bool(docked)
        self._report("dock", "yes" if self._docked else "no")

    def close(self):
        self.closed = True
        self._handlers = []

    def _report(self, event, value):
        for handler in self._handlers:
            handler(event, value)

class GpioPowerInputs:
    """The button and the dock line through gpiozero.

    Both are acquired in open(), and gpiozero is imported there and nowhere
    else (P9)"""

    device = "gpio"

    def __init__(self, button_gpio=BUTTON_GPIO, dock_gpio=DOCK_GPIO,
        hold_time_s=HOLD_TIME_S, bounce_time=0.05, **_):

        self.button_gpio = int(button_gpio)
        self.dock_gpio = int(dock_gpio)
        self.hold_time_s = float(hold_time_s)
        self.bounce_time = bounce_time
        self._button = None
        self._dock = None
        self._handlers = []
        self._pressed_at = None

    def open(self):
        from gpiozero import Button, DigitalInputDevice   # Only needed here

        # Active low: the board pulls both lines up.  With pull_up=False
        # every event arrives inverted and a press is never seen
        self._button = Button(self.button_gpio,
            pull_up=BUTTON_ACTIVE_LOW, bounce_time=self.bounce_time,
            hold_time=self.hold_time_s)
        self._button.when_pressed = self._on_pressed
        self._button.when_released = self._on_released
        # Fires while the button is still down, so the operator hears that
        # the press counted and can let go
        self._button.when_held = self._on_held

        self._dock = DigitalInputDevice(
            self.dock_gpio, pull_up=DOCK_ACTIVE_LOW)
        self._dock.when_activated = self._on_dock
        self._dock.when_deactivated = self._on_dock

    def add_handler(self, handler):
        self._handlers.append(handler)

    def docked(self):
        """Whether the host is docked, read from the line.  None while the
        line is not open"""

        if self._dock is None:
            return None
        return bool(self._dock.value) if DOCK_ACTIVE_LOW  \
            else not self._dock.value

    def close(self):
        for device in (self._button, self._dock):
            try:
                if device is not None:
                    device.close()
            except Exception:                            # noqa: BLE001
                pass
        self._button = self._dock = None
        self._handlers = []

# Every callback below runs on the gpiozero thread, and only reports ------- #

    def _on_pressed(self):
        self._pressed_at = time.monotonic()
        self._report("button", "down")

    def _on_held(self):
        self._report("button", "held")

    def _on_released(self):
        if self._pressed_at is None:
            return                     # A release with no press: ignore it
        seconds = time.monotonic() - self._pressed_at
        self._pressed_at = None
        self._report("button", f"up {seconds:.2f}")

    def _on_dock(self):
        self._report("dock", "yes" if self.docked() else "no")

    def _report(self, event, value):
        for handler in self._handlers:
            handler(event, value)

def choose_power_inputs(inputs="auto", **parameters):
    """The input lines for "inputs": "gpio", "none", or "auto", which is the
    real ones where gpiozero can be imported and the fake ones everywhere
    else.  Nothing is acquired here"""

    import importlib.util

    if inputs == "auto":
        inputs = "gpio" if importlib.util.find_spec("gpiozero") else "none"
    choices = {"gpio": GpioPowerInputs, "none": FakePowerInputs}
    if inputs not in choices:
        raise ValueError(
            f'unknown inputs "{inputs}": one of {sorted(choices)}')
    return choices[inputs](**parameters)

# --------------------------------------------------------------------------- #
