#!/usr/bin/env python3
#
# Aiko Services: Daemon Supervisor command line
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# Start Aiko Services when the operating system starts.  The operating
# system starts the ProcessManager, and the ProcessManager definition
# file starts everything else.
#
# Usage
# ~~~~~
# aiko_supervisor render  [options] DEFINITION_PATHNAME
# aiko_supervisor install [options] DEFINITION_PATHNAME   # Changes the host
# aiko_supervisor uninstall [--name NAME]
# aiko_supervisor start | stop | status [--name NAME]
#
# Examples
# ~~~~~~~~
# aiko_supervisor render ~/aiko01_supervisor.json              # Look, before you install
# sudo aiko_supervisor install ~/aiko01_supervisor.json \
#   --user claude --executable ~/venvs/venv_3.13/bin/aiko_process
#
# This module is a command line shell: ADR-022 "presentation/CLI shell"
# exemption from Interface composition

import click

from aiko_services.main.daemon_supervisor.daemon_supervisor import (
    DaemonDefinition, DaemonSupervisorNotSupported, choose_daemon_supervisor
)
from aiko_services.main.utilities import get_hostname

PLATFORMS = ["auto", "systemd", "launchd", "unsupported"]

def _spec(name, definition_pathname, executable, user, working_directory,
    mqtt_host, namespace, restart, grace_time, after=(), wants=(),
    environment=()):

    """The DaemonDefinition for the ProcessManager of one host"""

    variables = {}
    for setting in environment:
        if "=" not in setting:
            raise SystemExit(
                f'Error: --environment needs "NAME=VALUE", not "{setting}"')
        name_, value = setting.split("=", 1)
        variables[name_] = value
    environment = variables
    if mqtt_host:
        environment["AIKO_MQTT_HOST"] = mqtt_host
    if namespace:
        environment["AIKO_NAMESPACE"] = namespace

    return DaemonDefinition.for_process_manager(
        name=name or get_hostname(),
        definition_pathname=definition_pathname,
        executable=executable,
        grace_time=grace_time,
        user=user,
        working_directory=working_directory,
        environment=environment,
        restart=restart,
        after=tuple(after),
        wants=tuple(wants))

def _supervisor(platform):
    try:
        return choose_daemon_supervisor(platform)
    except DaemonSupervisorNotSupported as not_supported:
        raise SystemExit(f"Error: {not_supported}")

def common_options(function):
    """Options shared by the commands that need a complete DaemonDefinition"""

    function = click.option("--name", "-n", type=str, default=None,
        help="Service name, default is the local host name")(function)
    function = click.option("--platform", "-p", type=click.Choice(PLATFORMS),
        default="auto", help="Which DaemonSupervisor to use")(function)
    return function

@click.group()
@click.version_option()
def main():
    """Start Aiko Services when the operating system starts"""

@main.command(name="render")
@common_options
@click.option("--executable", "-e", type=str, default="aiko_process",
    help="ProcessManager pathname, usually in a virtual environment")
@click.option("--user", "-u", type=str, default="",
    help="Account that runs the ProcessManager (Linux only)")
@click.option("--working_directory", "-w", type=str, default="",
    help="Directory for the ProcessManager process")
@click.option("--mqtt_host", "-m", type=str, default="",
    help="AIKO_MQTT_HOST for the ProcessManager")
@click.option("--namespace", "-ns", type=str, default="",
    help="AIKO_NAMESPACE for the ProcessManager")
@click.option("--restart", "-r",
    type=click.Choice(["always", "on-failure", "no"]), default="always",
    help='Restart policy, "always" because --watchdog does nothing yet')
@click.option("--grace_time", "-gt", type=int, default=5,
    help="ProcessManager grace time, which sets the stop timeout")
@click.option("--after", "-a", multiple=True,
    default=["network-online.target"],
    help="Start after these services (Linux only), repeat for each one")
@click.option("--wants", multiple=True, default=["network-online.target"],
    help="Wants these services (Linux only), repeat for each one")
