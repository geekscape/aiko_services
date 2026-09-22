# Camera device contract and helpers shared by the camera DataSchemes
# (scheme_depthai.py, scheme_gigev.py) and their device layers
# (camera_oak_d.py, camera_ids_peak.py, camera_aravis.py)
#
# A device class implements the duck-typed Camera contract below, so that a
# DataScheme, the auto-expose and settle helpers, an integration test and a
# unit-test fake are interchangeable.  No camera SDK and no OpenCV is
# imported here: cv2 is imported lazily by resize_image()
#
# Parameters shared by the camera DataSources ...
# - resolution:  "WxH" (default "1920x1080"), or "native" / "full" for the
#                sensor's own size.  A camera delivers the nearest size it
#                can and publishes the actual size to share
# - frame_rate:  frames per second as 25, "25", "25.0" or a fraction "25/1"
#                (the VideoReadRTSP form), default 25.0
# - settle:      frames discarded while the camera converges after start,
#                as a count ("30") or a time ("3s"), 0 or "none": no wait
# - resize_mode: "crop" (keep the aspect ratio, crop the sensor),
#                "letterbox" (keep the aspect ratio, pad) or "stretch"
#
# capture() is bounded: the frame generator holds the Stream lock while it
# runs and destroy_stream() needs that lock, so a device wait must return
# within the timeout (CaptureTimeout) or the Stream can not end
#
# To Do
# ~~~~~
# - Device-clock timestamps (both SDKs stamp their frames) in place of
#   time.time() at the moment of dequeue

from collections import deque
import math
import re
import threading
import time

import numpy as np

__all__ = [
    "CAPTURE_TIMEOUT_LIMIT", "CAPTURE_TIMEOUT_S", "DEFAULT_FRAME_RATE",
    "DEFAULT_RESOLUTION", "NATIVE_RESOLUTION", "RESIZE_MODES",
    "Camera", "CaptureTimeout", "CountdownSettle", "RateMeter",
    "SettleMonitor", "auto_expose", "parse_bool", "parse_frame_rate",
    "parse_resolution", "parse_settle", "plan_resolution", "resize_image",
    "share_token", "utc_now"
]

NATIVE_RESOLUTION = (4000, 3000)   # both supported sensors deliver this
NATIVE_NAMES = ("native", "full")
RESIZE_MODES = ("crop", "letterbox", "stretch")
DEFAULT_RESOLUTION = "1920x1080"
DEFAULT_FRAME_RATE = 25.0
CAPTURE_TIMEOUT_S = 1.0            # bounded: destroy_stream() needs the lock
CAPTURE_TIMEOUT_LIMIT = 10         # consecutive timeouts before STOP

_RESOLUTION_RE = re.compile(r"^\s*(\d+)\s*[xX]\s*(\d+)\s*$")
_FRACTION_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)\s*$")
_SECONDS_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*s\s*$")
_TOKEN_RE = re.compile(r"[^A-Za-z0-9_.:@-]")

# --------------------------------------------------------------------------- #

class CaptureTimeout(Exception):
    """capture(): no frame within the timeout"""

class Camera:
    """The duck-typed device contract.  Subclasses implement open(),
    capture(), close() and the optional setters.  capture() returns
    (uint8 HxWx3 RGB image, metadata dict) within "timeout_s" seconds or
    raises CaptureTimeout.  The lock serialises capture() on the frame
    generator thread against setters called from the event-loop thread"""

    def __init__(self, address=None, resolution=None, frame_rate=None,
        resize_mode="crop", trigger="off", aux_stream=True, logger=None):

        self.address = address          # None: the first camera found
        self._resolution = resolution   # (w, h) or None: native
        self._frame_rate = frame_rate   # frames per second or None
        self.resize_mode = resize_mode
        self.trigger = trigger          # "off" (free-running) or "software"
        self.aux_stream = aux_stream
        self.logger = logger
        self.lock = threading.Lock()

    @classmethod
    def available(cls) -> bool:
        """True when the camera SDK imported"""

        return True

    @classmethod
    def diagnostic(cls) -> str:
        """What to install when available() is False"""

        return ""

    @classmethod
    def sdk_version(cls) -> str:
        return "-"

    def open(self):
        raise NotImplementedError

    def capture(self, timeout_s=CAPTURE_TIMEOUT_S):
        raise NotImplementedError

    def close(self):
        pass

    def device_id(self):
        return None

    def resolution(self):
        """Actual (w, h) delivered, known after open() or the first frame"""

        return self._resolution

    def frame_rate(self):
        return self._frame_rate

    def set_exposure(self, exposure_us):
        raise NotImplementedError

    def set_gain(self, gain):
        raise NotImplementedError

    def _log(self, level, message):
        if self.logger:
            getattr(self.logger, level)(message)

# --------------------------------------------------------------------------- #
# Parameter coercion: values arrive as strings from the command line

