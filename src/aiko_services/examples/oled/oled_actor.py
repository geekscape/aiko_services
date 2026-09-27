#!/usr/bin/env python3
#
# Aiko Services example: an Actor that draws on an SSD1306 OLED
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# One concept: an Actor that owns a small display and draws what remote
# clients ask for.  It speaks part of the "display:0" protocol (the Canvas
# commands clear, log and text), so the Display Actor's own clients drive
# it unchanged: "aiko_display text ...", "aiko_display keys" and the
# Dashboard page.  The full Display Actor is aiko_services.actors.display.
#
# Usage
# ~~~~~
#   ./oled_actor.py [-a 0x3C] [-n NAME]   # SSD1306 at I2C address 0x3C
#   ./oled_actor.py -a none               # draw in the terminal instead
#
#   aiko_display -n NAME text 0 8 Aloha   # Y=0 is the bottom row
#   aiko_display -n NAME log hello world  # scroll up, write the bottom row
#   aiko_display -n NAME clear
#   mosquitto_pub -t TOPIC_PATH/in -m "(text 0 0 hello)"
#   aiko_display -n NAME exit            # blank the panel and end the Actor
#
# To Do
# ~~~~~
# - None, yet !

import os
import sys

import click
from PIL import Image, ImageDraw, ImageFont

import aiko_services as aiko
from aiko_services.main.utilities import get_hostname

# The same protocol as aiko_services.actors.display.PROTOCOL, written here
# so that this example depends only on the framework
PROTOCOL = f"{aiko.SERVICE_PROTOCOL_AIKO}/display:0"
WIDTH, HEIGHT, ROW = 128, 64, 8     # pixels; one text row is 8 pixels high

class Panel:
    """Where the picture goes: open(), show(image) and close()"""

    def open(self):
        pass

    def show(self, image):
        pass

    def close(self):
        pass

class Ssd1306Panel(Panel):
    """A real SSD1306 on the I2C bus, through luma.oled"""

    def __init__(self, address):
        self.address = address
        self.device = None

    def open(self):
        from luma.core.interface.serial import i2c   # only needed here
        from luma.oled.device import ssd1306
        self.device = ssd1306(i2c(port=1, address=self.address))

    def show(self, image):
        self.device.display(image)

    def close(self):
        if self.device:
            self.device.cleanup()                    # blanks the panel

class TerminalPanel(Panel):
    """The picture in the terminal: one character per pair of pixel rows"""

    def show(self, image):
        pixels = image.load()
        rows = ["".join(" ▀▄█"[(pixels[x, y] > 0) + 2 * (pixels[x, y + 1] > 0)]
                        for x in range(image.width))
                for y in range(0, image.height, 2)]
        sys.stdout.write("\x1b[H\x1b[2J" + "\n".join(rows) + "\n")
        sys.stdout.flush()

def open_panel(address):
    """The SSD1306 when there is an I2C bus, else the terminal"""

    if address is not None and os.path.exists("/dev/i2c-1"):
        return Ssd1306Panel(address)
    return TerminalPanel()

class OLEDActor(aiko.Actor):
    """Draws on a panel.  Coordinates start at the bottom-left, as in the
    display:0 protocol: Y=0 is the bottom row of pixels"""

    def __init__(self, context):
        context.call_init(self, "Actor", context)
        self.panel = context.get_parameters()["panel"]
        self.image = Image.new("1", (WIDTH, HEIGHT))
        self.font = ImageFont.load_default(size=ROW)
        self.panel.open()
        self.panel.show(self.image)

    def clear(self):
        self.image.paste(0, (0, 0, WIDTH, HEIGHT))
        self.panel.show(self.image)

    def log(self, *words):
        self.image.paste(self.image.crop((0, ROW, WIDTH, HEIGHT)), (0, 0))
        self.image.paste(0, (0, HEIGHT - ROW, WIDTH, HEIGHT))
        self._draw(0, 0, words)

    def text(self, x, y, *words):
        self._draw(int(x), int(y), words)

    def _draw(self, x, y, words):
        # Pillow counts Y down from the top: the text row's bottom edge is
        # at HEIGHT - y, and anchor "ld" puts the descenders' bottom there
        ImageDraw.Draw(self.image).text((x, HEIGHT - y), " ".join(map(str, words)),
                                        font=self.font, fill=1, anchor="ld")
        self.panel.show(self.image)

@click.command("main", help="An Actor that draws on an SSD1306 OLED")
@click.option("--address", "-a", default="0x3C", show_default=True,
              help="I2C address of the SSD1306, or none for the terminal")
@click.option("--name", "-n", default=get_hostname(), show_default=True,
              help="Actor name, used by clients to find it")
def main(address, name):
    address = None if address.lower() == "none" else int(address, 0)
    panel = open_panel(address)
    tags = ["ec=true", f"device={'ssd1306' if address else 'terminal'}", "canvas=0"]
    aiko.compose_instance(OLEDActor, aiko.actor_args(
        name, parameters={"panel": panel}, protocol=PROTOCOL, tags=tags))
    try:
        aiko.process.run()
    finally:
        panel.close()

if __name__ == "__main__":
    main()
