# Usage
# ~~~~~
# pytest [-s] unit/test_power_manager_policy.py
#
# Unit tests for the rule that decides whether a host keeps its power
# (actors/power_manager/policy.py).
#
# decide() is pure, so the table below is the test.  Every row of the rule
# in ADR-028 decision 8 has a case, and so does every row's boundary: a
# threshold that is reached is not the same as a threshold that is passed,
# and the dwell is what separates a sag from a reason.
#
# The one thing to read first is that nothing here names an application.
# A client that needs the host asks for up-time and holds a Lease, so the
# rule counts claims (ADR-028 decision 13).  A host that nothing claims
# stops after a grace, and a client that cannot be reached cannot hold a
# claim, so "nobody answered" and "nobody needs me" are one thing.

import pytest

from aiko_services.actors.power_manager import (
    Dwell, HOLD, MODE_CONSERVE, MODE_NORMAL, MODE_QUIESCE, REASONS, SHUTDOWN,
    THRESHOLDS, decide, decide_mode,
)

EVERY = ("readings", "hold", "signal", "button", "dock")

def when(**changes):
    """One decision, with a healthy undocked host as the starting point"""

    case = dict(
        volts=12.0, battery_pack_celsius=25.0, docked=False, properties=EVERY,
        uptime_held=1, button_held=False,
        undocked_s=10.0, battery_low_s=0.0, uptime_idle_s=0.0,
        thresholds=THRESHOLDS)
    case.update(changes)
    return decide(**case)

# The rows of the rule, in their order ------------------------------------- #

def test_the_button_beats_everything():
    """A person asked.  Even a full battery pack with claims held stops"""

    assert when(button_held=True) == (SHUTDOWN, "button_held")
    assert when(button_held=True, docked=True) == (SHUTDOWN, "button_held")
    assert when(button_held=True, uptime_held=9, volts=12.6)  \
        == (SHUTDOWN, "button_held")

def test_the_floor_beats_every_claim():
    """A battery pack that is damaged is damaged for good, and work can
    wait.  A Lease asks, and it never commands"""

    assert when(volts=9.8, uptime_held=9) == (SHUTDOWN, "battery_floor")

def test_the_floor_is_a_boundary_not_a_range():
    assert when(volts=9.9)[0] == HOLD        # At the floor, not under it
    assert when(volts=9.89) == (SHUTDOWN, "battery_floor")

def test_a_hot_battery_pack_beats_every_claim():
    assert when(battery_pack_celsius=46.0) == (SHUTDOWN, "battery_pack_temperature")

def test_the_battery_pack_temperature_is_a_boundary():
    assert when(battery_pack_celsius=45.0)[0] == HOLD
    assert when(battery_pack_celsius=45.1) == (SHUTDOWN, "battery_pack_temperature")

def test_a_host_that_cannot_hold_its_power_has_nothing_to_decide():
    assert when(properties=("readings",)) == (HOLD, "no_hold_property")
    assert when(properties=("readings",), volts=9.0)[1] == "battery_floor"

def test_a_docked_host_holds():
    assert when(docked=True) == (HOLD, "docked")

def test_an_undocked_host_with_a_low_pack_stops_after_its_dwell():
    assert when(volts=10.4, battery_low_s=31.0) == (SHUTDOWN, "battery_low")

def test_a_sag_that_has_not_dwelt_is_not_a_reason():
    """A load step makes the voltage sag for seconds"""

    assert when(volts=10.4, battery_low_s=5.0)[0] == HOLD

def test_the_undocked_time_is_bounded():
    assert when(undocked_s=3601.0) == (SHUTDOWN, "undocked_timeout")

def test_the_bound_applies_however_many_claims_are_held():
    """Otherwise a client that keeps extending its claim holds the power
    until the battery pack is empty"""

    assert when(uptime_held=9, undocked_s=3601.0)  \
        == (SHUTDOWN, "undocked_timeout")

def test_a_host_that_nothing_claims_stops_after_its_grace():
    assert when(uptime_held=0, uptime_idle_s=61.0)  \
        == (SHUTDOWN, "uptime_idle")

def test_a_host_within_its_grace_holds_and_says_which():
    assert when(uptime_held=0, uptime_idle_s=5.0) == (HOLD, "uptime_grace")

def test_a_claim_that_is_held_holds_the_host():
    assert when(uptime_held=1) == (HOLD, "uptime_held")

def test_many_claims_hold_the_host_as_one_does():
    assert when(uptime_held=7) == (HOLD, "uptime_held")

def test_the_policy_names_no_application():
    """Every reason is about power, time or a claim.  None of them is the
    name of an Actor, a Pipeline or an application (ADR-028 decision 13)"""

    for reason in REASONS:
        assert "store_forward" not in reason
        assert "queue" not in reason

# Readings that a platform does not have ----------------------------------- #

def test_a_host_with_no_voltage_is_not_a_host_in_trouble():
    assert when(volts=None)[0] == HOLD

def test_a_host_with_no_battery_pack_temperature_is_not_a_host_in_trouble():
    assert when(battery_pack_celsius=None)[0] == HOLD

