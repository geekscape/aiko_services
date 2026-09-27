# Aiko Services: display Actor (the display:0 protocol)
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# A remote display as an Actor: protocol "display:0", the composite of the
# Canvas, Screen and Interaction aspects.  An SSD1306 128x64 OLED on a
# Linux SBC is the reference device; a desktop window, the terminal or a
# PNG file emulate it.  A status display for headless hosts, a
# wire-compatible canvas for aiko_engine_mp clients, applets (games,
# drawings, a clock, a demo) that run on the display, a keys console and
# a Dashboard page.  An Interface design and evaluation, not an example:
# examples/oled/ holds the simple newcomer example.
#
# Usage: aiko_display --help  (see cli.py); clients import the modules
# outputs, console and dashboard_plugin by name.

from aiko_services.actors.display.display import (  # noqa: F401
    ASPECT_TAGS, Canvas, Display, DisplayImpl, Interaction, PROTOCOL,
    PROTOCOL_TYPE, SETTINGS, SETTINGS_SPEC, Screen, WIRE_COMMANDS,
    service_filter, service_tags,
)

__all__ = [
    "ASPECT_TAGS", "Canvas", "Display", "DisplayImpl", "Interaction",
    "PROTOCOL", "PROTOCOL_TYPE", "SETTINGS", "SETTINGS_SPEC", "Screen",
    "WIRE_COMMANDS", "service_filter", "service_tags",
]
