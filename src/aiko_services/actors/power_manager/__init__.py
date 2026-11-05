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
from aiko_services.actors.power_manager.button import (  # noqa: F401
    BUTTON_ACTIVE_LOW, BUTTON_GPIO, DOCK_ACTIVE_LOW, DOCK_GPIO,
    FakePowerInputs, GpioPowerInputs, HOLD_TIME_S, choose_power_inputs,
    classify,
)
from aiko_services.actors.power_manager.policy import (  # noqa: F401
    Dwell, HOLD, MODES, MODE_CONSERVE, MODE_NORMAL, MODE_QUIESCE, REASONS,
    SHUTDOWN, decide, decide_mode,
)
from aiko_services.actors.power_manager.power_up import (  # noqa: F401
    BRIDGE_TOPIC, POWER_UP_MAXIMUM_S, POWER_UP_REQUESTS_MAXIMUM,
    REFUSED_MAXIMUM, REFUSED_NO_RESOURCE, REFUSED_PARAMETERS,
    PoweredUpLease, PoweredUpRegister,
)
from aiko_services.actors.power_manager.quiesce import (  # noqa: F401
    HOOK_QUIESCE, Quiesce, REMOUNT_GRACE_S, sync_filesystems,
)
from aiko_services.actors.power_manager.shutdown import (  # noqa: F401
    SUDO, power_off, remount_read_only, run_granted,
)
from aiko_services.actors.power_manager.hold import (  # noqa: F401
    HOLD_GPIO, HOLD_OFF, HOLD_ON, HOLD_UNKNOWN, HoldNotAvailable,
    hold_state, hold_tool, run_tool, set_hold,
)
from aiko_services.actors.power_manager.log import PowerLog  # noqa: F401
from aiko_services.actors.power_manager.render import (  # noqa: F401
    ARTIFACTS, GRANT_PATH, HOLD_RELEASE_DELAY_S, HOOK_PATH, InstallRefused,
    RELEASE_ACTIONS, UNIT_PATH, install, paths, render, verify,
)
from aiko_services.actors.power_manager.signal import (  # noqa: F401
    BUZZER_GPIO, FakeBuzzer, GpioBuzzer, PATTERNS, choose_buzzer,
    pattern_seconds,
)
from aiko_services.actors.power_manager.reading import (  # noqa: F401
    PowerReading, boot_id, utc_now,
)
from aiko_services.actors.power_manager.power_manager import (  # noqa: F401
    DEVICE_FUNCTIONS, DOCK_DWELL_S, ENFORCE, FUNCTIONS, LOG_DIRECTORY,
    PERIOD_DEVELOPMENT, POLICY_SHUTTING_DOWN,
    PERIOD_PRODUCTION, POLICY_ADVISORY, PROPERTIES, PROTOCOL, SAFE,
    SAFE_FUNCTIONS, THRESHOLDS, PowerManager, PowerManagerCommon,
    choose_power_manager, power_manager_args, service_filter, service_tags,
)
from aiko_services.actors.power_manager.mock import (  # noqa: F401
    DEFAULT_READING, MockPowerManagerImpl,
)
from aiko_services.actors.power_manager.pmm import (  # noqa: F401
    ADDRESS_BATTERY, ADDRESS_CHARGER, ADDRESS_BATTERY_PACK, I2C_BUS,
    PmmPowerManagerImpl, module_present,
)

__all__ = [
    "ADDRESS_BATTERY", "ADDRESS_BATTERY_PACK", "ADDRESS_CHARGER",
    "AMPS_PER_BIT", "ARTIFACTS", "At30tse", "BRIDGE_TOPIC",
    "BUTTON_ACTIVE_LOW", "BUTTON_GPIO", "BUZZER_GPIO", "CELSIUS_PER_BIT",
    "DEFAULT_READING", "DEVICE_FUNCTIONS", "DIE_ID", "DOCK_ACTIVE_LOW",
    "DOCK_DWELL_S", "DOCK_GPIO", "Dwell", "ENFORCE", "FUNCTIONS",
    "FakeBuzzer", "FakePowerInputs", "GRANT_PATH", "GpioBuzzer",
    "GpioPowerInputs", "HOLD", "HOLD_GPIO", "HOLD_OFF", "HOLD_ON",
    "HOLD_RELEASE_DELAY_S", "HOLD_TIME_S", "HOLD_UNKNOWN", "HOOK_PATH",
    "HOOK_QUIESCE", "HoldNotAvailable", "I2C_BUS", "Ina260",
    "InstallRefused", "LOG_DIRECTORY", "MANUFACTURER_ID", "MODES",
    "MODE_CONSERVE", "MODE_NORMAL", "MODE_QUIESCE", "MockPowerManagerImpl",
    "PATTERNS", "PERIOD_DEVELOPMENT", "PERIOD_PRODUCTION",
    "POLICY_ADVISORY", "POLICY_SHUTTING_DOWN", "POWER_UP_MAXIMUM_S",
    "POWER_UP_REQUESTS_MAXIMUM", "PROPERTIES", "PROTOCOL",
    "PmmPowerManagerImpl", "PowerLog", "PowerManager",
    "PowerManagerCommon", "PowerReading", "PoweredUpLease",
    "PoweredUpRegister", "Quiesce", "REASONS", "REFUSED_MAXIMUM",
    "REFUSED_NO_RESOURCE", "REFUSED_PARAMETERS", "REGISTER_BUS_VOLTAGE",
    "REGISTER_CONFIGURATION", "REGISTER_CURRENT", "REGISTER_DIE_ID",
    "REGISTER_MANUFACTURER_ID", "REGISTER_POWER", "REGISTER_TEMPERATURE",
    "RELEASE_ACTIONS", "REMOUNT_GRACE_S", "RESOLUTION_BITS", "SAFE",
    "SAFE_FUNCTIONS", "SHUTDOWN", "SUDO", "THRESHOLDS", "UNIT_PATH",
    "VOLTS_PER_BIT", "WATTS_PER_BIT", "boot_id", "choose_buzzer",
    "choose_power_inputs", "choose_power_manager", "classify", "decide",
    "decide_mode", "hold_state", "hold_tool", "install", "module_present",
    "paths", "pattern_seconds", "power_manager_args", "power_off",
    "remount_read_only", "render", "run_granted", "run_tool",
    "service_filter", "service_tags", "set_hold", "sync_filesystems",
    "utc_now", "verify",
]
