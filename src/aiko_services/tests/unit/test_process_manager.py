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
# An entry is either that string, or an object, which carries a working
# directory and keeps an argument that contains a space.  Both forms are
# tested here, as is the working directory reaching Popen, and the command
# resolution that prefers an executable on PATH to a module of the same
# name.
#
# The parsing functions are tested on their own, with a stub that records
# the processes created and the messages logged: no Actor is composed, no
# thread is started and no MQTT broker is used.

import importlib
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
    _parse_definition_object = ProcessManagerImpl._parse_definition_object
    _resolve_command = ProcessManagerImpl._resolve_command

    def __init__(self):
        self.created = []
        self.logger = FakeLogger()

    def create(self, command, arguments=None, uid=None, cwd=None):
        self.created.append((command, list(arguments or []), cwd))

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
        (True, "aiko_registrar", [], None)

def test_entry_disabled(process_manager):
    assert process_manager._parse_definition_entry("false aiko_dashboard") ==  \
        (False, "aiko_dashboard", [], None)

def test_entry_arguments_are_separated(process_manager):
    enabled, command, arguments, cwd =  \
        process_manager._parse_definition_entry(
            "true mosquitto -c 0_mosquitto.conf")
    assert (enabled, command, arguments, cwd) ==  \
        (True, "mosquitto", ["-c", "0_mosquitto.conf"], None)

def test_entry_flag_ignores_letter_case(process_manager):
    assert process_manager._parse_definition_entry("TRUE date")[0] is True
    assert process_manager._parse_definition_entry("False date")[0] is False

# Entries that can't be used: reported, then skipped ----------------------- #

def test_entry_without_a_flag_is_skipped(process_manager):
    assert process_manager._parse_definition_entry("aiko_registrar") ==  \
        (False, None, None, None)
    assert "must start with" in process_manager.logger.errors[0]

def test_entry_with_a_flag_and_no_command_is_skipped(process_manager):
    assert process_manager._parse_definition_entry("true") ==  \
        (False, None, None, None)
    assert "no command" in process_manager.logger.errors[0]

def test_entry_that_is_empty_is_skipped(process_manager):
    assert process_manager._parse_definition_entry("   ") ==  \
        (False, None, None, None)
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
        ("mosquitto", ["-c", "0_mosquitto.conf"], None),
        ("aiko_registrar", [], None)
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

    assert process_manager.created == [("aiko_dashboard", [], None)]
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

# The object form of a definition entry ------------------------------------ #
#
# A string entry splits on whitespace, so it cannot express an argument
# that contains a space, and it has nowhere to put a working directory.
# The object form answers both.  An entry that can't be used is still
# reported and skipped, never fatal

def test_object_entry_carries_a_working_directory(process_manager):
    assert process_manager._parse_definition_entry({
        "enabled": True, "command": "aiko_hyperspace run",
        "cwd": "/home/claude/hyperspace"}) ==  \
        (True, "aiko_hyperspace", ["run"], "/home/claude/hyperspace")

def test_object_entry_without_a_working_directory(process_manager):
    assert process_manager._parse_definition_entry(
        {"enabled": True, "command": "aiko_registrar"}) ==  \
        (True, "aiko_registrar", [], None)

def test_object_entry_command_as_a_list(process_manager):
    """A list needs no quoting rules at all"""

    assert process_manager._parse_definition_entry(
        {"enabled": True, "command": ["aiko_chat", "run", "--llm"]}) ==  \
        (True, "aiko_chat", ["run", "--llm"], None)

def test_object_entry_keeps_an_argument_that_contains_a_space(
    process_manager):
    """What the string form cannot do"""

    _, command, arguments, _ = process_manager._parse_definition_entry(
        {"enabled": True, "command": '/bin/sh -c "sleep 5; echo done"'})

    assert (command, arguments) == ("/bin/sh", ["-c", "sleep 5; echo done"])

def test_object_entry_disabled(process_manager):
    assert process_manager._parse_definition_entry(
        {"enabled": False, "command": "aiko_recorder"}) ==  \
        (False, "aiko_recorder", [], None)

