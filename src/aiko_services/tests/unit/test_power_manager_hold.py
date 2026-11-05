# Usage
# ~~~~~
# pytest [-s] unit/test_power_manager_hold.py
#
# Unit tests for the power hold (actors/power_manager/hold.py), and for the
# Actor's refusal to release it (pmm.py).
#
# No hardware and no subprocess: the runner is injected, so a test asserts
# the exact arguments and feeds back the exact output that the real utility
# prints.  The samples below were read from the hardware on 2026-11-05.
#
# The case that matters most is an input that floats high through its
# pull-up.  It is not a hold, and reporting it as one would hide a host that
# is one power cut away from stopping.

import itertools

import pytest

import aiko_services as aiko
from aiko_services.actors.power_manager import (
    HOLD_GPIO, HOLD_OFF, HOLD_ON, HOLD_UNKNOWN, HoldNotAvailable,
    PmmPowerManagerImpl, hold_state, power_manager_args, set_hold,
)
from aiko_services.actors.power_manager.hold import hold_tool, run_tool

_counter = itertools.count()

# What the utility prints, as read from the hardware.  ASSERTED is the one
# that matters: it is what GPIO 5 reports after "set 5 op dh" on the board,
# on 2026-11-05.  The drive column reads "--" and not "dh", so a parser that
# looked for the drive would call an asserted hold "unknown"
ASSERTED = " 5: op -- pu | hi // GPIO5 = output"
DRIVEN_HIGH = " 5: op dh pu | hi // GPIO5 = output"
DRIVEN_LOW = "14: op -- pn | lo // GPIO14 = output"
INPUT_HIGH = " 5: ip    pu | hi // GPIO5 = input"
INPUT_LOW = " 4: ip    pu | lo // GPIO4 = input"

def runner_of(text, code=0, calls=None):
    def runner(arguments, timeout=2.0):
        if calls is not None:
            calls.append(arguments)
        return code, text
    return runner

# Setting the hold -------------------------------------------------------- #

def test_asserting_the_hold_drives_the_line_high():
    calls = []
    assert set_hold(True, runner=runner_of("", calls=calls)) == HOLD_ON
    assert calls == [["set", "5", "op", "dh"]]

def test_releasing_the_hold_drives_the_line_low():
    calls = []
    assert set_hold(False, runner=runner_of("", calls=calls)) == HOLD_OFF
    assert calls == [["set", "5", "op", "dl"]]

def test_another_line_can_be_named():
    calls = []
    set_hold(True, gpio=17, runner=runner_of("", calls=calls))
    assert calls == [["set", "17", "op", "dh"]]

def test_a_utility_that_fails_raises():
    with pytest.raises(OSError):
        set_hold(True, runner=runner_of("no such pin", code=1))

def test_a_platform_with_no_utility_raises_hold_not_available():
    def refuse(arguments, timeout=2.0):
        raise HoldNotAvailable("no pinctrl")

    with pytest.raises(HoldNotAvailable):
        set_hold(True, runner=refuse)

# Reading the hold -------------------------------------------------------- #

def test_the_line_as_the_board_reports_it_after_an_assert_is_a_hold():
    """Read from the hardware on 2026-11-05.  The drive column is "--",
    so the level after the bar is the only evidence of the state"""

    assert hold_state(runner=runner_of(ASSERTED)) == HOLD_ON

def test_a_driven_line_that_is_high_is_a_hold():
    assert hold_state(runner=runner_of(DRIVEN_HIGH)) == HOLD_ON

def test_a_driven_line_that_is_low_is_not_a_hold():
    assert hold_state(runner=runner_of(DRIVEN_LOW)) == HOLD_OFF

def test_an_input_that_floats_high_is_not_a_hold():
    """The weak pull-up does not hold the relay.  Reporting this as "on"
    would hide a host that is one power cut away from stopping"""

    assert hold_state(runner=runner_of(INPUT_HIGH)) == HOLD_UNKNOWN

def test_an_input_that_is_low_is_not_a_hold():
    assert hold_state(runner=runner_of(INPUT_LOW)) == HOLD_UNKNOWN

