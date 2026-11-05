# Usage
# ~~~~~
# pytest [-s] unit/test_power_manager_pmm.py
#
# Unit tests for the two I2C drivers and for PmmPowerManagerImpl
# (actors/power_manager/ina260.py, at30tse.py, pmm.py).
#
# No hardware, and no smbus2.  A fake bus answers with recorded register
# values, which is why the drivers take a bus and never open one.
#
# The recorded values are the ones that the hardware reported on
# 2026-11-05: 10.047 V, 1.106 A and 11.650 W across the battery, 10.374 V
# across the charger, and a pack at 27.000 C.  Therefore a change that
# breaks the arithmetic is caught against a real measurement, and not
# against a number that this file invented.

import itertools

import pytest

import aiko_services as aiko
from aiko_services.actors.power_manager import (
    ADDRESS_BATTERY, ADDRESS_CHARGER, ADDRESS_PACK_TEMPERATURE, At30tse,
    DIE_ID, Ina260, MANUFACTURER_ID, PmmPowerManagerImpl, module_present,
    power_manager_args,
)

_counter = itertools.count()

# The hardware readings of 2026-11-05, as the parts reported them
BATTERY = {0x01: 885, 0x02: 8038, 0x03: 1165}       # 1.106 A, 10.047 V, 11.65 W
CHARGER = {0x01: 798, 0x02: 8299, 0x03: 1036}       # 0.998 A, 10.374 V, 10.36 W
PACK_27C = 27 * 8 << 5                              # 27.000 C, left justified

class FakeBus:
    """A bus of recorded registers.  An address with no entry raises, as a
    bus with no part does"""

    def __init__(self, registers):
        self.registers = dict(registers)
        self.reads = []
        self.closed = False

    def read_i2c_block_data(self, address, register, length):
        self.reads.append((address, register))
        try:
            value = self.registers[(address, register)]
        except KeyError:
            raise OSError(121, "Remote I/O error") from None
        return [(value >> 8) & 0xFF, value & 0xFF]

    def close(self):
        self.closed = True

def whole_board(pack=PACK_27C):
    registers = {}
    for address, values in (
        (ADDRESS_BATTERY, BATTERY), (ADDRESS_CHARGER, CHARGER)):
        registers[(address, 0xFE)] = MANUFACTURER_ID
        registers[(address, 0xFF)] = DIE_ID
        for register, value in values.items():
            registers[(address, register)] = value
    registers[(ADDRESS_PACK_TEMPERATURE, 0x00)] = pack
    return FakeBus(registers)

# The INA260 --------------------------------------------------------------- #

def test_the_part_is_identified_by_its_two_identifiers():
    assert Ina260(whole_board(), ADDRESS_BATTERY).identified() is True

def test_a_part_that_does_not_answer_is_not_identified():
    assert Ina260(FakeBus({}), ADDRESS_BATTERY).identified() is False

def test_a_wrong_identifier_is_not_this_part():
    bus = whole_board()
    bus.registers[(ADDRESS_BATTERY, 0xFF)] = 0x1234
    assert Ina260(bus, ADDRESS_BATTERY).identified() is False

def test_the_measured_battery_values_round_trip():
    volts, amps, watts = Ina260(whole_board(), ADDRESS_BATTERY).read()
    assert round(volts, 3) == 10.047
    assert round(amps, 3) == 1.106
    assert round(watts, 3) == 11.650

def test_the_measured_charger_values_round_trip():
    volts, amps, watts = Ina260(whole_board(), ADDRESS_CHARGER).read()
    assert round(volts, 3) == 10.374
    assert round(amps, 3) == 0.998
    assert round(watts, 3) == 10.360

def test_current_is_signed():
    """A pack that is charging and one that is discharging differ by the
    sign alone, so the sign is the reading"""

    bus = whole_board()
    bus.registers[(ADDRESS_BATTERY, 0x01)] = 0x10000 - 885
    assert round(Ina260(bus, ADDRESS_BATTERY).amps(), 3) == -1.106

def test_the_bus_voltage_is_never_signed():
    bus = whole_board()
    bus.registers[(ADDRESS_BATTERY, 0x02)] = 0x8000
    assert Ina260(bus, ADDRESS_BATTERY).volts() > 0

# The AT30TSE752A ---------------------------------------------------------- #

def test_the_pack_temperature_round_trips():
    assert At30tse(whole_board(), ADDRESS_PACK_TEMPERATURE).celsius() == 27.0

def test_a_temperature_below_zero_is_two_s_complement():
    bus = whole_board(pack=((-10 * 8) & 0x7FF) << 5)
    assert At30tse(bus, ADDRESS_PACK_TEMPERATURE).celsius() == -10.0

