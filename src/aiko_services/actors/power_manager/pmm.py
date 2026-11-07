#!/usr/bin/env python3
#
# Aiko Services: the power management module PowerManager
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# A single-board computer with a power management module: two INA260 power
# meters and one AT30TSE752A battery pack temperature sensor, on one I2C bus.
#
# Phase 1 reads, and writes nothing.  It claims no GPIO line and runs no
# subprocess, so it is safe to run beside a host that is already in service.
# The hold, the buzzer, the button and the dock line arrive in the phases
# after it, and properties() leaves them out until they do.
#
# Addresses, which a board may move: 0x40 is across the battery, 0x41 is
# across the charger, and 0x48 is against the battery pack.  One more address on
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

from contextlib import suppress

import aiko_services as aiko
from aiko_services.actors.power_manager.at30tse import At30tse
from aiko_services.actors.power_manager.button import choose_power_inputs
from aiko_services.actors.power_manager.hold import (
    HOLD_GPIO,
    HOLD_UNKNOWN,
    HoldNotAvailable,
    hold_state,
    hold_tool,
    run_tool,
    set_hold,
)
from aiko_services.actors.power_manager.ina260 import Ina260
from aiko_services.actors.power_manager.power_manager import PowerManager, PowerManagerCommon
from aiko_services.actors.power_manager.reading import PowerReading

# The function is imported under its own name: the package exports a
# "render" function, which shadows the module of the same name
from aiko_services.actors.power_manager.render import verify as verify_files
from aiko_services.actors.power_manager.signal import choose_buzzer

__all__ = [
    "ADDRESS_BATTERY",
    "ADDRESS_CHARGER",
    "ADDRESS_BATTERY_PACK",
    "I2C_BUS",
    "PmmPowerManagerImpl",
    "module_present",
]

I2C_BUS = 1
ADDRESS_BATTERY = 0x40  # INA260, across the battery
ADDRESS_CHARGER = 0x41  # INA260, across the charger
ADDRESS_BATTERY_PACK = 0x48  # AT30TSE752A, against the battery pack


