#!/usr/bin/env python3
#
# Aiko Services tests: a ProcessManager definition held in a Category
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# The convention is a convention, so the tests are about what survives:
# the codec, a command line with a space in it, and the object form that
# "process_manager.py" already parses.
#
# One test measures the codec rather than trusting the convention, because
# the convention exists only because of what that measurement says: a
# ServiceFilter's tags are joined with a space and are not escaped, so a
# command line cannot be a tag, while the two URL fields are escaped and
# arrive whole.
#
# To Do
# ~~~~~
# - The same definition, read by the ProcessManager itself

import json

import pytest

import aiko_services as aiko
from aiko_services.main.category_view import entry_of
from aiko_services.main.process_definition import (
    PROCESS_SCHEME, Process, command_line, definition_json,
    is_process_entry, process_of_entry, process_url,
)
from aiko_services.main.utilities import generate, parse

WILDCARD = "*"

def entry(storage_url, lcm_url="None", name="registrar"):
    """One Entry, as a Category holds it"""

    return entry_of(name,
        [[WILDCARD, name, WILDCARD, WILDCARD, WILDCARD, []],
            lcm_url, storage_url])

# Why the convention is what it is ---------------------------------------- #

def test_a_tag_cannot_hold_a_command_line():
    """Measured, not assumed: a ServiceFilter joins its tags with a space
    and the codec does not escape them, so one tag of "command=x y"
    arrives as two tags.  This is why a definition is not a tag"""

    service_filter = aiko.ServiceFilter(WILDCARD, "p", WILDCARD, WILDCARD,
        WILDCARD, ["command=aiko_registrar run"])
    _, arguments = parse(generate("add", ["p", service_filter, None, None]))

    assert arguments[1][5] == ["command=aiko_registrar", "run"]

def test_a_storage_url_arrives_whole():
    """The codec length-prefixes it, so the definition goes there"""

    url = process_url(True, "aiko_registrar run", "/home/claude/x y")
    service_filter = aiko.ServiceFilter(WILDCARD, "p", WILDCARD, WILDCARD,
        WILDCARD, [])
    _, arguments = parse(
        generate("add", ["p", service_filter, "aiko01", url]))

    assert arguments[3] == url
    assert arguments[2] == "aiko01"          # and so does the manager

# What an Entry says about a process -------------------------------------- #

def test_an_entry_that_says_nothing_about_one():
    for storage_url in ("None", "", "file:", "0:"):
        assert is_process_entry(entry(storage_url)) is False
        assert process_of_entry(entry(storage_url)) == (None, "not a process")

def test_an_entry_that_says_what_to_run():
    process, diagnostic = process_of_entry(
        entry(process_url(True, "aiko_registrar run")))

    assert diagnostic == ""
    assert process == Process(True, "aiko_registrar", ["run"], None)
    assert command_line(process) == "aiko_registrar run"

def test_an_entry_that_is_disabled():
    process, _ = process_of_entry(entry(process_url(False, "aiko_recorder")))

    assert process.enabled is False
    assert process.command == "aiko_recorder" and process.arguments == []

def test_a_working_directory_that_holds_a_space():
    process, _ = process_of_entry(
        entry(process_url(True, "aiko_hyperspace run", "/home/claude/x y")))

    assert process.cwd == "/home/claude/x y"

def test_an_argument_that_holds_a_space():
    """The object form splits with shlex, as the ProcessManager does"""

    process, _ = process_of_entry(
        entry(process_url(True, 'say "two words"')))

    assert process.arguments == ["two words"]

def test_a_command_given_as_its_tokens():
    url = PROCESS_SCHEME + json.dumps(
        {"enabled": True, "command": ["say", "two words"]})
    process, _ = process_of_entry(entry(url))

    assert process.command == "say" and process.arguments == ["two words"]

def test_the_manager_of_a_process_is_the_lifecycle_manager_url():
    """Which is what that field is for: the Actor that manages it"""

    assert entry(process_url(True, "x"), "aiko01").lcm_url == "aiko01"

# A definition that cannot be used says so -------------------------------- #

@pytest.mark.parametrize("definition,reason", [
    ("{oops", "not JSON"),
    ('["a list"]', "not an object"),
    ('{"command": "x"}', '"enabled"'),
    ('{"enabled": "true", "command": "x"}', '"enabled"'),
    ('{"enabled": true}', '"command"'),
    ('{"enabled": true, "command": 7}', '"command"'),
    ('{"enabled": true, "command": ["x", 7]}', '"command"'),
    ('{"enabled": true, "command": ""}', "no command"),
    ('{"enabled": true, "command": "say \\"one"}', "command"),
    ('{"enabled": true, "command": "x", "cwd": 7}', '"cwd"'),
], ids=["not JSON", "a list", "no enabled", "enabled is a string",
    "no command", "command is a number", "a token is a number",
    "command is empty", "an unbalanced quote", "cwd is a number"])
