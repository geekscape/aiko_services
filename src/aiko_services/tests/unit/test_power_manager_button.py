# Usage
# ~~~~~
# pytest [-s] unit/test_power_manager_button.py
#
# Unit tests for the button and the dock line
# (actors/power_manager/button.py).
#
# classify() is pure, so the rule that stops a host is tested without a
# button.  The rest is the sense of the two lines, which is the thing that
# fails silently: both are active LOW on this board, and with the wrong
# sense every event arrives inverted and a press is never seen.

import pytest

from aiko_services.actors.power_manager import (
    BUTTON_ACTIVE_LOW, BUTTON_GPIO, DOCK_ACTIVE_LOW, DOCK_GPIO,
    FakePowerInputs, GpioPowerInputs, HOLD_TIME_S, choose_power_inputs,
    classify,
)

# The rule ----------------------------------------------------------------- #

def test_a_press_that_reaches_the_hold_time_is_long():
    assert classify(3.0) == "long"
    assert classify(5.0) == "long"

def test_a_press_that_falls_short_is_short():
    assert classify(2.99) == "short"
    assert classify(0.0) == "short"

def test_the_hold_time_can_be_given():
    assert classify(1.0, hold_time_s=0.5) == "long"
    assert classify(1.0, hold_time_s=5.0) == "short"

def test_three_seconds_is_the_hold_time_of_the_goal():
    assert HOLD_TIME_S == 3.0

# The sense of the lines --------------------------------------------------- #

def test_both_lines_are_active_low_on_this_board():
    """The board pulls both up, and each goes low to mean something.  With
    the wrong sense every event arrives inverted"""

    assert BUTTON_ACTIVE_LOW is True
    assert DOCK_ACTIVE_LOW is True

def test_the_pins_are_the_ones_of_the_module():
    assert (BUTTON_GPIO, DOCK_GPIO) == (6, 7)

def test_gpiozero_is_asked_for_a_pull_up(monkeypatch):
    """pull_up=True is what active low needs.  This asserts the argument
    that reaches gpiozero, because the cost of it being wrong is silent"""

    created = []

    class FakeDevice:
        def __init__(self, gpio, **keywords):
            created.append((gpio, keywords))
            self.value = 1
            self.when_pressed = self.when_released = None
            self.when_held = None
            self.when_activated = self.when_deactivated = None

        def close(self):
            pass

    import sys, types
    module = types.ModuleType("gpiozero")
    module.Button = FakeDevice
    module.DigitalInputDevice = FakeDevice
    monkeypatch.setitem(sys.modules, "gpiozero", module)

    inputs = GpioPowerInputs()
    inputs.open()
    assert created[0][0] == BUTTON_GPIO
    assert created[0][1]["pull_up"] is True
    assert created[0][1]["hold_time"] == HOLD_TIME_S
    assert created[1][0] == DOCK_GPIO
    assert created[1][1]["pull_up"] is True
    inputs.close()

# The fake ----------------------------------------------------------------- #

def test_the_fake_reports_a_long_press_as_held():
    inputs = FakePowerInputs()
    seen = []
    inputs.add_handler(lambda event, value: seen.append((event, value)))
    assert inputs.press(3.2) == "held"
    assert seen == [("button", "held")]

def test_the_fake_reports_a_short_press_as_short():
    inputs = FakePowerInputs()
    seen = []
    inputs.add_handler(lambda event, value: seen.append((event, value)))
    assert inputs.press(1.0) == "short"
    assert seen == [("button", "short")]

def test_a_press_with_no_duration_is_a_held_one():
    """What a test means when it says "the operator held the button" """

    assert FakePowerInputs().press() == "held"

def test_the_fake_starts_docked_and_reports_a_change():
    inputs = FakePowerInputs(docked=True)
    seen = []
    inputs.add_handler(lambda event, value: seen.append((event, value)))
    assert inputs.docked() is True
    inputs.set_docked(False)
    assert inputs.docked() is False
    assert seen == [("dock", "no")]

def test_the_fake_can_start_undocked():
    assert FakePowerInputs(docked=False).docked() is False

def test_every_handler_is_told():
    inputs = FakePowerInputs()
    first, second = [], []
    inputs.add_handler(lambda event, value: first.append(value))
    inputs.add_handler(lambda event, value: second.append(value))
    inputs.press(3.2)
    assert first == second == ["held"]

def test_closing_forgets_the_handlers():
    inputs = FakePowerInputs()
    seen = []
    inputs.add_handler(lambda event, value: seen.append(value))
    inputs.close()
    inputs.press(3.2)
    assert seen == []

# Composition -------------------------------------------------------------- #

def test_none_is_chosen_by_name():
    assert choose_power_inputs("none").device == "none"

def test_gpio_is_chosen_by_name():
    assert choose_power_inputs("gpio").device == "gpio"

def test_an_unknown_choice_raises_rather_than_guessing():
    with pytest.raises(ValueError, match="unknown inputs"):
        choose_power_inputs("switch")

def test_auto_falls_back_without_gpiozero(monkeypatch):
    import importlib.util
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)
    assert choose_power_inputs("auto").device == "none"

def test_a_line_that_is_not_open_reports_no_dock():
    assert GpioPowerInputs().docked() is None

# --------------------------------------------------------------------------- #
