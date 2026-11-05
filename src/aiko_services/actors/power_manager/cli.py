#!/usr/bin/env python3
#
# Aiko Services: the PowerManager command line
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# Usage
# ~~~~~
# aiko_power_manager --help
#
# aiko_power_manager run [--device auto] [--period 5.0] [--log DIR]
#                        [--safe | --unsafe] [--advisory | --enforce]
#                        [--inputs auto]
# aiko_power_manager run --device mock --period 1    # On a laptop
# aiko_power_manager run --period 60                 # In the field
# aiko_power_manager run --enforce                   # Acting, in the field,
#                                                    #   after the battery
#                                                    #   pack is measured
#
# aiko_power_manager sample [--device auto]          # One reading, as JSON
#
# Change the sample period while it runs, as a shared variable:
#   mosquitto_pub -t TOPIC_PATH/control -m "(update sample_period_s 60)"
#
# aiko_power_manager hold on                         # Assert the power hold
# aiko_power_manager hold off --force                # *** CUTS THE POWER ***
# aiko_power_manager signal booted                   # One sound
#
# aiko_power_manager render unit | hook | grant      # Prints, changes nothing
# sudo aiko_power_manager install unit               # The only writer
# aiko_power_manager verify                          # What is in place
#
# "hold off" is how the shutdown hook releases the hold, and the hook is its
# only caller.  --force is needed at a terminal, because an undocked host
# stops the moment the line goes low.
#
# This module is a command line shell: ADR-022 "presentation/CLI shell"
# exemption from Interface composition

import json
import signal

import click

import aiko_services as aiko
from aiko_services.main.utilities import get_hostname

from aiko_services.actors.power_manager.hold import (
    HOLD_GPIO, HoldNotAvailable, hold_state, set_hold
)
from aiko_services.actors.power_manager.button import choose_power_inputs
from aiko_services.actors.power_manager.power_manager import (
    ENFORCE, LOG_DIRECTORY, PERIOD_DEVELOPMENT, SAFE, choose_power_manager,
    power_manager_args
)
from aiko_services.actors.power_manager.render import (
    ARTIFACTS, InstallRefused, install as install_artifact, paths, render,
    verify
)
from aiko_services.actors.power_manager.signal import PATTERNS

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
@click.option("--enforce/--advisory", "enforce", default=ENFORCE,
    help="Act on the policy, or publish it and act on nothing "
         "[default: --advisory]")
@click.option("--inputs", "-i", "inputs",
    type=click.Choice(["auto", "gpio", "none"]), default="auto",
    help="The button and dock lines [default: auto]")

def run_command(name, device, period, log_directory, no_log, keep_days, safe,
    enforce, inputs):
    """Run the PowerManager Actor

    \b
    Safe mode accepts (sample) and the log level, and denies every other
    function.  The command line is unaffected, because it does not go
    through the bus.  --unsafe accepts every function the Interface
    declares, which is only appropriate where the broker is not reachable
    from outside a trusted network (ADR-023 decision 6).  The posture is
    published as "safe" in the shared state, and a denial counts in
    "metrics.denied".

    \b
    --advisory is the default, and it is not timidity.  The thresholds come
    from a data sheet, so the policy decides on every sample, publishes
    what it would do in "policy_would" and "policy_reason", and acts on
    nothing.  Read the log, set the thresholds from the battery pack you have, and
    then pass --enforce.
    """

    implementation = choose_power_manager(device)
    init_args = power_manager_args(
        name or get_hostname(), implementation.device,
        declared=implementation.DECLARED_PROPERTIES,
        period=period, keep_days=keep_days, safe=safe, enforce=enforce,
        inputs=choose_power_inputs(inputs),
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
        f"{found or 'none'}, "
        f"{'ENFORCING' if enforce else 'advisory'}", err=True)
    if enforce:
        click.echo("# the policy will stop this host when it decides to",
            err=True)

    # A stop must reach close(), so that every line this Actor claimed is
    # released.  Without it the run ends on an unhandled signal, "finally"
    # never runs, and a claimed output stays driven after the process is
    # gone: measured on the hardware on 2026-11-05.  The power hold is the
    # opposite case and is never claimed here (ADR-028 decision 5)
    signal.signal(signal.SIGTERM, lambda *_: aiko.process.terminate())
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
        log_directory=None, timer=False, inputs=choose_power_inputs("none"))
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

