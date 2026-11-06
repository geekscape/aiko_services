# Usage
# ~~~~~
# pytest [-s] unit/test_power_manager_quiesce.py
#
# Unit tests for stopping before the power stops, and for the two
# privileged operations (actors/power_manager/quiesce.py, shutdown.py).
#
# No privilege and no subprocess: the runner is injected, so a test asserts
# the exact argument vector that sudo was asked for.  That matters more than
# it looks: sudo matches a command and its arguments literally, so a vector
# that differs from the granted one by one token is a privilege that cannot
# be used.

import pytest

from aiko_services.actors.power_manager import (
    HOOK_QUIESCE, Quiesce, REMOUNT_GRACE_S, SUDO, power_off,
    remount_read_only, run_granted, sync_filesystems,
)
from aiko_services.actors.power_manager.render import granted_commands

def runner_of(code=0, output="", calls=None):
    def runner(arguments):
        if calls is not None:
            calls.append(arguments)
        return code, output
    return runner

# The privileged operations ------------------------------------------------ #

def test_the_power_off_runs_the_granted_vector():
    calls = []
    assert power_off(runner=runner_of(calls=calls)) == (True, "")
    granted, _ = granted_commands()
    assert calls == [[SUDO, "-n", *granted]]

def test_the_remount_runs_the_granted_vector():
    calls = []
    assert remount_read_only(runner=runner_of(calls=calls)) == (True, "")
    _, granted = granted_commands()
    assert calls == [[SUDO, "-n", *granted]]

def test_sudo_is_asked_not_to_prompt():
    """An Actor has no terminal, so a prompt would hang it until the
    shutdown timed out.  Failing at once is what an operator can act on"""

    calls = []
    power_off(runner=runner_of(calls=calls))
    assert calls[0][1] == "-n"

def test_a_refused_privilege_is_reported_and_not_raised():
    ok, reason = power_off(
        runner=runner_of(code=1, output="a password is required"))
    assert ok is False
    assert "password" in reason

def test_a_runner_that_raises_is_reported_and_not_raised():
    def boom(arguments):
        raise OSError("no such file")

    ok, reason = power_off(runner=boom)
    assert ok is False and "no such file" in reason

def test_an_exit_code_with_no_output_still_gives_a_reason():
    ok, reason = run_granted(["/bin/true"], runner=runner_of(code=3))
    assert ok is False and "exit 3" in reason

def test_another_mount_point_reaches_the_vector():
    calls = []
    remount_read_only(runner=runner_of(calls=calls), mount_point="/data")
    assert calls[0][-1] == "/data"

# The sync ----------------------------------------------------------------- #

def test_the_sync_flushes_what_the_kernel_holds():
    done = []
    assert sync_filesystems(lambda: done.append("sync")) == (True, "")
    assert done == ["sync"]

def test_a_sync_that_fails_is_reported_and_not_raised():
    def boom():
        raise OSError("the disk went away")

    ok, reason = sync_filesystems(boom)
    assert ok is False and "disk went away" in reason

# The steps ---------------------------------------------------------------- #

def test_entering_flushes_once():
    done = []
    quiesce = Quiesce(syncer=lambda: done.append("sync"))
    assert quiesce.enter(100.0) == (True, "")
    assert quiesce.enter(101.0) is None          # Already done
    assert done == ["sync"]

def test_the_remount_waits_out_its_grace():
    """A file system refuses to go read-only while a process holds a file
    open for writing, so a writer that heard the alert needs time"""

    quiesce = Quiesce(syncer=lambda: None, grace=5.0)
    quiesce.enter(100.0)
    assert quiesce.ready_to_remount(104.9) is False
    assert quiesce.ready_to_remount(105.0) is True

def test_nothing_is_ready_before_entering():
    assert Quiesce().ready_to_remount(100.0) is False

def test_the_remount_happens_once():
    calls = []
    quiesce = Quiesce(syncer=lambda: None, runner=runner_of(calls=calls))
    quiesce.enter(100.0)
    assert quiesce.remount() == (True, "")
    assert quiesce.remount() is None
    assert len(calls) == 1

def test_a_failed_remount_is_recorded_and_not_fatal():
    """A host that is still writing is better off halted than left running
    on the last of its charge, so the shutdown carries on"""

    quiesce = Quiesce(syncer=lambda: None,
        runner=runner_of(code=32, output="target is busy"))
    quiesce.enter(100.0)
    ok, reason = quiesce.remount()
    assert ok is False and "busy" in reason
    assert quiesce.done()["quiesce.remounted"].startswith("failed")

def test_what_has_run_is_reported_as_tokens():
    quiesce = Quiesce(syncer=lambda: None, runner=runner_of())
    assert quiesce.done() == {
        "quiesce.synced": "-", "quiesce.remounted": "-"}
    quiesce.enter(100.0)
    quiesce.remount()
    assert quiesce.done() == {
        "quiesce.synced": "yes", "quiesce.remounted": "yes"}

def test_a_token_holds_no_space():
    """It is a shared variable, and ServiceFilter splits on a space"""

    quiesce = Quiesce(syncer=lambda: None,
        runner=runner_of(code=1, output="mount: /: target is busy"))
    quiesce.enter(100.0)
    quiesce.remount()
    for value in quiesce.done().values():
        assert " " not in value

def test_the_default_grace_gives_a_writer_time():
    assert REMOUNT_GRACE_S >= 1.0
    assert Quiesce().grace == REMOUNT_GRACE_S

def test_the_hook_has_a_declared_name():
    assert HOOK_QUIESCE and " " not in HOOK_QUIESCE

# --------------------------------------------------------------------------- #
