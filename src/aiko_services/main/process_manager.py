#!/usr/bin/env python3
#
# Aiko Service: Process Manager
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# Create, List(Read), Update and Destroy processes
#
# Usage
# ~~~~~
# export AIKO_DISCOVERY_TIMEOUT=5.0  # seconds for remote WAN hosts (optional)
#
# aiko_process run  [--name name] [--watchdog] [definition_pathname]
# aiko_process dump [--name name]
# aiko_process exit [--name name] [--grace_time seconds]
#
# aiko_process create  [--name name] [--uid uid] [--cwd pathname]
#                      command [arguments ...]
# aiko_process list    [--name name] [uid]
# aiko_process destroy [--name name] [--kill] uid
#
# aiko_process enable | disable | start | status | stop hyperspace_path
#
# export AIKO_DISCOVERY_TIMEOUT=5.0  # seconds for remote WAN hosts
#
# Definition file
# ~~~~~~~~~~~~~~~
# The "definition_pathname" is a JSON file, which holds a list of strings.
# Each string starts with an "enabled" flag, "true" or "false", and then
# the command and its arguments ...
#
#   [
#     "true  mosquitto -c 0_mosquitto.conf",
#     "true  aiko_registrar",
#     "false aiko_recorder"
#   ]
#
# The flag lets a process be disabled, but stay in the definition.
# The flag is required: an entry without one is reported and then skipped,
# because a command that silently doesn't start is worse than a diagnostic.
# Note that the flag applies to the definition file only, so that
# "aiko_process create true" still runs the "true" command.
#
# An entry is either that string, or an object, which carries a working
# directory and keeps an argument that contains a space ...
#
#   [
#     {"enabled": true, "command": "aiko_hyperspace run",
#      "cwd": "/home/claude/hyperspace"},
#     {"enabled": true, "command": ["aiko_chat", "run"],
#      "cwd": "/home/claude/chat_server"}
#   ]
#
# The string form splits on whitespace, so it cannot express an argument
# that contains a space.  The object form splits with "shlex", and takes a
# list as the command when even that is unwanted.  The "enabled" flag is
# required in both forms, "cwd" is optional, and an unknown key is
# reported and the entry skipped.
#
# Working directory
# ~~~~~~~~~~~~~~~~~
# A process inherits the ProcessManager's working directory, unless "cwd"
# names one.  Some Services locate their state by the working directory
# and nothing else.  HyperSpace file Storage resolves "_hyperspace_" and
# ".root" against it, so "aiko_hyperspace run" reads the storage of
# whichever directory it starts in.
#
# Shell and Python scripts
# ~~~~~~~~~~~~~~~~~~~~~~~~
# aiko_process create -u uid:0 date
# aiko_process create -u uid:1 sleep 5
# aiko_process create -u uid:2 aiko_process exit -gt 0  # self terminate !
#
# Simultaneous processes terminating at different times
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# aiko_process create -u uid:0 /bin/sh -c "echo Start A; sleep 10; echo Stop A"
# aiko_process create -u uid:1 /bin/sh -c "echo Start B; sleep 15; echo Stop B"
# aiko_process create -u uid:2 /bin/sh -c "echo Start C; sleep  5; echo Stop C"
#
# Design notes
# ~~~~~~~~~~~~
# Concurrency: Except _run(), all functions execute on the Actor main thread.
# Meaning that those functions are safely executed in order, one-at-a-time.
# The _run() function executes on its own daemon thread and needs to ...
# - Insulate itself from shared data updates, e.g loops must copy the iterator
# - All shared data updates must be posted to the Actor main thread
#
# To Do
# ~~~~~
# * Refactor ProcessManager to provide functionality without being an Actor
#   * Then, update LifeCycleManager accordingly
#
# * ProcessManager as-a LifeCycleManager as-a Category
#   * Design and use HyperSpace API and Storage SPI (file, SQL, MQTT, ValKey ?)
#
# * CLI commands: CRUD Services in HyperSpace/Storage filesystem structure
#   - Process LifeCycle: create, enable, start, status, stop, disable, destroy
#   - Disambiguate CLI create() versus start() and destroy() versus stop() !
#
# * Consider design and implementation of "./process_manager.py update ..." ?
#
# * Aiko Dashboard plug-in support: Process CRUD et al plus ThreadManager view
#   * Use ThreadManager: Investigate https://github.com/DedInc/pythread
#   * TUI ASCII graphs for metrics and events
#
# * Send "process events" to Dashboard, Agents, Time-Series DataBase --> Graphs
#   - Use Open Telemetry schema
#
# * Handle process standard output and standard error
# * Relaunch failed processes, but don't retry continuously failing processes
# * Auto-scaling workers up/down: same host, distributed ?
# * Schedule (crontab) automated modification of the process lifecycle state
#
# * Implement process "owner" field and populate automatically
#   * Implement "destroy --force" flag to destroy other owner's processes
#   * System processes owned by "aiko", e.g ProcessManager, MQTT, Registrar
#
# * Consider only one primary ProcessManager per host (refactor Registrar code)
#   * Don't allow two ProcessManagers with the same name
# * ProcessManager primary / watchdog: monitor and relaunch primary
# * Unify ProcessManagers on different hosts in the same namespace ?
#     * All the home/office servers plus handle mobile laptops (discovery) ?
#
# - aiko_process run --exit_no_processes -enp  # No running processes, then exit
#
# - Track runtime (seconds since started) for ProcessManager
#   - All process metrics: owner, restarts, runtime and resource usage (psutil)
#
# * Test on Windows operating system
# * Support Operating System specific: systemd, launchd and task scheduler
#
# - Shell pipe: (DataSource | shell command 0 | shell command 1 | DataTarget)
#   - DataSource file: with FileSystemEventPatternMatch() for any MediaType
#
# - Consider process specific "process_exit_handler()" implementations ?
#
# - Consider using "selectors" or "asyncio.create_subprocess_exec()"
# - Check out https://pypi.org/project/python-daemon
# - Use of threading versus multiprocessing
#   - https://docs.python.org/2/library/multiprocessing.html
#   - https://hackernoon.com/concurrent-programming-in-python-is-not-what-you-think-it-is-b6439c3f3e6a

