#!/usr/bin/env python3
#
# Aiko Services: Daemon Supervisor
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# Start Aiko Services when the operating system starts.
#
# The operating system starts one process for each host: the
# ProcessManager.  Everything else, including the broker, the Registrar,
# Actors, Agents and Pipelines, comes from the ProcessManager definition
# file.  So the DaemonDefinition is small on purpose: it describes one process,
# not a fleet.
#
# A DaemonDefinition is rendered as the platform's own service description, by
# the DaemonSupervisor Impl for that platform ...
#
#   Linux:   systemd unit        /etc/systemd/system/NAME.service
#   macOS:   launchd agent       ~/Library/LaunchAgents/LABEL.plist
#   Windows: not implemented, see "To Do"
#
# render() writes nothing, so it is safe to look before you install.
# install() is the only function that changes the host.
#
# Usage
# ~~~~~
# aiko_supervisor render  [options]  # Show the service description
# aiko_supervisor install [options]  # Write it, then enable the service
#
# To Do
# ~~~~~
# * Windows: a TaskSchedulerDaemonSupervisorImpl, with its own render()
# * Impls for "start", "stop" and "status" to report structured results,
#   instead of the command output
# * Consider a DaemonSupervisor Actor, so that a host reports which Services it
#   starts, and why a Service didn't start

from abc import abstractmethod
from dataclasses import dataclass, field, replace
from pathlib import Path
import platform as platform_module
import shutil
import subprocess

import aiko_services as aiko

__all__ = [
    "GRACE_TIME", "STOP_TIMEOUT_MARGIN", "DaemonDefinition", "DaemonSupervisor",
    "DaemonSupervisorNotSupported", "UnsupportedDaemonSupervisorImpl", "choose_daemon_supervisor",
    "daemon_supervisor_args"
]

# The ProcessManager "exit" grace time, before SIGTERM becomes SIGKILL.
# See process_manager.py "_GRACE_TIME"

GRACE_TIME = 5

# The operating system must wait longer than the ProcessManager waits for
# its own processes.  Otherwise the operating system kills the
# ProcessManager while its processes are still stopping, which leaves them
# running and makes a clean shutdown impossible

STOP_TIMEOUT_MARGIN = 25

class DaemonSupervisorNotSupported(OSError):
    """This platform has no DaemonSupervisor Impl"""

# The DaemonDefinition ----------------------------------------------------------- #

@dataclass(frozen=True)
class DaemonDefinition:
    """One process that the operating system starts and keeps running.

    name:                  Service name, usually the host name
    description:           One line, shown by the operating system
    executable:            Absolute pathname, usually a virtual environment
    arguments:             Command arguments
    user:                  Account that runs the process (Linux only)
    working_directory:     Directory for the process
    environment:           Environment variables for the process
    restart:               "always", "on-failure" or "no"
    restart_seconds:       Delay before a restart
    stop_signal:           Signal that asks the process to stop
    stop_timeout_seconds:  How long to wait, before the signal becomes
                           SIGKILL.  Must be more than the ProcessManager
                           grace time
    after, wants:          Service ordering (Linux only)
    """

    name: str
    description: str = "Aiko Services ProcessManager"
    executable: str = "aiko_process"
    arguments: tuple = ()
    user: str = ""
    working_directory: str = ""
    environment: dict = field(default_factory=dict)
    restart: str = "always"
    restart_seconds: int = 5
    stop_signal: str = "SIGTERM"
    stop_timeout_seconds: int = GRACE_TIME + STOP_TIMEOUT_MARGIN
    after: tuple = ("network-online.target",)
    wants: tuple = ("network-online.target",)

    def __post_init__(self):
        if not self.name:
            raise ValueError("DaemonDefinition: name is necessary")
        if self.restart not in ["always", "on-failure", "no"]:
            raise ValueError(
                f'DaemonDefinition: restart must be "always", "on-failure" or '
                f'"no", not "{self.restart}"')
        if self.stop_timeout_seconds <= GRACE_TIME:
            raise ValueError(
                f"DaemonDefinition: stop_timeout_seconds ({self.stop_timeout_seconds}"
                f") must be more than the ProcessManager grace time "
                f"({GRACE_TIME}), or its processes are killed before they stop")

    @classmethod
    def for_process_manager(cls, name, definition_pathname,
        executable="aiko_process", grace_time=GRACE_TIME, **parameters):

        """A DaemonDefinition that starts the ProcessManager for one host.

        The ProcessManager "--watchdog" option is recorded, but nothing
        relaunches anything yet, so the operating system does the
        restarting: "restart" is "always".

        PYTHONUNBUFFERED is set, because Python buffers stdout when it is
        a pipe, which is what a service gets.  Without it, the log stays
        in the buffer and the service looks silent"""

        environment = {
            "PYTHONUNBUFFERED": "1", **parameters.pop("environment", {})}
        return cls(
            name=name,
            executable=executable,
            arguments=("run", "--name", name, definition_pathname),
            stop_timeout_seconds=grace_time + STOP_TIMEOUT_MARGIN,
            environment=environment,
            **parameters)

    def command_line(self):
        """The executable and its arguments, as a list"""

        return [self.executable, *self.arguments]

    def with_environment(self, **variables):
        """A copy, with more environment variables"""

        return replace(self, environment={**self.environment, **variables})

