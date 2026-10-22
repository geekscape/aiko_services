# Usage
# ~~~~~
# pytest [-s] unit/test_process_manager.py
#
# Unit tests for the ProcessManager definition file (process_manager.py):
# each entry starts with an "enabled" flag, "true" or "false", and then the
# command and its arguments.  The flag is required, so that a command which
# doesn't start is always reported.  An entry that can't be used is skipped,
# not fatal, so that one bad entry doesn't stop the other processes.
#
# The parsing functions are tested on their own, with a stub that records
# the processes created and the messages logged: no Actor is composed, no
# thread is started and no MQTT broker is used.

import json

import pytest

from aiko_services.main.process_manager import ProcessManagerImpl

class FakeLogger:
    """Records the messages, so that a test can show what was reported"""

    def __init__(self):
        self.errors, self.infos = [], []

    def error(self, message):
        self.errors.append(message)

    def info(self, message):
        self.infos.append(message)

    def warning(self, message):
        pass

class FakeProcessManager:
    """Just enough ProcessManager to parse a definition: the two parsing
    functions, a logger and a create() that records, instead of running,
    each process"""

    _parse_definition = ProcessManagerImpl._parse_definition
    _parse_definition_entry = ProcessManagerImpl._parse_definition_entry

    def __init__(self):
        self.created = []
        self.logger = FakeLogger()

    def create(self, command, arguments=None, uid=None):
        self.created.append((command, list(arguments or [])))

@pytest.fixture
def process_manager():
    return FakeProcessManager()

def write_definition(tmp_path, entries, name="definition.json"):
    pathname = tmp_path / name
    pathname.write_text(json.dumps(entries))
    return str(pathname)

# The "enabled" flag ------------------------------------------------------- #

def test_entry_enabled(process_manager):
    assert process_manager._parse_definition_entry("true aiko_registrar") ==  \
        (True, "aiko_registrar", [])

def test_entry_disabled(process_manager):
    assert process_manager._parse_definition_entry("false aiko_dashboard") ==  \
        (False, "aiko_dashboard", [])

def test_entry_arguments_are_separated(process_manager):
    enabled, command, arguments = process_manager._parse_definition_entry(
        "true mosquitto -c 0_mosquitto.conf")
    assert (enabled, command, arguments) ==  \
        (True, "mosquitto", ["-c", "0_mosquitto.conf"])

def test_entry_flag_ignores_letter_case(process_manager):
    assert process_manager._parse_definition_entry("TRUE date")[0] is True
    assert process_manager._parse_definition_entry("False date")[0] is False

# Entries that can't be used: reported, then skipped ----------------------- #

def test_entry_without_a_flag_is_skipped(process_manager):
    assert process_manager._parse_definition_entry("aiko_registrar") ==  \
        (False, None, None)
    assert "must start with" in process_manager.logger.errors[0]

def test_entry_with_a_flag_and_no_command_is_skipped(process_manager):
    assert process_manager._parse_definition_entry("true") == (False, None, None)
    assert "no command" in process_manager.logger.errors[0]

def test_entry_that_is_empty_is_skipped(process_manager):
    assert process_manager._parse_definition_entry("   ") == (False, None, None)
    assert "empty" in process_manager.logger.errors[0]

# The definition file ------------------------------------------------------ #

def test_definition_creates_only_the_enabled_processes(
    process_manager, tmp_path):

    pathname = write_definition(tmp_path, [
        "true  mosquitto -c 0_mosquitto.conf",
        "false aiko_dashboard",
        "true  aiko_registrar"
    ])
    process_manager._parse_definition(pathname)

    assert process_manager.created == [
        ("mosquitto", ["-c", "0_mosquitto.conf"]),
        ("aiko_registrar", [])
    ]
    assert process_manager.logger.infos == ["Disabled: aiko_dashboard"]

def test_definition_reports_a_disabled_entry_with_its_arguments(
    process_manager, tmp_path):
    """The arguments matter: "Disabled: sleep" doesn't say which one"""

    pathname = write_definition(tmp_path, ["false sleep 400"])
    process_manager._parse_definition(pathname)
    assert process_manager.logger.infos == ["Disabled: sleep 400"]

def test_definition_skips_a_bad_entry_and_keeps_going(
    process_manager, tmp_path):

    pathname = write_definition(tmp_path, [
        "aiko_registrar",                 # No flag: this one is skipped
        "true aiko_dashboard"
    ])
    process_manager._parse_definition(pathname)

    assert process_manager.created == [("aiko_dashboard", [])]
    assert len(process_manager.logger.errors) == 1

