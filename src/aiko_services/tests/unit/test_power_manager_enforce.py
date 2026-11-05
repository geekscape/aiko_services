# Usage
# ~~~~~
# pytest [-s] unit/test_power_manager_enforce.py
#
# Unit tests for the Actor acting on its policy, through the mock
# (actors/power_manager/power_manager.py).
#
# Two postures, and the difference between them is the whole of this file.
# Advisory decides, publishes and acts on nothing, which is the default and
# is how a host runs while its battery pack is being measured.  Enforcing stops the
# host.  Every test here asserts which of the two happened, because a test
# that only read "policy_would" would pass for both.
#
# No privilege and no subprocess: the power-off runner is injected, and
# worker=False runs it where it is decided rather than on a thread.

import itertools

import pytest

import aiko_services as aiko
from aiko_services.actors.power_manager import (
    HOOK_QUIESCE, MODE_CONSERVE, MODE_NORMAL, MODE_QUIESCE,
    MockPowerManagerImpl, POLICY_ADVISORY, POLICY_SHUTTING_DOWN, Quiesce,
    SUDO, THRESHOLDS, power_manager_args,
)
from aiko_services.actors.power_manager.render import granted_commands

_counter = itertools.count()

def runner_of(code=0, output="", calls=None):
    def runner(arguments):
        if calls is not None:
            calls.append(arguments)
        return code, output
    return runner

def make_actor(**parameters):
    settings = {
        "log_directory": None, "telemetry": False, "timer": False,
        "worker": False,
    }
    settings.update(parameters)
    init_args = power_manager_args(
        f"power_enforce_test_{next(_counter)}", "mock",
        declared=MockPowerManagerImpl.DECLARED_PROPERTIES, **settings)
    return aiko.compose_instance(MockPowerManagerImpl, init_args)

def undocked(volts=12.0, **extra):
    """One reading of an undocked host"""

    return {"battery_volts": volts, "battery_pack_celsius": 25.0,
        "docked": False, **extra}

# The advisory posture ----------------------------------------------------- #

def test_advisory_is_the_default():
    actor = make_actor()
    assert actor.share["enforce"] is False

def test_advisory_publishes_the_decision_and_acts_on_nothing():
    calls = []
    actor = make_actor(
        properties=("readings", "hold", "signal", "button", "dock"),
        script=[undocked(volts=9.0)], power_off_runner=runner_of(calls=calls))
    actor.sample()
    assert actor.share["policy_would"] == "shutdown"
    assert actor.share["policy_reason"] == "battery_floor"
    assert actor.share["policy"] == POLICY_ADVISORY
    assert calls == []
    assert actor.share["metrics"]["shutdowns"] == 0

def test_advisory_still_enters_the_quiesce_mode():
    """Flushing and telling the writers costs nothing and loses nothing, so
    it happens whether or not this Actor may stop the host"""

    actor = make_actor(
        properties=("readings", "hold", "signal", "button", "dock"),
        script=[undocked(volts=9.0)], quiesce=Quiesce(syncer=lambda: None))
    actor.sample()
    assert actor.share["mode"] == MODE_QUIESCE
    assert actor.share["quiesce"]["synced"] == "yes"

# The enforcing posture ---------------------------------------------------- #

def enforcing(script, calls=None, **extra):
    settings = {
        "enforce": True,
        "properties": ("readings", "hold", "signal", "button", "dock"),
        "script": script,
        "power_off_runner": runner_of(calls=calls),
        # grace=0 unless a test is about the grace: at the floor the host
        # flushes, waits for its writers, remounts and only then stops, so
        # a test of the stopping must not also wait
        "quiesce": Quiesce(
            syncer=lambda: None, runner=runner_of(), grace=0.0),
    }
    settings.update(extra)
    return make_actor(**settings)

def test_enforcing_says_so():
    assert enforcing([undocked()]).share["enforce"] is True

def test_enforcing_powers_the_host_off_with_the_granted_vector():
    calls = []
    actor = enforcing([undocked(volts=10.0, docked=False)], calls=calls)
    actor._evaluate(actor.reading(), now=1000.0)    # Nothing claims it yet
    actor._evaluate(actor.reading(), now=1100.0)    # The grace has passed
    granted, _ = granted_commands()
    assert [SUDO, "-n", *granted] in calls

def test_enforcing_counts_the_shutdown_and_says_it_is_stopping():
    """With no grace to wait out, one sample flushes, remounts and stops.
    The grace itself has its own test"""

    calls = []
    actor = enforcing([undocked(volts=9.0)], calls=calls)
    actor.sample()
    assert actor.share["policy"] == POLICY_SHUTTING_DOWN
    assert actor.share["metrics"]["shutdowns"] == 1

def test_the_host_is_stopped_once_however_many_samples_follow():
    calls = []
    actor = enforcing([undocked(volts=9.0)], calls=calls)
    for _ in range(4):
        actor.sample()
    assert len(calls) == 1
    assert actor.share["metrics"]["shutdowns"] == 1