@click.option("--environment", "-E", multiple=True,
    help='Environment variable "NAME=VALUE", repeat for each one')
@click.argument("definition_pathname", type=str)

def render_command(name, platform, executable, user, working_directory,
    mqtt_host, namespace, restart, grace_time, after, wants, environment,
    definition_pathname):

    """Show the service description, and change nothing

    \b
    • DEFINITION_PATHNAME: ProcessManager definition, a ".json" file
    """

    supervisor = _supervisor(platform)
    spec = _spec(name, definition_pathname, executable, user,
        working_directory, mqtt_host, namespace, restart, grace_time,
        after, wants, environment)
    print(f"# {supervisor.pathname(spec)}")
    print(supervisor.render(spec))

@main.command(name="install")
@common_options
@click.option("--executable", "-e", type=str, default="aiko_process",
    help="ProcessManager pathname, usually in a virtual environment")
@click.option("--user", "-u", type=str, default="",
    help="Account that runs the ProcessManager (Linux only)")
@click.option("--working_directory", "-w", type=str, default="",
    help="Directory for the ProcessManager process")
@click.option("--mqtt_host", "-m", type=str, default="",
    help="AIKO_MQTT_HOST for the ProcessManager")
@click.option("--namespace", "-ns", type=str, default="",
    help="AIKO_NAMESPACE for the ProcessManager")
@click.option("--restart", "-r",
    type=click.Choice(["always", "on-failure", "no"]), default="always",
    help='Restart policy, "always" because --watchdog does nothing yet')
@click.option("--grace_time", "-gt", type=int, default=5,
    help="ProcessManager grace time, which sets the stop timeout")
@click.option("--after", "-a", multiple=True,
    default=["network-online.target"],
    help="Start after these services (Linux only), repeat for each one")
@click.option("--wants", multiple=True, default=["network-online.target"],
    help="Wants these services (Linux only), repeat for each one")
@click.option("--environment", "-E", multiple=True,
    help='Environment variable "NAME=VALUE", repeat for each one')
@click.option("--enable/--no-enable", default=True,
    help="Start the service when the host starts")
@click.argument("definition_pathname", type=str)

def install_command(name, platform, executable, user, working_directory,
    mqtt_host, namespace, restart, grace_time, after, wants, environment,
    enable, definition_pathname):

    """Write the service description, then enable the service

    \b
    • DEFINITION_PATHNAME: ProcessManager definition, a ".json" file
    """

    supervisor = _supervisor(platform)
    spec = _spec(name, definition_pathname, executable, user,
        working_directory, mqtt_host, namespace, restart, grace_time,
        after, wants, environment)
    try:
        pathname = supervisor.install(spec, enable=enable)
    except PermissionError:
        raise SystemExit(
            f"Error: can't write {supervisor.pathname(spec)}, try sudo")
    print(f"Installed: {pathname}")

@main.command(name="uninstall")
@common_options
def uninstall_command(name, platform):
    """Stop the service, then remove its service description"""

    supervisor = _supervisor(platform)
    spec = DaemonDefinition(name=name or get_hostname())
    print(f"Uninstalled: {supervisor.uninstall(spec)}")

def _report(returncode, output):
    if output:
        print(output)
    raise SystemExit(returncode)

@main.command(name="start")
@common_options
def start_command(name, platform):
    """Start the service now"""

    supervisor = _supervisor(platform)
    _report(*supervisor.start(DaemonDefinition(name=name or get_hostname())))

@main.command(name="stop")
@common_options
def stop_command(name, platform):
    """Stop the service now"""

    supervisor = _supervisor(platform)
    _report(*supervisor.stop(DaemonDefinition(name=name or get_hostname())))

@main.command(name="status")
@common_options
def status_command(name, platform):
    """What the platform says about the service"""

    supervisor = _supervisor(platform)
    _report(*supervisor.status(DaemonDefinition(name=name or get_hostname())))

if __name__ == "__main__":
    main()

# --------------------------------------------------------------------------- #
