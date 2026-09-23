# Luxonis OAK camera device layer (DepthAI v3), the camera behind the
# "depthai://" DataScheme (scheme_depthai.py)
#
# Main color sensor of the OAK-D S2 family: IMX378.  The DepthAI v3 full
# resolution output delivers 4000x3000 (the ISP crops the sensor readout),
# which is NATIVE_RESOLUTION here.  A scaled output of any smaller size
# comes from the ISP with the requested resize mode
#
# Frames are requested as NV12 and converted to RGB on the host.  NV12 is
# 1.5 bytes per pixel against 3 for BGR888i: 1920x1080 at 25 fps is then
# 78 MB/s, which a gigabit PoE link carries, where BGR888i (155 MB/s)
# backs up the device's output buffers until its firmware crashes
#
# Auto-focus models: the first frames after open() are out of focus and
# under- or over-exposed while the 3A loops converge.  The auxiliary
# 640x480 @ 10 fps stream keeps the sensor pipeline busy so the loops
# converge about four times faster in wall-clock time; the DataScheme
# discards frames until "lens_position" and "iso_sensitivity" settle.
# The auxiliary stream is skipped when the main output is that size or
# smaller: two identical outputs of one Camera node crashed the SDK
#
# PoE notes
# ~~~~~~~~~
# - Discovery: UDP port 11491 broadcast (same subnet only), data TCP 11490
# - No DHCP: the device falls back to link-local 169.254.1.222, so give
#   the host interface a 169.254.0.0/16 address
# - macOS: grant Local Network permission to the terminal / Python
#   process, otherwise discovery silently finds nothing
# - A second active interface (Wi-Fi) can break discovery
#   (X_LINK_DEVICE_NOT_FOUND): turn it off, or use depthai://<address>
# - The device reboots when its handle closes and is not discoverable
#   again for some seconds: open() retries the boot for OPEN_RETRY_S
#
# To Do
# ~~~~~
# - Manual exposure and ISO through the Camera control queue
# - Convert NV12 to RGB in one step to save the BGR -> RGB copy

from datetime import timedelta
import time

from aiko_services.elements.cameras import camera

__all__ = ["DEPTHAI_DIAGNOSTIC", "DEPTHAI_IMPORTED", "OakDCamera"]

DEPTHAI_IMPORTED = False
DEPTHAI_DIAGNOSTIC = ""
try:
    import depthai as dai
    DEPTHAI_IMPORTED = True
except ImportError:                     # missing, or a wheel for another CPU
    dai = None
    DEPTHAI_DIAGNOSTIC = "camera_oak_d.py: the depthai SDK is not "  \
        'installed: pip install "aiko_services[depthai]" or pip install '  \
        "depthai (3.9 or later)"

NATIVE_RESOLUTION = camera.NATIVE_RESOLUTION
MIN_FRAME_RATE = 1.42           # the sensor configuration's minimum
AUX_RESOLUTION = (640, 480)     # the 3A accelerator stream ...
AUX_FRAME_RATE = 10.0           # ... and its rate
QUEUE_MAX_SIZE = 2              # 18 MB per 12 MP NV12 frame: keep it tiny
OUTPUT_TYPE = "NV12"            # dai.ImgFrame.Type name: link bandwidth
OPEN_RETRY_S = 30.0             # a closed device reboots: wait for it ...
OPEN_RETRY_PERIOD_S = 1.0       # ... trying this often
_NOT_FOUND = ("X_LINK_DEVICE_NOT_FOUND", "Failed to find device")
_RESIZE_MODES = {"crop": "CROP", "letterbox": "LETTERBOX",
                 "stretch": "STRETCH"}

# --------------------------------------------------------------------------- #

