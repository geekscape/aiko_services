# Usage
# ~~~~~
# from aiko_services.main.utilities import *
# lock_test = Lock(f"{__name__}.test", aiko.logger(__name__))
# lock_test.acquire("add_service()")
### Critial code
# lock_test.release()

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

    def release(self):
        self._in_use = None
        self._lock.release()
