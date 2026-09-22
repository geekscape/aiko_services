# DataSchemeDepthAI: the "depthai://" DataScheme for Luxonis OAK cameras
# through the DepthAI v3 SDK (camera_oak_d.py), on the shared camera scheme
# base (scheme_camera.py), which documents the URL grammar, the common
# parameters, the shared state and the threads
#
# - "(depthai://)"           the first camera found (discovery)
# - "(depthai://<address>)"  an IP address, a device id or a USB path,
#                            whatever dai.DeviceInfo() accepts
#
# parameter: "settle"      default "30" frames: the OAK 3A loops (auto
#                          focus, exposure, white balance) need them; the
#                          wait ends early once lens_position and
#                          iso_sensitivity are stable
# parameter: "aux_stream"  true: the 640x480 @ 10 fps stream that makes
#                          the 3A loops converge about four times faster
#
# Shared state adds: aux_stream, sensor.iso_sensitivity,
#   sensor.lens_position, sensor.color_temperature_k
# Writable keys: capture_timeout, log_frames (the base's).  Exposure and
#   ISO stay under the camera's own control until the control queue is
#   wired (To Do)
#
# To Do
# ~~~~~
# - Writable exposure_us / iso through the OAK control queue

import aiko_services as aiko
from aiko_services.elements.cameras import camera
from aiko_services.elements.cameras.camera_oak_d import OakDCamera  # seam
from aiko_services.elements.cameras.scheme_camera import DataSchemeCamera

__all__ = ["DataSchemeDepthAI"]

SCHEME = "depthai"
DEFAULT_SETTLE = "30"

# --------------------------------------------------------------------------- #

class DataSchemeDepthAI(DataSchemeCamera):
    scheme = SCHEME
    camera_name = "OAK camera"
    default_settle = DEFAULT_SETTLE

    def _camera_class(self, settings):
        camera_class = OakDCamera         # module global: tests patch it
        if not camera_class.available():
            raise RuntimeError(camera_class.diagnostic())
        return camera_class

    def _extra_settings(self, settings):
        settings["aux_stream"] = camera.parse_bool(
            self.pipeline_element.get_parameter("aux_stream", True)[0],
            "aux_stream")

    def _start_warm_up(self, settings):
        self.settle = camera.SettleMonitor(settings["settle"])
        self._publish("aux_stream", str(settings["aux_stream"]).lower())

aiko.DataScheme.add_data_scheme(SCHEME, DataSchemeDepthAI)

# --------------------------------------------------------------------------- #
