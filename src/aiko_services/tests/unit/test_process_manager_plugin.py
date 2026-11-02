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

    assert sorted(default) ==  \
        ["category", "hyperspace",
        "process_manager", "recorder", "registrar"]

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
# The definition, held in a Category --------------------------------------- #
#
# The page matches a definition Entry to a running process by its command
# line, because the ProcessManager does not say which Entry a process came
# from.  These hold that, and what each row says about an Entry

from aiko_services.main.category_view import (                   # noqa: E402
    CategoryTree, entry_of,
)
from aiko_services.main.process_definition import process_url    # noqa: E402

WILDCARD = "*"

def process_entry(name, enabled=True, command=None, cwd=None):
    command = command if command else name
    return entry_of(name, [[WILDCARD, name, WILDCARD, WILDCARD, WILDCARD, []],
        "aiko01", process_url(enabled, command, cwd)])

def category_entry(name):
    from aiko_services.main import CATEGORY_PROTOCOL

    return entry_of(name,
        [[WILDCARD, name, CATEGORY_PROTOCOL, WILDCARD, WILDCARD, []],
            "None", "None"])

def tree_of(*entries):
    tree = CategoryTree("definition")
    tree.merge("", list(entries))
    return tree

LIVE = {"process": {"000000": "4242 aiko_registrar run",
    "000001": "4301 sleep 60"}}

def test_each_definition_key_asks_for_one_thing(page):
    assert page.action(ord("n")) == ("definition",)
    assert page.action(ord("s")) == ("start",)
    assert page.action(ord("t")) == ("stop",)
    assert page.action(ord("e")) == ("enabled",)
    assert page.action(ord("J")) == ("json",)

def test_starting_and_stopping_are_creating_and_destroying(page):
    """So that safe mode denies them for the same reason"""

    assert page.function_of("start") == "create"
    assert page.function_of("stop") == "destroy"
    assert page.may_send(SAFE, page.function_of("start"))[0] is False
    assert page.may_send(SAFE, page.function_of("stop"))[0] is False
    assert page.may_send(UNSAFE, page.function_of("start"))[0] is True

def test_reading_a_definition_is_never_denied(page):
    """It asks a HyperSpace, not this Actor"""

    for kind in ("definition", "json", "enabled"):
        assert page.function_of(kind) == kind
        assert page.may_send(SAFE, kind)[0] is True

def test_what_is_running_is_read_by_its_command_line(page):
    assert page.live_processes(LIVE) == {
        "aiko_registrar run": ("000000", "4242"),
        "sleep 60": ("000001", "4301")}

def test_nothing_is_running(page):
    assert page.live_processes({}) == {}
    assert page.live_processes({"process": "nonsense"}) == {}

def test_two_entries_of_one_command_line_are_one_process(page):
    """The ProcessManager cannot tell them apart either, so the first uid
    is the one a person acts on"""

    cache = {"process": {"1": "11 sleep 60", "0": "10 sleep 60"}}

    assert page.live_processes(cache) == {"sleep 60": ("0", "10")}

def test_a_definition_entry_that_is_running(page):
    tree = tree_of(process_entry("registrar", command="aiko_registrar run"))

    assert page.definition_rows(tree.rows(), LIVE) ==  \
        [(("registrar", "yes", "pid 4242", "aiko_registrar run"),
            "registrar")]

def test_a_definition_entry_that_is_enabled_and_not_running(page):
    tree = tree_of(process_entry("recorder", command="aiko_recorder"))

    assert page.definition_rows(tree.rows(), LIVE) ==  \
        [(("recorder", "yes", "stopped", "aiko_recorder"), "recorder")]

def test_a_definition_entry_that_is_disabled(page):
    tree = tree_of(process_entry("recorder", enabled=False))

    columns, _ = page.definition_rows(tree.rows(), LIVE)[0]
    assert columns[1:3] == ("no", "disabled")

def test_a_definition_entry_that_says_nothing_usable(page):
    """It says why, where the command line would be"""

    tree = tree_of(entry_of("broken",
        [[WILDCARD, "broken", WILDCARD, WILDCARD, WILDCARD, []],
            "None", "process:{oops"]))

    columns, _ = page.definition_rows(tree.rows(), LIVE)[0]
    assert columns[2] == "-"
    assert "not JSON" in columns[3]

def test_an_entry_that_is_not_a_process_at_all(page):
    tree = tree_of(entry_of("other",
        [[WILDCARD, "other", WILDCARD, WILDCARD, WILDCARD, []],
            "None", "None"]))

    columns, _ = page.definition_rows(tree.rows(), LIVE)[0]
    assert columns[3] == "not a process"

def test_a_category_of_a_definition_is_a_row_of_its_own(page):
    tree = tree_of(category_entry("hosts"))

    assert page.definition_rows(tree.rows(), LIVE) ==  \
        [(("hosts/", "", "", ""), "hosts")]

def test_a_definition_below_a_category_is_indented(page):
    tree = tree_of(category_entry("hosts"))
    tree.node("hosts").expanded = True
    tree.merge("hosts", [process_entry("registrar")])
    rows = page.definition_rows(tree.rows(), LIVE)

    assert [columns[0] for columns, _ in rows] == ["hosts/", "  registrar"]
    assert [path for _, path in rows] == ["hosts", "hosts/registrar"]

def test_no_definition_at_all(page):
    assert page.definition_rows([], LIVE) == []
    assert page.definition_processes([]) == []

def test_the_definition_json_holds_each_process_in_the_order_shown(page):
    import json

    tree = tree_of(process_entry("b", command="sleep 60"),
        process_entry("a", enabled=False, command="aiko_recorder",
            cwd="/home/claude"))
    text = page.definition_text(tree.rows())

    assert json.loads(text) == [
        {"enabled": True, "command": "sleep 60"},
        {"enabled": False, "command": "aiko_recorder",
            "cwd": "/home/claude"}]

def test_the_definition_json_of_a_category_that_holds_no_process(page):
    assert "no process Entry" in page.definition_text([])

def test_only_a_hyperspace_or_a_category_can_hold_a_definition(page):
    services = [
        ["aiko/nomad/1/1", "hs_a", "x/protocol/hyperspace:0", "mqtt", "o", []],
        ["aiko/nomad/2/1", "cat_a", "x/protocol/category:0", "mqtt", "o", []],
        ["aiko/nomad/3/1", "nomad", "x/protocol/registrar:2", "mqtt", "o", []],
    ]
    options = page.hyperspace_options(services)

    assert [value for _, value in options] ==  \
        ["aiko/nomad/2/1", "aiko/nomad/1/1"]       # by label, so cat_a first
    assert "hs_a" in dict((v, k) for k, v in options)["aiko/nomad/1/1"]

def test_no_service_can_hold_a_definition(page):
    assert page.hyperspace_options([]) == []

def test_the_help_names_every_definition_key(page):
    text = page.help_text()

    for phrase in ("n  name the HyperSpace", "s  start", "t  stop",
            "e  enable or disable", "J  the definition as the JSON",
            "process:", "lifecycle manager URL"):
        assert phrase in text

# --------------------------------------------------------------------------- #
