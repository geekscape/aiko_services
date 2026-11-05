# Usage
# ~~~~~
# pytest [-s] unit/test_power_manager_mock.py
#
# Unit tests for the Actor behavior that every Implementation shares, through
# the mock (actors/power_manager/mock.py, power_manager.py).
#
# No hardware and no broker.  The mock is the registered default
# Implementation, so these tests also assert that a platform with no
# Implementation of its own still reports, publishes and logs.
#
# Every wire function has at least one negative test (ADR-014), and the
# allow list is asserted exactly, because this Actor denies by default
# (P12, ADR-023).

import itertools
import json

import pytest

import aiko_services as aiko
from aiko_services.actors.power_manager import (
    DEFAULT_READING, DEVICE_FUNCTIONS, FUNCTIONS, MockPowerManagerImpl,
    POLICY_ADVISORY, PROPERTIES, PROTOCOL, SAFE, SAFE_FUNCTIONS, THRESHOLDS,
    PowerReading, power_manager_args,
)

_counter = itertools.count()

def make_actor(**parameters):
    settings = {"log_directory": None, "telemetry": False, "timer": False}
    settings.update(parameters)
    init_args = power_manager_args(
        f"power_mock_test_{next(_counter)}", "mock",
        declared=MockPowerManagerImpl.DECLARED_PROPERTIES, **settings)
    return aiko.compose_instance(MockPowerManagerImpl, init_args)

# The default Implementation ------------------------------------------------ #

def test_the_mock_is_the_registered_default():
    """A platform with no Implementation gets the mock, and says so"""

    composed = aiko.compose_instance(
        MockPowerManagerImpl, power_manager_args(
            f"power_default_{next(_counter)}", "mock",
            log_directory=None, timer=False))
    assert composed.device == "mock"
    assert composed.share["device"] == "mock"

def test_with_no_script_the_reading_is_a_healthy_docked_host():
    reading = make_actor().read()
    assert reading.battery_volts == DEFAULT_READING["battery_volts"]
    assert reading.docked is True

def test_a_script_is_walked_then_held_at_its_last_step():
    actor = make_actor(script=[
        {"battery_volts": 12.0}, {"battery_volts": 11.0}])
    assert actor.read().battery_volts == 12.0
    assert actor.read().battery_volts == 11.0
    assert actor.read().battery_volts == 11.0

def test_a_script_step_may_be_a_reading():
    actor = make_actor(script=[PowerReading(battery_volts=10.5)])
    assert actor.read().battery_volts == 10.5

def test_a_script_step_may_be_a_failing_bus():
    actor = make_actor(script=[OSError(121, "Remote I/O error")])
    with pytest.raises(OSError):
        actor.read()

# Sampling ----------------------------------------------------------------- #

def test_a_sample_publishes_the_reading():
    actor = make_actor(script=[{"battery_volts": 10.047, "docked": True}])
    actor.sample()
    assert actor.share["battery"]["volts"] == "10.047"
    assert actor.share["docked"] == "yes"
    assert actor.share["metrics"]["samples"] == 1

def test_a_sample_publishes_the_margin_above_the_floor():
    actor = make_actor(script=[{"battery_volts": 10.047}])
    actor.sample()
    assert actor.share["battery"]["margin_volts"] == "0.147"

def test_the_margin_is_negative_below_the_floor():
    actor = make_actor(script=[{"battery_volts": 9.8}])
    actor.sample()
    assert actor.share["battery"]["margin_volts"] == "-0.100"

def test_a_reading_carries_both_clocks_without_publishing():
    """What the "sample" sub-command prints: the same shape as the log"""

    actor = make_actor(script=[{"battery_volts": 12.0}])
    reading = actor.reading()
    assert reading.sampled_utc and reading.sampled_monotonic is not None
    assert actor.share["metrics"]["samples"] == 0      # Nothing was published

def test_a_sample_returns_the_reading_locally():
    """The wire form publishes, and the local call also hands it back"""

    actor = make_actor(script=[{"battery_volts": 12.0}])
    assert actor.sample().battery_volts == 12.0

def test_a_failing_sensor_is_recorded_and_the_actor_continues():
    actor = make_actor(script=[OSError(121, "Remote I/O error")])
    actor.sample()
    assert actor.share["metrics"]["sensor_errors"] == 1
    assert "Remote I/O error" in actor.share["last_error"]
    assert actor.share["metrics"]["samples"] == 1

def test_the_clocks_are_both_recorded():
    """A host with no real-time clock has a wall clock that is wrong, so the
    monotonic clock and the boot identifier order the log"""

    reading = make_actor().sample()
    assert reading.sampled_utc and reading.sampled_monotonic is not None

def test_a_sample_is_logged_as_one_json_line(tmp_path):
    actor = make_actor(
        script=[{"battery_volts": 10.047}], log_directory=str(tmp_path))
    actor.sample()
    actor.close()
    path = next(tmp_path.glob("*.jsonl"))
    record = json.loads(path.read_text().splitlines()[0])
    assert record["battery_volts"] == 10.047
    assert record["policy"] == POLICY_ADVISORY

# Phase 1 acts on nothing --------------------------------------------------- #

def test_the_policy_is_advisory_and_nothing_is_enforced():
    actor = make_actor(script=[{"battery_volts": 9.0}])    # Under every bound
    actor.sample()
    assert actor.share["policy"] == POLICY_ADVISORY
    assert actor.holds == []              # Nothing was held, nothing released

def test_the_thresholds_are_published_as_configuration():
    actor = make_actor()
    for name, value in THRESHOLDS.items():
        assert actor.share["thresholds"][name] == f"{value}"

