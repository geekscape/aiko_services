# Aiko Services actors: the WhisPlay Actor
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# The WhisPlay HAT as an Aiko Services Actor: the camera on the panel, and a
# long button press that performs an action.  It replaces the vendor
# demonstration that /etc/rc.local used to start.
#
# The panel is driven directly, in colour, because "display:0" is one bit at
# 128x64 and has no image command.  Epic 4 absorbs the panel when display:0
# gains a real depth.
#
# Usage: aiko_whisplay --help  (see cli.py)

from aiko_services.actors.whisplay.button import (  # noqa: F401
    BUTTON_ACTIVE_HIGH, BUTTON_GPIO, Button, FakeButtonImpl,
    GpioButtonImpl, LONG_PRESS_SECONDS,
    choose_button, classify,
)
from aiko_services.actors.whisplay.camera import (  # noqa: F401
    Camera, CameraNotFound, FakeCameraImpl, Picamera2CameraImpl, choose_camera,
)
from aiko_services.actors.whisplay.frame import (  # noqa: F401
    IMAGE_SIZE, PANEL_SIZE, TEXT_LINES, compose, parse_resolution, to_rgb565,
)
from aiko_services.actors.whisplay.panel import (  # noqa: F401
    NullPanelImpl, Panel, St7789PanelImpl, WindowPanelImpl, Y_OFFSET,
    choose_panel,
)
from aiko_services.actors.whisplay.whisplay import (  # noqa: F401
    ACTIONS, PROTOCOL, SETTINGS, WIRE_COMMANDS, WhisPlay, WhisPlayImpl,
    service_tags,
)

__all__ = [
    "ACTIONS", "BUTTON_ACTIVE_HIGH", "BUTTON_GPIO", "Button", "Camera",
    "CameraNotFound",
    "FakeButtonImpl", "FakeCameraImpl", "GpioButtonImpl", "IMAGE_SIZE",
    "LONG_PRESS_SECONDS", "NullPanelImpl", "PANEL_SIZE", "PROTOCOL", "Panel",
    "Picamera2CameraImpl", "SETTINGS", "St7789PanelImpl", "TEXT_LINES",
    "WIRE_COMMANDS", "WhisPlay", "WhisPlayImpl", "WindowPanelImpl", "Y_OFFSET",
    "choose_button", "choose_camera", "choose_panel", "classify", "compose",
    "parse_resolution", "service_tags", "to_rgb565",
]
