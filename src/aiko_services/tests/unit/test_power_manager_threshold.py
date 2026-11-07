# Usage
# ~~~~~
# pytest [-s] unit/test_power_manager_threshold.py
#
# Unit tests for changing a threshold while the Actor runs
# (actors/power_manager/power_manager.py).
#
# §3.3 of the plan says every threshold is a shared variable "so that the
# Dashboard changes it while the Actor runs".  Until now nothing
# implemented that: thresholds were command line only, and the
# "thresholds.*" items were a display snapshot that anything on the
# control topic could overwrite without changing the policy.  A page then
# showed a value the Actor was not using, and nothing reported it.
#
# So there are two surfaces here, and they must behave differently:
#
# - "(set_threshold NAME VALUE)" on the "in" topic changes the policy.  It
#   is outside SAFE_FUNCTIONS, so production denies it
# - "(update thresholds.NAME VALUE)" on the control topic is refused and
#   the stored value put back, the way "safe" already was
#
# The rules that refuse a value are the command line's own, through
# volts_ladder() and grace_order_diagnostic(), so that a person reads the
# same words whichever surface they used.

import itertools

import pytest

import aiko_services as aiko
from aiko_services.actors.power_manager import (
    FUNCTIONS,
    SAFE_FUNCTIONS,
    THRESHOLDS,
    MockPowerManagerImpl,
    power_manager_args,
)
from aiko_services.actors.power_manager.power_manager import (
    THRESHOLDS_OPTIONAL,
    volts_ladder,
)

_counter = itertools.count()


def make_actor(**parameters):
    settings = {"log_directory": None, "telemetry": False, "timer": False}
    settings.update(parameters)
    init_args = power_manager_args(
        f"power_threshold_test_{next(_counter)}", "mock", declared=MockPowerManagerImpl.DECLARED_PROPERTIES, **settings
    )
    return aiko.compose_instance(MockPowerManagerImpl, init_args)


def threshold(actor, name):
    return actor.share["thresholds"][name]


# The posture --------------------------------------------------------------- #


def test_a_threshold_change_is_denied_in_the_safe_posture():
    """A threshold stops a host, so it is not in the safe set.  No new
    gate code: the FunctionGate denies what SAFE_FUNCTIONS omits"""

    assert "set_threshold" in FUNCTIONS
    assert "set_threshold" not in SAFE_FUNCTIONS


# What is accepted ---------------------------------------------------------- #


def test_a_threshold_is_changed_and_published():
    actor = make_actor()
    actor.set_threshold("battery_volts_low", "10.8")

    assert actor._thresholds["battery_volts_low"] == 10.8
    assert threshold(actor, "battery_volts_low") == "10.8"
    assert actor.share["last_error"] == "-"


def test_the_policy_reads_the_new_value_and_not_the_replica():
    """The defect this closes: the replica moved and the policy did not"""

    actor = make_actor()
    actor.set_threshold("battery_pack_celsius_maximum", "40")

    assert actor._thresholds["battery_pack_celsius_maximum"] == 40.0


def test_a_threshold_that_may_be_turned_off_accepts_off():
    assert "supply_amps_maximum" in THRESHOLDS_OPTIONAL
    actor = make_actor(thresholds={"supply_amps_maximum": 1.5})
    actor.set_threshold("supply_amps_maximum", "off")

    assert actor._thresholds["supply_amps_maximum"] is None
    assert threshold(actor, "supply_amps_maximum") == "-"


@pytest.mark.parametrize("off", ["-", "none", "off", "0"])
def test_every_way_of_saying_off(off):
    actor = make_actor(thresholds={"supply_amps_maximum": 1.5})
    actor.set_threshold("supply_amps_maximum", off)

    assert actor._thresholds["supply_amps_maximum"] is None


def test_setting_the_value_it_already_has_changes_nothing():
    actor = make_actor()
    was = threshold(actor, "battery_volts_low")
    actor.set_threshold("battery_volts_low", was)

    assert threshold(actor, "battery_volts_low") == was
    assert actor.share["last_error"] == "-"


# What is refused ----------------------------------------------------------- #


def refused(actor, name, value):
    actor.set_threshold(name, value)
    error = actor.share["last_error"]
    assert error != "-", f"{name} {value} was accepted"
    return error


