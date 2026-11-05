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

from aiko_services.actors.power_manager import (
    MockPowerManagerImpl, PROPERTIES, PROTOCOL, PmmPowerManagerImpl,
    choose_power_manager, service_filter, service_tags,
)
from aiko_services.actors.power_manager.cli import main

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

def test_the_help_lists_the_two_phase_1_commands():
    result = CliRunner().invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "run" in result.output and "sample" in result.output
    # Each of these changes a host, and each arrives with its own phase
    for later in ("hold", "install", "verify"):
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

def test_run_help_states_the_posture():
    result = CliRunner().invoke(main, ["run", "--help"])
    assert result.exit_code == 0
    assert "--safe" in result.output and "--unsafe" in result.output
    assert "default: --safe" in result.output

# --------------------------------------------------------------------------- #
