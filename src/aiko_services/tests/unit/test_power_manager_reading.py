# Usage
# ~~~~~
# pytest [-s] unit/test_power_manager_reading.py
#
# Unit tests for PowerReading (actors/power_manager/reading.py): the value
# type that sample() returns.
#
# It is a frozen dataclass of numbers, strings and None, so every test here
# is a pure one.  The cases that matter are the absent field, which stays
# None all the way to the log, and the two clocks, which order a log that a
# host with no real-time clock cannot order by its wall clock.

import dataclasses
import re

import pytest

from aiko_services.actors.power_manager import PowerReading, boot_id, utc_now

def test_every_field_defaults_to_none_except_the_device():
    reading = PowerReading()
    assert reading.device == "mock"
    absent = [name for name in reading.field_names()
        if name != "device" and getattr(reading, name) is not None]
    assert absent == []

def test_a_reading_is_frozen():
    reading = PowerReading(battery_volts=12.0)
    with pytest.raises(dataclasses.FrozenInstanceError):
        reading.battery_volts = 11.0

def test_margin_is_the_distance_above_the_floor():
    assert PowerReading(battery_volts=10.047).margin_volts(9.9) == 0.147

def test_margin_is_negative_below_the_floor():
    assert PowerReading(battery_volts=9.8).margin_volts(9.9) == -0.1

def test_margin_is_none_with_no_battery():
    assert PowerReading().margin_volts(9.9) is None

def test_margin_is_none_with_no_floor():
    assert PowerReading(battery_volts=12.0).margin_volts(None) is None

def test_as_dict_keeps_the_columns_that_are_absent():
    record = PowerReading(battery_volts=12.0).as_dict()
    assert record["battery_volts"] == 12.0
    assert "supply_volts" in record and record["supply_volts"] is None

def test_as_share_names_the_pack_temperature_for_the_pack():
    items = PowerReading(battery_pack_celsius=27.0).as_share()
    assert items["battery.pack_celsius"] == "27.000"
    # The processor temperature is its own item, and never the pack's
    assert items["cpu.celsius"] == "-"

def test_as_share_turns_an_absent_field_into_a_token():
    assert PowerReading().as_share()["battery.volts"] == "-"

def test_as_share_turns_a_boolean_into_yes_or_no():
    assert PowerReading(docked=True).as_share()["docked"] == "yes"
    assert PowerReading(docked=False).as_share()["docked"] == "no"

def test_as_share_takes_a_prefix():
    items = PowerReading(battery_volts=12.0).as_share(prefix="power.")
    assert items["power.battery.volts"] == "12.000"

def test_utc_now_is_iso_8601_to_the_second():
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", utc_now())

def test_boot_id_is_a_string_or_none():
    value = boot_id()
    assert value is None or (isinstance(value, str) and value)

def test_boot_id_is_none_when_the_kernel_does_not_say(monkeypatch):
    from aiko_services.actors.power_manager import reading as module
    monkeypatch.setattr(module, "_BOOT_ID_PATH", "/nonexistent/boot_id")
    assert module.boot_id() is None

# --------------------------------------------------------------------------- #
