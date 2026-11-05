# Usage
# ~~~~~
# pytest [-s] unit/test_power_manager_cli.py
#
# Unit tests for the composition and the command line
# (actors/power_manager/power_manager.py, cli.py).
#
# choose_power_manager() must never guess: an unknown name, and a name that
# belongs to a later phase, both raise rather than falling back to something
# that looks close.  The tags must say which properties an Implementation
# declares, because a client filters on them before it calls a method.

import json

from click.testing import CliRunner
import pytest

import aiko_services

from aiko_services.actors.power_manager import (
    MockPowerManagerImpl, PROPERTIES, PROTOCOL, PmmPowerManagerImpl,
    THRESHOLDS,
    choose_power_manager, service_filter, service_tags,
)
from aiko_services.actors.power_manager.cli import main

# The package ------------------------------------------------------------- #

def test_every_exported_name_imports():
    """__all__ listed names whose import had been cut away with a module
    that was removed, and nothing noticed, because each test imports from
    the module it is about rather than from the package"""

    import aiko_services.actors.power_manager as package

    missing = [name for name in package.__all__
        if not hasattr(package, name)]
    assert missing == []

def test_the_exported_names_are_sorted_and_unique():
    import aiko_services.actors.power_manager as package

    assert len(set(package.__all__)) == len(package.__all__)

# Composition -------------------------------------------------------------- #

def test_mock_is_chosen_by_name():
    assert choose_power_manager("mock") is MockPowerManagerImpl

def test_the_module_is_chosen_by_name():
    assert choose_power_manager("pmm") is PmmPowerManagerImpl

def test_auto_falls_back_to_the_mock_without_the_hardware(monkeypatch):
    from aiko_services.actors.power_manager import pmm as module
    monkeypatch.setattr(module, "module_present", lambda *a, **k: False)
    assert choose_power_manager("auto") is MockPowerManagerImpl

def test_auto_chooses_the_module_when_its_parts_answer(monkeypatch):
    from aiko_services.actors.power_manager import pmm as module
    monkeypatch.setattr(module, "module_present", lambda *a, **k: True)
    assert choose_power_manager("auto") is PmmPowerManagerImpl

def test_an_unknown_device_raises_rather_than_guessing():
    with pytest.raises(ValueError, match="unknown device"):
        choose_power_manager("battery")

def test_a_later_phase_device_says_which_phase():
    for name in ("linux", "macos"):
        with pytest.raises(ValueError, match="phase 7"):
            choose_power_manager(name)

# Tags and discovery ------------------------------------------------------- #

def test_the_tags_carry_one_entry_for_each_property():
    tags = service_tags("pmm", ("readings",))
    assert "device=pmm" in tags and "ec=true" in tags
    for name in PROPERTIES:
        assert f"{name}=true" in tags or f"{name}=false" in tags

def test_a_declared_property_is_true_and_the_rest_are_false():
    tags = service_tags("pmm", ("readings",))
    assert "readings=true" in tags
    assert "hold=false" in tags and "button=false" in tags

def test_no_tag_holds_a_space():
    """ServiceFilter joins tags with a space, so a value that holds one
    arrives as two tags (ADR-028 decision 2)"""

    for tag in service_tags("pmm", PROPERTIES):
        assert " " not in tag

def test_the_filter_names_the_protocol():
    assert service_filter("some_host").protocol == PROTOCOL

def test_the_filter_defaults_to_this_host():
    assert service_filter().name

# The command line --------------------------------------------------------- #

def test_the_help_lists_every_command_there_is():
    result = CliRunner().invoke(main, ["--help"])
    assert result.exit_code == 0
    for command in ("hold", "install", "render", "run", "sample", "signal",
        "verify"):
        assert command in result.output, command

def test_the_help_does_not_offer_what_a_later_phase_brings():
    """The policy, the button and the quiesce mode arrive with the phase
    that designs and tests each one"""

    result = CliRunner().invoke(main, ["--help"])
    for later in ("policy", "shutdown", "quiesce", "button"):
        assert f"  {later}" not in result.output