def test_definition_pathname_of_none_does_nothing(process_manager):
    process_manager._parse_definition(None)
    assert process_manager.created == []

def test_definition_must_be_a_json_file(process_manager, tmp_path):
    pathname = write_definition(tmp_path, ["true date"], name="definition.txt")
    with pytest.raises(SystemExit) as error:
        process_manager._parse_definition(pathname)
    assert '".json" file' in str(error.value)

def test_definition_that_is_malformed_is_fatal(process_manager, tmp_path):
    pathname = tmp_path / "definition.json"
    pathname.write_text('[ "true date", ')             # Truncated on purpose
    with pytest.raises(SystemExit) as error:
        process_manager._parse_definition(str(pathname))
    assert "Definition format" in str(error.value)

# The flag belongs to the definition file only ----------------------------- #

def test_create_still_runs_the_true_command(process_manager):
    """"aiko_process create true" must still run the "true" command:
    the flag is parsed in the definition file, never in create()"""

    process_manager.create("true", ["sleep", "300"])
    assert process_manager.created == [("true", ["sleep", "300"])]

# The FunctionGate posture: "aiko_process run --safe" ---------------------- #
#
# A ProcessManager starts and stops processes on its host, so what it
# accepts from the message bus is the point of these tests.  Safe mode is
# the default.  The allow lists are derived, and the response topic rule is
# a pure function, so most of this needs no Actor and no broker.

import itertools

import aiko_services as aiko
from aiko_services.main.process_manager import (
    FUNCTIONS, SAFE, SAFE_FUNCTIONS, PROTOCOL, coerce_response_topic,
)

_counter = itertools.count()
OWN = "aiko/host/1000/1/in"

def make_process_manager(safe=SAFE):
    """A composed ProcessManager whose posted messages are collected"""

    name = f"process_manager_test_{next(_counter)}"
    init_args = aiko.actor_args(name, protocol=PROTOCOL)
    init_args["safe"] = safe
    actor = aiko.compose_instance(ProcessManagerImpl, init_args)
    posted = []
    actor._post_message = lambda topic, name, args: posted.append((name, args))
    return actor, posted

def test_the_allow_list_is_the_interface_and_the_framework():
    assert FUNCTIONS == frozenset({
        "create", "destroy", "dump", "exit", "list", "set_log_level", "stop"})

def test_safe_mode_allows_only_what_cannot_start_or_stop_a_process():
    assert SAFE_FUNCTIONS == frozenset({"list", "set_log_level"})
    assert SAFE_FUNCTIONS < FUNCTIONS
    for function in ("create", "destroy", "exit", "stop"):
        assert function not in SAFE_FUNCTIONS

def test_safe_is_the_default():
    assert SAFE is True
    actor, _ = make_process_manager()
    assert actor.share["safe"] is True
    assert actor.functions == FUNCTIONS & SAFE_FUNCTIONS

def test_unsafe_accepts_every_declared_function():
    actor, _ = make_process_manager(safe=False)
    assert actor.share["safe"] is False
    assert actor.functions == FUNCTIONS

def test_safe_mode_allows_list_and_the_log_level():
    """The test that matters most: safe mode must not deny everything"""

    actor, posted = make_process_manager()
    actor._topic_in_handler(None, "t/in", f"(list {actor.topic_path}/in)")
    actor._topic_in_handler(None, "t/in", "(set_log_level DEBUG)")

    assert [name for name, _ in posted] == ["list", "set_log_level"]

@pytest.mark.parametrize("payload", [
    "(create date)", "(destroy 000001)", "(exit 0)", "(stop)", "(dump)"])
def test_safe_mode_denies_everything_that_acts(payload):
    actor, posted = make_process_manager()
    actor._topic_in_handler(None, "t/in", payload)

    assert posted == []
    assert actor.share["metrics"]["denied"] == 1

@pytest.mark.parametrize("payload", [
    "(_remove 000001)", "(_run)", "(_parse_definition x)", "(run)",
    "(add_message_handler a b)", "(set_registrar_handler h)"])
def test_a_private_or_framework_function_is_denied_in_either_mode(payload):
    """These reached Message.invoke() by name before the gate existed"""

    for safe in (True, False):
        actor, posted = make_process_manager(safe=safe)
        actor._topic_in_handler(None, "t/in", payload)
        assert posted == [], payload

