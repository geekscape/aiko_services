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
# - Uncommenting the "print()" statements is a very useful diagnotic in general

from threading import Lock as ThreadingLock

__all__ = ["Lock"]

class Lock:
    def __init__(self, name, logger=None):
        self._name = name
        self._logger = logger
        self._lock = ThreadingLock()
        self._in_use = None

    def acquire(self, location):
        if self._in_use:
            diagnostic = f'Lock "{self._name}" '  \
                         f'at "{location}" in use by "{self._in_use}"'
            if self._logger:
                self._logger.warn(diagnostic)
            else:
                print(diagnostic)
        self._lock.acquire()
        self._in_use = location
    #   print(f'Lock "{self._name}" acquired by {location}')

    def release(self):
    #   print(f'Lock "{self._name}" released by {self._in_use}')
        self._in_use = None
        self._lock.release()
