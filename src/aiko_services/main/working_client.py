#!/usr/bin/env python3
#
# Aiko Services: reporting that a Service is doing its work
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# An operator with no screen needs to know that the application works, and
# not only that its processes are up.  So a Service that reaches its
# working state says so, and the host's power manager sounds it.
#
#     client = WorkingClient(aiko.process, detail="frames")
#     client.open()
#     client.report()        # when the work is really happening
#
# The division of knowledge is the design.  Only the Service knows what
# working means for it: a Pipeline that captures video knows that the
# frames arrive, and a power manager cannot know that without naming the
# application.  And only the power manager knows what the report sounds
# like, because the buzzer is its property and one sound must mean one
# thing.  Therefore the Service reports a fact, and never asks for a sound.
#
# This is the same direction as the up-time Lease of ADR-028 decision 13.
# The application tells the power manager what it needs or what it has
# done, and the power manager keeps the policy.  Nothing here makes the
# power manager aware of any application.
#
# A report is cheap and it is safe to repeat.  The power manager sounds it
# once for each reporter and then holds a dwell, so a caller in a loop is
# quiet rather than a siren.  A caller that wants the sound on a schedule
# of its own reports on that schedule, and the dwell still governs.
#
# This lives in "main" because any Service may report, and because "main"
# must not import from the "actors" tier.
#
# To Do
# ~~~~~
# * The discovery here is the same as PoweredUpClient's.  When a third
#   client needs it, the three share one finder rather than this pair
#   keeping two copies
# * Report a loss as well, so a Pipeline that stops capturing is heard.
#   That needs a second pattern, and a rule for how long a loss must last

import os

from aiko_services.main import aiko
from aiko_services.main.powered_up_client import POWERED_UP_PROTOCOL
from aiko_services.main.service import ServiceFilter
from aiko_services.main.utilities import generate, get_logger

__all__ = ["POWER_MANAGER_PROTOCOL", "WorkingClient"]

_LOGGER = get_logger(
    __name__, log_level=os.environ.get("AIKO_LOG_LEVEL_LEASE", "INFO"))

# One Actor answers both this and the up-time request, so the protocol is
# the same string.  It is named again here because what this file looks for
# is the power manager, and not a Lease
POWER_MANAGER_PROTOCOL = POWERED_UP_PROTOCOL

class WorkingClient:
    """Tells this host's power manager that its caller is doing its work.

    "service" is the Service that reports, and its topic identifies the
    reporter.  "detail" is one token for the operator and the log, such as
    "frames".  Nothing is acquired until open()
    """

    def __init__(self, service, detail="-",
        protocol=POWER_MANAGER_PROTOCOL, publish=None):

        self.service = service
        self.detail = str(detail or "-")
        self.protocol = protocol
        self._publish = publish    # Injected by a test
        self._discovery = None
        self._manager = None       # The power manager's topic path
        self.reports = 0           # For the caller's metrics

    def open(self):
        """Start watching for a power manager.  Returns at once: there may
        not be one, and then nothing is reported until there is"""

        from aiko_services.main.transport import ActorDiscovery

        if self._discovery is None:
            self._discovery = ActorDiscovery(self.service)
            self._discovery.add_handler(self._service_change, self._filter())
        return self

    def found(self):
        """Whether a power manager has been found on this host"""

        return self._manager is not None

    def report(self, detail=None):
        """Report that the work is happening now.

        Returns whether a message went out, which is False where no power
        manager has been found.  It does not report whether a sound was
        made: that is the power manager's decision, and the caller must not
        depend on it"""

        if detail is not None:
            self.detail = str(detail)
        if self._manager is None:
            return False
        payload = generate("report_working", [self._topic(), self.detail])
        try:
            if self._publish is not None:
                self._publish(f"{self._manager}/in", payload)
            else:
                aiko.process.message.publish(f"{self._manager}/in", payload)
        except Exception as error:                       # noqa: BLE001
            _LOGGER.warning(f"Could not report working: {error}")
            return False
        self.reports += 1
        return True

    def close(self):
        """Stop watching.  There is nothing to give up: a report is one
        message, and it holds no Lease"""

        self._discovery = None
        self._manager = None

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

    def _topic(self):
        """The Service's own topic, which identifies the reporter"""

        return f"{self.service.topic_path}/in"

# --------------------------------------------------------------------------- #
