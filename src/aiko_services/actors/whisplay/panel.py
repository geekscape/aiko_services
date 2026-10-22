#!/usr/bin/env python3
#
# Aiko Services: WhisPlay Actor, the panel
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# Where the picture goes.  One Interface, three Implementations: the real
# ST7789 panel, a desktop window and nothing at all.
#
# The window Impl is not a convenience.  It is how the whole Actor runs on a
# laptop with no HAT, in the way a desktop window stands in for the OLED of
# the Display Actor.
#
# The ST7789 detail that matters: the controller is 240x320 and the glass is
# 240x280, so the panel starts at row 20.  set_window() adds that offset.
# Get it wrong and the picture is shifted, not absent, which is a slow thing
# to notice.  The backlight is active LOW.
#
# To Do
# ~~~~~
# * Partial updates: only the rows that changed, which matters more as the
#   frame rate rises
# * Brightness, through the backlight PWM, as a shared variable

from abc import abstractmethod
import time

import aiko_services as aiko

from aiko_services.actors.whisplay.frame import PANEL_SIZE, to_rgb565

__all__ = [
    "BACKLIGHT_GPIO", "DC_GPIO", "NullPanelImpl", "Panel", "RESET_GPIO",
    "St7789PanelImpl", "WindowPanelImpl", "Y_OFFSET", "choose_panel",
    "panel_args"
]

DC_GPIO = 27                   # BOARD pin 13
RESET_GPIO = 4                 # BOARD pin 7
BACKLIGHT_GPIO = 22            # BOARD pin 15, active LOW
SPI_BUS, SPI_DEVICE = 0, 0
SPI_SPEED_HZ = 40_000_000
Y_OFFSET = 20                  # 240x280 glass on a 240x320 controller
CHUNK = 4096                   # The SPI driver's limit for one write

# The ST7789 start-up sequence, as the WhisPlay panel needs it
_INITIALIZE = (
    (0x36, (0xC0,)),                                  # Memory access control
    (0x3A, (0x05,)),                                  # RGB565
    (0xB2, (0x0C, 0x0C, 0x00, 0x33, 0x33)),           # Porch
    (0xB7, (0x35,)),                                  # Gate
    (0xBB, (0x32,)),                                  # VCOM
    (0xC2, (0x01,)),
    (0xC3, (0x15,)),                                  # VRH
    (0xC4, (0x20,)),                                  # VDV
    (0xC6, (0x0F,)),                                  # Frame rate
    (0xD0, (0xA4, 0xA1)),                             # Power control
    (0xE0, (0xD0, 0x08, 0x0E, 0x09, 0x09, 0x05, 0x31,
            0x33, 0x48, 0x17, 0x14, 0x15, 0x31, 0x34)),   # Gamma, positive
    (0xE1, (0xD0, 0x08, 0x0E, 0x09, 0x09, 0x15, 0x31,
            0x33, 0x48, 0x17, 0x14, 0x15, 0x31, 0x34)),   # Gamma, negative
    (0x21, ()),                                       # Inversion on
    (0x29, ()),                                       # Display on
)

class Panel(aiko.Interface):
    """Where the picture goes.  open() acquires the panel, show(image) puts
    one PIL frame on it, power(on) turns the panel and its backlight on or
    off, and close() releases it.  Every function is called from the Actor's
    own worker thread, which owns this object"""

    aiko.Interface.default(
        "Panel", "aiko_services.actors.whisplay.panel.NullPanelImpl")

    @abstractmethod
    def open(self):
        """Acquire the panel"""

    @abstractmethod
    def show(self, image):
        """Put one PIL frame on the panel"""

    @abstractmethod
    def power(self, on):
        """The panel and its backlight on or off"""

    @abstractmethod
    def close(self):
        """Release the panel"""

class NullPanelImpl(Panel):
    """No panel at all: the default Impl, and the test double.  The last
    frame is kept, so a test can look at what would have been shown"""

    device = "none"

    def __init__(self, context, size=PANEL_SIZE, **_):
        self.size = size
        self.frame = None
        self.powered = True

    def open(self):
        pass

    def show(self, image):
        self.frame = image

    def power(self, on):
        self.powered = bool(on)

    def close(self):
        pass

