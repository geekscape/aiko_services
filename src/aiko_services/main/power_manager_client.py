#!/usr/bin/env python3
#
# Aiko Services: finding this host's power manager
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# Three clients ask something of the power manager: one holds a Lease on
# the host staying powered, one reports that its work is happening, and one
# asks whether to write to the file systems.  All three have to find it
# first, and finding it is the same every time.  So it is here once.
#
# **Nothing but recording happens on the discovery thread.** The services
# cache calls back on its own thread, and the event list that the loop
# walks has no lock on it (event.py), so a Lease or a subscription made
# there would mutate a list the loop is reading.  Therefore _found() only
# writes down a topic, and whatever a subclass needs to build it builds on
# its caller's thread, through ready().  PoweredUpClient had this
# discipline from the start; writing_client.py broke it and this class is
# where it is kept.
#
# The protocol is named as the default of a parameter, so "main" depends on
# no Actor, which is the rule that put these clients here rather than
# beside the Actor that answers them.

import os

from aiko_services.main.service import ServiceFilter
from aiko_services.main.utilities import get_logger

__all__ = ["POWER_MANAGER_PROTOCOL", "PowerManagerClient"]

# The protocol that "actors/power_manager" registers
POWER_MANAGER_PROTOCOL = "github.com/geekscape/aiko_services/protocol/power_manager:0"

_LOGGER = get_logger(__name__, log_level=os.environ.get("AIKO_LOG_LEVEL_LEASE", "INFO"))


class PowerManagerClient:
    """Finds this host's power manager, and nothing else.

    A subclass asks something of it.  "service" is the Service that asks:
    its topic identifies it and receives any answers.  Nothing is acquired
    until open()
    """

    def __init__(self, service, protocol=POWER_MANAGER_PROTOCOL):
        self.service = service
        self.protocol = protocol
        self._discovery = None
        self._manager = None  # The power manager's topic path

    def open(self):
        """Start watching for a power manager.  Returns at once: there may
        not be one, and then the subclass simply asks nothing"""

        from aiko_services.main.transport import ActorDiscovery

        if self._discovery is None:
            self._discovery = ActorDiscovery(self.service)
            self._discovery.add_handler(self._service_change, self._filter())
        return self

    def found(self):
        """Whether a power manager has been found on this host"""

        return self._manager is not None

    def close(self):
        """Stop watching.  A subclass gives up what it holds first"""

        self._discovery = None
        self._manager = None

    def topic(self):
        """The Service's own topic, which identifies it to the power
        manager and receives the answers"""

        return f"{self.service.topic_path}/in"

    # What a subclass may override --------------------------------------------- #

    def ready(self):
        """Called on the caller's thread, where a subclass may build what
        it needs.  The default does nothing"""

    def lost(self):
        """Called when the power manager goes away.  The default does
        nothing"""

    # ---------------------------------------------------------------------- #

    def _filter(self):
        return ServiceFilter("*", "*", self.protocol, "*", "*", "*")

    def _service_change(self, command, service):
        """Runs on the services cache thread, so it records and no more.

        The event list has no lock, so anything that takes a timer belongs
        on the caller's thread and not on this one"""

        if command == "add" and self._manager is None:
            self._manager = str(service[0])
            _LOGGER.debug(f"Power manager found: {self._manager}")
        elif command == "remove" and str(service[0]) == self._manager:
            self._manager = None
            self.lost()


# --------------------------------------------------------------------------- #
