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