from abc import abstractmethod
import click
import importlib.util
import json
import os
import shlex
import shutil
from subprocess import Popen
import sys
from threading import Thread
import time

from aiko_services.main import *
from aiko_services.main.utilities import *

__all__ = [
    "FUNCTIONS", "SAFE", "SAFE_FUNCTIONS", "ProcessManager",
    "ProcessManagerCache", "ProcessManagerImpl", "coerce_response_topic",
    "parse_process_share", "print_processes"
]

ACTOR_TYPE = "process_manager"
VERSION = 0
PROTOCOL = f"{SERVICE_PROTOCOL_AIKO}/{ACTOR_TYPE}:{VERSION}"

_DEFINITION_KEYS = frozenset({"enabled", "command", "cwd"})
_GRACE_TIME=5.0  # seconds
_MY_UID="000000"  # self-aware 🤔
_PROCESS_POLL_TIME = 1.0  # seconds
_RESPONSE_TOPIC = f"{aiko.topic_in}"
_THREAD_NAME=f"aiko-{ACTOR_TYPE}"

SAFE = True              # the default posture of "aiko_process run"

# A ProcessManager starts and stops processes on its host, so what it
# accepts from the message bus is not a small matter.  Safe mode allows the
# two functions that cannot start or stop anything: "list", and the log
# level the Dashboard sets.  ADR-023 decision 6 allows this posture for an
# isolated deployment, as long as the policy is explicit and advertised.
#
# A diagnostic function stays out of this set, even though it starts and
# stops nothing.  "dump" writes the process table to the log, and internal
# data that a client reads is internal data that helps a client compromise
# the system.  Only a design and a test campaign make a function safe, not
# the observation that it looks harmless (project-lead direction,
# 2026-10-23).  So this set grows deliberately, or not at all
SAFE_FUNCTIONS = frozenset({"list", "set_log_level"})

# The suffixes a response topic may end with.  A caller asks for a reply on
# its own "in" topic, so this is not a list of topics to refuse
_RESPONSE_SUFFIXES = ("in", "out", "control")
_RESPONSE_TOPIC_LENGTH = 256