def test_object_entry_with_an_unknown_key_is_skipped(process_manager):
    """A key that is nearly right is the one worth reporting"""

    assert process_manager._parse_definition_entry({
        "enabled": True, "command": "date",
        "working_directory": "/tmp"}) == (False, None, None, None)
    assert "unknown key working_directory" in process_manager.logger.errors[0]

def test_object_entry_without_the_flag_is_skipped(process_manager):
    assert process_manager._parse_definition_entry({"command": "date"}) ==  \
        (False, None, None, None)
    assert 'must have "enabled"' in process_manager.logger.errors[0]

def test_object_entry_whose_flag_is_not_a_boolean_is_skipped(process_manager):
    """JSON "true" is a string, which is not the flag"""

    assert process_manager._parse_definition_entry(
        {"enabled": "true", "command": "date"}) == (False, None, None, None)
    assert 'must have "enabled"' in process_manager.logger.errors[0]

def test_object_entry_without_a_command_is_skipped(process_manager):
    assert process_manager._parse_definition_entry({"enabled": True}) ==  \
        (False, None, None, None)
    assert "must be a string" in process_manager.logger.errors[0]

def test_object_entry_whose_command_is_empty_is_skipped(process_manager):
    assert process_manager._parse_definition_entry(
        {"enabled": True, "command": "   "}) == (False, None, None, None)
    assert "no command" in process_manager.logger.errors[0]

def test_object_entry_whose_command_list_holds_a_number_is_skipped(
    process_manager):

    assert process_manager._parse_definition_entry(
        {"enabled": True, "command": ["sleep", 5]}) == (False, None, None, None)
    assert "list of strings" in process_manager.logger.errors[0]

def test_object_entry_with_an_unbalanced_quote_is_skipped(process_manager):
    assert process_manager._parse_definition_entry(
        {"enabled": True, "command": '/bin/sh -c "sleep 5'}) ==  \
        (False, None, None, None)
    assert "Definition entry command" in process_manager.logger.errors[0]

def test_object_entry_whose_working_directory_is_not_a_string_is_skipped(
    process_manager):

    assert process_manager._parse_definition_entry(
        {"enabled": True, "command": "date", "cwd": 0}) ==  \
        (False, None, None, None)
    assert '"cwd" must be a string' in process_manager.logger.errors[0]

# The definition file holds either form ------------------------------------ #

def test_definition_mixes_both_entry_forms(process_manager, tmp_path):
    pathname = write_definition(tmp_path, [
        "true  aiko_registrar",
        {"enabled": True, "command": "aiko_hyperspace run",
         "cwd": "/home/claude/hyperspace"},
        {"enabled": False, "command": "aiko_recorder"}
    ])
    process_manager._parse_definition(pathname)

    assert process_manager.created == [
        ("aiko_registrar", [], None),
        ("aiko_hyperspace", ["run"], "/home/claude/hyperspace")
    ]
    assert process_manager.logger.infos == ["Disabled: aiko_recorder"]

def test_definition_skips_a_bad_object_entry_and_keeps_going(
    process_manager, tmp_path):

    pathname = write_definition(tmp_path, [
        {"enabled": True, "cmd": "date"},              # This one is skipped
        {"enabled": True, "command": "aiko_dashboard"}
    ])
    process_manager._parse_definition(pathname)

    assert process_manager.created == [("aiko_dashboard", [], None)]
    assert len(process_manager.logger.errors) == 1

# Which pathname a command resolves to ------------------------------------- #
#
# A console script and an importable package often share a name, and
# resolving the module gave a "__init__.py" that is not executable.  So an
# executable on PATH wins, and a name that is only importable still
# resolves to the module

@pytest.fixture
def module_script(tmp_path, monkeypatch):
    """An importable module whose own file is executable, which is what
    the module fallback is for"""

    pathname = tmp_path / "aiko_module_0.py"
    pathname.write_text("#!/usr/bin/env python3\n")
    pathname.chmod(0o755)
    monkeypatch.syspath_prepend(str(tmp_path))
    importlib.invalidate_caches()
    return pathname

def test_a_command_on_the_path_resolves_to_itself(process_manager):
    assert process_manager._resolve_command("sh") == "sh"

