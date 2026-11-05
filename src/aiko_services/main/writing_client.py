#!/usr/bin/env python3
#
# Aiko Services: whether this host wants to be written to
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# A host on its battery pack has work it still wants, and work it does not.
# A recording that nobody asked for fills a transfer queue that then holds
# the host up to drain it.  So a Service that writes to the file systems
# asks whether writing is wanted now, and stops when it is not.
#
#     client = WritingClient(aiko.process)
#     client.open()
#     if client.writing_ok():
#         ...write...
#
# **It is True until something says otherwise.** A host with no power
# manager, a power manager not yet found, and a value not yet received all
# answer True.  Therefore adding this client changes nothing anywhere until
# a power manager is running and says to stop, which is the only safe
# default: the alternative loses data on every host that has no battery.
#
# This is a subscription and not a request (P3).  The power manager
# publishes "writing_ok" in its shared state, and this client replicates
# that one item through an ECConsumer.  So the power manager has no register
# of writers, no limit to set, and no notion of who is listening, and any
# number of writers cost it nothing.  A new reason to stop writing is a
# change in the power manager's policy alone.
#
# This lives in "main" because any Service may write, and because "main"
# must not import from the "actors" tier.
#
# To Do
# ~~~~~
# * The discovery here is the third copy of PoweredUpClient's.  Three is
#   where they become one finder
# * A reason, so a writer can log why it stopped.  The mode and its reason
#   are both in the shared state already

import os

from aiko_services.main.powered_up_client import POWERED_UP_PROTOCOL
from aiko_services.main.service import ServiceFilter
from aiko_services.main.utilities import get_logger

__all__ = ["POWER_MANAGER_PROTOCOL", "WRITING_ITEM", "WritingClient"]

_LOGGER = get_logger(
    __name__, log_level=os.environ.get("AIKO_LOG_LEVEL_LEASE", "INFO"))

# One Actor answers this and the up-time request, so the protocol is the
# same string.  It is named again here because what this file looks for is
# the power manager, and not a Lease
POWER_MANAGER_PROTOCOL = POWERED_UP_PROTOCOL

# The one item this client replicates
WRITING_ITEM = "writing_ok"

class WritingClient:
    """Whether this host wants its file systems written to now.

    "service" is the Service that writes.  "handler(writing_ok)" is called
    on each change, for a caller that wants to act rather than ask.
    Nothing is acquired until open()
    """

    def __init__(self, service, protocol=POWER_MANAGER_PROTOCOL,
        handler=None):

        self.service = service
        self.protocol = protocol
        self._handler = handler
        self._discovery = None
        self._manager = None       # The power manager's topic path
        self._consumer = None
        self._cache = {}
        # True until something says otherwise.  A host with no power
        # manager must write exactly as it did before this existed
        self._writing_ok = True
        self.changes = 0           # For the caller's metrics

    def open(self):
        """Start watching for a power manager.  Returns at once: there may
        not be one, and then writing stays allowed"""

        from aiko_services.main.transport import ActorDiscovery

        if self._discovery is None:
            self._discovery = ActorDiscovery(self.service)
            self._discovery.add_handler(self._service_change, self._filter())
        return self

    def found(self):
        """Whether a power manager has been found on this host"""

        return self._manager is not None

    def writing_ok(self):
        """Whether to write now.  True unless a power manager says not"""

        return self._writing_ok

    def close(self):
        """Stop watching, and allow writing again.

        A writer that closed this must not be left believing a stale "no":
        the client is gone, so nothing is saying otherwise any more"""

        if self._consumer is not None:
            try:
                self._consumer.terminate()
            except Exception as error:               # noqa: BLE001
                _LOGGER.debug(f"Writing consumer: {error}")
            self._consumer = None
        self._discovery = None
        self._manager = None
        self._cache = {}
        self._writing_ok = True

# ---------------------------------------------------------------------- #

    def _filter(self):
        return ServiceFilter("*", "*", self.protocol, "*", "*", "*")

    def _service_change(self, command, service):
        """Runs on the services cache thread.  It records the topic and
        attaches, because an ECConsumer is made where the producer is
        known"""

        if command == "add" and self._manager is None:
            self._manager = str(service[0])
            _LOGGER.debug(f"Power manager found: {self._manager}")
            self._attach()
        elif command == "remove" and str(service[0]) == self._manager:
            self._manager = None
            self._detach()

    def _attach(self):
        """Replicate the one item, through an ECConsumer.

        The handler is called with the cache as it stands first, so a
        client that attaches to a host already conserving is told at once
        rather than at the next change"""

        import aiko_services as aiko

        if self._consumer is not None or self._manager is None:
            return
        try:
            self._consumer = aiko.compose_instance(
                aiko.ECConsumerImpl, {
                    "context": aiko.Context(),
                    "service": self.service,
                    "ec_consumer_id": 0,
                    "cache": self._cache,
                    "ec_producer_topic_control": f"{self._manager}/control",
                    "filter": WRITING_ITEM,
                })
            self._consumer.add_handler(self._item_change)
        except Exception as error:                       # noqa: BLE001
            _LOGGER.warning(f"Could not watch the power manager: {error}")
            self._consumer = None

    def _detach(self):
        """A power manager that went away says nothing, so writing is
        allowed again.  A host whose power manager died must not stop
        recording for ever"""

        if self._consumer is not None:
            try:
                self._consumer.terminate()
            except Exception as error:                   # noqa: BLE001
                _LOGGER.debug(f"Writing consumer: {error}")
            self._consumer = None
        self._cache = {}
        self._set(True)

    def _item_change(self, consumer_id, command, item_name, item_value):
        """One item from the power manager's shared state"""

        if item_name != WRITING_ITEM:
            return
        if command == "remove":
            self._set(True)
            return
        self._set(_boolean(item_value))

    def _set(self, writing_ok):
        """Record a change, and tell the caller once"""

        writing_ok = bool(writing_ok)
        if writing_ok == self._writing_ok:
            return
        self._writing_ok = writing_ok
        self.changes += 1
        _LOGGER.info(
            f"Writing {'okay' if writing_ok else 'not okay'}: the power "
            "manager said so")
        if self._handler:
            try:
                self._handler(writing_ok)
            except Exception as error:                   # noqa: BLE001
                _LOGGER.warning(f"Writing handler: {error}")

def _boolean(value):
    """A shared value as a boolean.  It arrives as a string on the wire and
    as a boolean in the same process, and anything unreadable is True: a
    writer must not stop because a value could not be parsed"""

    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in ("false", "0", "no", "off"):
        return False
    return True

# --------------------------------------------------------------------------- #
