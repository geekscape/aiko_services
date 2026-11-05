#!/usr/bin/env python3
#
# Aiko Services: the mock PowerManager
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# The registered default Implementation of PowerManager, and the test
# double.  It needs no hardware, no bus and no privilege, so the policy and
# the log are exercised on a laptop and in continuous integration.
#
# A platform with no Implementation of its own gets this one.  Therefore it
# reports itself as a mock rather than doing something that cannot work
# (ADR-028 decision 1).
#
# The readings come from a script that the caller gives: a list of
# PowerReading, or of keyword dictionaries, which it walks and then holds at
# the last one.  With no script it reports a healthy docked host, which is
# the state that changes nothing.
#
# To Do
# ~~~~~
# * A discharge script, so that a test walks a pack from full to the floor
#   and asserts what the policy does at each step (phase 3)

from aiko_services.actors.power_manager.power_manager import (
    PowerManager, PowerManagerCommon
)
from aiko_services.actors.power_manager.reading import PowerReading

__all__ = ["DEFAULT_READING", "MockPowerManagerImpl"]

# A healthy docked host: above every threshold, so nothing is provoked
DEFAULT_READING = {
    "supply_volts": 12.0, "supply_amps": 1.0, "supply_watts": 12.0,
    "battery_volts": 12.6, "battery_amps": 0.1, "battery_watts": 1.26,
    "battery_pack_celsius": 25.0, "docked": True,
}

class MockPowerManagerImpl(PowerManagerCommon, PowerManager):
    """A PowerManager with no hardware.  The default Implementation"""

    device = "mock"
    DECLARED_PROPERTIES = ("readings", "dock")

    def __init__(self, context, script=None, properties=("readings", "dock"),
        period=None, log_directory=None, keep_days=None, safe=None,
        thresholds=None, telemetry=False, timer=False):

        self._script = list(script) if script else []
        self._properties = tuple(properties)
        self._index = 0
        self.opened = False
        self.closed = False
        self.holds = []                # Every hold() call, for a test
        self.signals = []              # Every signal() call, for a test

        from aiko_services.actors.power_manager.power_manager import (
            PERIOD_DEVELOPMENT, SAFE
        )
        self._init_power(context,
            period=PERIOD_DEVELOPMENT if period is None else period,
            log_directory=log_directory, keep_days=keep_days,
            safe=SAFE if safe is None else safe,
            thresholds=thresholds, telemetry=telemetry, timer=timer)

    def properties(self):
        return self._properties

    def open(self):
        self.opened = True

    def read(self):
        """The next reading of the script, or the last one again.  With no
        script, a healthy docked host"""

        if not self._script:
            return PowerReading(device=self.device, **DEFAULT_READING)
        step = self._script[min(self._index, len(self._script) - 1)]
        self._index += 1
        if isinstance(step, PowerReading):
            return step
        if isinstance(step, OSError):                    # A failing bus
            raise step
        return PowerReading(device=self.device, **step)

    def hold(self, on):
        """Records the call.  A mock holds nothing"""

        self.holds.append(on)

    def signal(self, name):
        """Records the call.  A mock sounds nothing"""

        self.signals.append(name)

    def press(self, kind="long", seconds=3.0):
        """Report a button press to every handler, as a real button would.
        Nothing acts on it before phase 3"""

        for handler in getattr(self, "_handlers", []):
            handler("button", f"{kind} {seconds:.2f}")

    def dock(self, docked):
        """Report a dock change to every handler"""

        for handler in getattr(self, "_handlers", []):
            handler("dock", "yes" if docked else "no")

    def close(self):
        self.closed = True
        super().close()

# --------------------------------------------------------------------------- #
