# Example
# ~~~~~~~
# from aiko_services.main import *
#
# def lease_expired(lease_uuid):
#     if lease_uuid in leases:
#         del leases[lease_uuid]
#
# leases = {}
# lease_time = 10  # seconds
# lease_uuid = "1"
# lease = Lease(lease_time, lease_uuid,
#     lease_expired_handler=lease_expired, automatic_extend=True)
# leases[lease_uuid] = lease
# event.loop()
# lease.extend()
#
# To Do
# ~~~~~
# - Change "lease_time: seconds" to "lease: {start: UTC, duration: seconds}" ?
#
# - Lease request rejected ...
#   - Response (lease_rejected maximum_time 60
#   - Response (lease_rejected no_resource memory)

import os

from aiko_services.main import *
from aiko_services.main.utilities import *

__all__ = ["Lease"]

_LEASE_EXTEND_TIME_FACTOR = 0.8

_AIKO_LOG_LEVEL_LEASE = os.environ.get("AIKO_LOG_LEVEL_LEASE", "INFO")
_LOGGER = aiko.logger(__name__, log_level=_AIKO_LOG_LEVEL_LEASE)

class Lease:
    def __init__(
        self,
        lease_time,
        lease_uuid,
        lease_expired_handler=None,
        lease_extend_handler=None,
        automatic_extend=False):

        self.lease_time = lease_time
        self.lease_uuid = lease_uuid
        self.lease_expired_handler = lease_expired_handler
        self.lease_extend_handler = lease_extend_handler
        self.automatic_extend = automatic_extend

        event.add_timer_handler(self._lease_expired_timer, lease_time)
        if self.automatic_extend:
            extend_time = self.lease_time * _LEASE_EXTEND_TIME_FACTOR
            event.add_timer_handler(self.extend, extend_time)
        if _LOGGER.isEnabledFor(DEBUG):  # Don't expand debug message
            _LOGGER.debug(f"Lease created: {lease_uuid}: time={lease_time}")

    def extend(self, lease_time=None):
        if lease_time:
            self.lease_time = lease_time
        event.remove_timer_handler(self._lease_expired_timer)
        event.add_timer_handler(self._lease_expired_timer, self.lease_time)
        if self.lease_extend_handler:
            self.lease_extend_handler(self.lease_time, self.lease_uuid)
        if _LOGGER.isEnabledFor(DEBUG):  # Don't expand debug message
            _LOGGER.debug(
                f"Lease extended: {self.lease_uuid}, time={self.lease_time}")

    def _lease_expired_timer(self):
        event.remove_timer_handler(self._lease_expired_timer)
        if self.lease_expired_handler:
            self.lease_expired_handler(self.lease_uuid)
        if _LOGGER.isEnabledFor(DEBUG):  # Don't expand debug message
            _LOGGER.debug(f"Lease expired: {self.lease_uuid}")

    def terminate(self):
        event.remove_timer_handler(self._lease_expired_timer)
        if self.automatic_extend:
            event.remove_timer_handler(self.extend)
        if _LOGGER.isEnabledFor(DEBUG):  # Don't expand debug message
            _LOGGER.debug(f"Lease terminated: {self.lease_uuid}")