def test_a_script_pathname_resolves_to_itself(process_manager):
    for pathname in ("/x/y/chat_start.sh", "./hyperspace.py"):
        assert process_manager._resolve_command(pathname) == pathname

def test_an_executable_module_resolves_to_the_module(
    process_manager, module_script):

    assert process_manager._resolve_command("aiko_module_0") ==  \
        str(module_script)
    assert "Module path resolved to" in process_manager.logger.infos[0]

def test_an_executable_on_the_path_wins_over_a_module(
    process_manager, module_script, tmp_path, monkeypatch):
    """The ordering that the "aiko_chat" case needs: a console script and
    a package of the same name"""

    directory = tmp_path / "bin"
    directory.mkdir()
    executable = directory / "aiko_module_0"
    executable.write_text("#!/bin/sh\nexit 0\n")
    executable.chmod(0o755)
    monkeypatch.setenv("PATH", str(directory))

    assert process_manager._resolve_command("aiko_module_0") ==  \
        "aiko_module_0"

@pytest.mark.parametrize("mode", [0o644, 0o755],
    ids=["__init__.py is not executable", "__init__.py is executable"])
def test_a_package_is_left_alone(process_manager, tmp_path, monkeypatch, mode):
    """The "aiko_chat" failure: the package resolved to its "__init__.py",
    and the process ran a file nobody asked for.  Left alone, Popen
    reports the command instead.

    Both file modes, because a library file carries the execute bit on
    some installations.  The hosted Python of the CI runner is one, for
    Python 3.11 and later, and the file mode decided this at first"""

    package = tmp_path / "aiko_package_0"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "__init__.py").chmod(mode)
    monkeypatch.syspath_prepend(str(tmp_path))
    importlib.invalidate_caches()

    assert process_manager._resolve_command("aiko_package_0") ==  \
        "aiko_package_0"
    assert process_manager.logger.infos == []

def test_a_module_that_is_not_executable_is_left_alone(
    process_manager, tmp_path, monkeypatch):
    """Popen then reports the command, instead of a permission error"""

    pathname = tmp_path / "aiko_module_1.py"
    pathname.write_text("")
    pathname.chmod(0o644)
    monkeypatch.syspath_prepend(str(tmp_path))
    importlib.invalidate_caches()

    assert process_manager._resolve_command("aiko_module_1") ==  \
        "aiko_module_1"

def test_a_command_that_is_neither_resolves_to_itself(process_manager):
    assert process_manager._resolve_command("no_such_command_0") ==  \
        "no_such_command_0"

def test_a_dotted_name_that_cannot_be_imported_does_not_raise(
    process_manager):
    """find_spec() raises for a parent that is not a package"""

    assert process_manager._resolve_command("no_such_package_0.sub") ==  \
        "no_such_package_0.sub"

# The working directory reaching Popen ------------------------------------- #
#
# create() is the real one here, with Popen recorded instead of run, because
# the working directory arriving at Popen is the whole point of it

class FakePopen:
    pid = 4242

    def poll(self):
        return None

class FakeECProducer:
    def __init__(self):
        self.updates = []

    def update(self, name, value):
        self.updates.append((name, value))

class FakeLauncher:
    """The real create(), with Popen recorded"""

    create = ProcessManagerImpl.create
    _get_process_info = ProcessManagerImpl._get_process_info
    _get_uid_str = ProcessManagerImpl._get_uid_str
    _process_share = ProcessManagerImpl._process_share
    _resolve_command = ProcessManagerImpl._resolve_command

    def __init__(self):
        self.calls = []
        self.logger = FakeLogger()
        self.processes = {}
        self.uid_default = 1
        self.ec_producer = FakeECProducer()
        self.share = {"metrics": {"created": 0}}

@pytest.fixture
def launcher(monkeypatch):
    launcher = FakeLauncher()

    def fake_popen(command_line, **kwargs):
        launcher.calls.append((list(command_line), kwargs))
        return FakePopen()

    monkeypatch.setattr(
        "aiko_services.main.process_manager.Popen", fake_popen)
    return launcher