class WindowPanelImpl(NullPanelImpl):
    """A desktop window, through pygame, so that the Actor runs on a laptop
    with no HAT.  Keeps the last frame, as the null Impl does"""

    device = "window"

    def __init__(self, context, size=PANEL_SIZE, title="WhisPlay", **_):
        self.size = size
        self.title = title
        self.frame = None
        self.powered = True
        self._surface = None

    def open(self):
        import pygame                              # only needed here

        pygame.init()
        pygame.display.set_caption(self.title)
        self._surface = pygame.display.set_mode(self.size)

    def show(self, image):
        import pygame

        self.frame = image
        if self._surface is None:
            return
        pygame.event.pump()                        # keep the window alive
        shown = image if self.powered else image.point(lambda _: 0)
        surface = pygame.image.frombuffer(
            shown.convert("RGB").tobytes(), self.size, "RGB")
        self._surface.blit(surface, (0, 0))
        pygame.display.flip()

    def close(self):
        import pygame

        if self._surface is not None:
            pygame.display.quit()
            self._surface = None

class St7789PanelImpl(Panel):
    """The WhisPlay ST7789 panel, over spidev, in RGB565"""

    device = "st7789"

    def __init__(self, context, size=PANEL_SIZE, dc_gpio=DC_GPIO,
        reset_gpio=RESET_GPIO, backlight_gpio=BACKLIGHT_GPIO,
        speed_hz=SPI_SPEED_HZ, **_):

        self.size = size
        self.dc_gpio, self.reset_gpio = dc_gpio, reset_gpio
        self.backlight_gpio, self.speed_hz = backlight_gpio, speed_hz
        self.powered = True
        self._spi = None
        self._dc = self._reset = self._backlight = None

    def open(self):
        import spidev                              # only needed here
        from gpiozero import DigitalOutputDevice

        self._dc = DigitalOutputDevice(self.dc_gpio)
        self._reset = DigitalOutputDevice(self.reset_gpio)
        # Active LOW, so initial_value False lights the backlight
        self._backlight = DigitalOutputDevice(
            self.backlight_gpio, active_high=False, initial_value=True)

        self._spi = spidev.SpiDev()
        self._spi.open(SPI_BUS, SPI_DEVICE)
        self._spi.max_speed_hz = self.speed_hz
        self._spi.mode = 0

        self._reset.on(); time.sleep(0.1)
        self._reset.off(); time.sleep(0.1)
        self._reset.on(); time.sleep(0.12)

        self._command(0x11)                        # Sleep out
        time.sleep(0.12)
        for command, data in _INITIALIZE:
            self._command(command, *data)

    def show(self, image):
        if image.size != tuple(self.size):
            image = image.resize(tuple(self.size))
        width, height = self.size
        self._set_window(0, 0, width - 1, height - 1)
        self._data(to_rgb565(image))

    def power(self, on):
        self.powered = bool(on)
        self._command(0x29 if self.powered else 0x28)
        if self._backlight:
            self._backlight.value = self.powered

    def close(self):
        if self._spi:
            self.power(False)
            self._spi.close()
            self._spi = None
        for device in (self._dc, self._reset, self._backlight):
            if device:
                device.close()
        self._dc = self._reset = self._backlight = None

    def _command(self, command, *data):
        self._dc.off()                             # command
        self._spi.xfer2([command])
        if data:
            self._data(bytes(data))

    def _data(self, data):
        self._dc.on()                              # data
        for start in range(0, len(data), CHUNK):
            self._spi.writebytes2(data[start:start + CHUNK])

    def _set_window(self, x0, y0, x1, y1):
        """The glass starts at row Y_OFFSET of the controller"""

        self._command(0x2A, x0 >> 8, x0 & 0xFF, x1 >> 8, x1 & 0xFF)
        y0, y1 = y0 + Y_OFFSET, y1 + Y_OFFSET
        self._command(0x2B, y0 >> 8, y0 & 0xFF, y1 >> 8, y1 & 0xFF)
        self._command(0x2C)                        # Write to memory

# Composition -------------------------------------------------------------- #

def panel_args(**parameters):
    """init_args for composing a Panel Impl"""

    return {"context": aiko.Context(), **parameters}

def choose_panel(panel="auto", **parameters):
    """The composed Panel.  "auto" is the ST7789 where the SPI device
    exists, else a window where there is a desktop and pygame, else nothing.
    No device is opened here: see open()"""

    import importlib.util
    import os
    from pathlib import Path
    import sys

    if panel == "auto":
        has_desktop = sys.platform == "darwin" or os.environ.get("DISPLAY")  \
            or os.environ.get("WAYLAND_DISPLAY")
        if Path(f"/dev/spidev{SPI_BUS}.{SPI_DEVICE}").exists():
            panel = "st7789"
        elif has_desktop and importlib.util.find_spec("pygame"):
            panel = "window"
        else:
            panel = "none"
    impls = {
        "st7789": St7789PanelImpl, "window": WindowPanelImpl,
        "none": NullPanelImpl
    }
    if panel not in impls:
        raise ValueError(f'unknown panel "{panel}": one of {sorted(impls)}')
    return aiko.compose_instance(impls[panel], panel_args(**parameters))

# --------------------------------------------------------------------------- #
