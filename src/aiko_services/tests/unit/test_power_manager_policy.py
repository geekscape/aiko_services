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
# A client that needs the host asks for a powered-up Lease and holds a Lease, so the
# rule counts claims (ADR-028 decision 13).  A host that nothing claims
# stops after a grace, and a client that cannot be reached cannot hold a
# claim, so "nobody answered" and "nobody needs me" are one thing.

import pytest

from aiko_services.actors.power_manager import (
    Dwell, HOLD, MODES, MODE_CONSERVE, MODE_NORMAL, MODE_QUIESCE, REASONS,
    SHUTDOWN,
    THRESHOLDS, decide, decide_mode,
)
from aiko_services.actors.power_manager.policy import (
    EXACT_REASONS, decide_action, supply_warning
)

EVERY = ("readings", "hold", "signal", "button", "dock")

def when(**changes):
    """One decision, with a healthy undocked host as the starting point"""

    case = dict(
        volts=12.0, battery_pack_celsius=25.0, docked=False, properties=EVERY,
        powered_up_held=1, button_held=False,
        undocked_s=10.0, battery_low_s=0.0, powered_up_idle_s=0.0,
        thresholds=THRESHOLDS)
    case.update(changes)
    return decide(**case)

# The rows of the rule, in their order ------------------------------------- #

def test_the_button_beats_everything():
    """A person asked.  Even a full battery pack with claims held stops"""

    assert when(button_held=True) == (SHUTDOWN, "button_held")
    assert when(button_held=True, docked=True) == (SHUTDOWN, "button_held")
    assert when(button_held=True, powered_up_held=9, volts=12.6)  \
        == (SHUTDOWN, "button_held")

def test_the_floor_beats_every_claim():
    """A battery pack that is damaged is damaged for good, and work can
    wait.  A Lease asks, and it never commands"""

    assert when(volts=9.8, powered_up_held=9) == (SHUTDOWN, "battery_floor")

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
    """The deadline of the default thresholds, which is twenty minutes"""

    assert when(undocked_s=1201.0) == (SHUTDOWN, "powered_down_grace")

def test_the_backstop_is_what_remains_with_no_deadline():
    """The backstop is unreachable while the deadline is shorter, which it
    is by default.  It is there for a deployment that turns the deadline
    off, or sets it longer than fifteen minutes"""

    thresholds = {**THRESHOLDS, "powered_down_grace_s": None}
    assert when(thresholds=thresholds, undocked_s=901.0)  \
        == (SHUTDOWN, "undocked_timeout")
    assert when(thresholds=thresholds, undocked_s=899.0)[0] == HOLD

def test_the_bound_applies_however_many_claims_are_held():
    """Otherwise a client that keeps extending its claim holds the power
    until the battery pack is empty"""

    assert when(powered_up_held=9, undocked_s=1201.0)  \
        == (SHUTDOWN, "powered_down_grace")

# The deployment's grace period ------------------------------------------- #

def grace(seconds, **changes):
    """One decision with a grace period set, on the healthy undocked host"""

    thresholds = {**THRESHOLDS, "powered_down_grace_s": seconds}
    return when(thresholds=thresholds, **changes)

def test_ten_minutes_is_the_default_deadline():
    """Deliberately short: the battery pack is unmeasured, and it is not
    certain that it charges.  The lead set the backstop to fifteen minutes
    on 2026-11-05, so the deadline has to be shorter than that or it could
    never fire"""

    from aiko_services.actors.power_manager.power_manager import (
        POWERED_DOWN_GRACE_S, UNDOCKED_MAXIMUM_S)

    assert THRESHOLDS["powered_down_grace_s"] == POWERED_DOWN_GRACE_S == 600.0
    assert THRESHOLDS["undocked_maximum_s"] == UNDOCKED_MAXIMUM_S == 900.0
    assert POWERED_DOWN_GRACE_S < UNDOCKED_MAXIMUM_S
    assert when(powered_up_held=1, undocked_s=500.0)  \
        == (HOLD, "powered_up_held")        # Inside it, a claim still holds
    assert when(powered_up_held=9, undocked_s=601.0)[1]  \
        == "powered_down_grace"             # Past it, nothing holds

