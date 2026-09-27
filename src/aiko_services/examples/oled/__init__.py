# Aiko Services: OLED example
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~
# An SSD1306 128x64 OLED as a display Actor (protocol "display:0", the
# composite of the Canvas, Screen and Interaction aspects): a status display
# for headless hosts, a wire-compatible canvas for aiko_engine_mp clients,
# and applets (games, drawings, demo) that run on the display.
#
# Usage: aiko_oled --help  (see oled.py)

from aiko_services.examples.oled.oled import (  # noqa: F401
    ASPECT_TAGS, Canvas, Display, Interaction, OLEDImpl, PROTOCOL,
    PROTOCOL_TYPE, SETTINGS, SETTINGS_SPEC, Screen, WIRE_COMMANDS,
    service_tags,
)