@main.command(name="hold")
@click.argument("state", type=click.Choice(["on", "off"]))
@click.option("--gpio", "-g", type=int, default=HOLD_GPIO,
    help=f"The hold line [default: {HOLD_GPIO}]")
@click.option("--force", is_flag=True,
    help='Required for "off", which cuts the power of an undocked host')

def hold_command(state, gpio, force):
    """Assert or release the power hold, then exit

    \b
    The pin keeps its state after this command exits, because nothing
    claims it.  That is the whole mechanism: a long-lived process cannot
    hold this line, because the GPIO character device releases it when the
    process exits (ADR-028 decision 5).

    \b
    "off" cuts the power of an undocked host.  The shutdown hook is its
    only proper caller, after the file systems are unmounted.  At a
    terminal it needs --force.
    """

    on = state == "on"
    if not on and not force:
        raise SystemExit(
            "hold off cuts the power of an undocked host: pass --force if "
            "that is what you mean.  The shutdown hook does this itself")
    try:
        result = set_hold(on, gpio)
    except HoldNotAvailable as error:
        raise SystemExit(f"No hold on this platform: {error}")
    except OSError as error:
        raise SystemExit(f"The hold did not change: {error}")
    click.echo(f"hold {result} (GPIO {gpio})")

@main.command(name="signal")
@click.argument("name", type=click.Choice(sorted(PATTERNS)))
@click.option("--buzzer", "-b", type=click.Choice(["auto", "gpio", "none"]),
    default="auto", help="The buzzer to sound [default: auto]")

def signal_command(name, buzzer):
    """Sound one pattern, then exit"""

    from aiko_services.actors.power_manager.signal import (
        choose_buzzer, pattern_seconds
    )
    import time

    device = choose_buzzer(buzzer)
    try:
        device.open()
    except Exception as error:                           # noqa: BLE001
        raise SystemExit(f"No buzzer: {error}")
    try:
        device.play(name)
        time.sleep(pattern_seconds(name) + 0.1)
    finally:
        device.close()
    click.echo(f"{name} on {device.device} "
        f"({pattern_seconds(name)} s)")

@main.command(name="render")
@click.argument("artifact", type=click.Choice(list(ARTIFACTS)))
@click.option("--account", "-a", type=str, default=None,
    help="The account that runs the Actor, for the grant")

def render_command(artifact, account):
    """Print one file that the operating system must hold, and change
    nothing

    \b
    "unit" asserts the hold at start-up.  "hook" releases it at shutdown,
    and never on a restart.  "grant" lets the unprivileged Actor power the
    host off and remount read-only.  Read each one before you install it
    (ADR-026 decision 3).
    """

    try:
        click.echo(render(artifact, account=account), nl=False)
    except ValueError as error:
        raise SystemExit(str(error))

@main.command(name="install")
@click.argument("artifact", type=click.Choice(list(ARTIFACTS)))
@click.option("--account", "-a", type=str, default=None,
    help="The account that runs the Actor, for the grant")
@click.option("--path", "-p", type=str, default=None,
    help="Write here instead of where the artifact belongs")

def install_command(artifact, account, path):
    """Write one rendered file.  The only command here that changes the host

    \b
    Needs a privilege, so a person runs it.  The grant is validated before
    it is written, because a malformed file in the sudoers directory denies
    every account the privilege to repair it.
    """

    try:
        text = render(artifact, account=account)
        written = install_artifact(artifact, text, path=path)
    except (ValueError, InstallRefused) as error:
        raise SystemExit(f"Not installed: {error}")
    click.echo(f"{artifact} written to {written}")
    if artifact == "unit":
        click.echo("Now: systemctl daemon-reload && "
            "systemctl enable aiko_power_hold", err=True)

@main.command(name="verify")
def verify_command():
    """Report what the operating system holds, and the hold line

    \b
    Nothing here is used, only read.  A host that cannot power itself off
    has a battery policy that is advisory, whatever its thresholds say.
    """

    for name, state in verify().items():
        click.echo(f"{name:6} {state:9} {paths()[name]}")
    click.echo(f"{'hold':6} {hold_state():9} GPIO {HOLD_GPIO}")

if __name__ == "__main__":
    main()

# --------------------------------------------------------------------------- #