def test_the_default_deadline_is_shorter_than_the_backstop():
    """Otherwise the deadline would never fire, and the pair would be a
    puzzle rather than a rule"""

    assert THRESHOLDS["powered_down_grace_s"]  \
        < THRESHOLDS["undocked_maximum_s"]

def test_a_deadline_can_still_be_turned_off():
    thresholds = {**THRESHOLDS,
        "powered_down_grace_s": None, "undocked_maximum_s": None}
    assert when(thresholds=thresholds, undocked_s=99999.0, powered_up_held=1) \
        == (HOLD, "powered_up_held")

def test_a_grace_period_stops_the_host_whatever_is_claimed():
    """"No matter what": the supply went, it did not come back, and the
    grace period passed"""

    assert grace(120.0, undocked_s=121.0, powered_up_held=9)  \
        == (SHUTDOWN, "powered_down_grace")

def test_inside_the_grace_period_a_claim_still_holds():
    assert grace(120.0, undocked_s=119.0, powered_up_held=9)  \
        == (HOLD, "powered_up_held")

def test_the_grace_period_is_a_boundary_not_a_range():
    assert grace(120.0, undocked_s=120.0)[0] == HOLD
    assert grace(120.0, undocked_s=120.1) == (SHUTDOWN, "powered_down_grace")

def test_a_supply_that_came_back_cancels_the_grace_period():
    """The lead's second half.  The host counts undocked seconds, and a
    dock makes that zero, so the count starts again from the beginning"""

    assert grace(120.0, undocked_s=119.0, docked=True) == (HOLD, "docked")
    assert grace(120.0, undocked_s=0.0, powered_up_held=9)  \
        == (HOLD, "powered_up_held")

def test_the_shorter_of_the_two_deadlines_wins_and_is_named():
    """Two thresholds answer one question.  The log must say which one
    stopped the host, because they mean different things"""

    assert grace(120.0, undocked_s=121.0)[1] == "powered_down_grace"
    assert grace(7200.0, undocked_s=3601.0)[1] == "undocked_timeout"

def test_a_tie_goes_to_the_grace_period():
    """An operator set that one on purpose"""

    assert grace(900.0, undocked_s=901.0)[1] == "powered_down_grace"

def test_a_grace_period_of_zero_is_off_and_not_an_instant_stop():
    """A mistyped setting must not stop a host the moment it undocks"""

    for value in (0, 0.0, -1.0):
        assert grace(value, undocked_s=5.0, powered_up_held=9)  \
            == (HOLD, "powered_up_held"), value

def test_the_battery_pack_still_beats_the_grace_period():
    """The grace period is a deployment's rule, and the cells come first"""

    assert grace(3600.0, undocked_s=10.0, volts=9.8)[1] == "battery_floor"
    assert grace(3600.0, undocked_s=10.0, volts=10.4, battery_low_s=31.0)[1]  \
        == "battery_low"

def test_a_docked_host_never_reaches_the_grace_period():
    """It is the supply going away that starts the count"""

    assert grace(1.0, docked=True, undocked_s=0.0) == (HOLD, "docked")

def test_both_deadlines_absent_leaves_the_claims_in_charge():
    """A host with no deadline at all holds while anything claims it, and
    the voltage floor is what stops it in the end"""

    thresholds = {**THRESHOLDS,
        "powered_down_grace_s": None, "undocked_maximum_s": None}
    assert when(thresholds=thresholds, undocked_s=99999.0, powered_up_held=1)  \
        == (HOLD, "powered_up_held")
    assert when(thresholds=thresholds, undocked_s=99999.0, volts=9.0)[1]  \
        == "battery_floor"