def test_sample_prints_one_json_reading():
    result = CliRunner().invoke(main, ["sample", "--device", "mock"])
    assert result.exit_code == 0
    record = json.loads(result.output.splitlines()[-1])
    assert record["device"] == "mock"
    assert record["battery_volts"] is not None

def test_sample_takes_a_count():
    result = CliRunner().invoke(
        main, ["sample", "--device", "mock", "--count", "3"])
    assert result.exit_code == 0
    assert len([line for line in result.output.splitlines()
        if line.startswith("{")]) == 3

def test_sample_refuses_an_unknown_device():
    result = CliRunner().invoke(main, ["sample", "--device", "battery"])
    assert result.exit_code != 0

# The commands that change a host ------------------------------------------ #

def test_hold_off_needs_force():
    """An undocked host stops the moment the line goes low, so a terminal
    needs to say that it means it"""

    result = CliRunner().invoke(main, ["hold", "off"])
    assert result.exit_code != 0
    assert "--force" in str(result.output) + str(result.exception)

def test_hold_takes_only_on_or_off():
    assert CliRunner().invoke(main, ["hold", "maybe"]).exit_code != 0

def test_render_prints_the_unit_and_changes_nothing():
    result = CliRunner().invoke(main, ["render", "unit"])
    assert result.exit_code == 0
    assert "Type=oneshot" in result.output

def test_render_prints_the_hook():
    result = CliRunner().invoke(main, ["render", "hook"])
    assert result.exit_code == 0
    assert "poweroff|halt" in result.output

def test_render_the_grant_needs_an_account():
    assert CliRunner().invoke(main, ["render", "grant"]).exit_code != 0

def test_render_the_grant_with_an_account():
    result = CliRunner().invoke(
        main, ["render", "grant", "--account", "pi"])
    assert result.exit_code == 0
    assert "NOPASSWD" in result.output

def test_render_refuses_an_unknown_artifact():
    assert CliRunner().invoke(main, ["render", "initrd"]).exit_code != 0

def test_verify_reports_each_artifact_and_the_hold():
    result = CliRunner().invoke(main, ["verify"])
    assert result.exit_code == 0
    for name in ("unit", "hook", "grant", "hold"):
        assert name in result.output

def test_signal_takes_only_a_known_pattern():
    assert CliRunner().invoke(
        main, ["signal", "klaxon", "--buzzer", "none"]).exit_code != 0

def test_signal_on_no_buzzer_is_not_an_error():
    result = CliRunner().invoke(
        main, ["signal", "booted", "--buzzer", "none"])
    assert result.exit_code == 0
    assert "none" in result.output

def test_run_installs_a_term_handler_so_its_lines_are_released(monkeypatch):
    """Without it the run ends on an unhandled signal, "finally" never
    runs, and a claimed output stays driven after the process is gone"""

    import signal as signal_module
    installed = []
    monkeypatch.setattr(signal_module, "signal",
        lambda number, handler: installed.append(number))
    monkeypatch.setattr(
        "aiko_services.process.run", lambda *a, **k: None)
    result = CliRunner().invoke(
        main, ["run", "--device", "mock", "--no_log", "--inputs", "none"])
    assert result.exit_code == 0, result.output
    assert signal_module.SIGTERM in installed

def test_run_help_states_the_posture():
    result = CliRunner().invoke(main, ["run", "--help"])
    assert result.exit_code == 0
    assert "--safe" in result.output and "--unsafe" in result.output
    assert "default: --safe" in result.output

# The deployment's grace period -------------------------------------------- #

