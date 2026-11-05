#!/usr/bin/env python3
#
# Aiko Services: asking a host to stay powered up
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# A battery pack is a finite resource that may be consumed within reason,
# so a Service that needs its host to keep running asks for the time it
# needs and holds a Lease (ADR-028 decision 13).
#
#     client = PoweredUpClient(aiko.process, seconds=300, reason="upload")
#     client.open()
#     client.claim()      # while there is work: takes it, or extends it
#     client.release()    # when the work is done
#
# A Lease has two conditions.  The seconds are the period for which it is
# valid, and this client extends them.  A constraint is a quantity of a
# finite resource, in the unit that measures it, and the host must still be
# able to meet it ...
#
#     PoweredUpClient(aiko.process, seconds=300, reason="upload",
#         constraint=("watt_hours", 12.5))
#
# A Service that does not know its own energy cost asks for time alone,
# which is what no constraint means.  A constraint in a unit the host
# cannot measure is refused, so a Service that asks for one must read the
# answer before it plans on having the resource.
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
# The answers come back to the Service's own topic, and this client reads
# them.  That is not a convenience.  An Actor dispatches an incoming
# message to a method of that name, so a Service with no such method logs
# an error for every answer: seen in production on 2026-11-05, where every
# grant and every change of mode became "Function not found in ...".  A
# client that asks must therefore also answer, so open() installs the
# handlers on the Service and close() takes them away again.  A Service
# that defines one of these names itself keeps its own.
#
# "mode_handler" is how an application acts on the answer that matters. A
# power manager publishes "(power_mode quiesce REASON)" when the power will
# end, and an application that writes files wants to stop.
#
# To Do
# ~~~~~
# * More units, as something needs them.  A unit is whatever the power
#   manager can measure and declare

import os

from aiko_services.main import aiko
from aiko_services.main.lease import Lease
from aiko_services.main.power_manager_client import (
    POWER_MANAGER_PROTOCOL, PowerManagerClient
)
from aiko_services.main.utilities import generate, get_logger

__all__ = ["POWERED_UP_PROTOCOL", "PoweredUpClient"]

# The same control that lease.py uses, so one variable turns up the logging
# of both ends of this agreement
_LOGGER = get_logger(
    __name__, log_level=os.environ.get("AIKO_LOG_LEVEL_LEASE", "INFO"))

# The protocol that "actors/power_manager" registers.  One Actor answers
# every one of these clients, so the string lives in one place and this is
# the name that the up-time clients have always used for it
POWERED_UP_PROTOCOL = POWER_MANAGER_PROTOCOL

SECONDS = 300.0                    # The default claim, which a caller sets

class PoweredUpClient(PowerManagerClient):
    """Holds a claim on this host staying powered up, for as long as its
    caller keeps asking.

    "service" is the Service that holds the claim: its own topic receives
    the answers and the changes of mode.  Nothing is acquired until open()
    """

    def __init__(self, service, seconds=SECONDS, reason="-",
        constraint=None, protocol=POWERED_UP_PROTOCOL, publish=None,
        mode_handler=None):

        super().__init__(service, protocol)
        self.seconds = float(seconds)
        self.reason = str(reason or "-")
        # (unit, quantity), or None for time alone
        self.constraint = tuple(constraint) if constraint else None
        self._publish = publish    # Injected by a test
        self._mode_handler = mode_handler
        self._lease = None
        self._installed = ()       # The handler names this client added
        self.claims = 0            # For the caller's metrics
        self.releases = 0
        # The last answer of each kind, for the caller and for a test
        self.granted = None
        self.refused = None
        self.mode = None

    def open(self):
        """Start watching for a power manager.  Returns at once: there may
        not be one, and a claim is simply not made until there is"""

        self._install_handlers()
        return super().open()

    def _install_handlers(self):
        """Put this protocol's answers on the Service, so that they are
        read rather than reported as functions it does not have.

        A name the Service already has is left alone: its own is better
        than this one"""

        handlers = {
            "powered_up_granted": self._granted,
            "powered_up_refused": self._refused,
            "powered_up_released": self._released,
            "power_mode": self._power_mode,
        }
        installed = []
        for name, handler in handlers.items():
            if hasattr(self.service, name):
                continue
            setattr(self.service, name, handler)
            installed.append(name)
        self._installed = tuple(installed)

    def _remove_handlers(self):
        """Take away only the names this client added"""

        for name in self._installed:
            try:
                delattr(self.service, name)
            except AttributeError:
                pass
        self._installed = ()

    def _granted(self, seconds):
        """The claim was taken or extended, for this many seconds"""

        self.granted = _seconds(seconds)
        _LOGGER.debug(f"Powered up granted: {self.granted} s")

    def _refused(self, why, detail=None):
        """The claim was not granted.  A caller that reads this can do less
        work, rather than plan on time it does not have"""

        self.refused = str(why)
        _LOGGER.warning(
            f"Powered up refused: {why}{f' {detail}' if detail else ''}")

    def _released(self, *arguments):
        """The claim is given up, by this client or by its expiry"""

        _LOGGER.debug("Powered up released")

    def _power_mode(self, mode, reason="-"):
        """The host changed what it expects of its power.  "quiesce" means
        the power will end, so an application stops writing"""

        self.mode = str(mode)
        _LOGGER.info(f"Power mode: {self.mode} ({reason})")
        if self._mode_handler:
            try:
                self._mode_handler(self.mode, str(reason))
            except Exception as error:               # noqa: BLE001
                _LOGGER.warning(f"Power mode handler: {error}")

    def claim(self, seconds=None, reason=None, constraint=None):
        """Take the claim, or extend the one that is held.

        Call it whenever there is still work.  It is cheap: the message
        goes out only when the claim is new or its own Lease says it is
        time to ask again"""

        if seconds is not None:
            self.seconds = float(seconds)
        if reason is not None:
            self.reason = str(reason)
        if constraint is not None:
            self.constraint = tuple(constraint) if constraint else None
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
        self._remove_handlers()
        super().close()

    def holding(self):
        """Whether a claim is held now"""

        return self._lease is not None

# ---------------------------------------------------------------------- #

    def _extend(self, seconds, uuid):
        """The client's own Lease asks again, before the claim lapses"""

        self._ask(self.seconds)

    def _ask(self, seconds):
        """One request to the power manager, if one has been found"""

        if self._manager is None:
            return
        arguments = [self._topic(), f"{float(seconds):.0f}", self.reason]
        if self.constraint:
            name, quantity = self.constraint
            arguments += [str(name), f"{float(quantity):g}"]
        payload = generate("request_powered_up", arguments)
        try:
            if self._publish is not None:
                self._publish(f"{self._manager}/in", payload)
            else:
                aiko.process.message.publish(f"{self._manager}/in", payload)
        except Exception as error:                       # noqa: BLE001
            _LOGGER.warning(f"Could not ask for powered up: {error}")

    def _topic(self):
        """The Service's own topic, which identifies the claim and receives
        the answers"""

        return self.topic()

def _seconds(value):
    """An answer's seconds as a number.  It arrives from the wire as a
    string, and an answer that cannot be read is None rather than a raise:
    a client is reporting, not deciding"""

    try:
        return float(value)
    except (TypeError, ValueError):
        return None

# --------------------------------------------------------------------------- #
