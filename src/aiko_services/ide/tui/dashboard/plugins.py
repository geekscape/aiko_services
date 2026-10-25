#!/usr/bin/env python3
#
# Aiko Services: the Aiko Dashboard's default plug-in registry
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# "aiko_dashboard" loads this module when no "--plugin" is given, so these
# are the pages that are always there.  Each key is the Service name or
# the protocol type, which is what the Dashboard derives from a selected
# Service.
#
# A page lives in its own module, and this file only names them, so that a
# page is added or removed in one line and nothing else moves.
#
# A page for an Actor that is not part of the framework lives with that
# Actor, and a person adds it with "--plugin", e.g
#
#   aiko_dashboard -p aiko_services.actors.display.dashboard_plugin
#
# To Do
# ~~~~~
# - Discover the pages, instead of naming them here

from aiko_services.actors.dashboard.process_manager_plugin import (
    ProcessManagerFrame
)
from aiko_services.actors.dashboard.recorder_plugin import RecorderFrame
from aiko_services.actors.dashboard.registrar_plugin import RegistrarFrame

__all__ = ["plugins"]

# plugin key can be either the Service "name" or "protocol"

plugins = {
    "process_manager": ProcessManagerFrame,
    "recorder": RecorderFrame,
    "registrar": RegistrarFrame
}

# --------------------------------------------------------------------------- #
