#!/usr/bin/env python3
#
# Aiko Services: the AT30TSE752A temperature sensor
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# The temperature of a battery pack, from one AT30TSE752A on an I2C bus.
#
# **This part measures the pack, and never the processor.**  A board puts it
# against the cells.  The processor temperature comes from the operating
# system, and the two are never mixed: a pack at 45 C is a reason to stop,
# and a processor at 45 C is an idle processor.
#
# The reading is 11 bits, left justified in two bytes, in two's complement,
# at 0.125 C for each bit.  The driver takes the bus and never opens one, so
# a test passes a fake bus with recorded bytes (P9).
#
# To Do
# ~~~~~
# * The configuration register, for the resolution and the alarm outputs.
#   The default of 11 bits is finer than a battery decision needs

__all__ = [
    "At30tse", "CELSIUS_PER_BIT", "REGISTER_TEMPERATURE", "RESOLUTION_BITS",
]

REGISTER_TEMPERATURE = 0x00
RESOLUTION_BITS = 11               # Left justified in the two bytes
CELSIUS_PER_BIT = 0.125

_SHIFT = 16 - RESOLUTION_BITS      # The low bits that carry nothing
_SIGN = 1 << (RESOLUTION_BITS - 1)
_RANGE = 1 << RESOLUTION_BITS

class At30tse:
    """One AT30TSE752A at "address" on "bus".

    The bus is given, and never opened here.  It needs one method,
    read_i2c_block_data(address, register, length)"""

    def __init__(self, bus, address):
        self.bus = bus
        self.address = address

    def celsius(self):
        """The temperature of whatever the part is against, which on a
        battery board is the pack.  Raises OSError when it does not answer"""

        data = self.bus.read_i2c_block_data(
            self.address, REGISTER_TEMPERATURE, 2)
        raw = ((data[0] << 8) | data[1]) >> _SHIFT
        if raw & _SIGN:                            # Two's complement, 11 bits
            raw -= _RANGE
        return raw * CELSIUS_PER_BIT

    def identified(self):
        """Whether a part answers at this address.  The AT30TSE752A has no
        identification register, so a plausible temperature is the only
        evidence that there is.  A reading outside the part's own range of
        -55 C to 125 C is not this part"""

        try:
            return -55.0 <= self.celsius() <= 125.0
        except OSError:
            return False

# --------------------------------------------------------------------------- #