def test_a_threshold_that_is_missing_does_not_fire():
    """A policy must not stop a host because a setting was mistyped"""

    thresholds = dict(THRESHOLDS)
    thresholds["battery_volts_floor"] = None
    assert when(volts=0.0, thresholds=thresholds)[1] != "battery_floor"

def test_a_threshold_that_is_nonsense_does_not_fire():
    thresholds = dict(THRESHOLDS)
    thresholds["battery_volts_floor"] = "soon"
    assert when(volts=0.0, thresholds=thresholds)[1] != "battery_floor"

def test_every_reason_is_a_declared_token():
    for case in (
        dict(button_held=True), dict(volts=9.0), dict(battery_pack_celsius=99.0),
        dict(properties=("readings",)), dict(docked=True),
        dict(volts=10.4, battery_low_s=99.0), dict(undocked_s=99999.0),
        dict(uptime_held=0, uptime_idle_s=99.0), dict(),
        dict(uptime_held=0, uptime_idle_s=0.0)):
        reason = when(**case)[1]
        assert reason in REASONS, reason
        assert " " not in reason

def test_no_threshold_is_the_cell_damage_limit():
    """9.0 V for the battery pack, or 3.0 V for a cell, is a limit this design never
    reaches.  It is never a trigger (the plan's S12)"""

    for name, value in THRESHOLDS.items():
        if "volts" in name:
            assert value > 9.0, name

# The dwell ---------------------------------------------------------------- #

def test_a_dwell_starts_when_the_condition_starts():
    dwell = Dwell()
    assert dwell.update(True, 100.0) == 0.0
    assert dwell.seconds(130.0) == 30.0

def test_a_dwell_clears_when_the_condition_clears():
    dwell = Dwell()
    dwell.update(True, 100.0)
    assert dwell.update(False, 110.0) == 0.0
    assert dwell.passed(1.0, 200.0) is False

def test_a_dwell_does_not_restart_while_the_condition_holds():
    dwell = Dwell()
    dwell.update(True, 100.0)
    dwell.update(True, 110.0)
    assert dwell.seconds(130.0) == 30.0

def test_a_dwell_passes_at_its_limit():
    dwell = Dwell()
    dwell.update(True, 0.0)
    assert dwell.passed(30.0, 29.9) is False
    assert dwell.passed(30.0, 30.0) is True

def test_a_dwell_that_never_started_has_not_passed():
    assert Dwell().passed(0.0, 100.0) is False

def test_a_clock_that_goes_backwards_does_not_make_a_negative_dwell():
    dwell = Dwell()
    dwell.update(True, 100.0)
    assert dwell.seconds(90.0) == 0.0

# The modes ---------------------------------------------------------------- #

def test_a_docked_host_is_normal():
    assert decide_mode(MODE_QUIESCE, HOLD, 12.0, True, "installed", THRESHOLDS)  \
        == (MODE_NORMAL, "docked")

def test_a_decision_to_stop_quiesces():
    assert decide_mode(MODE_NORMAL, SHUTDOWN, 12.0, False, "installed", THRESHOLDS) \
        == (MODE_QUIESCE, "policy")

def test_a_pack_at_the_quiesce_voltage_quiesces():
    assert decide_mode(MODE_NORMAL, HOLD, 10.2, False, "installed", THRESHOLDS)  \
        == (MODE_QUIESCE, "battery")

def test_an_unknown_hook_is_not_a_missing_one():
    """A platform with no such hook reports "unknown" for ever, and that is
    not evidence that the hold will be left asserted"""

    assert decide_mode(MODE_NORMAL, HOLD, 12.0, False, "unknown", THRESHOLDS) \
        == (MODE_CONSERVE, "undocked")

def test_a_missing_hook_quiesces_an_undocked_host():
    """The hold will not be released, so the battery pack will run out: whatever is
    writing should stop before it does"""

    assert decide_mode(MODE_NORMAL, HOLD, 12.0, False, "missing", THRESHOLDS)  \
        == (MODE_QUIESCE, "hook_missing")

def test_an_undocked_host_that_is_well_conserves():
    assert decide_mode(MODE_NORMAL, HOLD, 12.0, False, "installed", THRESHOLDS)  \
        == (MODE_CONSERVE, "undocked")

def test_a_mode_never_returns_to_normal_without_a_dock():
    """A battery pack that recovered a little is not a battery pack that was charged"""

    assert decide_mode(MODE_QUIESCE, HOLD, 12.0, False, "installed", THRESHOLDS)  \
        == (MODE_QUIESCE, "held")

def test_every_mode_is_one_of_the_declared_ones():
    for case in ((MODE_NORMAL, HOLD, 12.0, True, "installed"),
        (MODE_NORMAL, SHUTDOWN, 12.0, False, "installed"),
        (MODE_NORMAL, HOLD, 10.0, False, "installed"),
        (MODE_NORMAL, HOLD, 12.0, False, "missing"),
        (MODE_QUIESCE, HOLD, 12.0, False, "unknown")):
        from aiko_services.actors.power_manager import MODES
        assert decide_mode(*case, THRESHOLDS)[0] in MODES

# --------------------------------------------------------------------------- #
