# Usage
# ~~~~~
# from aiko_services.main.utilities import *
# lock_test = Lock(f"{__name__}.test", aiko.logger(__name__))
# try:
#     lock_test.acquire("add_service()")
#     ## Critial code ##
# finally:
#     lock_test.release()
#
# Notes
# ~~~~~
# - Generally useful debugging aid: export AIKO_LOG_LEVEL_LOCK=DEBUG

import os
from threading import Lock as ThreadingLock

from .logger import DEBUG, get_logger

_AIKO_LOG_LEVEL_LOCK = os.environ.get("AIKO_LOG_LEVEL_LOCK", "INFO")
_LOGGER = get_logger(__name__, log_level=_AIKO_LOG_LEVEL_LOCK)

__all__ = ["Lock"]

class Lock:
    def __init__(self, name, logger=None):
        self._name = name
        self._logger = logger
        self._lock = ThreadingLock()
        self._in_use = None

    def acquire(self, location):
        if self._in_use and _LOGGER.isEnabledFor(DEBUG):
            _LOGGER.debug(
                f'"{self._name}" at "{location}" in use by "{self._in_use}"')

        self._lock.acquire()
        self._in_use = location

        if _LOGGER.isEnabledFor(DEBUG):
            _LOGGER.debug(f'"{self._name}" acquired by {location}')

    def release(self):
        if _LOGGER.isEnabledFor(DEBUG):
            _LOGGER.debug(f'"{self._name}" released by {self._in_use}')

        self._in_use = None
        self._lock.release()