def coerce_response_topic(topic_path_response, topic_path_own):
    """The response topic a caller asked for, or None when it is not
    allowed.  A caller names the topic that "list" publishes to, so without
    this an unknown client makes a ProcessManager publish where it likes.

    Pure, so each rule is tested without an Actor:
    a wildcard is never a publication topic, the suffix must be one a
    Service owns, the rest must parse as a Service topic path, and the
    namespace must be the one this Service is in"""

    if not isinstance(topic_path_response, str):
        return None
    if len(topic_path_response) > _RESPONSE_TOPIC_LENGTH:
        return None
    if "+" in topic_path_response or "#" in topic_path_response:
        return None
    path, _, suffix = topic_path_response.rpartition("/")
    if suffix not in _RESPONSE_SUFFIXES:
        return None
    asked = ServiceTopicPath.parse(path)
    own = ServiceTopicPath.parse(topic_path_own)
    if not asked or not own or asked.namespace != own.namespace:
        return None
    return topic_path_response

# --------------------------------------------------------------------------- #

class ProcessManager(Actor):
    Interface.default("ProcessManager",
        "aiko_services.main.process_manager.ProcessManagerImpl")

    @abstractmethod
    def create(self, command, arguments=None, uid=None, cwd=None):
        pass

    @abstractmethod
    def destroy(self, uid, kill=False):
        pass

    @abstractmethod
    def dump(self):
        pass

    @abstractmethod
    def exit(self, grace_time=_GRACE_TIME):
        pass

    @abstractmethod
    def list(self, topic_path_response, uid=None):
        pass

# --------------------------------------------------------------------------- #

# Everything the Interface declares, plus the framework's two.  Derived, so
# that the allow list and the contract cannot drift apart (P12, ADR-023)
FUNCTIONS = interface_functions(ProcessManager)

class ProcessCurrent:
    def __init__(self):
        self.pid = os.getpid()
        self.stdin = sys.stdin
        self.stdout = sys.stdout
        self.stderr = sys.stderr
        self.returncode = None  # Current process is still running 😂

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        raise RuntimeError("Cannot wait on the current process")