def parse_resolution(value, parameter="resolution"):
    """"1920x1080", (w, h), [w, h], "native", "full" or None.  Returns
    (w, h), or None for the sensor's native size.  Raises ValueError"""

    if value is None:
        return None
    if isinstance(value, str):
        if value.strip().lower() in NATIVE_NAMES:
            return None
        match = _RESOLUTION_RE.match(value)
        if not match:
            raise ValueError(
                f'{parameter} "{value}" must be WxH, "native" or "full"')
        width, height = int(match.group(1)), int(match.group(2))
    else:
        try:
            width, height = int(value[0]), int(value[1])
        except (TypeError, ValueError, IndexError):
            raise ValueError(f'{parameter} "{value}" must be WxH')
    if width <= 0 or height <= 0:
        raise ValueError(f'{parameter} "{value}" must be positive')
    return width, height

def parse_frame_rate(value, parameter="frame_rate"):
    """25, 25.0, "25", "25.0", "25/1" or "30000/1001" --> float > 0.
    Raises ValueError"""

    if isinstance(value, str):
        match = _FRACTION_RE.match(value)
        try:
            if match:
                numerator, denominator = float(match.group(1)),  \
                    float(match.group(2))
                if denominator <= 0:
                    raise ValueError
                frame_rate = numerator / denominator
            else:
                frame_rate = float(value)
        except ValueError:
            raise ValueError(f'{parameter} "{value}" must be a number of '
                             'frames per second or a fraction such as 25/1')
    else:
        try:
            frame_rate = float(value)
        except (TypeError, ValueError):
            raise ValueError(f'{parameter} "{value}" must be a number')
    if not math.isfinite(frame_rate) or frame_rate <= 0:
        raise ValueError(f'{parameter} "{value}" must be positive')
    return frame_rate

def parse_settle(value, frame_rate, parameter="settle"):
    """"30" (frames), "3s" (seconds at frame_rate), 0, "none" or "off"
    --> frames to discard, an integer >= 0.  Raises ValueError"""

    if value is None:
        return 0
    if isinstance(value, str):
        text = value.strip().lower()
        if text in ("", "none", "off", "false"):
            return 0
        match = _SECONDS_RE.match(text)
        if match:
            return int(math.ceil(float(match.group(1)) * frame_rate))
        try:
            frames = int(float(text))
        except ValueError:
            raise ValueError(
                f'{parameter} "{value}" must be a frame count or seconds '
                'such as "3s"')
    else:
        try:
            frames = int(value)
        except (TypeError, ValueError):
            raise ValueError(f'{parameter} "{value}" must be a frame count')
    if frames < 0:
        raise ValueError(f'{parameter} "{value}" must not be negative')
    return frames

def parse_bool(value, parameter="parameter"):
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in ("true", "1", "yes", "on"):
        return True
    if text in ("false", "0", "no", "off", ""):
        return False
    raise ValueError(f'{parameter} "{value}" must be true or false')

def parse_resize_mode(value, parameter="resize_mode"):
    mode = str(value).strip().lower()
    if mode not in RESIZE_MODES:
        raise ValueError(
            f'{parameter} "{value}" must be one of {", ".join(RESIZE_MODES)}')
    return mode

# --------------------------------------------------------------------------- #
# Resolution planning and host-side resizing