def test_an_unknown_threshold_is_refused():
    actor = make_actor()

    assert "unknown threshold" in refused(actor, "battery_volts", "11.0")


def test_a_value_that_is_not_a_number_is_refused():
    actor = make_actor()

    assert "not a number" in refused(actor, "battery_volts_low", "soon")


def test_a_negative_value_is_refused():
    actor = make_actor()

    assert "negative" in refused(actor, "battery_dwell_s", "-5")


def test_a_threshold_that_must_not_be_off_refuses_off():
    """A floor that is off is a host that never stops for its battery pack"""

    actor = make_actor()
    assert "battery_volts_floor" not in THRESHOLDS_OPTIONAL

    assert "cannot be turned off" in refused(actor, "battery_volts_floor", "off")


def test_a_floor_at_the_cell_damage_limit_is_refused():
    actor = make_actor()

    assert "cell damage limit" in refused(actor, "battery_volts_floor", "9.0")


def test_a_ladder_out_of_order_is_refused():
    """The shutdown must start above the voltage it finishes at"""

    actor = make_actor()

    assert "must not be below" in refused(actor, "battery_volts_low", "9.5")


def test_an_application_grace_that_is_not_shorter_is_refused():
    """The writers stop before the host does.  The command line refuses
    this pair, and so does this, because a person is at both"""

    actor = make_actor(thresholds={"powered_down_grace_s": 120.0})

    assert "not less than" in refused(actor, "powered_down_application_grace_s", "120")


def test_a_refused_value_leaves_the_threshold_alone():
    actor = make_actor()
    was = actor._thresholds["battery_volts_floor"]
    refused(actor, "battery_volts_floor", "9.0")

    assert actor._thresholds["battery_volts_floor"] == was
    assert threshold(actor, "battery_volts_floor") == f"{was}"


# The rules are the command line's own -------------------------------------- #


def test_the_ladder_is_one_rule_with_two_prefixes():
    """The command line says "--battery_volts_low" and the bus says
    "battery_volts_low", and nothing else differs"""

    values = {**THRESHOLDS, "battery_volts_low": 9.5}
    bus = volts_ladder(values, {"battery_volts_low"})
    command_line = volts_ladder(values, {"battery_volts_low"}, prefix="--")

    assert bus is not None
    assert command_line == bus.replace("battery_volts", "--battery_volts")


# The shared state reports, and does not control ---------------------------- #


def test_a_write_to_the_threshold_replica_is_refused():
    """The Dashboard's own variable editor publishes this.  It used to
    succeed, change nothing, and leave the page lying"""

    actor = make_actor()
    was = threshold(actor, "battery_volts_low")
    denied = int(actor.share["metrics"]["denied"])

    actor._power_change_handler("update", "thresholds.battery_volts_low", "11")

    assert threshold(actor, "battery_volts_low") == was
    assert actor._thresholds["battery_volts_low"] == float(was)
    assert int(actor.share["metrics"]["denied"]) == denied + 1


def test_the_replica_set_to_what_it_already_holds_is_not_a_denial():
    actor = make_actor()
    was = threshold(actor, "battery_volts_low")
    denied = int(actor.share["metrics"]["denied"])

    actor._power_change_handler("update", "thresholds.battery_volts_low", was)

    assert int(actor.share["metrics"]["denied"]) == denied


def test_safe_is_still_defended():
    """The handler grew a second rule, and must not have lost the first"""

    actor = make_actor()
    denied = int(actor.share["metrics"]["denied"])

    actor._power_change_handler("update", "safe", "False")

    assert actor.share["safe"] == actor._safe
    assert int(actor.share["metrics"]["denied"]) == denied + 1


def test_a_threshold_set_through_the_function_publishes_without_a_denial():
    """set_threshold() publishes the replica itself, and that publication
    must not look like a write from the bus"""

    actor = make_actor()
    denied = int(actor.share["metrics"]["denied"])
    actor.set_threshold("battery_volts_low", "10.8")

    assert threshold(actor, "battery_volts_low") == "10.8"
    assert int(actor.share["metrics"]["denied"]) == denied


# --------------------------------------------------------------------------- #

# The work that stopped (§4.16) -------------------------------------------- #
#
# A loss is the absence of a report, so only a clock finds it.  These
# tests move the clock rather than wait, because a test that waits for a
# real dwell is a test nobody runs.