class ProcessManagerImpl(ProcessManager):
    def __init__(self, context, definition_pathname=None,
        watchdog=False, process_exit_handler=None, safe=SAFE):

    # The FunctionGate aspect, configured before the Actor initializes it.
    # Safe mode is the default, so a ProcessManager reached by an unknown
    # client cannot be asked to start or stop a process
        self._safe = bool(safe)
        functions = FUNCTIONS & SAFE_FUNCTIONS if self._safe else FUNCTIONS
        context.call_init(self, "FunctionGate", context, functions=functions)
        context.call_init(self, "Actor", context)

        if process_exit_handler:
            self.process_exit_handler=process_exit_handler
        else:
            self.process_exit_handler=self._process_exit_handler_default
        self.processes = {
            _MY_UID: {  # self-aware 🤔
                "command_line": ["aiko_process", "run"],
                "process": ProcessCurrent()
            }
        }
        self.uid_default = 1

        self.share = {
            "lifecycle": "ready",
            "log_level": get_log_level_name(self.logger),
            "source_file": f"v{VERSION}⇒ {__file__}",
            "definition_pathname": definition_pathname,
            "metrics": {
                "created": 1,  # Including self, i.e this ProcessManager 😅
                "running": len(self.processes),
                "denied": 0,
            #   "runtime": 0                                    # TODO: Runtime
            },
            "last_error": "-",
            "safe": self._safe,   # ADR-023 decision 3: an observable policy
            "watchdog": watchdog,
        # One entry for each process, so that a consumer follows the table
        # live instead of polling "list".  The ProcessManagerCache reads it
            "process": {
                uid: self._process_share(uid) for uid in self.processes
            }
        }
        self.ec_producer = compose_instance(
            ECProducerImpl, ec_producer_args(self, self.share))
        self.ec_producer.add_handler(self._ec_producer_change_handler)

        self.thread = Thread(target=self._run, daemon=True, name=_THREAD_NAME)
        self.thread.start()                           # TODO: Use ThreadManager

        self._parse_definition(definition_pathname)

    def _process_share(self, uid):
        """One process as one share value: its pid and its command line"""

        command, pid = self._get_process_info(uid)
        return f"{pid} {' '.join(command)}"

    def __str__(self):
        result = ""
        for uid in self.processes.keys():
            uid_str = self._get_uid_str(uid)
            new_line = "\n" if result else ""
            result += f"{new_line}  {uid_str}"
        return result

    def _resolve_command(self, command):
        """The pathname to run for a command, which is the command itself
        unless it names an importable module script.

        An executable on PATH wins, because a console script and an
        importable package often share a name.  "aiko_chat" is both, and
        the module resolved to its "__init__.py", which is not executable,
        so the process failed with a permission error naming a file nobody
        asked for.  A module is used only when its own file is executable,
        which is how a module script runs without a console script of its
        own.  Anything else is left as it is, so that Popen reports the
        command it could not find"""

        file_extension = os.path.splitext(command)[-1]
        if file_extension in [".py", ".sh"]:         # TODO: Other extensions ?
            return command
        if shutil.which(command):
            return command
        try:
            specification = importlib.util.find_spec(command)
        except (ImportError, ValueError):      # not a usable module name
            return command
        origin = specification.origin if specification else None
        if origin and os.access(origin, os.X_OK):
            self.logger.info(f'Module path resolved to: "{origin}"')
            return origin
        return command

    def create(self, command, arguments=None, uid=None, cwd=None):
    # Popen reports a working directory that is not one as a file not found
    # error which names the command, not the directory, so check it here.
    # Before the uid is allocated, so that nothing starting leaves no gap
    # in the sequence of uids
        if cwd is not None and not os.path.isdir(cwd):
            self.logger.error(
                f"Create: not a directory, process not started: {cwd}")
            return

        if not uid:
            uid = f"{self.uid_default:06d}"
            self.uid_default += 1
        if uid in self.processes:
            self.logger.warning(
                f"Create: <{uid}> exists, process not started: {command}")
            return

        command_line = [self._resolve_command(command)]
        if arguments:
            command_line.extend(arguments)
        where = f" cwd: {cwd}" if cwd else ""
        self.logger.info(f"Create: <{uid}>{where} {command_line}")
        try:
            process = Popen(command_line, bufsize=0, shell=False, cwd=cwd)
            self.processes[uid] = {
                "command_line": command_line,
                "cwd": cwd,
                "process": process
            }
            self.ec_producer.update(f"process.{uid}", self._process_share(uid))
            self.ec_producer.update("metrics.running", len(self.processes))
            self.ec_producer.update("metrics.created",
                self.share["metrics"]["created"] + 1)
        except FileNotFoundError as file_not_found_error:
            self.logger.warning(f"{file_not_found_error}")
        except Exception as exception:
            name = exception.__class__.__name__
            self.logger.error(f"Unexpected exception: {name}: {exception}")

    def destroy(self, uid, kill=False):
        if uid != _MY_UID and uid in self.processes:
            if self._is_running(uid):
                process = self.processes[uid]["process"]
                if kill:
                    process.kill()       # SIGKILL: Can't catch, no clean-up
                else:
                    process.terminate()  # SIGTERM: Can catch and clean-up

    def dump(self):
        if len(self.processes):
            state = f" ...\n{self}"
        else:
            state = ": no processes"
        self.logger.info(f"Dump state{state}")

    def _ec_producer_change_handler(self, command, item_name, item_value):
        if item_name == "log_level":
            self.logger.setLevel(str(item_value).upper())
    # "safe" is a report of the posture, not a control for it.  The posture
    # is decided by the command line, and the FunctionGate holds its own
    # allow list, so a write here never changed what is enforced -- it only
    # made the report lie.  Revert it, count it, and say so
        if item_name == "safe" and item_value != self._safe:
            self._function_denied("safe", "read_only", str(item_value)[:20])
            self.ec_producer.update("safe", self._safe)

    def exit(self, grace_time):
        grace_time = parse_int(grace_time, _GRACE_TIME)
        for uid in self.processes.keys():
            self.destroy(uid, kill=False)  # Graceful 😇

        self.ec_producer.update("metrics.running", len(self.processes))
        time.sleep(grace_time)    # TODO: Improve how to wait for all processes

        for uid in self.processes.keys():
            self.destroy(uid, kill=True)   # Brutal ☠️
        aiko.process.terminate()

    def _get_process_info(self, uid):
        command = pid = "unknown"
        if uid in self.processes:
            process_info = self.processes[uid]
            command = process_info["command_line"]
            pid = process_info["process"].pid
        return command, pid

    def _get_return_code(self, uid):
        return_code = "uid_unknown"
        if uid in self.processes:
            return_code = self.processes[uid]["process"].poll()
        return return_code

    def _get_uid_str(self, uid):
        command, pid = self._get_process_info(uid)
        cwd = self.processes.get(uid, {}).get("cwd")
        where = f" cwd: {cwd}" if cwd else ""
        return f"<{uid}> PID: {pid} {command[0]}{where}"

    def _is_running(self, uid):
        return self._get_return_code(uid) is None

    def list(self, topic_path_response, uid=None):
        topic_path_response = coerce_response_topic(
            topic_path_response, self.topic_path)
        if not topic_path_response:
            return self._function_denied("list", "topic")
        responses = []
        for uid_key in self.processes.keys():
            if uid is None or uid == uid_key:
                command, pid = self._get_process_info(uid_key)
                response = f"{uid_key} {pid} {' '.join(command)}"
                responses.append(response)
        aiko.message.publish(
            topic_path_response, f"(item_count {len(responses)})")
        for response in responses:
            aiko.message.publish(
                topic_path_response, f"(response {response})")

    def _parse_definition_entry(self, entry):
        """Parse one definition entry, in either of its two forms.

        A string is "enabled command [arguments ...]", split on
        whitespace.  An object is {"enabled": ..., "command": ...,
        "cwd": ...}, which carries a working directory and keeps an
        argument that contains a space.  The leading flag is required in
        both forms, so that a process can be disabled without being
        removed from the definition.

        Returns (enabled, command, arguments, cwd).  The command is None
        when the entry can't be used, which is reported and then skipped,
        so that one bad entry doesn't stop the other processes"""

        if isinstance(entry, dict):
            return self._parse_definition_object(entry)
        tokens = str(entry).split()
        if not tokens:
            self.logger.error("Definition entry is empty, skipped")
            return False, None, None, None
        enabled = tokens[0].lower()
        if enabled not in ["true", "false"]:
            self.logger.error('Definition entry must start with "true" or '
                f'"false", skipped: {entry}')
            return False, None, None, None
        if len(tokens) < 2:
            self.logger.error(
                f"Definition entry has no command, skipped: {entry}")
            return False, None, None, None
        return enabled == "true", tokens[1], tokens[2:], None

    def _parse_definition_object(self, entry):
        """Parse one definition entry in its object form.

        Returns the same four values as _parse_definition_entry(), which
        is the only caller"""

        skipped = False, None, None, None
        unknown = sorted(set(entry) - _DEFINITION_KEYS)
        if unknown:
            self.logger.error("Definition entry has unknown key "
                f"{', '.join(unknown)}, skipped: {entry}")
            return skipped
        enabled = entry.get("enabled")
        if not isinstance(enabled, bool):
            self.logger.error('Definition entry must have "enabled" true '
                f"or false, skipped: {entry}")
            return skipped

        command = entry.get("command")
        if isinstance(command, str):
            try:
                tokens = shlex.split(command)
            except ValueError as value_error:          # an unbalanced quote
                self.logger.error("Definition entry command "
                    f"{value_error}, skipped: {entry}")
                return skipped
        elif isinstance(command, list) and  \
            all(isinstance(token, str) for token in command):
            tokens = list(command)
        else:
            self.logger.error('Definition entry "command" must be a string '
                f"or a list of strings, skipped: {entry}")
            return skipped
        if not tokens:
            self.logger.error(
                f"Definition entry has no command, skipped: {entry}")
            return skipped

        cwd = entry.get("cwd")
        if cwd is not None and not isinstance(cwd, str):
            self.logger.error('Definition entry "cwd" must be a string, '
                f"skipped: {entry}")
            return skipped
        return enabled, tokens[0], tokens[1:], cwd

    def _parse_definition(self, definition_pathname):
        diagnostic = None
        if definition_pathname:
            if definition_pathname.endswith(".json"):
                try:
                    entries = json.load(open(definition_pathname, "r"))
                    for entry in entries:
                        enabled, command, arguments, cwd =  \
                            self._parse_definition_entry(entry)
                        if command is None:
                            continue
                        if enabled:
                            self.create(command, arguments, cwd=cwd)
                        else:
                            self.logger.info(
                                f"Disabled: {' '.join([command, *arguments])}")
                except json.decoder.JSONDecodeError as json_decode_error:
                    diagnostic = f"Definition format: {json_decode_error}"
            else:
                diagnostic = 'Definition must be a ".json" file: ' +  \
                    definition_pathname
        if diagnostic:
            raise SystemExit(f"Error: {diagnostic}")

    def _process_exit_handler_default(self, uid):
        if uid in self.processes:
            uid_str = self._get_uid_str(uid)
            return_code = self._get_return_code(uid)
            process_info = f"{uid_str}, return_code: {return_code}"
            self.logger.info(f"Exit {process_info}")

    def _remove(self, uids):
        for uid in uids:
            if uid in self.processes:
                if self.process_exit_handler:
                    self.process_exit_handler(uid)
                del self.processes[uid]
                self.ec_producer.remove(f"process.{uid}")
        self.ec_producer.update("metrics.running", len(self.processes))

