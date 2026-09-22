# IDS peak device layer for GenICam GigE Vision cameras, the "peak"
# backend of the "gigev://" DataScheme (scheme_gigev.py)
#
# Runs on Linux and Windows only: IDS peak has no macOS support.  Needs
# the native IDS peak SDK (drivers and the GenTL producer, a .cti file)
# and the Python bindings: pip install "aiko_services[ids_peak]"
#
# Two regimes ...
# - Stills, trigger "software": one software trigger per capture(), so
#   each exposure is fresh and the link idles between frames
# - Video, trigger "off": free-running at AcquisitionFrameRate
# The DataScheme picks the regime from frame_rate unless told otherwise
#
# Resolution: the area of interest (OffsetX/Y, Width/Height) and the
# camera's decimation or binning nodes deliver the requested size where
# they can, and a host-side resize covers the remainder
#
# GigE notes
# ~~~~~~~~~~
# - The camera needs a valid IP address first: the IDS peak Cockpit camera
#   manager, or the "IDS IP Config" tool as root; link-local works
# - Full 12 MP at 8 bits is about 989 Mbit/s at the 10 fps maximum: a few
#   frames per second need no tuning, more needs a NIC MTU of 9000 and a
#   larger receive buffer (the SDK ships ids_set_receive_buffer_size.sh)
# - The GenTL loader finds the producer through GENICAM_GENTL64_PATH; the
#   IDS package sets it for new login shells only, so the standard install
#   locations are searched here too
#
# To Do
# ~~~~~
# - IDS peak IPL is deprecated in favour of ICV: migrate the debayer
# - Verify the frame-rate and decimation node names on more models

import glob
import os

import numpy as np

from aiko_services.elements.cameras import camera

__all__ = ["IDS_PEAK_DIAGNOSTIC", "IDS_PEAK_IMPORTED", "IdsPeakCamera",
           "ensure_gentl_path"]

IDS_PEAK_IMPORTED = False
IDS_PEAK_DIAGNOSTIC = ""
try:
    from ids_peak import ids_peak, ids_peak_ipl_extension
    from ids_peak_ipl import ids_peak_ipl
    IDS_PEAK_IMPORTED = True
except ImportError:
    ids_peak = ids_peak_ipl_extension = ids_peak_ipl = None
    IDS_PEAK_DIAGNOSTIC = "camera_ids_peak.py: the IDS peak bindings are "  \
        'not installed (Linux and Windows only): pip install '  \
        '"aiko_services[ids_peak]", plus the native IDS peak SDK, which '  \
        "provides the GenTL producer (.cti)"

CTI_SEARCH_PATTERNS = [
    "/usr/lib/*/ids-peak/cti",            # ids-peak Debian / Ubuntu packages
    "/usr/lib/ids-peak/cti",
    "/usr/lib/ids/cti",
    "/usr/lib/*/ids/cti",
    "/usr/local/lib/ids/cti",
    "/opt/ids-peak*/lib/*/ids-peak/cti",  # tarball install under /opt
]
FRAME_RATE_NODES = (                      # probed in order
    ("AcquisitionFrameRateEnable", "AcquisitionFrameRate"),
    ("AcquisitionFrameRateTargetEnable", "AcquisitionFrameRateTarget"))
DECIMATION_NODES = ("DecimationHorizontal", "DecimationVertical")
BINNING_NODES = ("BinningHorizontal", "BinningVertical")
DECIMATION_CANDIDATES = (1, 2, 3, 4, 8)
TARGET_PIXEL_FORMAT = "BayerRG8"          # raw Bayer: debayer on the host

def ensure_gentl_path():
    """GENICAM_GENTL64_PATH, set from the standard install locations when
    the environment does not carry it; returns the value or None"""

    if not os.environ.get("GENICAM_GENTL64_PATH"):
        for pattern in CTI_SEARCH_PATTERNS:
            matches = sorted(glob.glob(pattern))
            if matches:
                os.environ["GENICAM_GENTL64_PATH"] = matches[-1]
                break
    return os.environ.get("GENICAM_GENTL64_PATH")

# --------------------------------------------------------------------------- #