from aiko_services.actors.power_manager.power_manager import (  # noqa: E402
    WORKING_LOST_PATTERN,
)


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def working_actor(loss=None, **parameters):
    actor = make_actor(thresholds={"working_loss_s": loss}, **parameters)
    actor._clock = clock = Clock()
    actor._now = clock
    return actor, clock


def test_nothing_is_lost_where_nothing_ever_reported():
    """A host that does not use the surface must never sound a loss"""

    actor, clock = working_actor(loss=60.0)
    clock.now += 3600
    actor._check_working(clock.now)

    assert actor.share["working"]["lost"] is False
    assert actor.signals == []


def test_a_reporter_that_goes_quiet_is_reported_once():
    actor, clock = working_actor(loss=60.0)
    actor.report_working("aiko/host/1/1/in", "frames")
    actor.signals.clear()
    clock.now += 61
    actor._check_working(clock.now)

    assert actor.share["working"]["lost"] is True
    assert actor.signals == [WORKING_LOST_PATTERN]
    assert int(actor.share["metrics"]["working_losses"]) == 1

    clock.now += 600  # And not again on every sample
    actor._check_working(clock.now)

    assert actor.signals == [WORKING_LOST_PATTERN]
    assert int(actor.share["metrics"]["working_losses"]) == 1


def test_a_reporter_that_comes_back_clears_the_loss():
    actor, clock = working_actor(loss=60.0)
    actor.report_working("aiko/host/1/1/in", "frames")
    clock.now += 61
    actor._check_working(clock.now)
    assert actor.share["working"]["lost"] is True

    clock.now += 1
    actor.report_working("aiko/host/1/1/in", "frames")

    assert actor.share["working"]["lost"] is False


def test_a_report_inside_the_dwell_still_counts_as_heard():
    """The dwell stops the sound, not the report.  Reading the sound's
    own clock for this would call a working Pipeline lost"""

    actor, clock = working_actor(loss=60.0)
    actor.report_working("aiko/host/1/1/in", "frames")
    for _ in range(4):  # Well inside working_dwell_s
        clock.now += 30
        actor.report_working("aiko/host/1/1/in", "frames")
    actor._check_working(clock.now)

    assert actor.share["working"]["lost"] is False


def test_the_loss_is_off_by_default():
    """How long a silence means something is the application's property"""

    assert THRESHOLDS["working_loss_s"] is None
    actor, clock = working_actor()
    actor.report_working("aiko/host/1/1/in", "frames")
    clock.now += 86400
    actor._check_working(clock.now)

    assert actor.share["working"]["lost"] is False


def test_the_age_is_published_whether_or_not_a_loss_is_watched_for():
    """The Dashboard shows the age, and that must not need the threshold"""

    actor, clock = working_actor()
    actor.report_working("aiko/host/1/1/in", "frames")
    clock.now += 42
    actor._check_working(clock.now)

    assert actor.share["working"]["age_s"] == "42"


def test_the_loss_can_be_turned_on_while_the_actor_runs():
    actor, clock = working_actor()
    actor.set_threshold("working_loss_s", "30")
    actor.report_working("aiko/host/1/1/in", "frames")
    actor.signals.clear()
    clock.now += 31
    actor._check_working(clock.now)

    assert actor.share["working"]["lost"] is True


# --------------------------------------------------------------------------- #

# The dock line and the supply voltage (§6 item 11) ------------------------ #
#
# The forklift found this.  Its supply was powered down and the rail sat
# between 0.3 V and 2.7 V, and the host reported "docked".  A host that
# believes it is docked starts no deadline, tells no writer to stop, and
# holds its own power on until the battery pack is flat.
#
# The plan adopted the cross-check in phase 3 and nothing implemented it:
# "docked" was the GPIO line alone.

from aiko_services.actors.power_manager.policy import (  # noqa: E402
    DOCK_DISAGREEMENTS,
    docked_state,
)
from aiko_services.actors.power_manager.power_manager import (  # noqa: E402
    DOCKED_VOLTS_MINIMUM,
)

DOCK = {"docked_volts_minimum": DOCKED_VOLTS_MINIMUM}