def test_no_threshold_is_the_cell_damage_limit():
    """9.0 V for the pack, or 3.0 V for a cell, is a limit that this design
    never reaches.  It is never a trigger (the plan's S12)"""

    assert 9.0 not in THRESHOLDS.values()
    assert THRESHOLDS["battery_volts_floor"] > 9.0

def test_a_hold_is_recorded_and_does_nothing_else():
    actor = make_actor()
    actor.hold("off")
    assert actor.holds == ["off"]
    assert actor.share["hold_state"] == "unknown"

# The sample period -------------------------------------------------------- #

def test_the_period_is_published():
    actor = make_actor(period=60.0)
    assert actor.share["sample_period_s"] == "60.0"

def test_the_period_changes():
    actor = make_actor(period=5.0)
    actor.set_period(60)
    assert actor.share["sample_period_s"] == "60.0"

def test_a_period_that_is_too_small_is_refused():
    actor = make_actor(period=5.0)
    actor.set_period(0.01)
    assert actor.share["sample_period_s"] == "5.0"
    assert "0.5 to 3600" in actor.share["last_error"]

def test_a_period_that_is_too_large_is_refused():
    actor = make_actor(period=5.0)
    actor.set_period(100000)
    assert actor.share["sample_period_s"] == "5.0"

def test_a_period_that_is_not_a_number_is_refused():
    """A wire function records the refusal, and never raises at the caller:
    the bus has no way to receive an exception"""

    actor = make_actor(period=5.0)
    actor.set_period("soon")
    assert actor.share["sample_period_s"] == "5.0"
    assert "soon" in actor.share["last_error"]

# The properties ----------------------------------------------------------- #

def test_the_properties_are_published_as_shared_variables():
    actor = make_actor(properties=("readings", "dock"))
    actor.publish_properties()
    assert actor.share["readings"] is True
    assert actor.share["dock"] is True
    assert actor.share["hold"] is False
    assert actor.share["signal"] is False

def test_every_property_of_the_protocol_is_published():
    actor = make_actor()
    actor.publish_properties()
    for name in PROPERTIES:
        assert name in actor.share

def test_an_absent_property_makes_its_method_a_no_op():
    """ADR-022 decision 1: a backend that lacks a method gets a no-op"""

    actor = make_actor(properties=("readings",))
    actor.publish_properties()
    assert actor.share["signal"] is False
    actor.signal("booted")                           # Records, acts on nothing
    assert actor.signals == ["booted"]

# The safe posture --------------------------------------------------------- #

def test_the_allow_list_is_exactly_the_wire_surface():
    assert sorted(FUNCTIONS) == [
        "hold", "sample", "set_log_level", "set_period", "signal", "stop"]

def test_the_device_seam_is_not_on_the_bus():
    """open(), close(), read(), add_handler() and properties() are called by
    the CLI and by this Actor, and never from the message bus"""

    assert not (DEVICE_FUNCTIONS & FUNCTIONS)

def test_safe_mode_allows_a_sample_and_the_log_level_only():
    assert sorted(SAFE_FUNCTIONS) == ["sample", "set_log_level"]

def test_safe_is_the_default_posture():
    assert SAFE is True
    assert make_actor().share["safe"] is True

def test_safe_mode_denies_the_functions_that_stop_a_host():
    actor = make_actor(safe=True)
    assert actor.deny_function("hold", ["off"])
    assert actor.deny_function("sample", []) is None

def test_an_unsafe_posture_accepts_them_and_says_so():
    actor = make_actor(safe=False)
    assert actor.share["safe"] is False
    assert actor.deny_function("hold", ["off"]) is None

def test_safe_cannot_be_changed_from_the_bus():
    """It is a report of the posture, not a control for it"""

    actor = make_actor(safe=True)
    actor.ec_producer.update("safe", False)
    assert actor.share["safe"] is True
    assert actor.share["metrics"]["denied"] == 1

# Handlers ----------------------------------------------------------------- #

def test_a_press_that_reaches_the_hold_time_decides_to_stop():
    actor = make_actor(script=[{"battery_volts": 12.0, "docked": True}])
    actor.press(3.2)
    assert actor.share["metrics"]["button_presses"] == 1
    assert actor.share["policy_would"] == "shutdown"
    assert actor.share["policy_reason"] == "button_held"

def test_a_press_that_reaches_the_hold_time_acts_on_nothing_while_advisory():
    """A person asked, and the posture still decides whether it happens"""

    actor = make_actor(script=[{"battery_volts": 12.0, "docked": True}])
    actor.press(3.2)
    assert actor.share["policy"] == POLICY_ADVISORY
    assert actor.share["metrics"]["shutdowns"] == 0

def test_a_short_press_decides_nothing():
    actor = make_actor(script=[{"battery_volts": 12.0, "docked": True}])
    actor.press(1.0)
    assert actor.share["metrics"]["button_presses"] == 0
    assert actor.share["policy_would"] == "-"

def test_a_dock_change_reaches_the_actor():
    actor = make_actor()
    actor.dock(False)
    assert actor._inputs.docked() is False

def test_a_handler_is_recorded():
    """add_handler is part of the Interface, for a client that wants the
    raw events rather than the decision"""

    actor = make_actor()
    seen = []
    actor.add_handler(lambda event, value: seen.append((event, value)))
    assert actor._handlers == [seen.append] or len(actor._handlers) == 1

def test_the_protocol_is_power_manager_0():
    assert PROTOCOL.endswith("/power_manager:0")

# --------------------------------------------------------------------------- #
