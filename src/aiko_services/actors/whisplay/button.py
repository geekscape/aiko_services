#!/usr/bin/env python3
#
# Aiko Services: WhisPlay Actor, the button
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# The WhisPlay button, on BOARD pin 11, which is BCM GPIO 17.
#
# The button is **active HIGH**: the pin is at 3.3V while it is held, and
# at 0V when it is not.  So gpiozero needs pull_up=False.  With pull_up=True
# every event arrives inverted: a press reports a release, and the press
# itself is never seen.
#
# classify() is a pure function of one duration, so the rule that decides a
# long press is tested without a button.  The Impls below only measure the
# duration and hand it over.
#
# P11: the callback runs on the gpiozero thread, so it does not touch Actor
# state.  It calls the handler, and the Actor posts the decision to its own
# mailbox.
#
# To Do
# ~~~~~
# * A double press, for Epic 6.  classify() returns the press kind already,
#   so the counting of two presses within a window is what is missing

from abc import abstractmethod
import time

import aiko_services as aiko

__all__ = [
    "BUTTON_ACTIVE_HIGH", "BUTTON_GPIO", "Button", "FakeButtonImpl",
    "GpioButtonImpl",
    "LONG_PRESS_SECONDS", "button_args", "choose_button", "classify"
]

BUTTON_GPIO = 17               # BOARD pin 11
LONG_PRESS_SECONDS = 3.0
# The pin is at 3.3V while the button is held, so gpiozero takes
# pull_up=False.  Named here so the reason survives, because the cost of
# getting it wrong is silent: every event arrives inverted
BUTTON_ACTIVE_HIGH = True

def classify(seconds, long_press_seconds=LONG_PRESS_SECONDS):
    """"long" when the press lasted longer than long_press_seconds, else
    "short".  A pure function of the duration, so that the rule is tested
    without a button"""

    return "long" if seconds > long_press_seconds else "short"

class Button(aiko.Interface):
    """One button.  open() acquires it, add_handler(handler) asks for
    handler(kind, seconds) on each release, and close() releases it.  The
    handler runs on the Impl's own thread, never on the event-loop thread"""

    aiko.Interface.default(
        "Button", "aiko_services.actors.whisplay.button.FakeButtonImpl")

    @abstractmethod
    def open(self):
        """Acquire the button"""

    @abstractmethod
    def add_handler(self, handler):
        """handler(kind, seconds): "down" when the button goes down, then
        "short" or "long" when it comes up, with how long it was held"""

    @abstractmethod
    def close(self):
        """Release the button"""

class FakeButtonImpl(Button):
    """No button: the default Impl, and the test double.  press(seconds)
    reports a press that lasted that long"""

    device = "none"

    def __init__(self, context, long_press_seconds=LONG_PRESS_SECONDS, **_):
        self.long_press_seconds = long_press_seconds
        self._handlers = []

    def open(self):
        pass

    def add_handler(self, handler):
        self._handlers.append(handler)

    def close(self):
        self._handlers = []

    def press(self, seconds):
        """Report a press of this duration, as a real button would: down
        first, then up"""

        self.press_down()
        kind = classify(seconds, self.long_press_seconds)
        for handler in self._handlers:
            handler(kind, seconds)
        return kind

    def press_down(self):
        """Report that the button went down, and stayed down"""

        for handler in self._handlers:
            handler("down", 0.0)

class GpioButtonImpl(Button):
    """The WhisPlay button through gpiozero.  The press is timed here and
    classified by classify(), so this Impl holds no rule of its own"""

    device = "gpio"

    def __init__(self, context, gpio=BUTTON_GPIO,
        long_press_seconds=LONG_PRESS_SECONDS, **_):

        self.gpio = gpio
        self.long_press_seconds = long_press_seconds
        self._handlers = []
        self._button = None
        self._pressed_at = None

    def open(self):
        from gpiozero import Button as GpioZeroButton   # only needed here

        # Active HIGH: the vendor driver says "pressed is 5V, released is
        # 0V".  With pull_up=True every event arrives inverted, so a press
        # looks like a release and the press is never seen
        self._button = GpioZeroButton(
            self.gpio, pull_up=not BUTTON_ACTIVE_HIGH, bounce_time=0.05)
        self._button.when_pressed = self._on_pressed
        self._button.when_released = self._on_released

    def add_handler(self, handler):
        self._handlers.append(handler)

    def close(self):
        if self._button:
            self._button.close()
            self._button = None
        self._handlers = []

    def _on_pressed(self):
        self._pressed_at = time.monotonic()
        for handler in self._handlers:
            handler("down", 0.0)

    def _on_released(self):
        if self._pressed_at is None:
            return                     # A release with no press: ignore it
        seconds = time.monotonic() - self._pressed_at
        self._pressed_at = None
        kind = classify(seconds, self.long_press_seconds)
        for handler in self._handlers:
            handler(kind, seconds)

# Composition -------------------------------------------------------------- #

def button_args(**parameters):
    """init_args for composing a Button Impl"""

    return {"context": aiko.Context(), **parameters}

def choose_button(button="auto", **parameters):
    """The composed Button.  "auto" is the real one where gpiozero can be
    imported, and the fake one everywhere else.  Nothing is acquired here"""

    import importlib.util

    if button == "auto":
        button = "gpio" if importlib.util.find_spec("gpiozero") else "none"
    impls = {"gpio": GpioButtonImpl, "none": FakeButtonImpl}
    if button not in impls:
        raise ValueError(f'unknown button "{button}": one of {sorted(impls)}')
    return aiko.compose_instance(impls[button], button_args(**parameters))

# --------------------------------------------------------------------------- #