############################################################################
# _run() executes on a daemon thread, see concurrency design notes (above) #
############################################################################

    def _run(self):
        while True:
            zombies = []
            for uid in list(self.processes.keys()):  # safe
                if not self._is_running(uid):
                    zombies.append(uid)
            if zombies:
                self._post_message(ActorTopic.IN, "_remove", [zombies])  # safe
            time.sleep(_PROCESS_POLL_TIME)

# --------------------------------------------------------------------------- #

def get_service_filter(name=None, owner="*"):
    name = name if name else get_hostname()
    return ServiceFilter("*", name, PROTOCOL, "*", owner, "*")

# --------------------------------------------------------------------------- #
# The client side: one live replica of what a ProcessManager publishes, for
# every client that wants the process table without asking for it.
#
# The Registrar has the ServicesCache, which many clients share instead of
# each one speaking to the Registrar.  This is the same idea for a
# ProcessManager, and it is thin, because ECCache already does the work:
# discovery through the ServicesCache, one leased ECConsumer for each
# ProcessManager that matches, and a local replica of each one's shared
# state.  So a remote getter becomes a local, non-blocking read.
#
# This is ECCache's first client.  The share carries one "process.<uid>"
# item for each process, so the table arrives and stays current with no
# polling of "list"

def parse_process_share(value):
    """One "process.<uid>" share item as (pid, command).  The Actor writes
    "<pid> <command line>".  Pure, so the format is tested on its own"""

    pid, _, command = str(value).partition(" ")
    return pid, command