def plan_resolution(native, target, mode="crop", decimations=(1,)):
    """How a sensor of "native" (w, h) delivers "target" (w, h): returns
    (aoi, decimation, host_size).  "aoi" is (x, y, w, h) on the sensor,
    "decimation" the sub-sampling factor chosen from "decimations" (1 when
    the camera has none) and "host_size" the (w, h) of a host-side resize
    still needed, or None.  target None: the full sensor, factor 1, no
    resize"""

    native_width, native_height = native
    if target is None:
        return (0, 0, native_width, native_height), 1, None
    target_width, target_height = target
    if mode == "crop":
        aoi_width = min(native_width,
            int(round(native_height * target_width / target_height)))
        aoi_height = min(native_height,
            int(round(native_width * target_height / target_width)))
    else:
        aoi_width, aoi_height = native_width, native_height
    x = (native_width - aoi_width) // 2
    y = (native_height - aoi_height) // 2

    decimation = 1
    for candidate in sorted(set(int(d) for d in decimations), reverse=True):
        if candidate >= 1 and aoi_width // candidate >= target_width  \
            and aoi_height // candidate >= target_height:
            decimation = candidate
            break
    delivered = (aoi_width // decimation, aoi_height // decimation)
    host_size = None if delivered == (target_width, target_height)  \
        else (target_width, target_height)
    return (x, y, aoi_width, aoi_height), decimation, host_size

def resize_image(image, size, mode="crop"):
    """uint8 HxWx3 --> exactly size (w, h).  crop: centre-crop to the
    target aspect ratio then resize; letterbox: fit inside, pad black;
    stretch: resize without regard to the aspect ratio"""

    import cv2                          # lazy: the package imports without it

    target_width, target_height = size
    height, width = image.shape[:2]
    if (width, height) == (target_width, target_height):
        return image
    interpolation = cv2.INTER_AREA  \
        if width > target_width else cv2.INTER_LINEAR
    if mode == "crop":
        crop_width = min(width, int(round(height * target_width /
                                          target_height)))
        crop_height = min(height, int(round(width * target_height /
                                            target_width)))
        x = (width - crop_width) // 2
        y = (height - crop_height) // 2
        image = image[y:y + crop_height, x:x + crop_width]
        return cv2.resize(image, (target_width, target_height),
                          interpolation=interpolation)
    if mode == "letterbox":
        scale = min(target_width / width, target_height / height)
        fit_width = max(1, int(round(width * scale)))
        fit_height = max(1, int(round(height * scale)))
        fitted = cv2.resize(image, (fit_width, fit_height),
                            interpolation=interpolation)
        canvas = np.zeros((target_height, target_width) + image.shape[2:],
                          dtype=image.dtype)
        x = (target_width - fit_width) // 2
        y = (target_height - fit_height) // 2
        canvas[y:y + fit_height, x:x + fit_width] = fitted
        return canvas
    return cv2.resize(image, (target_width, target_height),
                      interpolation=interpolation)

# --------------------------------------------------------------------------- #
# Warm-up helpers: one step per frame generator call, so start_stream()
# never blocks and the Stream can still be destroyed while a camera settles

class SettleMonitor:
    """Auto-focus / auto-exposure convergence: done once "lens_position"
    is engaged (> 0) and within +-2, and "iso_sensitivity" within 5 %,
    over three consecutive frames, or when max_frames were fed (then
    "timed_out" is True).  max_frames 0: done at once"""

    def __init__(self, max_frames, history=3):
        self.max_frames = int(max_frames)
        self.history = history
        self.frames = 0
        self.timed_out = False
        self.done = self.max_frames <= 0
        self._recent = deque(maxlen=history)

    def feed(self, metadata) -> bool:
        if self.done:
            return True
        self.frames += 1
        lens = metadata.get("lens_position")
        iso = metadata.get("iso_sensitivity", 0) or 0
        self._recent.append((lens, iso))
        if len(self._recent) >= self.history:
            lenses = [lens for lens, _ in self._recent]
            isos = [iso for _, iso in self._recent]
            if None not in lenses and min(lenses) > 0  \
                and max(lenses) - min(lenses) <= 2  \
                and max(isos) - min(isos) <= 0.05 * max(isos):
                self.done = True
        if not self.done and self.frames >= self.max_frames:
            self.timed_out = True
            self.done = True
        return self.done

class CountdownSettle:
    """Discard a fixed number of frames, for example after an exposure
    change; same shape as SettleMonitor"""

    def __init__(self, frames):
        self.max_frames = int(frames)
        self.frames = 0
        self.timed_out = False
        self.done = self.max_frames <= 0

    def feed(self, metadata) -> bool:
        if not self.done:
            self.frames += 1
            self.done = self.frames >= self.max_frames
        return self.done

def auto_expose(camera, logger=None, target_p99=225, max_exposure_us=250000,
    max_iterations=8, timeout_s=None):
    """Highlight-based auto-exposure for cameras without one: a generator
    whose every step captures a frame, meters the 99th percentile and
    adjusts exposure first (clean signal), then gain past the exposure cap.
    Yields (done, exposure_us, gain); done is True when within 7 % of the
    target or after max_iterations.  Capture errors propagate"""

    exposure = gain = None
    for iteration in range(max_iterations):
        image, metadata = camera.capture(timeout_s)  \
            if timeout_s else camera.capture()
        p99 = float(np.percentile(image, 99))
        exposure = float(metadata.get("exposure_us", 15000.0))
        gain = float(metadata.get("gain", 1.0))
        if logger:
            logger.debug(f"auto-expose {iteration}: p99={p99:.0f} "
                         f"exposure_us={exposure:.0f} gain={gain:.2f}")
        if 0.93 * target_p99 <= p99 <= 1.07 * target_p99:
            yield True, exposure, gain
            return
        factor = min(target_p99 / max(p99, 1.0), 8.0)  # 8x at most per step
        total = exposure * gain * factor
        exposure = float(camera.set_exposure(min(total, max_exposure_us)))
        gain = float(camera.set_gain(max(total / exposure, 1.0)))
        yield False, exposure, gain
    if logger:
        logger.warning("auto-expose did not converge: scene too dark at "
                       f"{max_exposure_us / 1000:.0f} ms and maximum gain, "
                       "add light or open the lens iris")
    yield True, exposure, gain

# --------------------------------------------------------------------------- #

class RateMeter:
    """Frames per second over a sliding window"""

    def __init__(self, window_s=2.0):
        self.window_s = window_s
        self._times = deque()

    def tick(self, now=None) -> float:
        now = time.monotonic() if now is None else now
        self._times.append(now)
        while self._times and now - self._times[0] > self.window_s:
            self._times.popleft()
        if len(self._times) < 2:
            return 0.0
        span = self._times[-1] - self._times[0]
        return (len(self._times) - 1) / span if span > 0 else 0.0

def share_token(text, limit=32) -> str:
    """One share token: non-token characters become "_", cut at limit"""

    token = _TOKEN_RE.sub("_", str(text))[:limit]
    return token or "-"

def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

# --------------------------------------------------------------------------- #
