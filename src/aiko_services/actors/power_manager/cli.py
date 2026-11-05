#!/usr/bin/env python3
#
# Aiko Services: the PowerManager command line
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# Usage
# ~~~~~
# aiko_power_manager --help
#
# aiko_power_manager run [--device auto] [--period 5.0] [--log DIR]
#                        [--safe | --unsafe]
# aiko_power_manager run --device mock --period 1    # On a laptop
# aiko_power_manager run --period 60                 # In the field
#
# aiko_power_manager sample [--device auto]          # One reading, as JSON
#
# Change the sample period while it runs, as a shared variable:
#   mosquitto_pub -t TOPIC_PATH/control -m "(update sample_period_s 60)"
#
# Phase 1 is read-only, so "hold", "signal", "render", "install" and
# "verify" are not here yet.  Each one changes a host, and each one arrives
# with the phase that designs and tests it.
#
# This module is a command line shell: ADR-022 "presentation/CLI shell"
# exemption from Interface composition

import json

import click

import aiko_services as aiko
from aiko_services.main.utilities import get_hostname

from aiko_services.actors.power_manager.power_manager import (
    LOG_DIRECTORY, PERIOD_DEVELOPMENT, SAFE, choose_power_manager,
    power_manager_args
)

DEVICES = ["auto", "pmm", "mock"]

@click.group()
@click.version_option()
def main():
    """Report the supply and the battery of this host, and log them"""

@main.command(name="run")
@click.option("--name", "-n", type=str, default=None,
    help="Actor name, default is the local host name")
@click.option("--device", "-d", type=click.Choice(DEVICES), default="auto",
    help="Where the readings come from [default: auto]")
@click.option("--period", "-p", type=float, default=PERIOD_DEVELOPMENT,
    help=f"Seconds between samples [default: {PERIOD_DEVELOPMENT}]")
@click.option("--log", "-l", "log_directory", type=str, default=LOG_DIRECTORY,
    help=f"Where the JSON lines go [default: {LOG_DIRECTORY}]")
@click.option("--no_log", is_flag=True, help="Do not write a log")
@click.option("--keep_days", "-k", type=int, default=None,
    help="Day files to keep [default: every one]")
@click.option("--safe/--unsafe", "safe", default=SAFE,
    help="Accept only (sample) and (set_log_level) from the message bus "
         "[default: --safe]")

def run_command(name, device, period, log_directory, no_log, keep_days, safe):
    """Run the PowerManager Actor

    \b
    Safe mode accepts (sample) and the log level, and denies every other
    function.  The command line is unaffected, because it does not go
    through the bus.  --unsafe accepts every function the Interface
    declares, which is only appropriate where the broker is not reachable
    from outside a trusted network (ADR-023 decision 6).  The posture is
    published as "safe" in the shared state, and a denial counts in
    "metrics.denied".
    """

    implementation = choose_power_manager(device)
    init_args = power_manager_args(
        name or get_hostname(), implementation.device,
        declared=implementation.DECLARED_PROPERTIES,
        period=period, keep_days=keep_days, safe=safe,
        log_directory=None if no_log else log_directory)
    power_manager = aiko.compose_instance(implementation, init_args)
    try:
        power_manager.open()
    except OSError as error:
        raise SystemExit(f"Cannot open {implementation.device}: {error}")

    # The tags carry what this Implementation declares, and the shared state
    # carries what open() actually found on this host
    found = power_manager.publish_properties()
    click.echo(f"# device {implementation.device}, properties "
        f"{found or 'none'}", err=True)
    try:
        aiko.process.run()
    finally:
        power_manager.close()

@main.command(name="sample")
@click.option("--device", "-d", type=click.Choice(DEVICES), default="auto",
    help="Where the readings come from [default: auto]")
@click.option("--count", "-c", type=int, default=1,
    help="Readings to take [default: 1]")

def sample_command(device, count):
    """Print one reading as JSON, with no Actor and no broker

    \b
    This is the first thing to run on a new host: it says which parts
    answer, and what they report, with no message bus in the way.
    """

    implementation = choose_power_manager(device)
    init_args = power_manager_args(
        get_hostname(), implementation.device,
        declared=implementation.DECLARED_PROPERTIES,
        log_directory=None, timer=False)
    power_manager = aiko.compose_instance(implementation, init_args)
    try:
        found = power_manager.open()
    except OSError as error:
        raise SystemExit(f"Cannot open {implementation.device}: {error}")
    click.echo(f"# device {implementation.device}, found {found or 'nothing'}",
        err=True)
    try:
        for _ in range(max(1, count)):
            reading = power_manager.reading()
            click.echo(json.dumps(reading.as_dict(), sort_keys=True))
    finally:
        power_manager.close()

if __name__ == "__main__":
    main()

# --------------------------------------------------------------------------- #
