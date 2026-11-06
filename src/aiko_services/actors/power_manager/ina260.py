#!/usr/bin/env python3
#
# Aiko Services: the INA260 power meter
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# One INA260 on an I2C bus: bus voltage, current and power.  The part holds
# its own shunt, so there is nothing to calibrate and no configuration to
# write.  Three registers are read, and each one is one multiplication away
# from volts, amps and watts.
#
# The driver takes the bus, and it never opens one.  Therefore a test passes
# a fake bus with recorded bytes, and nothing imports smbus2 (P9).  The bus
# needs one method, read_i2c_block_data(address, register, length).
#
# Current is signed: the sign says which way the charge moves through the
# shunt.  Which direction that is depends on how the board is wired, so this
# driver reports the sign and says nothing about its meaning.
#
# Identification: read_identity() returns (manufacturer, die).  A part that
# answers 0x5449 and 0x2270 is an INA260.  identified() is the predicate,
# and it is how "auto" decides that the hardware is present.
#
# To Do
# ~~~~~
# * Averaging and the conversion time, which live in the configuration
#   register.  The default of 1.1 ms with no averaging is enough while the
#   sample period is seconds

__all__ = [
    "AMPS_PER_BIT", "DIE_ID", "Ina260", "MANUFACTURER_ID",
    "REGISTER_BUS_VOLTAGE", "REGISTER_CONFIGURATION", "REGISTER_CURRENT",
    "REGISTER_DIE_ID", "REGISTER_MANUFACTURER_ID", "REGISTER_POWER",
    "VOLTS_PER_BIT", "WATTS_PER_BIT",
]

REGISTER_CONFIGURATION = 0x00
REGISTER_CURRENT = 0x01
REGISTER_BUS_VOLTAGE = 0x02
REGISTER_POWER = 0x03
REGISTER_MANUFACTURER_ID = 0xFE
REGISTER_DIE_ID = 0xFF

MANUFACTURER_ID = 0x5449           # "TI"
DIE_ID = 0x2270

# From the data sheet, and the reason each one is written as a quotient is
# that the data sheet gives it that way
AMPS_PER_BIT = 1.25 / 1000.0       # 1.25 mA
VOLTS_PER_BIT = 1.25 / 1000.0      # 1.25 mV
WATTS_PER_BIT = 10.0 / 1000.0      # 10 mW

class Ina260:
    """One INA260 at "address" on "bus".

    The bus is given, and never opened here.  It needs one method,
    read_i2c_block_data(address, register, length)"""

    def __init__(self, bus, address):
        self.bus = bus
        self.address = address

    def read_register(self, register):
        """The raw 16-bit value of one register, most significant byte
        first.  Raises OSError when the part does not answer"""

        data = self.bus.read_i2c_block_data(self.address, register, 2)
        return (data[0] << 8) | data[1]

    def read_identity(self):
        """(manufacturer, die) as read from the part"""

        return (self.read_register(REGISTER_MANUFACTURER_ID),
            self.read_register(REGISTER_DIE_ID))

    def identified(self):
        """Whether an INA260 answers at this address.  False for every
        OSError, because a bus with no part raises rather than answers"""

        try:
            return self.read_identity() == (MANUFACTURER_ID, DIE_ID)
        except OSError:
            return False

    def volts(self):
        """The bus voltage.  Always positive"""

        return self.read_register(REGISTER_BUS_VOLTAGE) * VOLTS_PER_BIT

    def amps(self):
        """The current, signed.  The sign is the direction through the
        shunt, and what that means depends on the wiring of the board"""

        return _signed(self.read_register(REGISTER_CURRENT)) * AMPS_PER_BIT

    def watts(self):
        """The power.  The part computes it, and it is never negative"""

        return self.read_register(REGISTER_POWER) * WATTS_PER_BIT

    def read(self):
        """(volts, amps, watts) from three register reads"""

        return self.volts(), self.amps(), self.watts()

def _signed(value):
    """A 16-bit two's complement value as a Python integer"""

    return value - 0x10000 if value & 0x8000 else value

# --------------------------------------------------------------------------- #