def test_the_grace_period_reason_is_a_declared_word():
    from aiko_services.actors.power_manager.policy import REASONS

    assert "powered_down_grace" in REASONS

def test_a_host_that_nothing_claims_stops_after_its_grace():
    assert when(powered_up_held=0, powered_up_idle_s=61.0)  \
        == (SHUTDOWN, "powered_up_idle")

def test_a_host_within_its_grace_holds_and_says_which():
    assert when(powered_up_held=0, powered_up_idle_s=5.0) == (HOLD, "powered_up_grace")

def test_a_claim_that_is_held_holds_the_host():
    assert when(powered_up_held=1) == (HOLD, "powered_up_held")

def test_many_claims_hold_the_host_as_one_does():
    assert when(powered_up_held=7) == (HOLD, "powered_up_held")

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
        dict(powered_up_held=0, powered_up_idle_s=99.0), dict(),
        dict(powered_up_held=0, powered_up_idle_s=0.0)):
        reason = when(**case)[1]
        assert reason in REASONS, reason
        assert " " not in reason

def test_no_threshold_is_the_cell_damage_limit():
    """9.0 V for the battery pack, or 3.0 V for a cell, is a limit this
    design never reaches.  It is never a trigger (the plan's S12), and a
    test holds the rule because a threshold is a number an edit can lower.

    Only the thresholds that are compared against the battery pack's own
    voltage are in scope.  A headroom is a difference between two voltages
    and is small on purpose, so naming every threshold with "volts" in it
    would fail on something that is not a pack voltage at all"""

    from aiko_services.actors.power_manager.power_manager import (
        CELL_DAMAGE_VOLTS)

    differences = ("supply_headroom_volts",)
    absolute = [name for name in THRESHOLDS
        if "volts" in name and name not in differences]
    assert sorted(absolute) == [
        "battery_volts_charged", "battery_volts_floor", "battery_volts_low",
        "quiesce_volts"]
    for name in absolute:
        assert float(THRESHOLDS[name]) > CELL_DAMAGE_VOLTS, name

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
        assert decide_mode(*case, THRESHOLDS)[0] in MODES

# --------------------------------------------------------------------------- #

# The application grace ---------------------------------------------------- #
#
# Goal 3.  A host on its battery pack does not want a recording nobody
# asked for: the transfer queue grows with work that is not wanted, and
# then holds the host up to drain it.  So the writers are told to stop
# before the host stops, and MODE_CONSERVE is how they are told.

def mode_with(application=None, **changes):
    """One mode decision, on an undocked host that is otherwise well"""

    thresholds = {**THRESHOLDS,
        "powered_down_application_grace_s": application}
    case = dict(mode=MODE_NORMAL, decision=HOLD, volts=12.0, docked=False,
        hook_state="installed", thresholds=thresholds, undocked_s=0.0)
    case.update(changes)
    return decide_mode(**case)

def test_no_application_grace_conserves_at_once():
    """What an undocked host did before this threshold existed"""

    assert THRESHOLDS["powered_down_application_grace_s"] is None
    assert mode_with() == (MODE_CONSERVE, "undocked")

def test_inside_the_application_grace_the_mode_stays_normal():
    """A supply that went for a moment must not stop a recording"""

    assert mode_with(application=120.0, undocked_s=60.0)  \
        == (MODE_NORMAL, "application_grace")

def test_past_the_application_grace_the_host_conserves():
    assert mode_with(application=120.0, undocked_s=121.0)  \
        == (MODE_CONSERVE, "undocked")

def test_the_application_grace_is_a_boundary():
    assert mode_with(application=120.0, undocked_s=120.0)[0] == MODE_NORMAL
    assert mode_with(application=120.0, undocked_s=120.1)[0] == MODE_CONSERVE

