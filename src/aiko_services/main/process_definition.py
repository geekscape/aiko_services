#!/usr/bin/env python3
#
# Aiko Services: a ProcessManager definition held in a Category
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# What a Category Entry says about a process, so that a Category tree can
# be what a ProcessManager runs.  "process_manager.py" reads a JSON file
# today, and its To Do asks for "ProcessManager as-a LifeCycleManager
# as-a Category", with "aiko_process enable | disable | start | status |
# stop hyperspace_path" in its usage.  This module is the part of that
# which both ends can agree on now.
#
# The convention
# ~~~~~~~~~~~~~~
# An Entry is a process when its Dependency's "storage_url" begins with
# "process:", and what follows is one entry of a ProcessManager
# definition, as JSON ...
#
#   process:{"enabled": true, "command": "aiko_registrar run"}
#   process:{"enabled": false, "command": "aiko_recorder",
#            "cwd": "/home/claude"}
#
# Its "lifecycle_manager_url" names the ProcessManager that runs it, which
# is what that field is for: "the Actor that manages the Service (load /
# unload)".  A Category of such Entries is a definition, and a Category of
# Categories groups them.
#
# Why those two fields, and not tags
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# Measured, not assumed: a ServiceFilter joins its tags with a space and
# the codec does not escape them, so a tag of "command=aiko_registrar
# run" arrives as two tags, "command=aiko_registrar" and "run".  A
# command line and a working directory both hold spaces.  The codec does
# length-prefix "lifecycle_manager_url" and "storage_url", which arrive
# whole, so the definition goes there.
#
# The object is the ProcessManager's own object form, which
# "_parse_definition_object()" already reads, so a definition made here
# needs no new parser when the ProcessManager reads a Category itself.
#
# To Do
# ~~~~~
# - The ProcessManager reads its definition from a Category, rather than
#   from a JSON file, and keeps the Category current as processes come
#   and go.  Until then, "definition_json()" writes the file it does read
# - "status": the ProcessManager says which Entry each process came from,
#   instead of a client matching them by command line
# - An Entry of a Pipeline or an Agent, which is a process with more to
#   say about it

import json
import shlex
from collections import namedtuple

__all__ = [
    "PROCESS_SCHEME",
    "Process",
    "command_line",
    "definition_json",
    "is_process_entry",
    "process_of_entry",
    "process_url",
]

PROCESS_SCHEME = "process:"

# One process, as the ProcessManager takes it: "command" is the program,
# "arguments" the rest of its command line, and "cwd" the directory it
# runs in, or None for the ProcessManager's own
Process = namedtuple("Process", "enabled command arguments cwd")


def is_process_entry(entry):
    """Whether an Entry says anything about a process"""

    return str(getattr(entry, "storage_url", "")).startswith(PROCESS_SCHEME)


def process_of_entry(entry):
    """(Process, diagnostic) from one Entry.  The Process is None when the
    Entry is not one, or says something this cannot use, and the
    diagnostic says which, because an Entry that silently does nothing is
    worse than one that explains itself"""

    if not is_process_entry(entry):
        return None, "not a process"
    text = entry.storage_url[len(PROCESS_SCHEME) :]
    try:
        definition = json.loads(text)
    except ValueError as value_error:
        return None, f"definition is not JSON: {value_error}"
    if not isinstance(definition, dict):
        return None, "definition is not an object"

    enabled = definition.get("enabled")
    if not isinstance(enabled, bool):
        return None, 'definition needs "enabled" true or false'

    command = definition.get("command")
    if isinstance(command, str):
        try:
            tokens = shlex.split(command)
        except ValueError as value_error:  # an unbalanced quote
            return None, f"command {value_error}"
    elif isinstance(command, list) and all(isinstance(token, str) for token in command):
        tokens = list(command)
    else:
        return None, 'definition needs "command", a string or a list'
    if not tokens:
        return None, "definition has no command"

    cwd = definition.get("cwd")
    if cwd is not None and not isinstance(cwd, str):
        return None, 'definition "cwd" must be a string'
    return Process(enabled, tokens[0], tokens[1:], cwd), ""


def process_url(enabled, command, cwd=None):
    """The storage_url of an Entry that says what to run.  "command" is a
    command line, or the tokens of one"""

    definition = {"enabled": bool(enabled), "command": command}
    if cwd:
        definition["cwd"] = cwd
    return PROCESS_SCHEME + json.dumps(definition, sort_keys=True)


def command_line(process):
    """What a person reads, and what a running process is matched by"""

    if process is None:
        return ""
    return " ".join([process.command, *process.arguments])


def definition_json(processes):
    """The JSON that "aiko_process run definition.json" reads, from each
    Process of a Category, in the order given"""

    entries = []
    for process in processes:
        entry = {"enabled": process.enabled, "command": command_line(process)}
        if process.cwd:
            entry["cwd"] = process.cwd
        entries.append(entry)
    return json.dumps(entries, indent=2)


# --------------------------------------------------------------------------- #
