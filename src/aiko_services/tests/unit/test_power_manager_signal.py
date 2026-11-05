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
    # The runner records, as hold.py's tests do, so the edges asserted
    # here are the exact commands the pin utility is given
    def runner(arguments):
        edges.append(("on",) if arguments[-1] == "dh" else ("off",))
        return 0, ""

    buzzer = GpioBuzzer(thread=False, runner=runner,
        sleeper=lambda seconds: edges.append(("sleep", seconds)))
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

    buzzer = GpioBuzzer(thread=False, sleeper=fail,
        runner=lambda arguments: (
            edges.append("on" if arguments[-1] == "dh" else "off"), (0, ""))[1])
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
    buzzer = choose_buzzer("gpio", thread=False, sleeper=lambda s: None,
        runner=lambda arguments: (0, ""))
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

# Nothing is claimed ------------------------------------------------------- #
#
# The first attempt at this claimed the line for each pattern and gave it
# back, on the belief that closing a device releases the line.  It does
# not.  gpiozero re-claims the line as an input with no pull and leaves the
# claim in place, which its own source says in as many words, so the claim
# is held for the life of the process and no other writer can have the pad.
# Measured on 2026-11-05: the command line was refused "GPIO busy" by an
# Actor that had claimed the line once at start-up.
#
# So the pad is driven through the pin utility and nothing is claimed, as
# hold.py does it.  These tests assert the commands, because the commands
# are now the whole of the mechanism.

def recording_buzzer(**parameters):
    """A buzzer whose pin utility records, with no subprocess"""

    calls = []

    def runner(arguments):
        calls.append(list(arguments))
        return 0, ""

    settings = {"thread": False, "runner": runner,
        "sleeper": lambda seconds: None}
    settings.update(parameters)
    return GpioBuzzer(**settings), calls

def test_opening_leaves_the_line_low_and_claims_nothing():
    buzzer, calls = recording_buzzer()
    buzzer.open()
    assert calls == [["set", "4", "op", "dl"]]

def test_a_pattern_is_the_pin_utility_and_nothing_else():
    """The same commands the start-up unit and the shutdown hook render,
    so this pad has one mechanism across all three"""

    buzzer, calls = recording_buzzer()
    buzzer.play("booted")
    assert calls == [
        ["set", "4", "op", "dh"],
        ["set", "4", "op", "dl"],
        ["set", "4", "op", "dh"],
        ["set", "4", "op", "dl"]]

def test_a_pattern_leaves_the_line_low():
    buzzer, calls = recording_buzzer()
    buzzer.play("pipeline")
    assert calls[-1] == ["set", "4", "op", "dl"]

def test_the_line_is_named_in_every_command():
    buzzer, calls = recording_buzzer(gpio=23)
    buzzer.play("booted")
    assert all(call[1] == "23" for call in calls), calls

def test_a_failing_pattern_still_leaves_the_line_low():
    """A buzzer that failed must not keep the pad high, or the host sounds
    broken until something else drives it"""

    def fail(seconds):
        raise OSError("the clock went away")

    buzzer, calls = recording_buzzer(sleeper=fail)
    with pytest.raises(OSError):
        buzzer.play("booted")
    assert calls[-1] == ["set", "4", "op", "dl"]

def test_a_utility_that_refuses_is_an_error_and_not_a_silence():
    """A typo in the arguments, or a pad that cannot be driven, must not
    look like a sound that happened"""

    buzzer = GpioBuzzer(thread=False, sleeper=lambda s: None,
        runner=lambda arguments: (1, "unknown pin"))
    with pytest.raises(OSError, match="unknown pin"):
        buzzer.play("booted")

def test_closing_leaves_the_line_low_and_never_raises():
    buzzer, calls = recording_buzzer()
    buzzer.open()
    buzzer.close()
    assert calls[-1] == ["set", "4", "op", "dl"]
    assert buzzer.opened is False

def test_closing_a_buzzer_whose_utility_is_gone_is_not_an_error():
    """A close runs while a host is stopping, so it swallows what it
    cannot do anything about"""

    def gone(arguments):
        raise OSError("no pin utility")

    buzzer = GpioBuzzer(thread=False, runner=gone)
    buzzer.close()
    assert buzzer.opened is False

def test_auto_is_the_fake_where_there_is_no_pin_utility(monkeypatch):
    import aiko_services.actors.power_manager.signal as signal

    monkeypatch.setattr(signal, "hold_tool", lambda *a, **k: None)
    assert signal.choose_buzzer("auto").device == "none"

def test_auto_is_the_real_one_where_the_utility_is_there(monkeypatch):
    import aiko_services.actors.power_manager.signal as signal

    monkeypatch.setattr(signal, "hold_tool", lambda *a, **k: "/usr/bin/pinctrl")
    assert signal.choose_buzzer("auto").device == "gpio"