def test_a_dock_ends_the_application_grace_whatever_it_counted():
    """Writing is okay again as soon as the supply is back"""

    assert mode_with(application=120.0, undocked_s=999.0, docked=True)  \
        == (MODE_NORMAL, "docked")

def test_an_application_grace_of_zero_is_off():
    for value in (0, 0.0, -1.0):
        assert mode_with(application=value, undocked_s=1.0)[0]  \
            == MODE_CONSERVE, value

def test_the_battery_pack_still_beats_the_application_grace():
    """The grace is about work that is not wanted.  A pack near its quiesce
    voltage is about a host that is about to lose its power"""

    assert mode_with(application=3600.0, undocked_s=1.0, volts=10.1)  \
        == (MODE_QUIESCE, "battery")

def test_a_decision_to_stop_still_beats_the_application_grace():
    assert mode_with(application=3600.0, undocked_s=1.0, decision=SHUTDOWN) \
        == (MODE_QUIESCE, "policy")

def test_a_missing_hook_still_beats_the_application_grace():
    assert mode_with(application=3600.0, undocked_s=1.0,
        hook_state="missing") == (MODE_QUIESCE, "hook_missing")

def test_quiesce_is_never_left_by_an_application_grace():
    """A mode never returns to normal without a dock"""

    assert mode_with(application=3600.0, undocked_s=1.0,
        mode=MODE_QUIESCE)[0] == MODE_QUIESCE

def test_the_application_grace_reason_is_a_declared_word():
    from aiko_services.actors.power_manager.policy import REASONS

    assert "application_grace" in REASONS

# What an application asks -------------------------------------------------- #

def test_writing_is_okay_only_in_the_normal_mode():
    """One boolean, derived in one place, so a later reason to stop writing
    needs no change in any client"""

    from aiko_services.actors.power_manager.policy import writing_ok

    assert writing_ok(MODE_NORMAL) is True
    assert writing_ok(MODE_CONSERVE) is False
    assert writing_ok(MODE_QUIESCE) is False

def test_every_mode_has_an_answer():
    from aiko_services.actors.power_manager.policy import writing_ok

    for mode in MODES:
        assert isinstance(writing_ok(mode), bool), mode

# An inert reason must not mask an active one ------------------------------ #
#
# Measured in production on 2026-11-05.  The battery pack sagged from
# 9.996 V to 9.770 V in the first second of an undocking, below its 9.900 V
# floor, so decide() answered "battery_floor" every time.  That reason
# comes from a data sheet, so an advisory posture holds it back, and
# decide() had already returned, so the deadline below it was never
# reached.  The deadline would have acted.  The host ran on a flat pack
# until it browned out, logging "would shut down now" once a minute.

def action(actionable=None, **changes):
    """The decision a caller can act on, on an undocked host"""

    case = dict(
        volts=12.0, battery_pack_celsius=25.0, docked=False, properties=EVERY,
        powered_up_held=1, button_held=False,
        undocked_s=10.0, battery_low_s=0.0, powered_up_idle_s=0.0,
        thresholds=THRESHOLDS)
    case.update(changes)
    return decide_action(**case, actionable=actionable)

def test_the_production_case_reaches_the_deadline():
    """The pack is under its floor and the deadline has passed.  What is
    most urgent cannot act, so what can act is the deadline"""

    flat = dict(volts=9.77, undocked_s=601.0, powered_up_held=9)
    assert when(**flat) == (SHUTDOWN, "battery_floor")      # most urgent
    assert action(actionable=EXACT_REASONS, **flat)  \
        == (SHUTDOWN, "powered_down_grace")                 # what can act

def test_nothing_actionable_holds_rather_than_stopping():
    """Under the floor, inside the deadline, and a claim held.  A hold is
    final, so the walk stops there and the host keeps running"""

    assert action(actionable=EXACT_REASONS,
        volts=9.77, undocked_s=10.0, powered_up_held=1)  \
        == (HOLD, "powered_up_held")

