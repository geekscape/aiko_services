#!/usr/bin/env python3
#
# Aiko Services: one power reading
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# PowerReading is what sample() returns: the supply, the battery, the battery pack
# temperature and the processor load, at one moment, from one host.
#
# A field that the platform does not measure is None, and it stays None all
# the way to the shared state and the log.  A laptop has no supply current,
# a continuous integration host has no battery, and neither is an error.
#
# Both clocks are recorded.  A host with no real-time clock has a wall clock
# that is wrong whenever the network is away, and an undocked host is
# exactly such a host.  The monotonic clock and the boot identifier together
# order the lines of a log that the wall clock cannot order.
#
# This module is a value type: ADR-022 "value or data type" exemption from
# Interface composition.
#
# To Do
# ~~~~~
# * percent, minutes_left and watt_hours, after a discharge curve is
#   measured on the hardware (ADR-028 decision 10)

from dataclasses import dataclass, asdict, fields
from datetime import datetime, timezone
import time

__all__ = ["PowerReading", "boot_id", "utc_now"]

_BOOT_ID_PATH = "/proc/sys/kernel/random/boot_id"

@dataclass(frozen=True)
class PowerReading:
    """One moment of power, from one host.  Every field is a number, a
    string or None: nothing here is a device, so a reading crosses a thread,
    a wire or a file unchanged"""

    device: str = "mock"

    supply_volts: float = None
    supply_amps: float = None
    supply_watts: float = None

    battery_volts: float = None
    battery_amps: float = None
    battery_watts: float = None
    battery_pack_celsius: float = None

    cpu_percent: float = None
    memory_percent: float = None
    cpu_celsius: float = None
    load_1m: float = None

    docked: bool = None

    sampled_utc: str = None
    sampled_monotonic: float = None
    boot_id: str = None

    error: str = None

    def margin_volts(self, floor_volts):
        """How far the battery is above "floor_volts", or None when there is
        no battery reading.  Negative means the floor is passed"""

        if self.battery_volts is None or floor_volts is None:
            return None
        return round(self.battery_volts - float(floor_volts), 3)

    def as_dict(self):
        """Every field, including the ones that are None.  A log line keeps
        its columns, so a reader does not have to guess why one is absent"""

        return asdict(self)

    def as_share(self, prefix=""):
        """The fields as the shared-state items of ADR-028, flat and dotted:
        "battery.volts", "supply.watts", "cpu.percent".  A field that is
        None becomes "-", because a shared variable holds a token"""

        items = {}
        for name, value in _SHARE_NAMES.items():
            items[f"{prefix}{value}"] = _token(getattr(self, name))
        return items

    @staticmethod
    def field_names():
        """Every field name, in order"""

        return tuple(field.name for field in fields(PowerReading))

# The one place that maps a field to its shared-state name.  ADR-028 names
# the battery pack temperature for the battery pack, so that no reader confuses it with the
# processor temperature beside it
_SHARE_NAMES = {
    "supply_volts": "supply.volts",
    "supply_amps": "supply.amps",
    "supply_watts": "supply.watts",
    "battery_volts": "battery.volts",
    "battery_amps": "battery.amps",
    "battery_watts": "battery.watts",
    "battery_pack_celsius": "battery.pack_celsius",
    "cpu_percent": "cpu.percent",
    "memory_percent": "memory.percent",
    "cpu_celsius": "cpu.celsius",
    "load_1m": "load.1m",
    "docked": "docked",
    "sampled_utc": "sampled_utc",
    "sampled_monotonic": "sampled_monotonic",
    "boot_id": "boot_id",
}

def _token(value):
    """One shared-state token.  None is "-", a bool is "yes" or "no", and a
    float keeps three decimals, which is finer than any sensor here"""

    if value is None:
        return "-"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)

def utc_now():
    """The wall clock, as ISO 8601 with a "Z", to the second.  The same form
    that store_forward:0 publishes"""

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def boot_id():
    """This boot of this host, or None where the kernel does not say.  Two
    lines with the same boot identifier have comparable monotonic clocks,
    and two lines without it do not"""

    try:
        with open(_BOOT_ID_PATH, encoding="utf-8") as file:
            return file.read().strip() or None
    except OSError:
        return None

def _monotonic():
    return round(time.monotonic(), 3)

# --------------------------------------------------------------------------- #
