#!/usr/bin/env python3
#
# Aiko Services: the power hold
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# One output line that keeps a host powered after its external supply
# stops.  While the line is driven high, a relay on the power management
# module connects the battery.
#
# **The hold does not use the GPIO character device** (ADR-028 decision 5).
# gpiozero, lgpio and libgpiod all claim a line through /dev/gpiochip0, and
# the kernel releases the claim when the process exits, which returns the
# line to an input.  Therefore a long-lived Actor that held this line would
# cut the power of a Device each time it stopped, crashed or restarted.  The
# platform pin utility writes the pad registers and exits, and the pin keeps
# its state because nothing claims it.  So the safest component here is the
# one that is not running.
#
# For that reason this module is a short-lived operation and not a device
# that is held open.  set_hold() runs the utility and returns.  The Actor
# calls it to assert the hold, and never to release it: the release belongs
# to the shutdown hook alone (ADR-028 decision 6, render.py).
#
# The runner is injected, so a test asserts the exact arguments with no
# subprocess and no hardware.
#
# To Do
# ~~~~~
# * A second Implementation for a board whose hold is an I2C write rather
#   than a pin, which the Interface already hides

import os
import re
import shutil
import subprocess

__all__ = [
    "HOLD_GPIO",
    "HOLD_OFF",
    "HOLD_ON",
    "HOLD_UNKNOWN",
    "HoldNotAvailable",
    "hold_state",
    "hold_tool",
    "run_tool",
    "set_hold",
]

HOLD_GPIO = 5  # BCM, active high

HOLD_ON = "on"
HOLD_OFF = "off"
HOLD_UNKNOWN = "unknown"

_TOOL = "pinctrl"
_TIMEOUT = 2.0

# The utility prints one line for one pin, as
#   "14: op -- pn | lo // GPIO14 = output"     a driven output, low
#   " 5: op dh pu | hi // GPIO5 = output"      a driven output, high
#   " 5: ip    pu | hi // GPIO5 = input"       an input that floats high
# The fields between the mode and the level vary, so the mode and the level
# are read separately rather than by one shape
_MODE = re.compile(r"^\s*\d+:\s*(?P<mode>[a-z]+)")
_LEVEL = re.compile(r"\|\s*(?P<level>hi|lo)\b")


class HoldNotAvailable(OSError):
    """The platform has no pin utility, so there is no hold here"""


def hold_tool(name=_TOOL):
    """The path of the pin utility, looking in /usr/sbin and /sbin as well
    as PATH (a non-login shell often lacks them); None when absent"""

    found = shutil.which(name)
    if found:
        return found
    for path in (f"/usr/sbin/{name}", f"/sbin/{name}", f"/usr/bin/{name}"):
        if os.access(path, os.X_OK):
            return path
    return None


def run_tool(arguments, timeout=_TIMEOUT):
    """Run the pin utility and return (returncode, stdout).  The default
    runner, which a test replaces"""

    tool = hold_tool()
    if tool is None:
        raise HoldNotAvailable(f'no "{_TOOL}" on this platform')
    try:
        done = subprocess.run([tool, *arguments], capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as error:
        raise HoldNotAvailable(str(error)) from error
    return done.returncode, done.stdout


def set_hold(on, gpio=HOLD_GPIO, runner=run_tool):
    """Drive the hold line high, or low.

    **Driving it low cuts the power of an undocked host.**  Only the
    shutdown hook does that, after the file systems are unmounted.

    Returns the state that was asked for.  Raises HoldNotAvailable when
    the platform has no pin utility, and OSError when the utility fails"""

    level = "dh" if on else "dl"
    code, output = runner(["set", str(gpio), "op", level])
    if code != 0:
        raise OSError(f"set {gpio} op {level} failed: {output.strip()[:80]}")
    return HOLD_ON if on else HOLD_OFF


def hold_state(gpio=HOLD_GPIO, runner=run_tool):
    """ "on" while the line is a driven output that is high, "off" while it
    is a driven output that is low, and "unknown" for anything else.

    An input that floats high through its pull-up is **not** a hold, and it
    reports "unknown": the weak pull-up does not hold the relay, and
    reporting it as "on" would hide a host that is one power cut from
    stopping"""

    try:
        code, output = runner(["get", str(gpio)])
    except HoldNotAvailable:
        return HOLD_UNKNOWN
    if code != 0:
        return HOLD_UNKNOWN
    mode = _MODE.match(output)
    if not mode or mode.group("mode") != "op":
        return HOLD_UNKNOWN  # Not a driven output
    level = _LEVEL.search(output)
    if not level:
        return HOLD_UNKNOWN
    return HOLD_ON if level.group("level") == "hi" else HOLD_OFF


# --------------------------------------------------------------------------- #