class ProcessManagerCache:
    """A live replica of what one or more ProcessManagers publish.

    get_processes() and the rest read the replica, never the network.  A
    handler is called for each change.  terminate() cancels the leases.

    "service" is the local Service, or "aiko.process" for a client that is
    not a Service (see the note in share.py)
    """

    def __init__(self, service, name=None, owner="*"):
        self.cache = compose_instance(ECCacheImpl, ec_cache_args(
            service, get_service_filter(name, owner)))

    def topic_paths(self):
        """Each ProcessManager the cache has a replica of"""

        return sorted(self.cache.caches)

    def get_processes(self, topic_path=None):
        """{uid: (pid, command)}, as the share holds it.  Empty until a
        ProcessManager is discovered and its state arrives"""

        processes = self.cache.get("process", default={},
            topic_path=topic_path) or {}
        return {uid: parse_process_share(value)
            for uid, value in sorted(processes.items())}

    def get_safe(self, topic_path=None):
        """The posture a ProcessManager advertises: True, False, or None
        when it has not said (an older Actor, or no replica yet)"""

        safe = self.cache.get("safe", default=None, topic_path=topic_path)
        if safe is None or isinstance(safe, bool):
            return safe
        return str(safe).lower() == "true"

    def get_denied(self, topic_path=None):
        """How many functions a ProcessManager has denied"""

        return parse_int(self.cache.get(
            "metrics.denied", default=0, topic_path=topic_path), 0)

    def get(self, item_name, default=None, topic_path=None):
        """Any other share item, for a client that wants one this class
        does not name"""

        return self.cache.get(item_name, default=default,
            topic_path=topic_path)

    def add_handler(self, handler, filter=None):
        """handler(topic_path, command, item_name, item_value) for each
        change, with the current replica replayed first"""

        self.cache.add_handler(handler, filter)

    def remove_handler(self, handler):
        self.cache.remove_handler(handler)

    def terminate(self):
        self.cache.terminate()

