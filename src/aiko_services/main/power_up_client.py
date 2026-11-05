#!/usr/bin/env python3
#
# Aiko Services: asking a host to stay powered up
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# A battery pack is a finite resource that may be consumed within reason,
# so a Service that needs its host to keep running asks for the time it
# needs and holds a Lease (ADR-028 decision 13).
#
#     client = PowerUpClient(aiko.process, seconds=300, reason="upload")
#     client.open()
#     client.claim()      # while there is work: takes it, or extends it
#     client.release()    # when the work is done
#
# The client holds a Lease of its own as well, with automatic_extend, whose
# extend handler asks again.  Therefore the claim is renewed before it
# lapses without the caller counting seconds, and a caller that stops
# calling claim() lets the claim go by itself.  That symmetry is the point:
# both ends of this agreement are a Lease, and both act at the time that was
# agreed.
#
# This lives in "main" because any Service may need it, and because "main"
# must not import from the "actors" tier.  The power manager that answers is
# an Actor, and its protocol is named here only as the default of a
# parameter.
#
# A claim asks, and it never commands.  A host still stops when its battery
# pack reaches the voltage floor, when the pack is too hot, or when it has
# been undocked for longer than its bound.  A Service that holds a claim is
# told, as "(power_mode quiesce REASON)" on its own topic, so it can stop
# writing before the power goes.
#
# To Do
# ~~~~~
# * Read the answers.  Today the claim is made and the replies are observed
#   by whatever subscribes to the Service's own topic.  A handler for
#   "(power_up_refused ...)" belongs here, so that a Service that is refused
#   can do less work rather than assume it has the time

import os

from aiko_services.main import aiko
from aiko_services.main.lease import Lease
from aiko_services.main.service import ServiceFilter
from aiko_services.main.utilities import generate, get_logger

__all__ = ["POWER_UP_PROTOCOL", "PowerUpClient"]

# The same control that lease.py uses, so one variable turns up the logging
# of both ends of this agreement
_LOGGER = get_logger(
    __name__, log_level=os.environ.get("AIKO_LOG_LEVEL_LEASE", "INFO"))

# The protocol that "actors/power_manager" registers.  Named here as the
# default of a parameter, so that "main" depends on no Actor
POWER_UP_PROTOCOL =  \
    "github.com/geekscape/aiko_services/protocol/power_manager:0"

SECONDS = 300.0                    # The default claim, which a caller sets

class PowerUpClient:
    """Holds a claim on this host staying powered up, for as long as its
    caller keeps asking.

    "service" is the Service that holds the claim: its own topic receives
    the answers and the changes of mode.  Nothing is acquired until open()
    """

    def __init__(self, service, seconds=SECONDS, reason="-",
        protocol=POWER_UP_PROTOCOL, publish=None):

        self.service = service
        self.seconds = float(seconds)
        self.reason = str(reason or "-")
        self.protocol = protocol
        self._publish = publish    # Injected by a test
        self._discovery = None
        self._manager = None       # The power manager's topic path
        self._lease = None
        self.claims = 0            # For the caller's metrics
        self.releases = 0

    def open(self):
        """Start watching for a power manager.  Returns at once: there may
        not be one, and a claim is simply not made until there is"""

        from aiko_services.main.transport import ActorDiscovery

        if self._discovery is None:
            self._discovery = ActorDiscovery(self.service)
            self._discovery.add_handler(self._service_change, self._filter())
        return self

    def found(self):
        """Whether a power manager has been found on this host"""

        return self._manager is not None

    def claim(self, seconds=None, reason=None):
        """Take the claim, or extend the one that is held.

        Call it whenever there is still work.  It is cheap: the message
        goes out only when the claim is new or its own Lease says it is
        time to ask again"""

        if seconds is not None:
            self.seconds = float(seconds)
        if reason is not None:
            self.reason = str(reason)
        if self._lease is not None:
            return False           # Held already, and extending itself
        self._lease = Lease(self.seconds, self._topic(),
            lease_extend_handler=self._extend, automatic_extend=True)
        self._ask(self.seconds)
        self.claims += 1
        return True

    def release(self):
        """Give the claim up.  A Service that has finished says so, rather
        than leaving a host powered until the claim lapses"""

        if self._lease is None:
            return False
        self._lease.terminate()
        self._lease = None
        self._ask(0)
        self.releases += 1
        return True

    def close(self):
        """Release the claim and stop watching.  A client that is not
        closed leaves its Lease timers in the event loop"""

        self.release()
        self._discovery = None
        self._manager = None

    def holding(self):
        """Whether a claim is held now"""

        return self._lease is not None

# ---------------------------------------------------------------------- #

    def _filter(self):
        return ServiceFilter("*", "*", self.protocol, "*", "*", "*")

    def _service_change(self, command, service):
        """Runs on the services cache thread, so it only records a topic"""

        if command == "add" and self._manager is None:
            self._manager = str(service[0])
            _LOGGER.debug(f"Power manager found: {self._manager}")
        elif command == "remove" and str(service[0]) == self._manager:
            self._manager = None

    def _extend(self, seconds, uuid):
        """The client's own Lease asks again, before the claim lapses"""

        self._ask(self.seconds)

    def _ask(self, seconds):
        """One request to the power manager, if one has been found"""

        if self._manager is None:
            return
        payload = generate("request_power_up",
            [self._topic(), f"{float(seconds):.0f}", self.reason])
        try:
            if self._publish is not None:
                self._publish(f"{self._manager}/in", payload)
            else:
                aiko.process.message.publish(f"{self._manager}/in", payload)
        except Exception as error:                       # noqa: BLE001
            _LOGGER.warning(f"Could not ask for power up: {error}")

    def _topic(self):
        """The Service's own topic, which identifies the claim and receives
        the answers"""

        return f"{self.service.topic_path}/in"

# --------------------------------------------------------------------------- #
