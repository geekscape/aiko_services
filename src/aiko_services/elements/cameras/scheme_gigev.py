# DataSchemeGigE: the "gigev://" DataScheme for GenICam GigE Vision
# cameras through IDS peak (camera_ids_peak.py) or, experimentally, Aravis
# (camera_aravis.py), on the shared camera scheme base (scheme_camera.py),
# which documents the URL grammar, the common parameters, the shared state
# and the threads
#
# - "(gigev://)"                     the first camera found
# - "(gigev://<address-substring>)"  IDS peak: a substring of the device's
#                                    display name, key or serial number;
#                                    Aravis: the device id or IP address
#
# parameter: "backend"      auto | peak | aravis (default auto: IDS peak
#                           when it imports, else Aravis)
# parameter: "trigger"      auto | software | off.  auto: "software" (one
#                           trigger per frame: fresh exposures, an idle
#                           link between stills) when frame_rate <= 2,
#                           else "off" (free-running video at frame_rate)
# parameter: "exposure_us"  fixed exposure; default "auto": a highlight
#                           based auto-expose runs before the first frame,
#                           because the IDS default user set has none
# parameter: "gain"         analog gain, applied with a fixed exposure_us
# parameter: "settle"       frames discarded after an exposure change,
#                           default "2"
# In software-trigger mode "rate" defaults to frame_rate: the frame
# generator triggers one exposure per delivered frame
#
# Shared state adds: backend, trigger, exposure_us (the actual value, or
#   "auto" while auto-expose runs), gain
# Writable keys: exposure_us (a number, or "auto" to run auto-expose
#   again), gain, and the base's capture_timeout and log_frames.  They act
#   on the open camera at once and the next Stream starts from them
#
# To Do
# ~~~~~
# - Region of interest offsets as parameters (the crop is centred)

import aiko_services as aiko
from aiko_services.elements.cameras import camera
from aiko_services.elements.cameras.camera_aravis import AravisCamera
from aiko_services.elements.cameras.camera_ids_peak import IdsPeakCamera
from aiko_services.elements.cameras.scheme_camera import DataSchemeCamera

__all__ = ["BACKENDS", "DataSchemeGigE", "select_backend"]

SCHEME = "gigev"
DEFAULT_SETTLE = "2"
TRIGGER_MODES = ("auto", "software", "off")
STILLS_FRAME_RATE = 2.0             # at or below: software trigger
AUTO = ("", "none", "auto")

BACKENDS = {"peak": IdsPeakCamera, "aravis": AravisCamera}  # tests add one
BACKEND_ORDER = ("peak", "aravis")  # "auto" preference

def select_backend(name, backends=None):
    """--> (backend name, camera class), or RuntimeError naming what to
    install.  "auto" takes the first backend whose SDK imported"""

    backends = BACKENDS if backends is None else backends
    name = str(name).strip().lower()
    if name == "auto":
        order = [n for n in BACKEND_ORDER if n in backends]  \
            + [n for n in backends if n not in BACKEND_ORDER]
        for candidate in order:
            if backends[candidate].available():
                return candidate, backends[candidate]
        diagnostics = "; ".join(backends[n].diagnostic() for n in order)
        raise RuntimeError(f"No GigE camera backend is available: "
                           f"{diagnostics}")
    if name not in backends:
        raise RuntimeError(f'backend "{name}" is not one of auto, '
                           f'{", ".join(backends)}')
    if not backends[name].available():
        raise RuntimeError(backends[name].diagnostic())
    return name, backends[name]

# --------------------------------------------------------------------------- #

class DataSchemeGigE(DataSchemeCamera):
    scheme = SCHEME
    camera_name = "GigE camera"
    default_settle = DEFAULT_SETTLE

    def __init__(self, pipeline_element):
        super().__init__(pipeline_element)
        self.backend_name = None
        self._settle_frames = 0

    def _camera_class(self, settings):
        self.backend_name, camera_class = select_backend(settings["backend"])
        return camera_class

    def _extra_settings(self, settings):
        get = self.pipeline_element.get_parameter
        settings["backend"] = str(get("backend", "auto")[0]).strip().lower()
        trigger = str(get("trigger", "auto")[0]).strip().lower()
        if trigger not in TRIGGER_MODES:
            raise ValueError(f'trigger "{trigger}" must be one of '
                             f'{", ".join(TRIGGER_MODES)}')
        if trigger == "auto":
            trigger = "software"  \
                if settings["frame_rate"] <= STILLS_FRAME_RATE else "off"
        settings["trigger"] = trigger
        settings["exposure_us"] = _optional_float(
            get("exposure_us", None)[0], "exposure_us")
        settings["gain"] = _optional_float(get("gain", None)[0], "gain")
        if trigger == "software" and settings["rate"] is None:
            settings["rate"] = settings["frame_rate"]  # one trigger a frame

    def _start_warm_up(self, settings):
        self._settle_frames = settings["settle"]
        self.settle = camera.CountdownSettle(settings["settle"])
        self._publish("backend", self.backend_name)
        self._publish("trigger", settings["trigger"])
        if settings["exposure_us"] is None:
            self._publish("exposure_us", "auto")
            self.warm_up_steps = self._auto_expose_steps()
        else:
            self._set_exposure(settings["exposure_us"], settings["gain"])

    def _auto_expose_steps(self):
        steps = camera.auto_expose(self.camera, self.pipeline_element.logger,
            timeout_s=max(self.capture_timeout, 2.0))
        for done, exposure_us, gain in steps:
            values = {}
            if exposure_us is not None:
                values["exposure_us"] = f"{exposure_us:.0f}"
            if gain is not None:
                values["gain"] = f"{gain:.2f}"
            yield done, values

    def _set_exposure(self, exposure_us, gain=None):
        try:
            actual = self.camera.set_exposure(exposure_us)
            self._publish("exposure_us", f"{actual:.0f}")
            if gain is not None:
                actual_gain = self.camera.set_gain(gain)
                self._publish("gain", f"{actual_gain:.2f}")
        except Exception as exception:
            self.pipeline_element.logger.warning(
                f"{self.camera_name} exposure set-up failed: {exception}")

    def _apply_update(self, item_name, item_value):
        if item_name not in ("exposure_us", "gain"):
            return
        if not self.camera:
            raise ValueError("no camera is open")
        if item_name == "exposure_us":
            if str(item_value).strip().lower() in AUTO:
                self._publish("exposure_us", "auto")
                self.warm_up_steps = self._auto_expose_steps()
            else:
                exposure_us = float(item_value)
                if exposure_us <= 0:
                    raise ValueError("must be positive")
                actual = self.camera.set_exposure(exposure_us)
                self._publish("exposure_us", f"{actual:.0f}")
        else:
            gain = float(item_value)
            if gain < 0:
                raise ValueError("must not be negative")
            actual = self.camera.set_gain(gain)
            self._publish("gain", f"{actual:.2f}")
        self.settle = camera.CountdownSettle(self._settle_frames)
        self._publish("settled", "waiting")
        self._publish("state", "settling")

def _optional_float(value, parameter):
    if value is None or str(value).strip().lower() in AUTO:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f'{parameter} "{value}" must be a number or auto')
    if number < 0 or (parameter == "exposure_us" and number == 0):
        raise ValueError(f'{parameter} "{value}" must be positive')
    return number

aiko.DataScheme.add_data_scheme(SCHEME, DataSchemeGigE)

# --------------------------------------------------------------------------- #