# --------------------------------------------------------------------------- #

@click.group()

def main():
    """Create, Read/List, Update and Destroy Processes

    \b
    export AIKO_DISCOVERY_TIMEOUT=5.0  # seconds for remote WAN hosts (optional)
    """
    pass

@main.command(name="create",
    context_settings=dict(allow_interspersed_args=False), no_args_is_help=True)
@click.option("--name", "-n", type=str, default=None,
    help="ProcessManager name, default is the local hostname")
@click.option("--uid", "-u", type=str, default=None,
    help="Unique name for referring to the process")
@click.option("--cwd", "-c", type=str, default=None,
    help="Working directory, default is the ProcessManager's")
@click.argument("command", type=str)
@click.argument("arguments", nargs=-1, type=click.UNPROCESSED)

def create_command(name, uid, cwd, command, arguments):
    """Create Process

    \b
    aiko_process create [--name NAME] [--uid UID] [--cwd CWD]
        COMMAND [ARGUMENTS ...]

    \b
    • NAME:       ProcessManager name, default is the local hostname
    • UID:        Unique IDentifier
    • CWD:        Working directory, default is the ProcessManager's
    • COMMAND:    Command name
    • ARGUMENTS:  Command arguments
    """

    do_command(ProcessManager, get_service_filter(name),
        lambda actor: actor.create(command, arguments, uid, cwd),
        terminate=True)
    aiko.process.run()

@main.command(name="destroy", no_args_is_help=True)
@click.option("--kill", "-k", is_flag=True,
    help="Use SIGKILL, process can't catch and no clean-up")
@click.option("--name", "-n", type=str, default=None,
    help="ProcessManager name, default is the local hostname")
@click.argument("uid", type=str)

def destroy_command(kill, name, uid):
    """Destroy Process

    aiko_process destroy [--kill] [--name NAME] UID

    \b
    • NAME: ProcessManager name, default is the local hostname
    • UID:  Unique IDentifier
    """

    do_command(ProcessManager, get_service_filter(name),
        lambda actor: actor.destroy(uid, kill), terminate=True)
    aiko.process.run()

@main.command(name="dump", help="Dump ProcessManager state")
@click.option("--name", "-n", type=str, default=None,
    help="ProcessManager name, default is the local hostname")

def dump_command(name):
    do_command(ProcessManager, get_service_filter(name),
        lambda actor: actor.dump(), terminate=True)
    aiko.process.run()

@main.command(name="exit", help="Exit ProcessManager")
@click.option("--grace_time", "-gt", type=int, default=_GRACE_TIME,
    help="Wait time before killing child processes")
@click.option("--name", "-n", type=str, default=None,
    help="ProcessManager name, default is the local hostname")

def exit_command(grace_time, name):
    do_command(ProcessManager, get_service_filter(name),
        lambda actor: actor.exit(grace_time), terminate=True)
    aiko.process.run()

def print_processes(cache, uid=None, topic_path=None):
    """One ProcessManager's table, as "list" prints it.  Pure except for
    the printing, so a test gives it a cache double"""

    safe = cache.get_safe(topic_path)
    posture = "safe" if safe else ("unsafe" if safe is False else "unknown")
    print(f"\n{topic_path}  posture: {posture}"
          f"  denied: {cache.get_denied(topic_path)}")
    processes = cache.get_processes(topic_path)
    matched = {process_uid: value
        for process_uid, value in processes.items()
        if uid is None or uid == process_uid}
    if not matched:
        print("  no processes")
    for process_uid, (pid, command_line) in matched.items():
        print(f"  uid: {process_uid}, pid: {pid}, {command_line}")