def test_create_passes_the_working_directory_to_popen(launcher, tmp_path):
    launcher.create("sh", ["-c", "exit 0"], cwd=str(tmp_path))

    command_line, kwargs = launcher.calls[0]
    assert command_line == ["sh", "-c", "exit 0"]
    assert kwargs["cwd"] == str(tmp_path)

def test_create_without_a_working_directory_inherits_it(launcher):
    """Popen with cwd of None is the behaviour every process had before"""

    launcher.create("sh")

    _, kwargs = launcher.calls[0]
    assert kwargs["cwd"] is None

def test_create_records_the_working_directory(launcher, tmp_path):
    launcher.create("sh", uid="uid:0", cwd=str(tmp_path))

    assert launcher.processes["uid:0"]["cwd"] == str(tmp_path)

def test_dump_shows_the_working_directory(launcher, tmp_path):
    launcher.create("sh", uid="uid:0", cwd=str(tmp_path))

    assert launcher._get_uid_str("uid:0") ==  \
        f"<uid:0> PID: 4242 sh cwd: {tmp_path}"

def test_dump_of_a_process_without_one_says_nothing_about_it(launcher):
    launcher.create("sh", uid="uid:0")

    assert launcher._get_uid_str("uid:0") == "<uid:0> PID: 4242 sh"

def test_create_reports_a_working_directory_that_is_not_one(
    launcher, tmp_path):
    """Popen names the command, not the directory, so create() checks"""

    absent = str(tmp_path / "absent")
    launcher.create("sh", cwd=absent)

    assert launcher.calls == []
    assert launcher.processes == {}
    assert f"not a directory, process not started: {absent}"  \
        in launcher.logger.errors[0]

def test_create_reports_a_working_directory_that_is_a_file(
    launcher, tmp_path):

    pathname = tmp_path / "definition.json"
    pathname.write_text("[]")
    launcher.create("sh", cwd=str(pathname))

    assert launcher.calls == []
    assert "not a directory" in launcher.logger.errors[0]

def test_a_rejected_working_directory_leaves_no_gap_in_the_uids(
    launcher, tmp_path):
    """The uid is allocated after the directory is checked, so a process
    that does not start does not consume a number"""

    launcher.create("sh", cwd=str(tmp_path / "absent"))
    launcher.create("sh")

    assert list(launcher.processes) == ["000001"]

def test_a_real_process_starts_in_the_working_directory(tmp_path):
    """The claim, end to end, with a real Popen: the file the process
    creates lands in the directory it was given, which needs no comparison
    of pathnames that a symbolic link would spoil"""

    launcher = FakeLauncher()                   # Popen is not recorded here
    launcher.create("/bin/sh", ["-c", "touch started_here"], uid="uid:0",
        cwd=str(tmp_path))
    launcher.processes["uid:0"]["process"].wait(timeout=10)

    assert (tmp_path / "started_here").is_file()

# The flag belongs to the definition file only ----------------------------- #

def test_create_still_runs_the_true_command(process_manager):
    """"aiko_process create true" must still run the "true" command:
    the flag is parsed in the definition file, never in create()"""

    process_manager.create("true", ["sleep", "300"])
    assert process_manager.created == [("true", ["sleep", "300"], None)]

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

# The shared state is a report, not a control ------------------------------ #
#
# Any client can write any share item through the Actor's "control" topic:
# ECProducerImpl._producer_handler() accepts (update K V), (remove K) and a
# key that did not exist, with no allow list.  The FunctionGate guards the
# "in" topic, not that one.  These tests hold the two consequences this
# Actor must survive.

def test_a_write_to_safe_does_not_change_what_is_enforced():
    """The question worth asking of a Dashboard: can an edit turn the gate
    off?  It cannot.  The gate holds its own allow list, decided at
    construction from the command line"""

    actor, posted = make_process_manager(safe=True)
    before = set(actor.functions)

    actor.ec_producer.update("safe", "false")   # as the control topic does

    assert set(actor.functions) == before
    actor._topic_in_handler(None, "t/in", "(create date)")
    assert posted == []                         # still denied