class OakDCamera(camera.Camera):
    def __init__(self, address=None, resolution=None, frame_rate=None,
        resize_mode="crop", trigger="off", aux_stream=True, logger=None):

        super().__init__(address, resolution, frame_rate, resize_mode,
                         trigger, aux_stream, logger)
        self.device = None
        self.pipeline = None
        self.queue = None
        self.aux_queue = None

    @classmethod
    def available(cls) -> bool:
        return DEPTHAI_IMPORTED

    @classmethod
    def diagnostic(cls) -> str:
        return DEPTHAI_DIAGNOSTIC

    @classmethod
    def sdk_version(cls) -> str:
        return getattr(dai, "__version__", "-") if dai else "-"

    def open(self):
        if not DEPTHAI_IMPORTED:
            raise RuntimeError(DEPTHAI_DIAGNOSTIC)
        frame_rate = self._frame_rate or camera.DEFAULT_FRAME_RATE
        if frame_rate < MIN_FRAME_RATE:
            self._log("warning", f"OAK frame_rate {frame_rate} is below "
                      f"the sensor minimum {MIN_FRAME_RATE}")
        self.device = self._boot_device()
        self.pipeline = dai.Pipeline(self.device)
        node = self.pipeline.create(dai.node.Camera).build(
            dai.CameraBoardSocket.CAM_A)
        if self.aux_stream and self._aux_stream_useful():
            self.aux_queue = node.requestOutput(   # self-overwriting queue
                AUX_RESOLUTION, fps=AUX_FRAME_RATE).createOutputQueue(
                maxSize=1, blocking=False)
        output_type = getattr(dai.ImgFrame.Type, OUTPUT_TYPE)
        if self._resolution is None  \
            or tuple(self._resolution) == NATIVE_RESOLUTION:
            output = node.requestFullResolutionOutput(
                type=output_type, fps=frame_rate,
                useHighestResolution=True)  # else capped below 4000x3000
        else:
            resize_mode = getattr(
                dai.ImgResizeMode, _RESIZE_MODES[self.resize_mode])
            output = node.requestOutput(tuple(self._resolution),
                type=output_type, resizeMode=resize_mode, fps=frame_rate)
        self.queue = output.createOutputQueue(
            maxSize=QUEUE_MAX_SIZE, blocking=False)
        self.pipeline.start()
        self._frame_rate = frame_rate

    def _boot_device(self):
        """dai.Device for the address (or the first found), retried while
        the device is not discoverable: a device that just closed reboots
        and comes back after some seconds"""

        deadline = time.monotonic() + OPEN_RETRY_S
        while True:
            try:
                return dai.Device(dai.DeviceInfo(self.address))  \
                    if self.address else dai.Device()
            except RuntimeError as runtime_error:
                not_found = any(text in str(runtime_error)
                                for text in _NOT_FOUND)
                if not not_found or time.monotonic() >= deadline:
                    raise
                self._log("info", "OAK camera not found yet (rebooting "
                          "after a close?), retrying")
                time.sleep(OPEN_RETRY_PERIOD_S)

    def _aux_stream_useful(self):
        """Not when the main output is the auxiliary size or smaller: it
        keeps the sensor busy by itself, and a second identical output of
        one Camera node crashed the SDK"""

        if self._resolution is None:
            return True
        width, height = self._resolution
        return width > AUX_RESOLUTION[0] or height > AUX_RESOLUTION[1]

    def capture(self, timeout_s=camera.CAPTURE_TIMEOUT_S):
        """Returns (numpy uint8 HxWx3 RGB image, metadata dict)"""

        with self.lock:
            if not self.queue:
                raise RuntimeError("OAK camera is not open")
            try:
                frame = self.queue.get(timedelta(seconds=timeout_s))
            except dai.MessageQueue.QueueException as queue_exception:
                raise RuntimeError(f"OAK camera queue closed: "
                                   f"{queue_exception}")
        if frame is None:
            raise camera.CaptureTimeout(
                f"OAK camera: no frame within {timeout_s} s")
        image_bgr = frame.getCvFrame()            # NV12 --> BGR, on the host
        image_rgb = image_bgr[..., ::-1].copy()   # BGR --> RGB
        self._resolution = (image_rgb.shape[1], image_rgb.shape[0])

        metadata = {"pixel_format": OUTPUT_TYPE}
        for name, getter in [
                ("exposure_us", frame.getExposureTime),
                ("iso_sensitivity", frame.getSensitivity),
                ("lens_position", frame.getLensPosition),
                ("color_temperature_k", frame.getColorTemperature)]:
            try:
                value = getter()
                if isinstance(value, timedelta):
                    value = value / timedelta(microseconds=1)
                metadata[name] = value
            except Exception:
                pass
        return image_rgb, metadata

    def device_id(self):
        try:
            return self.device.getDeviceId()
        except Exception:
            return None

    def close(self):
        with self.lock:
            if self.pipeline:
                try:
                    self.pipeline.stop()
                except Exception as exception:
                    self._log("warning", f"OAK pipeline stop: {exception}")
                self.pipeline = None
            if self.device:
                try:
                    self.device.close()
                except Exception as exception:
                    self._log("warning", f"OAK device close: {exception}")
                self.device = None
            self.queue = None
            self.aux_queue = None

# --------------------------------------------------------------------------- #