def test_a_refused_power_off_is_reported_and_the_policy_waits():
    """A battery policy that cannot act is advice, whatever it says, and an
    operator must see that"""

    actor = enforcing([undocked(volts=9.0)],
        power_off_runner=runner_of(code=1, output="a password is required"))
    actor.sample()
    assert "power off" in actor.share["last_error"]
    assert actor.share["policy"] == "shutdown_pending"

def test_a_refused_power_off_is_tried_again_on_the_next_sample():
    calls = []
    actor = enforcing([undocked(volts=9.0)],
        power_off_runner=runner_of(code=1, output="refused", calls=calls))
    actor.sample()
    actor.sample()
    assert len(calls) == 2

# The floor, and the remount ----------------------------------------------- #

def test_the_remount_waits_out_its_grace_before_the_power_off():
    """The order is forced: the writers are told, then the kernel is
    flushed, and only then can a file system go read-only"""

    power, mount = [], []
    actor = enforcing([undocked(volts=9.0)], calls=power,
        quiesce=Quiesce(syncer=lambda: None, runner=runner_of(calls=mount),
            grace=5.0))
    actor._evaluate(actor.reading(), now=100.0)
    assert mount == [] and power == []           # Still inside the grace
    actor._evaluate(actor.reading(), now=106.0)
    _, granted = granted_commands()
    assert mount == [[SUDO, "-n", *granted]]
    assert power                                 # And then the host stops

def test_a_failed_remount_still_stops_the_host():
    """A host that is still writing is better off halted than left running
    on the last of its charge"""

    power = []
    actor = enforcing([undocked(volts=9.0)], calls=power,
        quiesce=Quiesce(syncer=lambda: None,
            runner=runner_of(code=32, output="target is busy"), grace=0.0))
    actor._evaluate(actor.reading(), now=100.0)
    assert actor.share["quiesce"]["remounted"].startswith("failed")
    assert power

def test_a_shutdown_that_is_not_at_the_floor_does_not_remount():
    """Only the lowest voltage this design operates at makes the file
    systems read-only.  A button press does not"""

    mount = []
    actor = enforcing([undocked(volts=12.0)],
        quiesce=Quiesce(syncer=lambda: None, runner=runner_of(calls=mount),
            grace=0.0))
    actor.press(3.2)
    assert actor.share["policy_reason"] == "button_held"
    assert mount == []

def test_no_threshold_is_the_cell_damage_limit():
    """9.0 V for the battery pack is a limit this design never reaches, so it is
    never a trigger (the plan's S12).  A test holds the rule, because a
    threshold is a number that an edit can lower"""

    for name, value in THRESHOLDS.items():
        if "volts" in name:
            assert float(value) > 9.0, name

# The modes ---------------------------------------------------------------- #

def test_a_docked_host_is_normal():
    actor = make_actor(script=[{"battery_volts": 12.0, "docked": True}])
    actor.sample()
    assert actor.share["mode"] == MODE_NORMAL

def test_an_undocked_host_that_is_well_conserves():
    actor = make_actor(
        properties=("readings", "hold", "signal", "button", "dock"),
        script=[undocked(volts=12.0)])
    actor._evaluate(actor.reading(), now=1000.0)
    actor._evaluate(actor.reading(), now=1011.0)       # Past the dock dwell
    assert actor.share["mode"] == MODE_CONSERVE

def test_the_quiesce_hook_is_declared_and_fires():
    fired = []
    actor = make_actor(
        properties=("readings", "hold", "signal", "button", "dock"),
        script=[undocked(volts=9.0)], quiesce=Quiesce(syncer=lambda: None))
    actor.add_hook_handler(HOOK_QUIESCE,
        lambda name, component, logger, variables, options:
            fired.append(variables))
    actor.sample()
    assert fired and fired[0]["mode"] == MODE_QUIESCE

def test_the_disks_are_flushed_once_however_many_samples_follow():
    synced = []
    actor = make_actor(
        properties=("readings", "hold", "signal", "button", "dock"),
        script=[undocked(volts=9.0)],
        quiesce=Quiesce(syncer=lambda: synced.append("sync")))
    for _ in range(3):
        actor.sample()
    assert synced == ["sync"]

# The dock dwell ----------------------------------------------------------- #

def test_a_dock_that_flickers_does_not_start_a_shutdown():
    """An external supply glitches.  The host counts as docked until it has
    been undocked for its dwell"""

    actor = make_actor(
        properties=("readings", "hold", "signal", "button", "dock"),
        script=[undocked(volts=10.0)])
    actor._evaluate(actor.reading(), now=1000.0)
    assert actor.share["policy_would"] == "hold"
    assert actor.share["policy_reason"] == "docked"

def test_an_undock_that_holds_is_believed():
    actor = make_actor(
        properties=("readings", "hold", "signal", "button", "dock"),
        script=[undocked(volts=12.0)])
    actor._evaluate(actor.reading(), now=1000.0)
    actor._evaluate(actor.reading(), now=1011.0)       # Past the dwell
    assert actor.share["docked"] == "no"
    assert actor.share["undocked_since_utc"] != "-"