def test_a_write_to_safe_is_reverted_and_counted():
    """So the report cannot be made to lie either"""

    actor, _ = make_process_manager(safe=True)

    actor.ec_producer.update("safe", "false")

    assert actor.share["safe"] is True
    assert actor.share["last_error"] == "read_only safe"

def test_writing_the_posture_it_already_has_is_not_a_denial():
    actor, _ = make_process_manager(safe=True)

    actor.ec_producer.update("safe", True)

    assert actor.share["safe"] is True
    assert actor.share["last_error"] == "-"

def test_a_falsified_denial_count_is_corrected_by_the_next_denial():
    """A client wrote (update metrics.denied 0), which made the item the
    string "0".  The count is held by the Actor, so "string + 1" is never
    evaluated and the published count is right again"""

    actor, _ = make_process_manager(safe=True)
    actor._topic_in_handler(None, "t/in", "(exit 0)")
    assert actor.share["metrics"]["denied"] == 1

    actor.ec_producer.update("metrics.denied", "0")      # falsified
    actor._topic_in_handler(None, "t/in", "(exit 0)")    # no TypeError

    assert actor.share["metrics"]["denied"] == 2

# --------------------------------------------------------------------------- #

# The ProcessManagerCache: a live replica, with no broker --------------- #
#
# The cache is thin, because ECCache does the work: discovery through the
# ServicesCache, one leased ECConsumer for each ProcessManager, and a local
# replica.  These tests simulate a discovery event and write the replica
# directly, the way test_share.py exercises ECCache.

from aiko_services.main.process_manager import (
    ProcessManagerCache, parse_process_share,
)

TOPIC = "aiko/host/1234/1"

def make_cache(name="review"):
    """A cache, plus a discovered ProcessManager and its replica"""

    actor, _ = make_process_manager()
    cache = ProcessManagerCache(actor, name)
    cache.cache._service_change_handler(
        "add", [TOPIC, name, "*", "*", "*", []])
    return cache, cache.cache.caches[TOPIC]

def test_a_process_share_item_is_a_pid_and_a_command():
    assert parse_process_share("4242 sleep 60") == ("4242", "sleep 60")
    assert parse_process_share("4242 /bin/sh -c echo a; sleep 1") ==  \
        ("4242", "/bin/sh -c echo a; sleep 1")

def test_a_process_share_item_without_a_command():
    assert parse_process_share("4242") == ("4242", "")

def test_an_empty_cache_reads_as_empty_and_not_as_an_error():
    actor, _ = make_process_manager()
    cache = ProcessManagerCache(actor, "nobody")

    assert cache.topic_paths() == []
    assert cache.get_processes() == {}
    assert cache.get_safe() is None
    assert cache.get_denied() == 0

def test_discovery_gives_the_cache_a_replica():
    cache, _ = make_cache()

    assert cache.topic_paths() == [TOPIC]
    assert isinstance(cache.cache.consumers[TOPIC], aiko.ECConsumerImpl)

def test_the_process_table_is_read_from_the_replica():
    cache, replica = make_cache()
    replica["process"] = {
        "000000": "4242 aiko_process run", "000001": "4301 sleep 60"}

    assert cache.get_processes() == {
        "000000": ("4242", "aiko_process run"),
        "000001": ("4301", "sleep 60")}

def test_the_posture_is_read_as_a_boolean_either_way():
    """A share value is a bool from the Actor, and a string once a client
    has written it through the control topic"""

    cache, replica = make_cache()
    for value, expected in (
        (True, True), (False, False), ("true", True), ("false", False)):
        replica["safe"] = value
        assert cache.get_safe() is expected

def test_the_denial_count_survives_a_string():
    cache, replica = make_cache()
    replica["metrics"] = {"denied": "7"}
    assert cache.get_denied() == 7

    replica["metrics"] = {"denied": "not a number"}
    assert cache.get_denied() == 0

def test_any_other_share_item_is_readable_too():
    cache, replica = make_cache()
    replica["watchdog"] = "False"
    assert cache.get("watchdog") == "False"
    assert cache.get("absent", default="fallback") == "fallback"

