#!/usr/bin/env python3
#
# Aiko Services: what the operating system must hold
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# Three files live outside Aiko Services, because only the operating system
# can hold them: the unit that asserts the power hold at start-up, the
# shutdown hook that releases it, and the grant that lets an unprivileged
# Actor power the host off.
#
# render() returns the text and changes nothing, and install() is the only
# operation that changes the host (ADR-026 decision 3, ADR-028 decision 9).
# Therefore a person reads each file before they trust it, and a test
# compares it with a string.
#
# Both the unit and the hook sound a pattern, and neither can import Python.
# So the durations come from the one table in signal.py and are rendered as
# commands, by _beep_commands(), rather than written twice.  The unit sounds
# "booted" after the hold is on, which is what tells an operator holding a
# soft power button that it is safe to let go.  No Actor can say this: the
# operator needs it seconds before Aiko Services starts.
#
# Two properties of the hook are the reason it exists at all.
#
# It releases the hold only when the host is stopping.  The operating system
# passes "poweroff", "reboot", "halt" or "kexec" to every hook, and a
# release on a restart would stop an undocked Device that is trying to come
# back.  The learning script ignored its argument, and that is the fault
# this one does not have.
#
# And it runs after the file systems are unmounted, which is the one place
# where cutting the power cannot corrupt them.
#
# The grant names two exact commands and nothing else.  install() validates
# it before it writes, because a malformed file in the sudoers directory
# denies every account the privilege to repair it, and a host with no
# console cannot be repaired at all.
#
# To Do
# ~~~~~
# * A launchd Implementation, for a laptop, through the DaemonSupervisor
#   Interface of ADR-026 rather than this module

import os
import shutil
import subprocess
import tempfile

from aiko_services.actors.power_manager.hold import HOLD_GPIO
from aiko_services.actors.power_manager.signal import (
    BUZZER_GPIO, PATTERNS
)

__all__ = [
    "ARTIFACTS", "GRANT_PATH", "HOOK_PATH", "HOLD_RELEASE_DELAY_S",
    "InstallRefused", "POWEROFF_COMMAND", "RELEASE_ACTIONS",
    "REMOUNT_COMMAND", "UNIT_PATH", "granted_commands", "install", "paths",
    "render", "verify",
]

UNIT_PATH = "/etc/systemd/system/aiko_power_hold.service"
HOOK_PATH = "/usr/lib/systemd/system-shutdown/aiko_power_off"
GRANT_PATH = "/etc/sudoers.d/aiko_power_manager"

ARTIFACTS = ("unit", "hook", "grant")

# The hold is released for these, and for nothing else.  A restart keeps it
HOLD_RELEASE_DELAY_S = 2.0
RELEASE_ACTIONS = ("poweroff", "halt")

_PINCTRL = "/usr/bin/pinctrl"
_SLEEP = "/usr/bin/sleep"
_SYSTEMCTL = "/usr/bin/systemctl"
_MOUNT = "/usr/bin/mount"

# The two privileged operations, as the exact argument vectors that the
# grant permits.  sudo matches a command and its arguments literally, so
# whatever runs them must use these and not a spelling of its own.  Keeping
# them here, beside the text that grants them, is what stops the two from
# drifting apart.
#
# The remount passes "-o" twice rather than "-o remount,ro".  A comma
# separates commands in a sudoers file, so the one-option form needs an
# escape, and an escape that a later edit drops turns one command into two
POWEROFF_COMMAND = (_SYSTEMCTL, "poweroff")
REMOUNT_COMMAND = (_MOUNT, "-o", "remount", "-o", "ro")

def granted_commands(mount_point="/", systemctl=_SYSTEMCTL, mount=_MOUNT):
    """The exact argument vectors that the grant permits, in the order the
    grant lists them.  A caller of either one uses this, so that what it
    runs is what was granted"""

    return (
        (systemctl, "poweroff"),
        (mount, "-o", "remount", "-o", "ro", mount_point),
    )

class InstallRefused(Exception):
    """install() would not write: the text did not validate, or the caller
    has no privilege"""