def test_a_denial_is_observable():
    """ADR-023 decision 3: a client sees the policy and sees a denial"""

    actor, _ = make_process_manager()
    actor._topic_in_handler(None, "t/in", "(exit 0)")

    assert actor.share["metrics"]["denied"] == 1
    assert actor.share["last_error"] == "function exit"

# The response topic "list" publishes to ----------------------------------- #

def test_the_callers_own_in_topic_is_allowed():
    """The real caller asks for its own "in" topic, so this must work"""

    assert coerce_response_topic(OWN, "aiko/host/2000/1") == OWN

def test_another_suffix_a_service_owns_is_allowed():
    for suffix in ("in", "out", "control"):
        topic = f"aiko/host/1000/1/{suffix}"
        assert coerce_response_topic(topic, "aiko/host/2000/1") == topic

@pytest.mark.parametrize("topic", [
    "aiko/host/1000/1/+", "aiko/+/1000/1/in", "aiko/#/1000/1/in",
    "aiko/host/1000/1/#"])
def test_a_wildcard_is_never_a_response_topic(topic):
    assert coerce_response_topic(topic, "aiko/host/2000/1") is None

@pytest.mark.parametrize("topic", [
    "aiko/host/1000/1/log", "aiko/host/1000/1", "aiko/host/1000/1/in/extra",
    "", "in", "/in"])
def test_a_topic_that_is_not_a_service_topic_is_denied(topic):
    assert coerce_response_topic(topic, "aiko/host/2000/1") is None

def test_another_namespace_is_denied():
    """The boundary that matters: inside the namespace a caller publishes
    for itself, so the ProcessManager adds no reach.  Outside it, this is
    the only thing that stops a stranger using it to publish anywhere"""

    assert coerce_response_topic(
        "elsewhere/host/1000/1/in", "aiko/host/2000/1") is None

def test_a_topic_that_is_not_a_string_is_denied():
    for topic in (None, 7, ["aiko/host/1000/1/in"]):
        assert coerce_response_topic(topic, "aiko/host/2000/1") is None

def test_a_very_long_topic_is_denied():
    assert coerce_response_topic(
        "aiko/host/1000/" + "x" * 300 + "/in", "aiko/host/2000/1") is None

class _FakeMessage:
    """Collects what the Actor publishes, instead of reaching a broker"""

    def __init__(self):
        self.published = []

    def publish(self, topic, payload=None, **_):
        self.published.append((topic, payload))

def fake_message(monkeypatch):
    """Replace the process data the module publishes through.  list() uses
    only "aiko.message.publish", so a stub of that is enough"""

    import aiko_services.main.process_manager as module

    message = _FakeMessage()
    monkeypatch.setattr(
        module, "aiko", type("_Aiko", (), {"message": message})())
    return message

def test_list_denies_a_foreign_response_topic(monkeypatch):
    actor, _ = make_process_manager()
    message = fake_message(monkeypatch)

    actor.list("elsewhere/host/1000/1/in")

    assert message.published == []            # it replies to nothing at all
    assert actor.share["metrics"]["denied"] == 1

def test_list_publishes_to_a_topic_in_its_own_namespace(monkeypatch):
    actor, _ = make_process_manager()
    own = f"{actor.topic_path}/in"
    message = fake_message(monkeypatch)

    actor.list(own)

    assert message.published
    assert all(topic == own for topic, _ in message.published)
    assert message.published[0][1].startswith("(item_count")

# The process table in the shared state ------------------------------------ #

def test_the_table_holds_the_process_manager_itself():
    """Each process is one share entry, so a consumer follows the table
    live instead of polling "list" """

    actor, _ = make_process_manager()
    table = actor.share["process"]

    assert list(table) == ["000000"]          # self-aware
    assert table["000000"].endswith("aiko_process run")

def test_a_process_leaves_the_table_when_it_is_removed():
    """The leak this closes: a destroyed process stayed in the share for
    ever, because nothing called ECProducer.remove()"""

    actor, _ = make_process_manager()
    actor.processes["000001"] = {
        "command_line": ["date"], "process": _FakeProcess()}
    actor.ec_producer.update("process.000001", "4242 date")
    assert "000001" in actor.share["process"]

    actor._remove(["000001"])

    assert "000001" not in actor.share["process"]
    assert actor.share["metrics"]["running"] == 1

class _FakeProcess:
    pid = 4242

    def poll(self):
        return 0                              # it has exited

# --------------------------------------------------------------------------- #