# The Interface ------------------------------------------------------------ #

class DaemonSupervisor(aiko.Interface):
    """Starts Aiko Services when the operating system starts.

    render(spec) returns the platform's service description as text and
    changes nothing.  pathname(spec) is where install() writes it.
    install() writes that file and returns its pathname, uninstall()
    removes it, and start(), stop() and status() use the platform's own
    command.  Every function is local: a DaemonSupervisor is not on the message
    bus
    """

    aiko.Interface.default(
        "DaemonSupervisor", "aiko_services.main.daemon_supervisor.daemon_supervisor.UnsupportedDaemonSupervisorImpl")

    @abstractmethod
    def render(self, spec):
        """The service description for this DaemonDefinition, as text"""

    @abstractmethod
    def pathname(self, spec):
        """Where install() writes the service description"""

    @abstractmethod
    def install(self, spec, enable=True):
        """Write the service description; enable it, unless told not to"""

    @abstractmethod
    def uninstall(self, spec):
        """Stop the service, then remove its service description"""

    @abstractmethod
    def start(self, spec):
        """Start the service now"""

    @abstractmethod
    def stop(self, spec):
        """Stop the service now"""

    @abstractmethod
    def status(self, spec):
        """What the platform says about the service"""

class UnsupportedDaemonSupervisorImpl(DaemonSupervisor):
    """The default Impl: every function reports the platform, instead of
    doing something that can't work.  Windows gets this, until it has an
    Impl of its own"""

    platform = "unsupported"

    def __init__(self, context, **_):
        pass

    def _not_supported(self):
        raise DaemonSupervisorNotSupported(
            f'No DaemonSupervisor for platform "{platform_module.system()}": '
            f"use systemd (Linux) or launchd (macOS)")

    def render(self, spec):
        self._not_supported()

    def pathname(self, spec):
        self._not_supported()

    def install(self, spec, enable=True):
        self._not_supported()

    def uninstall(self, spec):
        self._not_supported()

    def start(self, spec):
        self._not_supported()

    def stop(self, spec):
        self._not_supported()

    def status(self, spec):
        self._not_supported()

# Shared by the Impls that run a platform command -------------------------- #

def run_command(command_line):
    """Run a platform command, return (returncode, output).  The output
    holds both stdout and stderr, because that is what a diagnostic needs"""

    if not shutil.which(command_line[0]):
        raise DaemonSupervisorNotSupported(f'Command not found: "{command_line[0]}"')
    result = subprocess.run(
        command_line, capture_output=True, text=True, check=False)
    return result.returncode, (result.stdout + result.stderr).strip()

# Composition -------------------------------------------------------------- #

def daemon_supervisor_args(**parameters):
    """init_args for composing a DaemonSupervisor Impl (like output_args)"""

    return {"context": aiko.Context(), **parameters}

def choose_daemon_supervisor(platform="auto", **parameters):
    """The composed DaemonSupervisor for a platform.  "auto" is this host's
    platform.  Nothing is written and no command is run here: see
    render() and install()"""

    from aiko_services.main.daemon_supervisor.launchd import LaunchdDaemonSupervisorImpl
    from aiko_services.main.daemon_supervisor.systemd import SystemdDaemonSupervisorImpl

    if platform == "auto":
        system = platform_module.system()
        platform = {"Linux": "systemd", "Darwin": "launchd"}.get(
            system, "unsupported")
    impls = {
        "systemd": SystemdDaemonSupervisorImpl,
        "launchd": LaunchdDaemonSupervisorImpl,
        "unsupported": UnsupportedDaemonSupervisorImpl
    }
    if platform not in impls:
        raise ValueError(
            f'Unknown platform "{platform}": one of {sorted(impls)}')
    return aiko.compose_instance(impls[platform], daemon_supervisor_args(**parameters))

# --------------------------------------------------------------------------- #