def test_the_quarter_degree_is_kept():
    bus = whole_board(pack=int(27.125 * 8) << 5)
    assert At30tse(bus, ADDRESS_PACK_TEMPERATURE).celsius() == 27.125

def test_a_sensor_that_does_not_answer_is_not_identified():
    assert At30tse(FakeBus({}), ADDRESS_PACK_TEMPERATURE).identified() is False

def test_a_reading_outside_the_part_range_is_not_this_part():
    bus = whole_board(pack=int(126.0 * 8) << 5)      # Above the part's 125 C
    assert At30tse(bus, ADDRESS_PACK_TEMPERATURE).identified() is False

# The Implementation ------------------------------------------------------- #

def make_actor(bus, **parameters):
    settings = {"bus": bus, "log_directory": None, "telemetry": False,
        "timer": False}
    settings.update(parameters)
    init_args = power_manager_args(
        f"power_pmm_test_{next(_counter)}", "pmm",
        declared=PmmPowerManagerImpl.DECLARED_PROPERTIES, **settings)
    return aiko.compose_instance(PmmPowerManagerImpl, init_args)

def test_every_part_that_answers_is_found():
    actor = make_actor(whole_board())
    assert actor.open() == ("battery", "charger", "pack")
    assert "readings" in actor.properties()
    actor.close()

def test_a_reading_carries_every_part():
    actor = make_actor(whole_board())
    actor.open()
    reading = actor.read()
    assert round(reading.battery_volts, 3) == 10.047
    assert round(reading.supply_volts, 3) == 10.374
    assert reading.battery_pack_celsius == 27.0
    assert reading.device == "pmm"
    actor.close()

def test_a_missing_part_is_left_out_rather_than_raising():
    bus = whole_board()
    del bus.registers[(ADDRESS_CHARGER, 0xFE)]
    actor = make_actor(bus)
    assert actor.open() == ("battery", "pack")
    reading = actor.read()
    assert reading.battery_volts is not None
    assert reading.supply_volts is None
    actor.close()

def test_no_part_means_no_readings_property():
    """Only "readings" is asserted: whether this host also has "hold" or
    "signal" depends on the host, and a test that depends on the host is
    worse than no test"""

    actor = make_actor(FakeBus({}))
    assert actor.open() == ()
    assert "readings" not in actor.properties()
    actor.close()

def test_a_part_that_stops_answering_becomes_a_recorded_error():
    bus = whole_board()
    actor = make_actor(bus)
    actor.open()
    del bus.registers[(ADDRESS_BATTERY, 0x02)]
    reading = actor._read_guarded()
    assert reading.error
    assert actor.share["metrics"]["sensor_errors"] == 1
    actor.close()

def test_phase_1_reads_only_the_three_known_addresses():
    """A bus scan writes to every address, and one address on this bus is
    unidentified.  So this Implementation never scans"""

    bus = whole_board()
    actor = make_actor(bus)
    actor.open()
    actor.read()
    touched = {address for address, _ in bus.reads}
    assert touched <= {
        ADDRESS_BATTERY, ADDRESS_CHARGER, ADDRESS_PACK_TEMPERATURE}
    actor.close()

def test_a_given_bus_is_not_closed_by_the_actor():
    """A test or a caller that supplies the bus keeps it"""

    bus = whole_board()
    actor = make_actor(bus)
    actor.open()
    actor.close()
    assert bus.closed is False

def test_hold_and_signal_are_no_ops_where_the_platform_lacks_them(
    monkeypatch):

    """A host with no pin utility and no buzzer has neither property, so
    both methods are no-ops (ADR-022 decision 1).

    The utility and the buzzer are both taken away here.  Without that this
    test would pass on a laptop and behave differently on the hardware,
    which is worse than no test"""

    from aiko_services.actors.power_manager import pmm as module
    from aiko_services.actors.power_manager.signal import FakeBuzzer
    monkeypatch.setattr(module, "hold_tool", lambda *a, **k: None)

    actor = make_actor(whole_board(), buzzer=FakeBuzzer())
    actor.open()
    assert actor.properties() == ("readings",)
    actor.hold(True)                                 # Logs, and does nothing
    actor.signal("booted")
    assert actor.share["hold_state"] == "unknown"
    assert actor.share["metrics"]["signals"] == 0
    actor.close()

def test_module_present_is_false_without_smbus2(monkeypatch):
    import builtins
    real_import = builtins.__import__

    def refuse(name, *arguments, **keywords):
        if name == "smbus2":
            raise ImportError("no smbus2")
        return real_import(name, *arguments, **keywords)

    monkeypatch.setattr(builtins, "__import__", refuse)
    assert module_present() is False

# --------------------------------------------------------------------------- #