def test_a_handler_is_replayed_and_then_relayed():
    cache, replica = make_cache()
    replica["process"] = {"000001": "4301 sleep 60"}
    seen = []
    cache.add_handler(lambda *event: seen.append(event))

    assert ("aiko/host/1234/1", "add", "process.000001", "4301 sleep 60")  \
        in seen

    cache.remove_handler(seen.append)             # a handler never attached
    assert len(cache.cache.handlers) == 1

def test_terminate_empties_the_cache():
    cache, _ = make_cache()
    cache.terminate()

    assert cache.topic_paths() == []
    assert cache.get_processes() == {}

def test_two_process_managers_are_separate_replicas():
    cache, replica = make_cache()
    other = "aiko/host/5678/1"
    cache.cache._service_change_handler(
        "add", [other, "review", "*", "*", "*", []])
    replica["process"] = {"000001": "1 one"}
    cache.cache.caches[other]["process"] = {"000002": "2 two"}

    assert cache.topic_paths() == sorted([TOPIC, other])
    assert cache.get_processes(TOPIC) == {"000001": ("1", "one")}
    assert cache.get_processes(other) == {"000002": ("2", "two")}
    assert cache.get_processes() == {}            # ambiguous: no sole producer

# --------------------------------------------------------------------------- #

# "aiko_process list --watch" ---------------------------------------------- #
#
# This path had no test, and the whole suite passed while the function it
# calls was missing from the file.  A command line is code too.

from click.testing import CliRunner

from aiko_services.main.process_manager import main, print_processes

class _CacheDouble:
    def __init__(self, processes, safe=True, denied=0):
        self._processes, self._safe, self._denied = processes, safe, denied

    def get_processes(self, topic_path=None):
        return self._processes

    def get_safe(self, topic_path=None):
        return self._safe

    def get_denied(self, topic_path=None):
        return self._denied

def test_the_watch_output_names_the_posture_and_each_process(capsys):
    cache = _CacheDouble(
        {"000000": ("4242", "aiko_process run"),
         "000001": ("4301", "sleep 60")}, safe=False, denied=2)

    print_processes(cache, topic_path="aiko/host/1/1")
    output = capsys.readouterr().out

    assert "aiko/host/1/1  posture: unsafe  denied: 2" in output
    assert "uid: 000000, pid: 4242, aiko_process run" in output
    assert "uid: 000001, pid: 4301, sleep 60" in output

def test_the_watch_output_says_so_when_there_is_nothing(capsys):
    print_processes(_CacheDouble({}), topic_path="aiko/host/1/1")
    output = capsys.readouterr().out

    assert "posture: safe" in output and "no processes" in output

def test_an_unreported_posture_prints_as_unknown(capsys):
    print_processes(_CacheDouble({}, safe=None), topic_path="t")
    assert "posture: unknown" in capsys.readouterr().out

def test_a_uid_narrows_the_watch_output(capsys):
    cache = _CacheDouble(
        {"000000": ("4242", "run"), "000001": ("4301", "sleep 60")})

    print_processes(cache, uid="000001", topic_path="t")
    output = capsys.readouterr().out

    assert "000001" in output and "000000" not in output

def test_the_watch_flag_reaches_the_watch_path(monkeypatch):
    """Without this, the flag could call a function that does not exist --
    which is how it shipped the first time"""

    called = []
    monkeypatch.setattr(
        "aiko_services.main.process_manager._list_watch",
        lambda name, uid: called.append((name, uid)))

    result = CliRunner().invoke(main, ["list", "-n", "review", "--watch"])

    assert result.exit_code == 0, result.output
    assert called == [("review", None)]

def test_list_without_the_flag_does_not_take_the_watch_path(monkeypatch):
    monkeypatch.setattr(
        "aiko_services.main.process_manager._list_watch",
        lambda name, uid: pytest.fail("the request path was expected"))
    monkeypatch.setattr(
        "aiko_services.main.process_manager.do_request",
        lambda *args, **kwargs: None)
    monkeypatch.setattr(aiko.process, "run", lambda *args, **kwargs: None)

    result = CliRunner().invoke(main, ["list", "-n", "review"])

    assert result.exit_code == 0, result.output

# --------------------------------------------------------------------------- #