class PmmPowerManagerImpl(PowerManagerCommon, PowerManager):
    """A power management module through its I2C parts.  Read-only"""

    device = "pmm"
    # What this Implementation offers when its parts are there
    DECLARED_PROPERTIES = ("readings", "hold", "signal", "button", "dock")

    def __init__(
        self,
        context,
        bus=None,
        bus_number=I2C_BUS,
        battery_address=ADDRESS_BATTERY,
        charger_address=ADDRESS_CHARGER,
        battery_pack_address=ADDRESS_BATTERY_PACK,
        period=None,
        log_directory=None,
        keep_days=None,
        safe=None,
        thresholds=None,
        telemetry=True,
        timer=True,
        buzzer=None,
        hold_gpio=HOLD_GPIO,
        hold_runner=None,
        artifact_paths=None,
        inputs=None,
        enforce=None,
        button_shutdown=None,
        quiesce=None,
        power_off_runner=None,
        worker=True,
    ):

        self._buzzer = buzzer if buzzer is not None else choose_buzzer("auto")
        self._inputs = inputs if inputs is not None else choose_power_inputs("auto")
        self._hold_gpio = int(hold_gpio)
        self._hold_runner = hold_runner or run_tool
        self._artifact_paths = artifact_paths
        self._bus = bus  # Given by a test, else open() makes it
        self._bus_number = int(bus_number)
        self._owns_bus = bus is None
        self._addresses = {
            "battery": battery_address,
            "charger": charger_address,
            "battery_pack": battery_pack_address,
        }
        self._battery = self._charger = self._battery_pack = None
        self._found = ()
        if self._bus is not None:
            self._attach()

        from aiko_services.actors.power_manager.power_manager import (
            BUTTON_SHUTDOWN,
            ENFORCE,
            LOG_DIRECTORY,
            PERIOD_DEVELOPMENT,
            SAFE,
        )

        self._init_power(
            context,
            period=PERIOD_DEVELOPMENT if period is None else period,
            log_directory=LOG_DIRECTORY if log_directory is None else log_directory,
            keep_days=keep_days,
            safe=SAFE if safe is None else safe,
            thresholds=thresholds,
            telemetry=telemetry,
            timer=timer,
            enforce=ENFORCE if enforce is None else enforce,
            button_shutdown=BUTTON_SHUTDOWN if button_shutdown is None else button_shutdown,
            quiesce=quiesce,
            power_off_runner=power_off_runner,
            worker=worker,
        )

    def properties(self):
        """What is real on this host: "readings" while at least one part
        answers, "hold" while the pin utility is there, and "signal" while
        there is a buzzer.

        Each one is tested for rather than assumed, so a host with no pin
        utility advertises "hold=false" and a client knows before it asks"""

        found = []
        if self._found:
            found.append("readings")
        if self._hold_available():
            found.append("hold")
        if getattr(self._buzzer, "device", "none") != "none":
            found.append("signal")
        if getattr(self._inputs, "device", "none") != "none":
            found.extend(("button", "dock"))
        return tuple(found)

    def _hold_available(self):
        """Whether this host can hold its own power.  A runner that a test
        injects counts as available, because that is what it stands in for"""

        return self._hold_runner is not run_tool or hold_tool() is not None

    def open(self):
        """Open the I2C bus and attach to the parts that answer.

        An address that does not answer is left out, and properties() says
        so.  A bus that cannot be opened raises OSError, which the caller
        reports: there is nothing to read without it"""

        if self._bus is None:
            from smbus2 import SMBus  # Only needed here

            self._bus = SMBus(self._bus_number)
            self._owns_bus = True
        self._attach()
        try:
            self._buzzer.open()
        except Exception as error:  # noqa: BLE001
            self.logger.warning(f"No buzzer: {error}")
            self._buzzer = choose_buzzer("none")
        try:
            # The handler runs on the device's thread and only posts, so
            # nothing it reports touches Actor state there (P11)
            self._inputs.add_handler(self._post_input)
            self._inputs.open()
        except Exception as error:  # noqa: BLE001
            self.logger.warning(f"No input lines: {error}")
            self._inputs = choose_power_inputs("none")
        return self._found

    def read(self):
        """One PowerReading from the parts that answered at open().

        A part that stops answering raises OSError, which the Actor turns
        into a reading that records the error"""

        values = {}
        if self._battery:
            volts, amps, watts = self._battery.read()
            values.update(battery_volts=volts, battery_amps=amps, battery_watts=watts)
        if self._charger:
            volts, amps, watts = self._charger.read()
            values.update(supply_volts=volts, supply_amps=amps, supply_watts=watts)
        if self._battery_pack:
            values["battery_pack_celsius"] = self._battery_pack.celsius()
        if "dock" in self.properties():
            values["docked"] = self._inputs.docked()
        return PowerReading(device=self.device, **values)

    def _post_input(self, event, value):
        """Runs on the input device's thread, so it only posts (P11)"""

        self._post_message(aiko.ActorTopic.IN, "_input_event", [event, value])

    def hold(self, on):
        """Assert the power hold.  **A release is refused here.**

        The release is the one operation that software cannot undo, and it
        belongs to the shutdown hook alone, after the file systems are
        unmounted (ADR-028 decision 6).  A message, a timer or a Pipeline
        must not be able to reach it, so this method will not do it however
        it is called.  "aiko_power_manager hold off" is the mechanism, and
        the hook is its only caller"""

        wanted = on if isinstance(on, bool) else str(on).lower() in ("on", "true", "yes", "1")
        if not wanted:
            self.logger.error("hold(off) refused: only the shutdown hook releases the hold (ADR-028 decision 6)")
            self.ec_producer.update("last_error", "hold(off) refused")
            self._count("denied")
            return
        if "hold" not in self.properties():
            super().hold(on)
            return
        try:
            state = set_hold(True, self._hold_gpio, self._hold_runner)
        except OSError as error:
            self.logger.error(f"hold failed: {error}")
            self.ec_producer.update("last_error", str(error)[:120])
            return
        if self.share["hold_state"] != state:
            self._count("hold_changes")
        self.ec_producer.update("hold_state", state)
        self.logger.info(f"Power hold: {state}")

    def signal(self, name):
        """Sound one pattern on the buzzer"""

        if "signal" not in self.properties():
            super().signal(name)
            return
        try:
            self._buzzer.play(name)
        except (ValueError, OSError) as error:
            self.logger.warning(f"signal refused: {error}")
            self.ec_producer.update("last_error", str(error)[:120])
            return
        self._count("signals")

    def hold_state(self):
        """What the hold line is doing now, read from the pin"""

        if "hold" not in self.properties():
            return HOLD_UNKNOWN
        try:
            return hold_state(self._hold_gpio, self._hold_runner)
        except HoldNotAvailable:
            return HOLD_UNKNOWN

    def hook_state(self):
        """Whether the shutdown hook is installed.  It is read, never run"""

        return verify_files(self._artifact_paths)["hook"]

    def close(self):
        """Close the bus and the buzzer, when this Implementation opened
        them.  **The power hold is never released here**: only the shutdown
        hook does that (ADR-028 decision 6)"""

        super().close()
        for device in (self._buzzer, self._inputs):
            with suppress(Exception):
                device.close()
        if self._owns_bus and self._bus is not None:
            with suppress(AttributeError, OSError):
                self._bus.close()
        if self._owns_bus:
            self._bus = None
            self._battery = self._charger = self._battery_pack = None
            self._found = ()

    def _attach(self):
        """Attach to each part that answers.  Identification matters: an
        address that answers with the wrong part is not read"""

        found = []
        battery = Ina260(self._bus, self._addresses["battery"])
        charger = Ina260(self._bus, self._addresses["charger"])
        battery_pack = At30tse(self._bus, self._addresses["battery_pack"])
        self._battery = battery if battery.identified() else None
        self._charger = charger if charger.identified() else None
        self._battery_pack = battery_pack if battery_pack.identified() else None
        for name, part in (
            ("battery", self._battery),
            ("charger", self._charger),
            ("battery_pack", self._battery_pack),
        ):
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
