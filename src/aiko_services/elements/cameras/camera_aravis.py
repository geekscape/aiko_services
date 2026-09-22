# Aravis device layer for GenICam GigE Vision cameras, the experimental
# "aravis" backend of the "gigev://" DataScheme (scheme_gigev.py).
# Aravis is the vendor-independent GigE Vision implementation and the
# only path to such a camera on macOS
#
# Set-up (macOS):  brew install aravis pygobject3
# Set-up (Linux):  apt install gir1.2-aravis-0.8 python3-gi
#
# EXPERIMENTAL: with the camera model this was written against, Aravis
# discovers and controls the camera but no frames arrive, because every
# write of the stream packet size register reads back zero on that
# firmware.  Streaming is unverified until a retest on newer firmware.
# The "auto" backend selection prefers IDS peak whenever it imports
#
# Same Camera contract as IdsPeakCamera (camera.py), so the DataScheme,
# auto_expose() and the tests work with either backend.  Verify colours on
# first use: GenICam "BayerRG8" corresponds to OpenCV's BayerBG code; if
# red and blue swap, the demosaic code below is the place to change
#
# To Do
# ~~~~~
# - Retest streaming after the camera firmware update
# - Binning through Aravis.Camera.set_binning()

import numpy as np

from aiko_services.elements.cameras import camera

__all__ = ["ARAVIS_DIAGNOSTIC", "ARAVIS_IMPORTED", "AravisCamera"]

ARAVIS_IMPORTED = False
ARAVIS_DIAGNOSTIC = ""
try:
    import gi
    gi.require_version("Aravis", "0.8")
    from gi.repository import Aravis
    ARAVIS_IMPORTED = True
except (ImportError, ValueError, AttributeError):
    Aravis = None
    ARAVIS_DIAGNOSTIC = "camera_aravis.py: Aravis 0.8 is not available "  \
        "(experimental backend): macOS \"brew install aravis pygobject3\", "  \
        'Linux "apt install gir1.2-aravis-0.8 python3-gi"'

BUFFER_COUNT = 4

# --------------------------------------------------------------------------- #

class AravisCamera(camera.Camera):
    def __init__(self, address=None, resolution=None, frame_rate=None,
        resize_mode="crop", trigger="off", aux_stream=True, logger=None):

        super().__init__(address, resolution, frame_rate, resize_mode,
                         trigger, aux_stream, logger)
        self.camera = None
        self.stream = None
        self._host_size = None

    @classmethod
    def available(cls) -> bool:
        return ARAVIS_IMPORTED

    @classmethod
    def diagnostic(cls) -> str:
        return ARAVIS_DIAGNOSTIC

    @classmethod
    def sdk_version(cls) -> str:
        if not Aravis:
            return "-"
        try:
            return "aravis-%d.%d.%d" % (Aravis.MAJOR_VERSION,
                Aravis.MINOR_VERSION, Aravis.MICRO_VERSION)
        except Exception:
            return "aravis-0.8"

    def open(self):
        if not ARAVIS_IMPORTED:
            raise RuntimeError(ARAVIS_DIAGNOSTIC)
        self.camera = Aravis.Camera.new(self.address)  # None: the first
        try:
            self.camera.set_pixel_format(Aravis.PIXEL_FORMAT_BAYER_RG_8)
        except Exception:
            pass                       # mono model: keep the camera's format
        try:
            native = self.camera.get_width_bounds()[1],  \
                self.camera.get_height_bounds()[1]
        except Exception:
            native = camera.NATIVE_RESOLUTION
        aoi, _, self._host_size = camera.plan_resolution(
            native, self._resolution, self.resize_mode)
        try:
            self.camera.set_region(*aoi)
        except Exception as exception:
            self._log("warning", f"Aravis set_region {aoi}: {exception}")
        if self.trigger == "software":
            self.camera.set_trigger("Software")
        else:
            try:
                self.camera.set_trigger("Off")
            except Exception:
                pass
            if self._frame_rate:
                try:
                    self.camera.set_frame_rate(float(self._frame_rate))
                    self._frame_rate = float(self.camera.get_frame_rate())
                except Exception as exception:
                    self._log("warning",
                              f"Aravis set_frame_rate: {exception}")

        self.stream = self.camera.create_stream(None, None)
        if self.stream is None:
            raise RuntimeError(
                "Could not create an Aravis stream (a firewall blocking "
                "GVSP UDP, or the camera on another subnet?)")
        payload = self.camera.get_payload()
        for _ in range(BUFFER_COUNT):
            self.stream.push_buffer(Aravis.Buffer.new_allocate(payload))
        self.camera.start_acquisition()
        try:
            _, _, width, height = self.camera.get_region()
            self._resolution = self._host_size or (width, height)
        except Exception:
            pass

    def capture(self, timeout_s=camera.CAPTURE_TIMEOUT_S):
        """Returns (numpy uint8 HxWx3 RGB image, metadata dict)"""

        import cv2                     # lazy: the package imports without it

        with self.lock:
            if not self.stream:
                raise RuntimeError("GigE camera is not open")
            if self.trigger == "software":
                self.camera.software_trigger()
            buffer = self.stream.timeout_pop_buffer(int(timeout_s * 1e6))
            if buffer is None:
                raise camera.CaptureTimeout(
                    f"GigE camera: no frame within {timeout_s} s")
            try:
                if buffer.get_status() != Aravis.BufferStatus.SUCCESS:
                    raise RuntimeError(
                        f"Aravis buffer status {buffer.get_status()}")
                height = buffer.get_image_height()
                width = buffer.get_image_width()
                raw = np.frombuffer(
                    buffer.get_data(), dtype=np.uint8)[:height * width]
                image = cv2.cvtColor(raw.reshape(height, width),
                                     cv2.COLOR_BayerBG2RGB)
            finally:
                self.stream.push_buffer(buffer)
            metadata = {"pixel_format": "BayerRG8"}
            for key, getter in (("exposure_us", "get_exposure_time"),
                                ("gain", "get_gain")):
                try:
                    metadata[key] = float(getattr(self.camera, getter)())
                except Exception:
                    pass
        if self._host_size:
            image = camera.resize_image(image, self._host_size,
                                        self.resize_mode)
        return image, metadata

    def set_exposure(self, exposure_us):
        with self.lock:
            self.camera.set_exposure_time(float(exposure_us))
            return float(self.camera.get_exposure_time())

    def set_gain(self, gain):
        with self.lock:
            self.camera.set_gain(float(gain))
            return float(self.camera.get_gain())

    def device_id(self):
        try:
            return self.camera.get_device_serial_number()
        except Exception:
            return None

    def close(self):
        with self.lock:
            if self.camera:
                try:
                    self.camera.stop_acquisition()
                except Exception:
                    pass
                self.camera = None
            self.stream = None

# --------------------------------------------------------------------------- #