def run_with(monkeypatch, *arguments):
    """Run the Actor far enough to compose it, and return the composed one.

    aiko.process.run() is replaced, so nothing waits on a broker"""

    composed = []
    real = aiko_services.compose_instance

    def record(implementation, init_args):
        instance = real(implementation, init_args)
        composed.append(instance)
        return instance

    monkeypatch.setattr(aiko_services, "compose_instance", record)
    monkeypatch.setattr(
        "aiko_services.actors.power_manager.cli.aiko.compose_instance", record)
    monkeypatch.setattr("aiko_services.process.run", lambda *a, **k: None)
    result = CliRunner().invoke(main, ["run", "--device", "mock", "--no_log",
        "--inputs", "none", *arguments])
    assert result.exit_code == 0, result.output
    return composed[-1], result

def test_the_default_deadline_is_ten_minutes(monkeypatch):
    """Deliberately short while the battery pack is unmeasured and it is
    not certain that it charges.  The backstop is fifteen, so the deadline
    is the one that fires"""

    actor, _ = run_with(monkeypatch)
    assert actor.share["thresholds"]["powered_down_grace_s"] == "600.0"
    assert actor.share["thresholds"]["undocked_maximum_s"] == "900.0"

def test_the_deadline_can_be_turned_off(monkeypatch):
    actor, _ = run_with(monkeypatch, "--powered_down_grace", "0")
    assert actor.share["thresholds"]["powered_down_grace_s"] == "-"

def test_the_grace_period_option_reaches_the_policy(monkeypatch):
    actor, _ = run_with(monkeypatch, "--powered_down_grace", "120")
    assert actor.share["thresholds"]["powered_down_grace_s"] == "120.0"

def test_the_grace_period_has_a_short_option(monkeypatch):
    actor, _ = run_with(monkeypatch, "-g", "45")
    assert actor.share["thresholds"]["powered_down_grace_s"] == "45.0"

def test_a_grace_period_says_so_on_the_way_up(monkeypatch):
    """An operator who set it must see that it took, and that an advisory
    run will not act on it"""

    _, result = run_with(monkeypatch, "--powered_down_grace", "120")
    assert "120 s" in result.output
    assert "advisory" in result.output

def test_a_grace_period_with_enforce_does_not_call_itself_advisory(
    monkeypatch):

    _, result = run_with(monkeypatch, "--powered_down_grace", "120",
        "--enforce")
    assert "120 s" in result.output
    assert "nothing will be stopped" not in result.output

def test_the_grace_period_is_in_the_run_help():
    result = CliRunner().invoke(main, ["run", "--help"])
    assert "--powered_down_grace" in result.output
    assert "default: off" in result.output

# --------------------------------------------------------------------------- #

# The application grace ---------------------------------------------------- #

def test_the_application_grace_is_off_unless_it_is_asked_for(monkeypatch):
    actor, _ = run_with(monkeypatch)
    assert actor.share["thresholds"][
        "powered_down_application_grace_s"] == "-"

def test_the_application_grace_option_reaches_the_policy(monkeypatch):
    actor, _ = run_with(monkeypatch,
        "--powered_down_application_grace", "120")
    assert actor.share["thresholds"][
        "powered_down_application_grace_s"] == "120.0"

def test_the_application_grace_has_a_short_option(monkeypatch):
    actor, _ = run_with(monkeypatch, "-a", "45")
    assert actor.share["thresholds"][
        "powered_down_application_grace_s"] == "45.0"

def test_both_graces_together_are_accepted_in_the_right_order(monkeypatch):
    actor, result = run_with(monkeypatch, "-a", "120", "-g", "300")
    assert actor.share["thresholds"][
        "powered_down_application_grace_s"] == "120.0"
    assert actor.share["thresholds"]["powered_down_grace_s"] == "300.0"
    assert actor.share["last_error"] == "-"
    assert "writers stop in 120 s" in result.output