def test_with_everything_actionable_it_is_the_most_urgent():
    """An enforcing posture passes no set, and then this is decide()"""

    flat = dict(volts=9.77, undocked_s=601.0, powered_up_held=9)
    assert action(**flat) == when(**flat) == (SHUTDOWN, "battery_floor")

def test_a_hold_is_final_and_is_never_stepped_past():
    """A docked host holds.  Walking past that into the undocked rows
    would stop a host that has its supply"""

    assert action(actionable=EXACT_REASONS, volts=9.77, docked=True)  \
        == (HOLD, "docked")

def test_the_button_is_reached_past_an_inert_floor():
    """A person asked, and the floor must not swallow that either"""

    assert action(actionable=EXACT_REASONS, volts=9.77, button_held=True)  \
        == (SHUTDOWN, "button_held")

def test_the_backstop_is_reached_past_an_inert_floor():
    thresholds = {**THRESHOLDS, "powered_down_grace_s": None}
    assert action(actionable=EXACT_REASONS, thresholds=thresholds,
        volts=9.77, undocked_s=901.0, powered_up_held=9)  \
        == (SHUTDOWN, "undocked_timeout")

def test_a_host_with_no_hold_property_still_holds():
    assert action(actionable=EXACT_REASONS, volts=9.77,
        properties=("readings",)) == (HOLD, "no_hold_property")

def test_one_rule_is_read_two_ways_and_not_written_twice():
    """Both walk the same generator, so they cannot drift apart"""

    import inspect

    from aiko_services.actors.power_manager import policy

    for name in ("decide", "decide_action"):
        source = inspect.getsource(getattr(policy, name))
        assert "_rows(" in source, name

# A supply too small to charge the battery pack ----------------------------- #
#
# Measured on 2026-11-05.  A 12 V 1.5 A supply carried a 1.5 A load, so the
# charger saw 10.22 V against a pack at 9.89 V, which is 0.33 V where about
# 2 V is wanted.  The pack had never been charged, and every voltage
# threshold in this design had been argued about it.
#
# The warning decides nothing: a small supply is a thing to replace, and no
# row of decide() reads it.

SUPPLY = {"supply_headroom_volts": 0.5, "supply_amps_maximum": 1.5,
    "supply_amps_fraction": 0.95}

def test_the_measured_case_is_warned_about():
    assert supply_warning(10.220, 1.505, 9.894, True, SUPPLY)  \
        == "supply_current"

def test_the_current_is_the_cause_where_the_rating_is_known():
    """A supply at its rating has nothing spare, whatever its voltage"""

    assert supply_warning(12.4, 1.48, 11.0, True, SUPPLY) == "supply_current"

def test_without_a_rating_the_headroom_is_the_symptom():
    thresholds = {"supply_headroom_volts": 0.5}
    assert supply_warning(10.220, 1.505, 9.894, True, thresholds)  \
        == "supply_headroom"

def test_a_supply_with_room_to_charge_is_not_warned_about():
    assert supply_warning(12.4, 1.0, 11.1, True, SUPPLY) is None

def test_an_undocked_host_is_not_warned_about():
    """There is no supply to judge, and the headroom of a supply that is
    gone is not a fault in the supply"""

    assert supply_warning(0.4, 0.0, 9.9, False, SUPPLY) is None

def test_a_platform_that_measures_nothing_is_not_warned_about():
    assert supply_warning(None, None, None, True, SUPPLY) is None
    assert supply_warning(None, 1.6, None, True, SUPPLY) == "supply_current"

def test_a_rating_that_is_off_is_not_a_warning_on_its_own():
    thresholds = {"supply_amps_maximum": None, "supply_headroom_volts": 0.5}
    assert supply_warning(12.4, 99.0, 11.0, True, thresholds) is None

def test_the_headroom_can_be_turned_off():
    thresholds = {"supply_headroom_volts": 0}
    assert supply_warning(10.220, 1.505, 9.894, True, thresholds) is None

