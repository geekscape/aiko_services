#!/usr/bin/env python3
#
# Aiko Services: the WhisPlay Actor command line
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# Usage
# ~~~~~
# aiko_whisplay run [--panel auto] [--camera auto] [--button auto]
#                   [--rate 3.0] [--resolution 240x180] [--action power_off]
#
# aiko_whisplay run --panel window --camera none   # On a laptop, no HAT
#
# Change a setting while it runs, as shared variables, not wire commands:
#   mosquitto_pub -t TOPIC_PATH/control -m "(update rate 1.0)"
#
# This module is a command line shell: ADR-022 "presentation/CLI shell"
# exemption from Interface composition

import click

import aiko_services as aiko
from aiko_services.main.utilities import get_hostname

from aiko_services.actors.whisplay.button import LONG_PRESS_SECONDS, choose_button
from aiko_services.actors.whisplay.camera import choose_camera
from aiko_services.actors.whisplay.panel import choose_panel
from aiko_services.actors.whisplay.whisplay import (
    ACTIONS, PROTOCOL, WhisPlayImpl, service_tags
)

PANELS = ["auto", "st7789", "window", "none"]
CAMERAS = ["auto", "picamera2", "none"]
BUTTONS = ["auto", "gpio", "none"]

@click.group()
@click.version_option()
def main():
    """Show the camera on the WhisPlay panel, and act on a long button press"""

@main.command(name="run")
@click.option("--name", "-n", type=str, default=None,
    help="Actor name, default is the local host name")
@click.option("--panel", "-p", type=click.Choice(PANELS), default="auto",
    help="Where the picture goes")
@click.option("--camera", "-c", type=click.Choice(CAMERAS), default="auto",
    help="Where the picture comes from")
@click.option("--button", "-b", type=click.Choice(BUTTONS), default="auto",
    help="The button to listen to")
@click.option("--action", "-a", type=click.Choice(ACTIONS), default="power_off",
    help="What a long button press does")
@click.option("--rate", "-r", type=str, default="3.0",
    help="Frames each second")
@click.option("--resolution", "-R", type=str, default="240x180",
    help="What is read from the camera")
@click.option("--rotate", type=click.Choice(["0", "90", "180", "270"]),
    default="0", help="Degrees to turn the camera image")
@click.option("--long_press", "-l", type=float, default=LONG_PRESS_SECONDS,
    help="Seconds that make a press a long one")

def run_command(name, panel, camera, button, action, rate, resolution,
    rotate, long_press):

    """Run the WhisPlay Actor"""

    panel_impl = choose_panel(panel)
    camera_impl = choose_camera(camera)
    button_impl = choose_button(button, long_press_seconds=long_press)

    init_args = aiko.actor_args(
        name or get_hostname(),
        protocol=PROTOCOL,
        tags=service_tags(panel_impl.device))
    init_args.update({
        "panel": panel_impl, "camera": camera_impl, "button": button_impl,
        "action": action, "rate": rate, "resolution": resolution,
        "rotate": rotate
    })
    aiko.compose_instance(WhisPlayImpl, init_args)
    try:
        aiko.process.run()
    finally:
        for device in (camera_impl, panel_impl, button_impl):
            try:
                device.close()
            except Exception:                            # noqa: BLE001
                pass

if __name__ == "__main__":
    main()

# --------------------------------------------------------------------------- #