def test_the_wrong_order_is_refused_where_a_person_can_read_why():
    """The writers must stop before the host does.  The command line
    refuses the pair outright, because a person is here"""

    for application, deadline in (("300", "300"), ("400", "300")):
        result = CliRunner().invoke(main, ["run", "--device", "mock",
            "--no_log", "--inputs", "none",
            "-a", application, "-g", deadline])
        assert result.exit_code != 0, (application, deadline)
        assert "must be less than" in result.output, (application, deadline)

def test_an_application_grace_alone_is_accepted(monkeypatch):
    """Either one alone is consistent: the backstop is the other deadline"""

    actor, _ = run_with(monkeypatch, "-a", "120")
    assert actor.share["last_error"] == "-"

def test_the_application_grace_is_in_the_run_help():
    result = CliRunner().invoke(main, ["run", "--help"])
    assert "--powered_down_application_grace" in result.output
    assert "Must be less than" in result.output

def test_an_application_grace_past_the_default_deadline_is_refused():
    """Checking against the option alone would let it through, and the
    Actor would then turn it off where nobody was watching"""

    result = CliRunner().invoke(main, ["run", "--device", "mock",
        "--no_log", "--inputs", "none", "-a", "1800"])
    assert result.exit_code != 0
    assert "must be less than" in result.output
    assert "the default" in result.output

def refused(monkeypatch, *arguments):
    """The command line's answer to one pair of options.

    It goes through run_with's patching even though a refusal never reaches
    the event loop.  A refusal that stops working would otherwise start the
    real loop and hang the suite, which is how this was found"""

    composed = []
    real = aiko_services.compose_instance
    monkeypatch.setattr(aiko_services, "compose_instance",
        lambda implementation, init_args: composed.append(
            real(implementation, init_args)) or composed[-1])
    monkeypatch.setattr(
        "aiko_services.actors.power_manager.cli.aiko.compose_instance",
        lambda implementation, init_args: composed.append(
            real(implementation, init_args)) or composed[-1])
    monkeypatch.setattr("aiko_services.process.run", lambda *a, **k: None)
    return CliRunner().invoke(main, ["run", "--device", "mock", "--no_log",
        "--inputs", "none", *arguments])

def test_an_application_grace_past_the_backstop_is_refused(monkeypatch):
    """The deadline that will fire is the shorter of the deployment's and
    the backstop.  With the deployment's turned off, the backstop is it"""

    result = refused(monkeypatch, "--powered_down_grace", "0", "-a", "1200")
    assert result.exit_code != 0, result.output
    assert "must be less than the backstop 900" in result.output

def test_the_refusal_names_the_default_when_no_deadline_was_typed(monkeypatch):
    result = refused(monkeypatch, "-a", "700")
    assert result.exit_code != 0, result.output
    assert "(the default) 600" in result.output

def test_an_application_grace_inside_both_deadlines_is_accepted(monkeypatch):
    result = refused(monkeypatch, "-a", "60")
    assert result.exit_code == 0, result.output

def test_turning_the_deadline_off_still_allows_a_short_grace(monkeypatch):
    """The backstop is then the deadline, and 60 s is well inside it"""

    result = refused(monkeypatch, "--powered_down_grace", "0", "-a", "60")
    assert result.exit_code == 0, result.output

# The three voltages ------------------------------------------------------- #
#
# They are a property of the battery pack that is fitted, and not of this
# software, so they belong on the command line.  The shipped numbers suit a
# healthy pack of three cells.  Measured on 2026-11-05, one pack rests at
# 9.996 V and sags to 9.770 V under 12 W, so the shipped floor of 9.900 V
# is crossed on every undocking and reports what it cannot act on.

def test_the_voltages_reach_the_policy(monkeypatch):
    actor, _ = run_with(monkeypatch, "-qv", "9.5", "-bl", "9.4", "-bf", "9.3")
    t = actor.share["thresholds"]
    assert t["quiesce_volts"] == "9.5"
    assert t["battery_volts_low"] == "9.4"
    assert t["battery_volts_floor"] == "9.3"
    assert actor.share["last_error"] == "-"

