#!/usr/bin/env python3
#
# Aiko Services tests: the ProcessManager's Dashboard page
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# asciimatics has no screen double, so the Frame itself is exercised by
# hand.  Everything that decides anything lives in ProcessManagerPage,
# which is pure, and that is what these tests cover: the keys, the posture,
# the two tables and what the page says when a function would be denied.
#
# No broker, no Actor, no screen.
#
# To Do
# ~~~~~
# - None, yet !

import pytest

asciimatics = pytest.importorskip("asciimatics")

from aiko_services.ide.tui.dashboard.process_manager_plugin import (  # noqa: E402
    FUNCTIONS_DENIED_WHEN_SAFE, KEYS, ProcessManagerPage, plugins,
)

SAFE = {"safe": True, "metrics": {"denied": 3}}
UNSAFE = {"safe": False, "metrics": {"denied": 0}}
OLD = {"lifecycle": "ready"}             # an Actor from before --safe

@pytest.fixture
def page():
    return ProcessManagerPage()

# The plug-in registration ------------------------------------------------ #

def test_the_plugin_key_is_the_protocol_type():
    assert list(plugins) == ["process_manager"]

def test_the_default_plugin_module_registers_it():
    """It loads with no --plugin flag, beside the Registrar's page"""

    from aiko_services.ide.tui.dashboard.plugins import plugins as default

    assert sorted(default) == ["process_manager", "recorder", "registrar"]

# The keys ---------------------------------------------------------------- #

def test_each_key_asks_for_one_function(page):
    assert page.action(ord("c")) == ("create",)
    assert page.action(ord("d")) == ("destroy", False)     # SIGTERM
    assert page.action(ord("k")) == ("destroy", True)      # SIGKILL
    assert page.action(ord("u")) == ("dump",)
    assert page.action(ord("K")) == ("exit",)
    assert page.action(ord("L")) == ("log_level",)
    assert page.action(ord("H")) == ("help",)

def test_the_dashboards_own_keys_are_left_alone(page):
    """"D" is the Dashboard's back, and x and q are its own"""

    for reserved in "DxqXS":
        assert page.action(ord(reserved)) is None

def test_a_key_that_is_not_a_character_is_ignored(page):
    for key_code in (-1, -204, 0x110000):
        assert page.action(key_code) is None

# The posture --------------------------------------------------------------#

def test_the_posture_reads_as_a_boolean_either_way(page):
    """A share value is a bool from the Actor, and a string once a client
    has written it through the control topic"""

    assert page.read_safe({"safe": True}) is True
    assert page.read_safe({"safe": "true"}) is True
    assert page.read_safe({"safe": False}) is False
    assert page.read_safe({"safe": "false"}) is False

def test_an_actor_that_does_not_report_a_posture(page):
    assert page.read_safe(OLD) is None

@pytest.mark.parametrize("function", FUNCTIONS_DENIED_WHEN_SAFE)
def test_safe_mode_stops_the_page_sending_a_denied_function(page, function):
    may_send, why = page.may_send(SAFE, function)

    assert may_send is False
    assert "--unsafe" in why and function in why

@pytest.mark.parametrize("function", FUNCTIONS_DENIED_WHEN_SAFE)
def test_unsafe_mode_lets_each_one_through(page, function):
    assert page.may_send(UNSAFE, function) == (True, "")

def test_dump_is_denied_in_safe_mode_too(page):
    """SAFE_FUNCTIONS is {list, set_log_level}, and dump is not in it.  It
    only writes to the Actor's own log, so whether it belongs there is a
    policy question -- but the page must report the policy as it is"""

    assert page.may_send(SAFE, "dump")[0] is False
    assert page.may_send(UNSAFE, "dump")[0] is True

def test_log_level_and_help_are_not_functions_of_the_actor(page):
    for kind in ("log_level", "help"):
        assert page.may_send(SAFE, kind) == (True, "")

def test_an_unreported_posture_is_treated_as_the_careful_one(page):
    may_send, why = page.may_send(OLD, "create")

    assert may_send is False
    assert "does not report a posture" in why

# The tables -------------------------------------------------------------- #

def test_the_process_table_is_one_row_for_each_process(page):
    cache = {"process": {
        "000001": "4301 sleep 60", "000000": "4242 aiko_process run"}}

    assert page.process_rows(cache) == [
        ("000000", "4242", "aiko_process run"),
        ("000001", "4301", "sleep 60")]

def test_no_process_table_yet(page):
    assert page.process_rows({}) == []
    assert page.process_rows({"process": "not a dictionary"}) == []

def test_the_state_table_names_what_the_actor_is(page):
    cache = {
        "safe": True, "watchdog": False, "definition_pathname": "x.json",
        "lifecycle": "ready", "log_level": "INFO", "last_error": "-",
        "source_file": "v0= process_manager.py",
        "metrics": {"created": 1, "denied": 0, "running": 1},
    }
    rows = page.state_rows(cache)
    names = [name for name, _ in rows]

    assert names == [
        "safe", "watchdog", "definition_pathname", "lifecycle", "log_level",
        "last_error", "metrics.created", "metrics.denied", "metrics.running"]
    assert "source_file" not in names             # as the Dashboard omits it

def test_the_state_table_leaves_out_what_is_absent(page):
    assert page.state_rows({"safe": True}) == [("safe", "True")]

def test_the_title_reports_the_posture_and_the_denials(page):
    assert page.title(SAFE) == "posture: safe   denied: 3"
    assert page.title(UNSAFE) == "posture: UNSAFE   denied: 0"
    assert page.title(OLD) == "posture: not reported"

def test_the_help_names_every_key_the_page_takes(page):
    text = page.help_text()

    for key in KEYS:
        assert key in text
    assert "--unsafe" in text

# --------------------------------------------------------------------------- #
