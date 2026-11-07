#!/usr/bin/env python3
#
# Aiko Services: the two privileged operations
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# An Actor runs unprivileged, so powering the host off and remounting its
# file systems read-only both need a grant from the operating system
# (ADR-028 decision 12).  render.py holds the grant's text and the exact
# argument vectors that it permits, and this module runs them.
#
# The vectors come from render.granted_commands() and are never spelled out
# again here.  sudo matches a command and its arguments literally, so a
# second spelling is a privilege that was granted and cannot be used.
#
# "sudo -n" is deliberate.  An Actor has no terminal, so a password prompt
# would hang it until the shutdown timed out.  Failing at once, with a
# reason that is published, is what an operator can act on.
#
# Nothing here raises into its caller.  A power manager that cannot power
# the host off must say so and carry on reading the battery: the reading is
# still the evidence, and an operator still needs it.
#
# To Do
# ~~~~~
# * A privileged unit of the operating system that the Actor asks for,
#   instead of a grant (the plan's §6.17).  The seam is this module

import subprocess

from aiko_services.actors.power_manager.render import granted_commands

__all__ = ["SUDO", "TIMEOUT_S", "power_off", "remount_read_only", "run_granted"]

SUDO = "/usr/bin/sudo"
TIMEOUT_S = 30.0


def run_granted(command, runner=None, timeout=TIMEOUT_S):
    """Run one granted command through sudo, without a terminal.

    Returns (True, "") when it succeeded, and (False, reason) otherwise.
    It never raises: the caller is usually in the middle of stopping a host

    "runner" is injected by a test, and takes the whole argument list"""

    arguments = [SUDO, "-n", *command]
    try:
        if runner is not None:
            code, output = runner(arguments)
        else:
            done = subprocess.run(arguments, capture_output=True, text=True, timeout=timeout)
            code, output = done.returncode, (done.stderr or done.stdout)
    except (OSError, subprocess.SubprocessError) as error:
        return False, str(error)[:160]
    if code != 0:
        return False, (output or f"exit {code}").strip()[:160]
    return True, ""


def power_off(runner=None, timeout=TIMEOUT_S, **where):
    """Ask the operating system to power the host off.

    The last step of the policy, and the one that ends in the shutdown hook
    releasing the power hold.  Returns (ok, reason)"""

    command, _ = granted_commands(**where)
    return run_granted(command, runner=runner, timeout=timeout)


def remount_read_only(runner=None, timeout=TIMEOUT_S, **where):
    """Remount the file systems read-only, so that nothing writes while the
    last of the charge goes.

    A failure is reported and never fatal: a host that is still writing is
    better off halted than left running on the last of its charge, so the
    shutdown continues either way.  Returns (ok, reason)"""

    _, command = granted_commands(**where)
    return run_granted(command, runner=runner, timeout=timeout)


# --------------------------------------------------------------------------- #