def test_the_fraction_is_what_counts_as_at_the_rating():
    """A supply does not have to reach its label to be at its limit"""

    thresholds = {"supply_amps_maximum": 1.5, "supply_amps_fraction": 0.5}
    assert supply_warning(12.0, 0.8, 11.0, True, thresholds)  \
        == "supply_current"

def test_every_token_is_declared():
    from aiko_services.actors.power_manager.policy import SUPPLY_WARNINGS

    for case in ((10.220, 1.505, 9.894, True, SUPPLY),
        (10.220, 1.505, 9.894, True, {"supply_headroom_volts": 0.5})):
        assert supply_warning(*case) in SUPPLY_WARNINGS

def test_no_decision_reads_the_supply_warning():
    """It is for a person.  A small supply is replaced, not a reason to
    stop a host"""

    import inspect

    from aiko_services.actors.power_manager import policy

    for name in ("decide", "decide_action", "_rows", "decide_mode"):
        source = inspect.getsource(getattr(policy, name))
        assert "supply_" not in source, name

# A full battery pack shows no headroom either ------------------------------ #
#
# Found on 2026-11-06.  A larger supply charged the battery pack from
# 9.9 V to
# 11.13 V, and the headroom warning stayed on, because a charger that has
# finished leaves no headroom.  So headroom alone cannot tell a healthy
# host from a starved one, and on a properly sized supply it would warn for
# ever: the very noise the warning was meant to avoid.

def test_a_full_battery_pack_with_no_headroom_is_not_warned_about():
    """The false positive.  The charger has stopped, which is why there is
    no headroom, and nothing is wrong"""

    assert supply_warning(12.5, 0.6, 12.3, True, THRESHOLDS) is None

def test_a_starved_battery_pack_with_no_headroom_is_still_warned_about():
    """The measurement that started all this: a supply 0.33 V above a
    battery pack
    that had never been charged"""

    assert supply_warning(10.220, 1.20, 9.894, True, THRESHOLDS)  \
        == "supply_headroom"

def test_a_part_charged_battery_pack_is_still_warned_about():
    """The state after the larger supply: charging, and capped well below
    full by the supply's own voltage.  That is worth saying"""

    assert supply_warning(11.434, 0.667, 11.116, True, THRESHOLDS)  \
        == "supply_headroom"

def test_the_boundary_is_the_charged_voltage():
    charged = THRESHOLDS["battery_volts_charged"]
    assert supply_warning(charged + 0.2, 0.6, charged - 0.01, True,
        THRESHOLDS) == "supply_headroom"
    assert supply_warning(charged + 0.2, 0.6, charged, True,
        THRESHOLDS) is None

def test_a_saturated_supply_is_warned_about_even_with_a_full_battery_pack():
    """A supply at its rating has nothing spare, whatever the battery pack
    reads.
    That is a fact about the supply and not about the charging"""

    thresholds = {**THRESHOLDS, "supply_amps_maximum": 1.5}
    assert supply_warning(12.5, 1.5, 12.3, True, thresholds)  \
        == "supply_current"

def test_turning_the_charged_voltage_off_restores_the_noise():
    """Documented rather than hidden: without it the headroom check cannot
    tell the two apart, and says so about both"""

    thresholds = {**THRESHOLDS, "battery_volts_charged": None}
    assert supply_warning(12.5, 0.6, 12.3, True, thresholds)  \
        == "supply_headroom"

def test_the_charged_voltage_is_above_every_other_battery_pack_voltage():
    """A battery pack counts as charged well above every voltage that means
    trouble.  Each is asserted on its own, because the quiesce and low
    pair is itself the wrong way round and a chain would read as though it
    were not"""

    charged = THRESHOLDS["battery_volts_charged"]
    for name in ("quiesce_volts", "battery_volts_low",
        "battery_volts_floor"):
        assert charged > THRESHOLDS[name], name