def render(artifact, account=None, pinctrl=_PINCTRL, hold_gpio=HOLD_GPIO,
    buzzer_gpio=BUZZER_GPIO, delay=HOLD_RELEASE_DELAY_S,
    mount_point="/", systemctl=_SYSTEMCTL, mount=_MOUNT, sleep=_SLEEP):

    """The text of one artifact: "unit", "hook" or "grant".

    Pure: it reads nothing and writes nothing.  "account" is the account
    that runs the Actor, and it is rendered rather than written into the
    code, so one deployment's account never reaches another's"""

    if artifact not in ARTIFACTS:
        raise ValueError(
            f'unknown artifact "{artifact}": one of {list(ARTIFACTS)}')
    if artifact == "unit":
        return _unit(pinctrl, hold_gpio, buzzer_gpio, sleep)
    if artifact == "hook":
        return _hook(pinctrl, hold_gpio, buzzer_gpio, delay, sleep)
    if not account:
        raise ValueError('the grant needs "account": whose privilege it is')
    return _grant(account, systemctl, mount, mount_point)

def _beep_commands(pinctrl, buzzer_gpio, pattern, sleep):
    """The commands that play one pattern through pinctrl: a level, a wait,
    then the opposite level, and a last command that leaves the line low.

    Both the start-up unit and the shutdown hook play a pattern, and
    neither can import Python, so the table in signal.py becomes commands
    here rather than twice"""

    commands = []
    for index, seconds in enumerate(PATTERNS[pattern]):
        level = "dh" if index % 2 == 0 else "dl"
        commands.append(f"{pinctrl} set {buzzer_gpio} op {level}")
        commands.append(f"{sleep} {seconds}")
    commands.append(f"{pinctrl} set {buzzer_gpio} op dl")
    return commands

def _unit(pinctrl, hold_gpio, buzzer_gpio, sleep=_SLEEP):
    """The start-up unit.  It is a oneshot that exits, and the pin keeps its
    state because nothing claims it (ADR-028 decision 5).

    It asserts the hold, and then sounds "booted".  The order is the point:
    the sound means the hold is on, so an operator who holds a soft power
    button hears when it is safe to let go.  No Actor can do this, because
    the sound is wanted seconds before Aiko Services starts.

    Its stop sounds "shutdown", which is why the unit also orders itself
    against shutdown.target.  The hook of decision 6 sounds the same
    pattern, but it runs after the file systems are gone, which can be a
    minute after the operator asked.  A stop runs while the host is still
    up, so this is the prompt answer to the button, and it answers for
    every cause of a shutdown rather than for the button alone.

    The stop never releases the hold.  Only the shutdown hook does that
    (ADR-028 decision 6), and a release here would cut the power of a host
    that is restarting"""

    beeps = "\n".join(f"ExecStartPost=-{command}"
        for command in _beep_commands(pinctrl, buzzer_gpio, "booted", sleep))
    stopping = "\n".join(f"ExecStop=-{command}"
        for command in _beep_commands(pinctrl, buzzer_gpio, "shutdown", sleep))
    return f"""\
[Unit]
Description=Aiko Services: assert the power hold
Documentation=constitution/adr/ADR-028_PowerManagement.md
DefaultDependencies=no
After=sysinit.target
Before=multi-user.target
# DefaultDependencies=no adds no shutdown ordering, so the two lines that
# it would have added are here.  Without them the stop runs at an
# unspecified point, and the sound that answers the button could arrive
# after the file systems are gone
Conflicts=shutdown.target
Before=shutdown.target

[Service]
Type=oneshot
RemainAfterExit=yes
# The pin keeps its state after this exits, which is why the hold is not
# held by a long-lived process: the character device would release it
ExecStart={pinctrl} set {hold_gpio} op dh
# Then the "booted" pattern, which tells an operator that the hold is on
# and a soft power button can be released.  Each line is prefixed with "-"
# so that a buzzer which does not sound never reports the hold as failed
{beeps}
# The stop sounds "shutdown" while the host is still up, which is the
# prompt answer to a button press.  It releases nothing: only the shutdown
# hook releases the hold
{stopping}

[Install]
WantedBy=multi-user.target
"""

def _hook(pinctrl, hold_gpio, buzzer_gpio, delay, sleep=_SLEEP):
    """The shutdown hook.  It releases the hold for a stop, and never for a
    restart, and it waits before the release.

    Every command is an absolute path.  This script runs when almost
    nothing else does, and "sleep" is a program here and not a shell
    built-in, so a PATH that the shutdown environment did not set would
    skip the wait and release the hold at once"""

    beeps = "\n".join(
        _beep_commands(pinctrl, buzzer_gpio, "shutdown", sleep))
    return f"""\
#!/bin/sh
# Aiko Services: release the power hold, after the file systems are gone.
# Rendered by "aiko_power_manager render hook" -- do not edit here.
#
# The operating system passes the action as $1.  The hold is released for
# {" and ".join(RELEASE_ACTIONS)}, and for nothing else: a release on a
# restart would stop an undocked host that is trying to come back.
set -u

# Every command below is an absolute path, because this script runs when
# almost nothing else does and must not depend on a PATH

case "$1" in
{"|".join(RELEASE_ACTIONS)}) ;;
*) exit 0 ;;
esac

# Three chirps: the host is about to lose its power
{beeps}

# The kernel needs time to finish after this hook returns.  The operating
# system allows every hook 90 s, so this wait must stay well inside that
{sleep} {delay}

# *** This cuts the power when the host is undocked ***
{pinctrl} set {hold_gpio} op dl
"""