def _list_watch(name, uid):
    """Follow the process table live, through the ProcessManagerCache.

    The ProcessManager publishes one "process.<uid>" item for each process,
    so this needs no polling of "list", and no request at all"""

    cache = ProcessManagerCache(aiko.process, name)
    shown = {}

    def changed(topic_path, command, item_name, item_value):
        if not item_name.startswith("process") and item_name != "safe":
            return
        processes = cache.get_processes(topic_path)
        if processes == shown.get(topic_path):
            return                        # a change to something else
        shown[topic_path] = processes
        print_processes(cache, uid, topic_path)

    cache.add_handler(changed)
    print(f'Watching ProcessManager "{name or get_hostname()}"'
          " ... Ctrl-C to stop")
    aiko.process.run()

@main.command(name="list")
@click.option("--name", "-n", type=str, default=None,
    help="ProcessManager name, default is the local hostname")
@click.option("--watch", "-w", is_flag=True,
    help="Follow the process table live, through the ProcessManagerCache")
@click.argument("uid", type=str, required=False, default=None)

def list_command(name, uid, watch):
    """List Processes

    aiko_process list [--name NAME] [--watch] [UID]

    \b
    • NAME: ProcessManager name, default is the local hostname
    • UID:  Unique IDentifier to match

    \b
    One list is a request, which safe mode allows.  --watch instead keeps a
    live replica of the shared state, so the table stays current with no
    further requests.  Any client can hold that replica: the Dashboard page
    does, through the ProcessManagerCache.
    """

    if watch:
        return _list_watch(name, uid)

    def response_handler(response):
        if len(response):
            output = f"Processes ..."
            for process_record in response:
                uid = process_record[0]
                pid = process_record[1]
                command = process_record[2:]
                output += f"\n  uid: {uid}, pid: {pid}, {' '.join(command)}"
        else:
            output = "No processes"
        print(output)

    do_request(ProcessManager, get_service_filter(name),
        lambda actor: actor.list(_RESPONSE_TOPIC, uid),
        response_handler, _RESPONSE_TOPIC, terminate=True)
    aiko.process.run()

@main.command(name="run")
@click.option("--name", "-n", type=str, default=None,
    help="ProcessManager name, default is the local hostname")
@click.option("--watchdog", "-w", is_flag=True,
    help="Monitor ProcessManager, if required relauch it")
@click.option("--safe/--unsafe", "safe", default=SAFE,
    help="Accept only (list) and (set_log_level) from the message bus "
         "[default: --safe]")
@click.argument("definition_pathname", required=False, default=None)

def run_command(name, watchdog, safe, definition_pathname):
    """Run ProcessManager

    aiko_process run [--name NAME] [--watchdog] [--unsafe]
    [HYPERSPACE_PATHNAME]

    \b
    • NAME:                ProcessManager name, default is the local hostname
    • HYPERSPACE_PATHNAME: HyperSpace storage file-system location

    \b
    A ProcessManager starts and stops processes on its host, so --safe is
    the default: it accepts (list) and (set_log_level) from the message bus,
    and denies every other function, (create) and (exit) among them.  The
    command line is unaffected, because it does not go through the bus.
    --unsafe accepts every function the Interface declares, which is only
    appropriate where the broker is not reachable from outside a trusted
    network (ADR-023 decision 6).  The posture is published as "safe" in
    the shared state, and a denial counts in "metrics.denied".
    """

    name = name if name else get_hostname()

    tags = ["ec=true"]       # TODO: Add ECProducer tag before add to Registrar
    init_args = actor_args(name, None, None, PROTOCOL, tags)
    init_args["definition_pathname"] = definition_pathname
    init_args["watchdog"] = watchdog
    init_args["safe"] = safe
    process_manager = compose_instance(ProcessManagerImpl, init_args)
    aiko.process.run()

if __name__ == "__main__":
    main()

# --------------------------------------------------------------------------- #
