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
    # maker returns None, so no line is taken and _set() records instead
    buzzer = GpioBuzzer(thread=False, maker=lambda: None,
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

def test_booted_is_short_then_long():
    """The lead found 300 ms of two chirps easy to miss, after a press of
    the button that can last ten seconds.  The long note is the part that
    carries, so the sound an operator waits for ends on one"""

    assert edges_of("booted") == [
        ("on",), ("sleep", 0.15), ("off",), ("sleep", 0.1),
        ("on",), ("sleep", 0.5), ("off",)]

def test_shutdown_is_three_fast_chirps():
    assert len([edge for edge in edges_of("shutdown")
        if edge[0] == "on"]) == 3

def test_pipeline_is_quick_taps_and_then_a_note():
    """The cheerful one.  A buzzer has one pitch, so the mood is in the
    rhythm: three short taps, and a longer note that resolves them"""

    notes = [seconds for name, seconds in
        [(edge[0], edge[1] if len(edge) > 1 else 0) for edge in
            edges_of("pipeline")] if name == "sleep"][::2]
    assert len(notes) == 4
    assert all(note < 0.1 for note in notes[:3])
    assert notes[3] > 2 * max(notes[:3])

def test_every_pattern_sounds_different_from_every_other():
    """Four sounds that mean four things.  Two that share a shape are worse
    than one of them not existing, because an operator acts on a guess"""

    shapes = {name: tuple(PATTERNS[name]) for name in PATTERNS}
    assert len(set(shapes.values())) == len(shapes)
    lengths = {name: pattern_seconds(name) for name in PATTERNS}
    assert len(set(lengths.values())) == len(lengths), lengths

def test_a_sound_an_operator_waits_for_ends_on_its_longest_note():
    """"booted" and "accepted" both answer a person who is holding the
    button.  Both must end on the note that carries"""

    for name in ("booted", "accepted"):
        notes = tuple(PATTERNS[name][::2])
        assert notes[-1] == max(notes), name

def test_the_line_is_always_left_off():
    for name in PATTERNS:
        assert edges_of(name)[-1] == ("off",), name

def test_the_line_is_left_off_even_when_the_sleep_fails():
    """A failing buzzer must not leave a note sounding, and must not raise
    into a caller that is shutting a host down"""

    edges = []
    def fail(seconds):
        raise OSError("the clock went away")

    buzzer = GpioBuzzer(thread=False, maker=lambda: None, sleeper=fail)
    buzzer._set = lambda on: edges.append("on" if on else "off")
    with pytest.raises(OSError):
        buzzer.play("booted")
    assert edges[-1] == "off"

def test_the_pattern_length_is_reported():
    assert pattern_seconds("booted") == 0.75
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
    buzzer = choose_buzzer("gpio", thread=False, maker=lambda: None,
        sleeper=lambda s: None)
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

# The line is held for a pattern, and not for a run ------------------------ #
#
# Recorded as 6.22 and fixed here.  open() used to claim the line and hold
# it for as long as the Actor ran, while the start-up unit and the shutdown
# hook write the same pad with the platform's pin utility.  A shutdown stops
# those and this Actor in no defined order, so the two could overlap and a
# pattern that was sounding would be cut short.

def made_buzzer(**parameters):
    """A buzzer whose line is a recorder, so that taking it and giving it
    back are both visible without any hardware"""

    taken = []

    class FakeLine:
        def __init__(self):
            self.value = 0
            self.closed = False
        def close(self):
            self.closed = True

    def maker():
        line = FakeLine()
        taken.append(line)
        return line

    return GpioBuzzer(thread=False, maker=maker,
        sleeper=lambda seconds: None, **parameters), taken

def test_opening_takes_the_line_and_gives_it_straight_back():
    """It proves the line, so a platform with no library still reports no
    "signal" property, and it holds nothing"""

    buzzer, taken = made_buzzer()
    buzzer.open()
    assert len(taken) == 1 and taken[0].closed is True
    assert buzzer._device is None

def test_a_pattern_takes_the_line_and_gives_it_back():
    buzzer, taken = made_buzzer()
    buzzer.open()
    buzzer.play("booted")
    assert len(taken) == 2                       # The open, then the pattern
    assert taken[1].closed is True
    assert buzzer._device is None

def test_nothing_is_held_between_patterns():
    """The whole point.  Between sounds the pad is free for the start-up
    unit and the shutdown hook to write"""

    buzzer, taken = made_buzzer()
    buzzer.open()
    for name in ("booted", "pipeline", "shutdown"):
        buzzer.play(name)
        assert buzzer._device is None, name
    assert all(line.closed for line in taken)

def test_the_line_is_left_low_when_it_is_given_back():
    buzzer, taken = made_buzzer()
    buzzer.play("booted")
    assert taken[-1].value == 0

def test_a_failing_pattern_still_gives_the_line_back():
    """A buzzer that fails must not keep the pad, or the shutdown hook
    cannot sound the host going down"""

    def fail(seconds):
        raise OSError("the clock went away")

    buzzer, taken = made_buzzer()
    buzzer._sleep = fail
    with pytest.raises(OSError):
        buzzer.play("booted")
    assert buzzer._device is None
    assert taken[-1].closed is True

def test_closing_gives_back_a_line_held_during_a_pattern():
    buzzer, taken = made_buzzer()
    buzzer._device = taken_line = buzzer._make()
    buzzer.close()
    assert taken_line.closed is True
    assert buzzer._device is None

def test_closing_with_nothing_held_is_not_an_error():
    buzzer, _ = made_buzzer()
    buzzer.open()
    buzzer.close()
    assert buzzer._device is None