def test_a_floating_rail_does_not_count_as_docked():
    """The reading that started this: the supply is off and the line
    still says docked"""

    for volts in (0.3, 1.4, 2.7, 7.9):
        assert docked_state(True, volts, DOCK) == (False, "line_without_supply"), volts


def test_a_live_rail_with_the_line_docked_is_docked():
    assert docked_state(True, 12.0, DOCK) == (True, None)
    assert docked_state(True, 8.0, DOCK) == (True, None)  # At the line


def test_a_line_that_says_undocked_under_a_live_rail_is_reported():
    """The other way round, which means the line or its sense circuit
    has failed.  Undocked is still the conservative answer: running the
    battery pack down is the worse mistake"""

    assert docked_state(False, 12.0, DOCK) == (False, "supply_without_line")


def test_the_two_signals_agreeing_on_undocked_is_not_a_disagreement():
    assert docked_state(False, 0.3, DOCK) == (False, None)


@pytest.mark.parametrize("disagreement", DOCK_DISAGREEMENTS)
def test_every_disagreement_is_one_word(disagreement):
    """It is a shared state value and a log column, so a reader counts
    them"""

    assert " " not in disagreement


def test_one_signal_is_the_answer_where_the_other_is_absent():
    """An Implementation with no dock line, or with no supply monitor,
    must behave as it did"""

    assert docked_state(None, 12.0, DOCK) == (None, None)
    assert docked_state(True, None, DOCK) == (True, None)


@pytest.mark.parametrize("off", [None, 0, 0.0])
def test_the_cross_check_can_be_turned_off(off):
    """One signal where the design calls for two, for a deployment that
    trusts its dock line"""

    assert docked_state(True, 0.3, {"docked_volts_minimum": off}) == (True, None)


def test_the_threshold_can_be_turned_off_at_run_time():
    actor = make_actor()
    actor.set_threshold("docked_volts_minimum", "off")

    assert actor._thresholds["docked_volts_minimum"] is None


# What the Actor does with it ---------------------------------------------- #


def test_a_disagreement_is_published_and_counted():
    actor = make_actor(script=[{"docked": True, "supply_volts": 1.4, "battery_volts": 11.0}])
    actor.sample()

    assert actor.share["dock_disagreement"] == "line_without_supply"
    assert int(actor.share["metrics"]["dock_disagreements"]) == 1


def test_a_disagreement_is_counted_once_and_not_every_sample():
    """A forklift is powered down for weeks.  A warning every sample for
    weeks is one an operator stops reading"""

    actor = make_actor(script=[{"docked": True, "supply_volts": 1.4, "battery_volts": 11.0}])
    for _ in range(5):
        actor.sample()

    assert int(actor.share["metrics"]["dock_disagreements"]) == 1


def test_the_report_clears_when_the_signals_agree_again():
    actor = make_actor(
        script=[
            {"docked": True, "supply_volts": 1.4, "battery_volts": 11.0},
            {"docked": True, "supply_volts": 12.0, "battery_volts": 11.0},
        ]
    )
    actor.sample()
    assert actor.share["dock_disagreement"] == "line_without_supply"

    actor.sample()

    assert actor.share["dock_disagreement"] == "-"


def test_a_floating_rail_makes_the_host_undocked_to_the_policy():
    """The whole point.  "docked" published as "no" is what starts the
    deadline that puts this host away.

    The dock dwell applies to this as it does to the line itself: a host
    counts as docked until it has been undocked for "dock_dwell_s", so a
    supply that dips for a moment stops nothing"""

    actor = make_actor(script=[{"docked": True, "supply_volts": 1.4, "battery_volts": 11.0}])
    dwell = float(THRESHOLDS["dock_dwell_s"])
    reading = actor.reading()

    actor._evaluate(reading, now=1000.0)
    assert actor.share["docked"] == "yes"  # Inside the dwell

    actor._evaluate(reading, now=1000.0 + dwell + 1)

    assert actor.share["docked"] == "no"


def test_a_powered_supply_still_reads_as_docked():
    actor = make_actor(script=[{"docked": True, "supply_volts": 12.0, "battery_volts": 11.0}])
    actor.sample()

    assert actor.share["docked"] == "yes"
    assert actor.share["dock_disagreement"] == "-"


# --------------------------------------------------------------------------- #
