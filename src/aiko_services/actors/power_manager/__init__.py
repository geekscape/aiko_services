# Aiko Services actors: the PowerManager Actor
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# Host power as a Service (ADR-028): what the supply and the battery are
# doing, and what to do about it.  One Interface, PowerManager, with one
# Implementation for each platform, as DaemonSupervisor has (ADR-026).
#
# Phase 1 is read-only: it reads, publishes and logs, and acts on nothing.
# The power hold, the signals, the button and the policy arrive after it.
#
# Usage: aiko_power_manager --help  (see cli.py)

from aiko_services.actors.power_manager.at30tse import (  # noqa: F401
    At30tse, CELSIUS_PER_BIT, REGISTER_TEMPERATURE, RESOLUTION_BITS,
)
from aiko_services.actors.power_manager.ina260 import (  # noqa: F401
    AMPS_PER_BIT, DIE_ID, Ina260, MANUFACTURER_ID, REGISTER_BUS_VOLTAGE,
    REGISTER_CONFIGURATION, REGISTER_CURRENT, REGISTER_DIE_ID,
    REGISTER_MANUFACTURER_ID, REGISTER_POWER, VOLTS_PER_BIT, WATTS_PER_BIT,
)
from aiko_services.actors.power_manager.log import PowerLog  # noqa: F401
from aiko_services.actors.power_manager.reading import (  # noqa: F401
    PowerReading, boot_id, utc_now,
)
from aiko_services.actors.power_manager.power_manager import (  # noqa: F401
    DEVICE_FUNCTIONS, FUNCTIONS, LOG_DIRECTORY, PERIOD_DEVELOPMENT,
    PERIOD_PRODUCTION, POLICY_ADVISORY, PROPERTIES, PROTOCOL, SAFE,
    SAFE_FUNCTIONS, THRESHOLDS, PowerManager, PowerManagerCommon,
    choose_power_manager, power_manager_args, service_filter, service_tags,
)
from aiko_services.actors.power_manager.mock import (  # noqa: F401
    DEFAULT_READING, MockPowerManagerImpl,
)
from aiko_services.actors.power_manager.pmm import (  # noqa: F401
    ADDRESS_BATTERY, ADDRESS_CHARGER, ADDRESS_PACK_TEMPERATURE, I2C_BUS,
    PmmPowerManagerImpl, module_present,
)

__all__ = [
    "ADDRESS_BATTERY", "ADDRESS_CHARGER", "ADDRESS_PACK_TEMPERATURE",
    "AMPS_PER_BIT", "At30tse", "CELSIUS_PER_BIT", "DEFAULT_READING",
    "DEVICE_FUNCTIONS", "DIE_ID", "FUNCTIONS", "I2C_BUS", "Ina260",
    "LOG_DIRECTORY", "MANUFACTURER_ID", "MockPowerManagerImpl",
    "PERIOD_DEVELOPMENT", "PERIOD_PRODUCTION", "POLICY_ADVISORY",
    "PROPERTIES", "PROTOCOL", "PmmPowerManagerImpl", "PowerLog",
    "PowerManager", "PowerManagerCommon", "PowerReading",
    "REGISTER_BUS_VOLTAGE", "REGISTER_CONFIGURATION", "REGISTER_CURRENT",
    "REGISTER_DIE_ID", "REGISTER_MANUFACTURER_ID", "REGISTER_POWER",
    "REGISTER_TEMPERATURE", "RESOLUTION_BITS", "SAFE", "SAFE_FUNCTIONS",
    "THRESHOLDS", "VOLTS_PER_BIT", "WATTS_PER_BIT", "boot_id",
    "choose_power_manager", "module_present", "power_manager_args",
    "service_filter", "service_tags", "utc_now",
]
