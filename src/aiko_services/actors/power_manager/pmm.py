#!/usr/bin/env python3
#
# Aiko Services: the power management module PowerManager
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# A single-board computer with a power management module: two INA260 power
# meters and one AT30TSE752A pack temperature sensor, on one I2C bus.
#
# Phase 1 reads, and writes nothing.  It claims no GPIO line and runs no
# subprocess, so it is safe to run beside a host that is already in service.
# The hold, the buzzer, the button and the dock line arrive in the phases
# after it, and properties() leaves them out until they do.
#
# Addresses, which a board may move: 0x40 is across the battery, 0x41 is
# across the charger, and 0x48 is against the pack.  One more address on
# such a bus is a display, and one is unidentified, and this module reads
# neither.  It never scans the bus, because a scan writes to every address.
#
# smbus2 is imported in open(), and nowhere else (P9): a laptop runs the
# tests with no I2C bus and no package.
#
# To Do
# ~~~~~
# * The hold on its own pin, through the platform pin utility, which keeps
#   the pin driven after the process exits (ADR-028 decision 5): phase 2
# * The buzzer, the button and the dock line, through gpiozero: phases 2
#   and 3
# * The charger channel reports a voltage that the supply does not explain,
#   and the direction of each shunt is unconfirmed.  The log answers the
#   second question the first time the host is undocked

from aiko_services.actors.power_manager.at30tse import At30tse
from aiko_services.actors.power_manager.ina260 import Ina260
from aiko_services.actors.power_manager.power_manager import (
    PowerManager, PowerManagerCommon
)
from aiko_services.actors.power_manager.reading import PowerReading

__all__ = [
    "ADDRESS_BATTERY", "ADDRESS_CHARGER", "ADDRESS_PACK_TEMPERATURE",
    "I2C_BUS", "PmmPowerManagerImpl", "module_present",
]

I2C_BUS = 1
ADDRESS_BATTERY = 0x40             # INA260, across the battery
ADDRESS_CHARGER = 0x41             # INA260, across the charger
ADDRESS_PACK_TEMPERATURE = 0x48    # AT30TSE752A, against the pack

class PmmPowerManagerImpl(PowerManagerCommon, PowerManager):
    """A power management module through its I2C parts.  Read-only"""

    device = "pmm"
    # What this Implementation offers when its parts are there.  Phase 1
    # claims no output and no input line, so the rest of PROPERTIES waits
    DECLARED_PROPERTIES = ("readings",)

    def __init__(self, context, bus=None, bus_number=I2C_BUS,
        battery_address=ADDRESS_BATTERY, charger_address=ADDRESS_CHARGER,
        pack_address=ADDRESS_PACK_TEMPERATURE, period=None,
        log_directory=None, keep_days=None, safe=None, thresholds=None,
        telemetry=True, timer=True):

        self._bus = bus                # Given by a test, else open() makes it
        self._bus_number = int(bus_number)
        self._owns_bus = bus is None
        self._addresses = {
            "battery": battery_address,
            "charger": charger_address,
            "pack": pack_address,
        }
        self._battery = self._charger = self._pack = None
        self._found = ()
        if self._bus is not None:
            self._attach()

        from aiko_services.actors.power_manager.power_manager import (
            LOG_DIRECTORY, PERIOD_DEVELOPMENT, SAFE
        )
        self._init_power(context,
            period=PERIOD_DEVELOPMENT if period is None else period,
            log_directory=LOG_DIRECTORY if log_directory is None
                else log_directory,
            keep_days=keep_days, safe=SAFE if safe is None else safe,
            thresholds=thresholds, telemetry=telemetry, timer=timer)

    def properties(self):
        """"readings" while at least one part answers, and nothing else in
        phase 1: this Implementation claims no output and no input line"""

        return ("readings",) if self._found else ()

    def open(self):
        """Open the I2C bus and attach to the parts that answer.

        An address that does not answer is left out, and properties() says
        so.  A bus that cannot be opened raises OSError, which the caller
        reports: there is nothing to read without it"""

        if self._bus is None:
            from smbus2 import SMBus                     # Only needed here
            self._bus = SMBus(self._bus_number)
            self._owns_bus = True
        self._attach()
        return self._found

    def read(self):
        """One PowerReading from the parts that answered at open().

        A part that stops answering raises OSError, which the Actor turns
        into a reading that records the error"""

        values = {}
        if self._battery:
            volts, amps, watts = self._battery.read()
            values.update(battery_volts=volts, battery_amps=amps,
                battery_watts=watts)
        if self._charger:
            volts, amps, watts = self._charger.read()
            values.update(supply_volts=volts, supply_amps=amps,
                supply_watts=watts)
        if self._pack:
            values["battery_pack_celsius"] = self._pack.celsius()
        return PowerReading(device=self.device, **values)

    def close(self):
        """Close the bus, when this Implementation opened it.  No pin is
        touched: phase 1 claims none, and the power hold is released by the
        shutdown hook alone (ADR-028 decision 6)"""

        super().close()
        if self._owns_bus and self._bus is not None:
            try:
                self._bus.close()
            except (AttributeError, OSError):
                pass
        if self._owns_bus:
            self._bus = None
            self._battery = self._charger = self._pack = None
            self._found = ()

    def _attach(self):
        """Attach to each part that answers.  Identification matters: an
        address that answers with the wrong part is not read"""

        found = []
        battery = Ina260(self._bus, self._addresses["battery"])
        charger = Ina260(self._bus, self._addresses["charger"])
        pack = At30tse(self._bus, self._addresses["pack"])
        self._battery = battery if battery.identified() else None
        self._charger = charger if charger.identified() else None
        self._pack = pack if pack.identified() else None
        for name, part in (("battery", self._battery),
            ("charger", self._charger), ("pack", self._pack)):
            if part is not None:
                found.append(name)
        self._found = tuple(found)

def module_present(bus_number=I2C_BUS, battery_address=ADDRESS_BATTERY):
    """Whether a power management module answers on this host.

    One identified INA260 across the battery is the evidence.  Used by
    choose_power_manager("auto"), and it opens and closes the bus itself,
    so it costs one bus open and two register reads"""

    try:
        from smbus2 import SMBus
    except ImportError:
        return False
    try:
        with SMBus(bus_number) as bus:
            return Ina260(bus, battery_address).identified()
    except (OSError, ValueError):
        return False

# --------------------------------------------------------------------------- #