class IdsPeakCamera(camera.Camera):
    def __init__(self, address=None, resolution=None, frame_rate=None,
        resize_mode="crop", trigger="off", aux_stream=True, logger=None):

        super().__init__(address, resolution, frame_rate, resize_mode,
                         trigger, aux_stream, logger)
        self.device = None
        self.nodemap = None
        self.stream = None
        self.converter = None
        self._library_initialized = False
        self._host_size = None
        self.decimation = 1

    @classmethod
    def available(cls) -> bool:
        return IDS_PEAK_IMPORTED

    @classmethod
    def diagnostic(cls) -> str:
        return IDS_PEAK_DIAGNOSTIC

    @classmethod
    def sdk_version(cls) -> str:
        if not ids_peak:
            return "-"
        try:
            return ids_peak.Library.Version().ToString()
        except Exception:
            return getattr(ids_peak, "__version__", "-")

    # GenICam node helpers -------------------------------------------------- #

    def _node(self, name):
        return self.nodemap.FindNode(name)

    def _execute(self, name):
        node = self._node(name)
        node.Execute()
        node.WaitUntilDone()

    def _set_float(self, name, value):
        node = self._node(name)
        value = float(min(max(value, node.Minimum()), node.Maximum()))
        node.SetValue(value)
        return node.Value()

    def _set_integer(self, name, value):
        node = self._node(name)
        increment = 1
        try:
            increment = max(1, int(node.Increment()))
        except Exception:
            pass
        value = int(value) - int(value) % increment
        value = int(min(max(value, node.Minimum()), node.Maximum()))
        node.SetValue(value)
        return node.Value()

    def _try(self, action, default=None):
        try:
            return action()
        except Exception:
            return default

    # Open, capture, close ------------------------------------------------- #

    def open(self):
        if not IDS_PEAK_IMPORTED:
            raise RuntimeError(IDS_PEAK_DIAGNOSTIC)
        if not ensure_gentl_path():
            raise RuntimeError(
                "GENICAM_GENTL64_PATH is not set and no GenTL producer "
                "(.cti) was found in the standard locations: is the native "
                "IDS peak SDK installed?  Locate it with "
                "\"find /usr /opt -name '*.cti'\" and export the directory")

        ids_peak.Library.Initialize()
        self._library_initialized = True
        device_manager = ids_peak.DeviceManager.Instance()
        device_manager.Update()               # GVCP broadcast discovery
        descriptors = [descriptor for descriptor in device_manager.Devices()
            if descriptor.IsOpenable(ids_peak.DeviceAccessType_Control)]
        if self.address:
            descriptors = [descriptor for descriptor in descriptors
                if any(self.address in text for text in (
                    self._try(descriptor.DisplayName, ""),
                    self._try(descriptor.Key, ""),
                    self._try(descriptor.SerialNumber, "")))]
        if not descriptors:
            matching = f" matching {self.address!r}" if self.address else ""
            raise RuntimeError(
                f"No openable GigE camera found{matching}: check the "
                "camera's IP configuration (IDS IP Config) and "
                "GENICAM_GENTL64_PATH")

        self.device = descriptors[0].OpenDevice(
            ids_peak.DeviceAccessType_Control)
        self.nodemap = self.device.RemoteDevice().NodeMaps()[0]
        self._node("UserSetSelector").SetCurrentEntry("Default")
        self._execute("UserSetLoad")          # known-good starting point

        native = (self._try(lambda: int(self._node("WidthMax").Value()),
                            camera.NATIVE_RESOLUTION[0]),
                  self._try(lambda: int(self._node("HeightMax").Value()),
                            camera.NATIVE_RESOLUTION[1]))
        aoi, decimation, self._host_size = camera.plan_resolution(
            native, self._resolution, self.resize_mode,
            self._decimation_candidates())
        self._apply_geometry(aoi, decimation)
        self._try(lambda: self._node("PixelFormat").SetCurrentEntry(
            TARGET_PIXEL_FORMAT))             # else keep the user set's

        if self.trigger == "software":
            try:
                self._node("TriggerSelector").SetCurrentEntry("ExposureStart")
            except Exception:
                self._node("TriggerSelector").SetCurrentEntry("FrameStart")
            self._node("TriggerMode").SetCurrentEntry("On")
            self._node("TriggerSource").SetCurrentEntry("Software")
        else:
            self._try(lambda: self._node("TriggerMode").SetCurrentEntry("Off"))
            if self._frame_rate:
                actual = self._apply_frame_rate(self._frame_rate)
                if actual is not None:
                    self._frame_rate = actual

        self.stream = self.device.DataStreams()[0].OpenDataStream()
        payload_size = self._node("PayloadSize").Value()
        for _ in range(self.stream.NumBuffersAnnouncedMinRequired()):
            buffer = self.stream.AllocAndAnnounceBuffer(payload_size)
            self.stream.QueueBuffer(buffer)
        self.converter = ids_peak_ipl.ImageConverter()  # reuse: no reallocs
        self._node("TLParamsLocked").SetValue(1)
        self.stream.StartAcquisition()
        self._execute("AcquisitionStart")

        width = self._try(lambda: int(self._node("Width").Value()))
        height = self._try(lambda: int(self._node("Height").Value()))
        self._resolution = self._host_size or (
            (width, height) if width and height else self._resolution)

    def _decimation_candidates(self):
        for names in (DECIMATION_NODES, BINNING_NODES):
            try:
                node = self._node(names[0])
                low, high = int(node.Minimum()), int(node.Maximum())
                return [c for c in DECIMATION_CANDIDATES if low <= c <= high]
            except Exception:
                continue
        return [1]

    def _apply_geometry(self, aoi, decimation):
        x, y, width, height = aoi
        self._try(lambda: self._set_integer("OffsetX", 0))
        self._try(lambda: self._set_integer("OffsetY", 0))
        if decimation > 1:
            applied = False
            for names in (DECIMATION_NODES, BINNING_NODES):
                try:
                    for name in names:
                        self._node(name).SetValue(int(decimation))
                    applied = True
                    break
                except Exception:
                    continue
            if not applied:
                self._log("warning", f"decimation {decimation} not "
                          "accepted, resizing on the host instead")
                if self._resolution:
                    self._host_size = tuple(self._resolution)
                decimation = 1
        self.decimation = decimation
        self._set_integer("Width", width // decimation)
        self._set_integer("Height", height // decimation)
        self._try(lambda: self._set_integer("OffsetX", x // decimation))
        self._try(lambda: self._set_integer("OffsetY", y // decimation))

    def _apply_frame_rate(self, frame_rate):
        for enable_name, rate_name in FRAME_RATE_NODES:
            try:
                self._try(lambda: self._node(enable_name).SetValue(True))
                actual = self._set_float(rate_name, frame_rate)
                if abs(actual - frame_rate) > 0.01:
                    self._log("warning", f"frame_rate {frame_rate} clamped "
                              f"to {actual:.2f} by the camera")
                return actual
            except Exception:
                continue
        self._log("warning", "the camera has no frame rate node: running "
                  "at its own rate")
        return None

    def set_exposure(self, exposure_us):
        with self.lock:
            return self._set_float("ExposureTime", exposure_us)

    def set_gain(self, gain):
        with self.lock:
            self._try(lambda: self._node("GainSelector").SetCurrentEntry(
                "AnalogAll"))                 # single-gain models: no node
            return self._set_float("Gain", gain)

    def capture(self, timeout_s=camera.CAPTURE_TIMEOUT_S):
        """Returns (numpy uint8 HxWx3 RGB image, metadata dict)"""

        with self.lock:
            if not self.stream:
                raise RuntimeError("GigE camera is not open")
            if self.trigger == "software":
                self._execute("TriggerSoftware")
            try:
                buffer = self.stream.WaitForFinishedBuffer(
                    int(timeout_s * 1000))
            except Exception as exception:
                if "Timeout" in type(exception).__name__:
                    raise camera.CaptureTimeout(
                        f"GigE camera: no frame within {timeout_s} s")
                raise
            try:
                if buffer.IsIncomplete():
                    raise RuntimeError(
                        "Incomplete buffer (GigE packet loss): set the NIC "
                        "MTU to 9000 and raise net.core.rmem_max")
                image_raw = ids_peak_ipl_extension.BufferToImage(buffer)
                image_rgb = self.converter.Convert(  # debayer, copies
                    image_raw, ids_peak_ipl.PixelFormatName_RGB8)
                image = image_rgb.get_numpy_3D().copy()
            finally:
                self.stream.QueueBuffer(buffer)
            metadata = {"pixel_format": self._try(
                lambda: self._node("PixelFormat").CurrentEntry()
                .SymbolicValue(), "-")}
            for name, key in (("ExposureTime", "exposure_us"),
                              ("Gain", "gain")):
                value = self._try(lambda: float(self._node(name).Value()))
                if value is not None:
                    metadata[key] = value
        if self._host_size:
            image = camera.resize_image(
                np.ascontiguousarray(image), self._host_size,
                self.resize_mode)
        return image, metadata

    def device_id(self):
        return self._try(lambda: self.device.SerialNumber())

    def close(self):
        with self.lock:
            try:
                if self.nodemap:
                    self._try(lambda: self._execute("AcquisitionStop"))
                if self.stream:
                    self._try(lambda: self.stream.StopAcquisition(
                        ids_peak.AcquisitionStopMode_Default))
                    self._try(lambda: self.stream.Flush(
                        ids_peak.DataStreamFlushMode_DiscardAll))
                    for buffer in self._try(
                            self.stream.AnnouncedBuffers, []) or []:
                        self._try(lambda: self.stream.RevokeBuffer(buffer))
                    self.stream = None
                if self.nodemap:
                    self._try(lambda: self._node("TLParamsLocked").SetValue(0))
                    self.nodemap = None
                self.device = None
            finally:
                if self._library_initialized:
                    self._try(ids_peak.Library.Close)
                    self._library_initialized = False

# --------------------------------------------------------------------------- #