def _grant(account, systemctl, mount, mount_point):
    """The privilege grant: two exact commands, absolute paths, no wildcard,
    and never NOPASSWD: ALL"""

    commands = "\n".join(
        f"{account} ALL=(root) NOPASSWD: {' '.join(command)}"
        for command in granted_commands(mount_point, systemctl, mount))
    return f"""\
# Aiko Services: the power manager's two privileged operations.
# Rendered by "aiko_power_manager render grant" -- do not edit here.
#
# Two exact commands, with absolute paths and no wildcard.  The power-off
# is the policy's last step, and the remount makes the file systems
# read-only at the floor voltage so that nothing writes while the last of
# the charge goes.
#
# The remount passes "-o" twice.  A comma separates commands in this file,
# so "-o remount,ro" would need an escape, and an escape that an edit drops
# turns one command into two.
{commands}
"""

def paths(unit=UNIT_PATH, hook=HOOK_PATH, grant=GRANT_PATH):
    """Where each artifact belongs"""

    return {"unit": unit, "hook": hook, "grant": grant}

def verify(where=None):
    """Which artifacts are in place: {"unit": "installed" | "missing", ...}.

    It reports without using any of them.  A host that cannot power itself
    off has a battery policy that is advisory, whatever its thresholds say,
    and an operator must be able to see that"""

    where = where or paths()
    return {name: ("installed" if os.path.exists(path) else "missing")
        for name, path in where.items()}

def install(artifact, text, path=None, mode=None, validator=None):
    """Write one rendered artifact.  The only operation here that changes
    the host, and a person runs it.

    Raises InstallRefused when the text does not validate, or when the
    caller cannot write where the artifact belongs.  The write is atomic,
    with the mode set before the rename, because a half-written file in the
    sudoers directory does the same damage as a malformed one"""

    if artifact not in ARTIFACTS:
        raise ValueError(f'unknown artifact "{artifact}"')
    path = path or paths()[artifact]
    mode = mode if mode is not None else _MODES[artifact]
    validator = validator or _VALIDATORS[artifact]
    reason = validator(text)
    if reason:
        raise InstallRefused(f"{artifact} did not validate: {reason}")
    directory = os.path.dirname(path)
    if not os.path.isdir(directory):
        raise InstallRefused(f"{directory} does not exist: make it first")
    try:
        handle, temporary = tempfile.mkstemp(
            dir=directory, prefix=f".{os.path.basename(path)}.")
        with os.fdopen(handle, "w", encoding="utf-8") as file:
            file.write(text)
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    except OSError as error:
        raise InstallRefused(str(error)) from error
    return path

_MODES = {"unit": 0o644, "hook": 0o755, "grant": 0o440}

def _validate_nothing(text):
    return None if text.strip() else "the text is empty"

def _validate_grant(text):
    """The sudoers file must parse, and it must not grant everything.

    A malformed file in the sudoers directory denies every account the
    privilege to repair it.  On a host with no console that cannot be
    repaired, so this check is part of the decision and not a nicety"""

    if "NOPASSWD: ALL" in text or "ALL=(ALL) ALL" in text:
        return "it grants more than the two commands"
    tool = shutil.which("visudo") or "/usr/sbin/visudo"
    if not os.access(tool, os.X_OK):
        return "visudo is not available to check it"
    handle, temporary = tempfile.mkstemp(prefix="aiko_sudoers.")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as file:
            file.write(text)
        os.chmod(temporary, 0o440)
        done = subprocess.run([tool, "-c", "-f", temporary],
            capture_output=True, text=True, timeout=10)
        if done.returncode != 0:
            return (done.stderr or done.stdout).strip()[:120]
    except (OSError, subprocess.SubprocessError) as error:
        return str(error)[:120]
    finally:
        try:
            os.unlink(temporary)
        except OSError:
            pass
    return None

_VALIDATORS = {
    "unit": _validate_nothing,
    "hook": _validate_nothing,
    "grant": _validate_grant,
}

# --------------------------------------------------------------------------- #
