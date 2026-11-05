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
# * A discharge script, so that a test walks a battery pack from full to the floor
#   and asserts what the policy does at each step (phase 3)

from aiko_services.actors.power_manager.button import FakePowerInputs
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
        thresholds=None, telemetry=False, timer=False, inputs=None,
        enforce=None, button_shutdown=None, quiesce=None,
        power_off_runner=None, worker=False):

        self._inputs = inputs if inputs is not None else FakePowerInputs()
        self._script = list(script) if script else []
        self._properties = tuple(properties)
        self._index = 0
        self.opened = False
        self.closed = False
        self.holds = []                # Every hold() call, for a test
        self.signals = []              # Every signal() call, for a test
        self.power_offs = []           # Every power-off, for a test

        # The mock never stops a real host.  Without this a test that
        # reaches the acting path runs the privileged power-off of the
        # platform it is running on, and on a host with password-less
        # privilege that test ends the session.  Found on 2026-11-05, when
        # the button began to act while advisory and one test in this file
        # reached "sudo systemctl poweroff" on the machine running it.
        # A test that wants to watch the real path injects its own runner
        if power_off_runner is None:
            power_off_runner = self._record_power_off

        from aiko_services.actors.power_manager.power_manager import (
            BUTTON_SHUTDOWN, ENFORCE, PERIOD_DEVELOPMENT, SAFE
        )
        self._init_power(context,
            period=PERIOD_DEVELOPMENT if period is None else period,
            log_directory=log_directory, keep_days=keep_days,
            safe=SAFE if safe is None else safe,
            thresholds=thresholds, telemetry=telemetry, timer=timer,
            enforce=ENFORCE if enforce is None else enforce,
            button_shutdown=BUTTON_SHUTDOWN if button_shutdown is None
                else button_shutdown,
            quiesce=quiesce,
            power_off_runner=power_off_runner, worker=worker)
        self._inputs.add_handler(self._input_event)

    def properties(self):
        return self._properties

    def _record_power_off(self, arguments):
        """Record a power-off and report that it worked, so that the acting
        path can be tested without any host being stopped"""

        self.power_offs.append(list(arguments))
        return 0, ""

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

    def press(self, seconds=3.0):
        """Report a press that lasted this long, as a real button would.
        A press that reaches the hold time reports "held" """

        return self._inputs.press(seconds=seconds)

    def dock(self, docked):
        """Report a dock change, as the line would"""

        self._inputs.set_docked(docked)

    def close(self):
        self.closed = True
        super().close()

# --------------------------------------------------------------------------- #