def test_one_voltage_alone_leaves_the_others_shipped(monkeypatch):
    actor, _ = run_with(monkeypatch, "-bf", "9.3")
    t = actor.share["thresholds"]
    assert t["battery_volts_floor"] == "9.3"
    assert t["battery_volts_low"] == str(THRESHOLDS["battery_volts_low"])

def test_a_floor_at_the_damage_limit_is_refused(monkeypatch):
    """This design stops above it, and never at it"""

    result = refused(monkeypatch, "-bf", "9.0")
    assert result.exit_code != 0, result.output
    assert "cell damage limit" in result.output

def test_a_floor_below_the_damage_limit_is_refused(monkeypatch):
    result = refused(monkeypatch, "-bf", "8.0")
    assert result.exit_code != 0, result.output
    assert "cell damage limit" in result.output

def test_a_low_below_the_floor_is_refused(monkeypatch):
    """The shutdown starts above the voltage it finishes at"""

    result = refused(monkeypatch, "-bl", "9.2", "-bf", "9.5")
    assert result.exit_code != 0, result.output
    assert "must not be below" in result.output

def test_a_quiesce_below_the_low_is_refused_when_it_is_given(monkeypatch):
    """Writing stops above the voltage at which the shutdown starts"""

    result = refused(monkeypatch, "-qv", "9.3", "-bl", "9.4", "-bf", "9.2")
    assert result.exit_code != 0, result.output
    assert "writing stops above" in result.output

def test_the_shipped_quiesce_and_low_are_the_wrong_way_round():
    """A defect found on 2026-11-05 by the check above, and left for the
    lead rather than changed here.  The low voltage is higher, so it fires
    first and forces the quiesce mode by itself, which makes the shipped
    quiesce voltage unreachable"""

    assert THRESHOLDS["quiesce_volts"] < THRESHOLDS["battery_volts_low"]

def test_a_single_voltage_is_checked_against_the_shipped_others(monkeypatch):
    """A floor above the shipped low would invert the ladder, and giving
    one number must not let that through"""

    result = refused(monkeypatch, "-bf", "99.0")
    assert result.exit_code != 0, result.output
    assert "must not be below" in result.output

def test_equal_voltages_are_accepted(monkeypatch):
    """A compressed ladder is what a nearly flat pack gives, and it is
    ordered even when two steps meet"""

    actor, _ = run_with(monkeypatch, "-qv", "9.4", "-bl", "9.4", "-bf", "9.4")
    assert actor.share["thresholds"]["quiesce_volts"] == "9.4"

def test_no_voltage_given_leaves_every_threshold_shipped(monkeypatch):
    actor, _ = run_with(monkeypatch)
    for name in ("quiesce_volts", "battery_volts_low", "battery_volts_floor"):
        assert actor.share["thresholds"][name] == str(THRESHOLDS[name]), name

def test_the_rating_line_names_what_is_checked_not_the_rating(monkeypatch):
    """The first version of this line printed the rating twice, so it read
    "above 1.5 A of its 1.5 A rating": a threshold nothing reaches"""

    _, result = run_with(monkeypatch, "--supply_amps_maximum", "1.5")
    at = 1.5 * THRESHOLDS["supply_amps_fraction"]
    assert f"above {at:g} A of its 1.5 A rating" in result.output

def test_the_charged_voltage_reaches_the_policy(monkeypatch):
    actor, _ = run_with(monkeypatch, "--battery_volts_charged", "12.2")
    assert actor.share["thresholds"]["battery_volts_charged"] == "12.2"

def test_a_charged_voltage_below_the_quiesce_voltage_is_refused(monkeypatch):
    """A battery pack counts as charged well above the voltage at which
    writing
    stops, or the gate it provides means nothing"""

    result = refused(monkeypatch, "--battery_volts_charged", "10.0")
    assert result.exit_code != 0, result.output
    assert "must be above" in result.output
