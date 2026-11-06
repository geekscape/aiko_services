#!/usr/bin/env python3
#
# Aiko Services: stopping before the power stops
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# The battery is finite, so a host that keeps the power on is only delaying
# the end.  When the power will end, by any route, the host says so and
# stops writing (ADR-028 decision 11).
#
# Three mechanisms, because applications differ.
#
# The mode is a shared variable, so every observer sees it.  A Pipeline or
# the SegmentStoreForward Actor watches it with a consumer and stops of its
# own accord.
#
# A declared hook, POWER_QUIESCE, reaches whatever runs in this process with
# no message round trip.
#
# And os.sync() flushes what the kernel holds, whatever any application
# does.  That is the one of the three that needs nobody's cooperation.
#
# At the floor voltage the file systems are remounted read-only as well.
# The order is forced: a file system refuses to go read-only while a process
# holds a file open for writing, so the writers are told first, the log is
# closed, the kernel is flushed, and the remount is tried after a grace.
# A remount that fails is reported, and the shutdown continues: a host that
# is still writing is better off halted.
#
# **The trigger for the remount is the policy's floor, which is the lowest
# voltage this design operates at.  The cell damage limit is never a
# trigger**, because this design never reaches it (the plan's S12).
#
# To Do
# ~~~~~
# * Tell the writers by name, once a Pipeline publishes a state that says
#   it is writing.  Today the mode is published and they watch it

import os

from aiko_services.actors.power_manager.shutdown import remount_read_only

__all__ = [
    "HOOK_QUIESCE", "REMOUNT_GRACE_S", "Quiesce", "sync_filesystems",
]

HOOK_QUIESCE = "power_quiesce"     # The declared hook's name
REMOUNT_GRACE_S = 5.0              # Between the alert and the remount

def sync_filesystems(syncer=None):
    """Flush what the kernel holds.  Returns (ok, reason).

    It never raises.  This runs on a worker thread, because a sync on a
    loaded disk blocks, and the event-loop thread must not (P2)"""

    try:
        (syncer or os.sync)()
    except OSError as error:
        return False, str(error)[:160]
    return True, ""

class Quiesce:
    """What the host does on its way to losing power, once.

    Each step is done one time only, so a mode that stays in quiesce does
    not sync the disks on every sample.  done() reports which steps ran"""

    def __init__(self, syncer=None, runner=None, mount_point="/",
        grace=REMOUNT_GRACE_S):

        self._syncer = syncer
        self._runner = runner
        self._mount_point = mount_point
        self.grace = float(grace)
        self.synced = None             # None: not tried.  Else (ok, reason)
        self.remounted = None
        self.entered_at = None

    def enter(self, now):
        """The host is about to lose its power: flush, once.

        Returns (ok, reason) of the sync, or None when it has already run"""

        if self.synced is not None:
            return None
        self.entered_at = now
        self.synced = sync_filesystems(self._syncer)
        return self.synced

    def ready_to_remount(self, now):
        """Whether the grace since enter() has passed.

        The grace is what gives a writer that heard the alert time to close
        what it holds, because a file system refuses to go read-only while
        one is open for writing"""

        return self.entered_at is not None  \
            and (now - self.entered_at) >= self.grace

    def remount(self):
        """Make the file systems read-only, once.

        Returns (ok, reason), or None when it has already run.  A failure is
        not fatal and the caller carries on to the shutdown"""

        if self.remounted is not None:
            return None
        self.remounted = remount_read_only(
            runner=self._runner, mount_point=self._mount_point)
        return self.remounted

    def done(self):
        """Which steps have run, as tokens for the shared state"""

        return {
            "quiesce.synced": _token(self.synced),
            "quiesce.remounted": _token(self.remounted),
        }

def _token(outcome):
    if outcome is None:
        return "-"
    ok, reason = outcome
    return "yes" if ok else f"failed:{reason.split()[0][:24] if reason else '?'}"

# --------------------------------------------------------------------------- #