def test_output_that_cannot_be_parsed_is_unknown():
    assert hold_state(runner=runner_of("pinctrl: bad pin")) == HOLD_UNKNOWN

def test_a_failing_read_is_unknown():
    assert hold_state(runner=runner_of(DRIVEN_HIGH, code=1)) == HOLD_UNKNOWN

def test_a_platform_with_no_utility_reads_unknown():
    def refuse(arguments, timeout=2.0):
        raise HoldNotAvailable("no pinctrl")

    assert hold_state(runner=refuse) == HOLD_UNKNOWN

def test_the_tool_lookup_returns_a_path_or_none():
    found = hold_tool()
    assert found is None or found.endswith("pinctrl")

def test_an_absent_tool_is_not_found():
    assert hold_tool("no_such_pin_utility_at_all") is None

# The Actor ---------------------------------------------------------------- #

class EmptyBus:
    """A bus with no parts.  The hold does not need one: it is a pin, and
    "hold" in properties() depends on the utility alone"""

    def read_i2c_block_data(self, address, register, length):
        raise OSError(121, "Remote I/O error")

def make_actor(hold_output=DRIVEN_HIGH, **parameters):
    calls = parameters.pop("calls", [])
    settings = {
        "bus": EmptyBus(), "log_directory": None, "telemetry": False,
        "timer": False, "hold_runner": runner_of(hold_output, calls=calls),
        "buzzer": None,
    }
    settings.update(parameters)
    init_args = power_manager_args(
        f"power_hold_test_{next(_counter)}", "pmm",
        declared=PmmPowerManagerImpl.DECLARED_PROPERTIES, **settings)
    actor = aiko.compose_instance(PmmPowerManagerImpl, init_args)
    return actor, calls

def test_an_injected_runner_means_the_hold_property_is_real():
    actor, _ = make_actor()
    actor.open()
    assert "hold" in actor.properties()
    actor.close()

def test_the_actor_asserts_the_hold():
    actor, calls = make_actor()
    actor.open()
    actor.hold(True)
    assert ["set", "5", "op", "dh"] in calls
    assert actor.share["hold_state"] == HOLD_ON
    actor.close()

def test_the_actor_refuses_to_release_the_hold():
    """The release is the one operation software cannot undo, and it belongs
    to the shutdown hook alone (ADR-028 decision 6).  A message, a timer or
    a Pipeline must not be able to reach it"""

    actor, calls = make_actor()
    actor.open()
    actor.hold(False)
    assert not any("dl" in call for call in calls)
    assert actor.share["metrics"]["denied"] == 1
    assert "refused" in actor.share["last_error"]
    actor.close()

def test_every_spelling_of_off_is_refused():
    for value in (False, "off", "false", "no", "0"):
        actor, calls = make_actor()
        actor.open()
        actor.hold(value)
        assert not any("dl" in call for call in calls), value
        actor.close()

def test_the_hold_state_is_read_from_the_pin():
    actor, _ = make_actor(hold_output=INPUT_HIGH)
    actor.open()
    actor.publish_properties()
    assert actor.share["hold_state"] == HOLD_UNKNOWN
    actor.close()

def test_a_hold_that_fails_is_recorded_and_the_actor_continues():
    actor, _ = make_actor(calls=[])
    actor._hold_runner = runner_of("no such pin", code=1)
    actor.open()
    actor.hold(True)
    assert "failed" in actor.share["last_error"]
    actor.close()

def test_closing_the_actor_never_releases_the_hold():
    actor, calls = make_actor()
    actor.open()
    actor.hold(True)
    actor.close()
    assert [call for call in calls if "dl" in call] == []

def test_a_host_with_no_utility_has_no_hold_property(monkeypatch):
    from aiko_services.actors.power_manager import pmm as module
    monkeypatch.setattr(module, "hold_tool", lambda *a, **k: None)
    actor, _ = make_actor(hold_runner=run_tool)
    actor.open()
    assert "hold" not in actor.properties()
    actor.hold(True)                                 # A no-op, and no error
    assert actor.share["hold_state"] == "unknown"
    actor.close()

# --------------------------------------------------------------------------- #
