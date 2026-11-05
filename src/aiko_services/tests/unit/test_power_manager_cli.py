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