def test_a_host_with_no_dock_line_counts_as_docked():
    """Reporting nothing is not reporting "undocked", and a host that
    cannot tell must not stop itself"""

    actor = make_actor(properties=("readings", "hold"),
        script=[{"battery_volts": 12.0}])
    actor.sample()
    assert actor.share["policy_reason"] == "docked"

# --------------------------------------------------------------------------- #

# The deployment's grace period -------------------------------------------- #
#
# The end of the chain that test_power_manager_policy.py tests as a rule:
# the dock line goes false, the Actor counts the seconds itself, and the
# host stops although a client holds a claim.

def make_grace_actor(seconds, calls=None, **extra):
    settings = {
        "enforce": True,
        "properties": ("readings", "hold", "signal", "button", "dock"),
        "thresholds": {**THRESHOLDS, "powered_down_grace_s": seconds},
        "quiesce": Quiesce(syncer=lambda: None),
        "power_off_runner": runner_of(calls=calls),
    }
    settings.update(extra)
    return make_actor(**settings)

def test_the_grace_period_stops_a_host_that_a_claim_still_holds():
    """The lead's requirement, through the Actor: the supply went, a client
    holds a powered-up Lease, and the host stops anyway"""

    calls = []
    actor = make_grace_actor(60.0, calls=calls,
        script=[undocked(), undocked(), undocked()])
    namespace, host = str(actor.topic_path).split("/")[:2]
    actor.request_powered_up(f"{namespace}/{host}/900/1/in", 600, "upload")
    actor._evaluate(actor.reading(), now=1000.0)         # The supply goes
    assert actor.share["policy_reason"] == "docked"      # Within the dwell
    actor._evaluate(actor.reading(), now=1020.0)         # Past the dwell
    assert actor.share["policy_reason"] == "powered_up_held"
    assert calls == []
    actor._evaluate(actor.reading(), now=1081.0)         # Past the grace
    assert actor.share["policy_reason"] == "powered_down_grace"
    assert actor.share["metrics"]["shutdowns"] == 1
    assert calls

def test_a_supply_that_returns_resets_the_count():
    """"If power is restored then the need to shutdown is no more, and the
    grace time resets back to the specified value" """

    calls = []
    actor = make_grace_actor(60.0, calls=calls, script=[
        undocked(), undocked(), {"battery_volts": 12.0,
            "battery_pack_celsius": 25.0, "docked": True}, undocked(),
        undocked()])
    namespace, host = str(actor.topic_path).split("/")[:2]
    actor.request_powered_up(f"{namespace}/{host}/900/1/in", 600, "upload")
    actor._evaluate(actor.reading(), now=1000.0)
    actor._evaluate(actor.reading(), now=1050.0)         # 50 s of 60 gone
    assert actor.share["policy_would"] == "hold"
    actor._evaluate(actor.reading(), now=1051.0)         # Docked again
    assert actor.share["policy_reason"] == "docked"
    actor._evaluate(actor.reading(), now=1052.0)         # Undocked again
    actor._evaluate(actor.reading(), now=1100.0)         # 48 s, not 100 s
    assert actor.share["policy_would"] == "hold"
    assert calls == []
    assert actor.share["metrics"]["shutdowns"] == 0

def test_the_grace_period_shutdown_quiesces_first():
    """"Shutdown gracefully": the writers are told and the file systems are
    flushed before the host stops"""

    actor = make_grace_actor(60.0,
        script=[undocked(), undocked(), undocked()])
    actor._evaluate(actor.reading(), now=1000.0)
    actor._evaluate(actor.reading(), now=1020.0)
    actor._evaluate(actor.reading(), now=1081.0)
    assert actor.share["mode"] == MODE_QUIESCE
    assert actor.share["quiesce"]["synced"] == "yes"

def test_no_grace_period_leaves_a_claim_in_charge():
    """The default, through the Actor"""

    calls = []
    actor = make_grace_actor(None, calls=calls,
        script=[undocked(), undocked(), undocked()])
    namespace, host = str(actor.topic_path).split("/")[:2]
    actor.request_powered_up(f"{namespace}/{host}/900/1/in", 600, "upload")
    actor._evaluate(actor.reading(), now=1000.0)
    actor._evaluate(actor.reading(), now=1020.0)
    actor._evaluate(actor.reading(), now=2000.0)
    assert actor.share["policy_reason"] == "powered_up_held"
    assert calls == []

def test_a_grace_period_that_is_off_publishes_as_a_dash():
    """The shared state is read by an operator, and the word "None" reads
    like a fault"""

    actor = make_actor()
    assert actor.share["thresholds"]["powered_down_grace_s"] == "-"

def test_a_grace_period_that_is_set_publishes_its_value():
    actor = make_grace_actor(60.0, script=[undocked()])
    assert actor.share["thresholds"]["powered_down_grace_s"] == "60.0"