def test_a_definition_that_cannot_be_used(definition, reason):
    """An Entry that silently does nothing is worse than one that says
    why, so each of these names its own fault"""

    process, diagnostic = process_of_entry(entry(PROCESS_SCHEME + definition))

    assert process is None
    assert reason in diagnostic

# The URL, and the JSON that a ProcessManager reads ----------------------- #

def test_the_url_holds_what_it_was_given():
    assert process_url(True, "x") == PROCESS_SCHEME +  \
        '{"command": "x", "enabled": true}'
    assert "cwd" not in process_url(True, "x", None)
    assert "cwd" not in process_url(True, "x", "")

def test_the_url_round_trips():
    for enabled in (True, False):
        for cwd in (None, "/home/claude/x y"):
            url = process_url(enabled, "aiko_registrar run", cwd)
            process, _ = process_of_entry(entry(url))
            assert process == Process(
                enabled, "aiko_registrar", ["run"], cwd)
            assert process_url(enabled, command_line(process), cwd) == url

def test_the_definition_json_is_what_aiko_process_run_reads():
    """The object form of "process_manager.py", which it already parses"""

    processes = [Process(True, "aiko_registrar", ["run"], None),
        Process(False, "aiko_recorder", [], "/home/claude")]
    entries = json.loads(definition_json(processes))

    assert entries == [
        {"enabled": True, "command": "aiko_registrar run"},
        {"enabled": False, "command": "aiko_recorder",
            "cwd": "/home/claude"}]

def test_the_definition_json_of_nothing():
    assert json.loads(definition_json([])) == []

def test_the_process_manager_parses_what_this_writes():
    """The two ends agree, which is the whole point of the object form"""

    from aiko_services.main.process_manager import ProcessManagerImpl

    processes = [Process(True, "aiko_registrar", ["run"], None),
        Process(False, "aiko_recorder", [], "/home/claude")]
    parsed = [ProcessManagerImpl._parse_definition_object(None, entry)
        for entry in json.loads(definition_json(processes))]

    assert parsed == [(True, "aiko_registrar", ["run"], None),
        (False, "aiko_recorder", [], "/home/claude")]

def test_the_command_line_of_nothing():
    assert command_line(None) == ""

# --------------------------------------------------------------------------- #
# What a Category's "(list ...)" can carry -------------------------------- #
#
# A Dependency writes itself as an S-expression by hand, and a Category's
# listing embeds that, so a URL holding a space used to break the
# expression and the definition came back as nonsense.  Each URL field is
# now length-prefixed the way generate_s_expression() does it.
#
# These are about "dependency.py" and "utilities/parser.py", and they live
# here because the definition is why they had to change

from aiko_services.main.utilities.parser import generate_symbol   # noqa: E402

def dependency_of(storage_url, lcm_url="pm_a"):
    return aiko.compose_instance(aiko.DependencyImpl, aiko.dependency_args(
        None, aiko.ServiceFilter(WILDCARD, "sleeper", WILDCARD, WILDCARD,
            WILDCARD, []), lcm_url, storage_url))

def test_a_symbol_is_left_alone_when_it_holds_no_delimiter():
    assert generate_symbol("plain") == "plain"
    assert generate_symbol("aiko/protocol/foo:0") == "aiko/protocol/foo:0"

def test_a_symbol_that_holds_a_delimiter_is_length_prefixed():
    assert generate_symbol("a b") == "3:a b"
    assert generate_symbol("(x)") == "3:(x)"
    assert generate_symbol("7:seven") == "7:7:seven"   # or it reads as one

def test_a_definition_url_survives_a_listing():
    """The record that a Category publishes for one Entry, as
    "_get_entry_records()" builds it"""

    url = process_url(True, "sleep 300", "/home/claude/x y")
    record = f"0 sleeper {dependency_of(url)}"
    command, arguments = parse(f"(response {record})")

    assert command == "response"
    assert arguments[2][1] == "pm_a"              # the manager
    assert arguments[2][2] == url                 # and the definition
    process, diagnostic = process_of_entry(
        entry(arguments[2][2], arguments[2][1]))
    assert diagnostic == ""
    assert command_line(process) == "sleep 300"
    assert process.cwd == "/home/claude/x y"

def test_a_dependency_that_holds_no_url_is_unchanged():
    """The codec's None stays the word it has always been"""

    assert str(dependency_of(None, None)) ==  \
        "((* sleeper * * * ()) None None)"

# --------------------------------------------------------------------------- #
