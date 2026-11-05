# Usage
# ~~~~~
# pytest [-s] unit/test_power_manager_signal.py
#
# Unit tests for the signals (actors/power_manager/signal.py).
#
# A pattern is data, so these tests compare lists with no hardware and no
# sound.  The buzzer is driven with the sleeper replaced, so a test takes
# microseconds rather than the pattern's own length.

import itertools

import pytest

import aiko_services as aiko
from aiko_services.actors.power_manager import (
    BUZZER_GPIO, FakeBuzzer, GpioBuzzer, PATTERNS, PmmPowerManagerImpl,
    choose_buzzer, pattern_seconds, power_manager_args,
)

_counter = itertools.count()

class EmptyBus:
    def read_i2c_block_data(self, address, register, length):
        raise OSError(121, "Remote I/O error")

def edges_of(name):
    """The on and off edges that one pattern makes, with its sleeps"""

    edges = []
    buzzer = GpioBuzzer(thread=False,
        sleeper=lambda seconds: edges.append(("sleep", seconds)))
    buzzer._set = lambda on: edges.append(("on" if on else "off",))
    buzzer.play(name)
    return edges

# The patterns ------------------------------------------------------------- #

def test_the_four_patterns_of_the_plan_are_there():
    assert sorted(PATTERNS) == ["accepted", "booted", "pipeline", "shutdown"]

def test_every_pattern_is_durations_in_seconds():
    for name, pattern in PATTERNS.items():
        assert pattern, name
        assert all(isinstance(value, float) and value > 0
            for value in pattern), name

def test_every_pattern_is_short_enough_to_be_one_sound():
    """A signal tells an operator one thing.  A pattern that runs for
    seconds is a fault report, not a signal"""

    for name in PATTERNS:
        assert pattern_seconds(name) <= 1.0, name

def test_booted_is_two_chirps():
    assert edges_of("booted") == [
        ("on",), ("sleep", 0.1), ("off",), ("sleep", 0.1),
        ("on",), ("sleep", 0.1), ("off",)]

def test_shutdown_is_three_fast_chirps():
    assert len([edge for edge in edges_of("shutdown")
        if edge[0] == "on"]) == 3

def test_pipeline_is_one_longer_note():
    assert len([edge for edge in edges_of("pipeline")
        if edge[0] == "on"]) == 1

def test_the_line_is_always_left_off():
    for name in PATTERNS:
        assert edges_of(name)[-1] == ("off",), name

def test_the_line_is_left_off_even_when_the_sleep_fails():
    """A failing buzzer must not leave a note sounding, and must not raise
    into a caller that is shutting a host down"""

    edges = []
    def fail(seconds):
        raise OSError("the clock went away")

    buzzer = GpioBuzzer(thread=False, sleeper=fail)
    buzzer._set = lambda on: edges.append("on" if on else "off")
    with pytest.raises(OSError):
        buzzer.play("booted")
    assert edges[-1] == "off"

def test_the_pattern_length_is_reported():
    assert pattern_seconds("booted") == 0.3
    assert pattern_seconds("accepted") == 0.5

def test_an_unknown_pattern_is_refused():
    """A typo must be silent, and not a long note"""

    with pytest.raises(ValueError, match="unknown pattern"):
        GpioBuzzer(thread=False).play("klaxon")

# The devices -------------------------------------------------------------- #

def test_the_fake_buzzer_records_and_sounds_nothing():
    buzzer = FakeBuzzer()
    buzzer.open()
    buzzer.play("booted")
    buzzer.close()
    assert buzzer.played == ["booted"]
    assert buzzer.opened and buzzer.closed

def test_the_fake_buzzer_accepts_any_name():
    """It is a double, and refusing a name here would hide the refusal that
    matters, which is the real device's"""

    buzzer = FakeBuzzer()
    buzzer.play("whatever")
    assert buzzer.played == ["whatever"]

def test_none_is_chosen_by_name():
    assert choose_buzzer("none").device == "none"

def test_gpio_is_chosen_by_name():
    assert choose_buzzer("gpio").device == "gpio"

def test_an_unknown_buzzer_raises_rather_than_guessing():
    with pytest.raises(ValueError, match="unknown buzzer"):
        choose_buzzer("klaxon")

def test_auto_chooses_without_gpiozero(monkeypatch):
    import importlib.util
    monkeypatch.setattr(
        importlib.util, "find_spec", lambda name: None)
    assert choose_buzzer("auto").device == "none"

def test_the_default_line_is_the_board_s_buzzer():
    assert BUZZER_GPIO == 4

# The Actor ---------------------------------------------------------------- #

def make_actor(buzzer=None, **parameters):
    settings = {
        "bus": EmptyBus(), "log_directory": None, "telemetry": False,
        "timer": False, "buzzer": buzzer if buzzer else FakeBuzzer(),
        "hold_runner": lambda arguments, timeout=2.0: (0, ""),
    }
    settings.update(parameters)
    init_args = power_manager_args(
        f"power_signal_test_{next(_counter)}", "pmm",
        declared=PmmPowerManagerImpl.DECLARED_PROPERTIES, **settings)
    return aiko.compose_instance(PmmPowerManagerImpl, init_args)

def test_a_buzzer_makes_the_signal_property_real():
    actor = make_actor(buzzer=choose_buzzer("gpio"))
    assert "signal" in actor.properties()

def test_no_buzzer_means_no_signal_property():
    actor = make_actor(buzzer=FakeBuzzer())
    assert "signal" not in actor.properties()

def test_the_actor_sounds_a_pattern_and_counts_it():
    buzzer = choose_buzzer("gpio", thread=False, sleeper=lambda s: None)
    buzzer._set = lambda on: None
    actor = make_actor(buzzer=buzzer)
    actor.signal("booted")
    assert buzzer.played == ["booted"]
    assert actor.share["metrics"]["signals"] == 1

def test_the_actor_refuses_an_unknown_pattern_and_records_it():
    buzzer = choose_buzzer("gpio", thread=False, sleeper=lambda s: None)
    buzzer._set = lambda on: None
    actor = make_actor(buzzer=buzzer)
    actor.signal("klaxon")
    assert actor.share["metrics"]["signals"] == 0
    assert "unknown pattern" in actor.share["last_error"]

def test_a_signal_on_a_host_with_no_buzzer_is_a_no_op():
    actor = make_actor(buzzer=FakeBuzzer())
    actor.signal("booted")
    assert actor.share["metrics"]["signals"] == 0

# --------------------------------------------------------------------------- #
