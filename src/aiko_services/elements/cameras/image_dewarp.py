# ImageDewarp: undistort each image with an OpenCV lens calibration, so a
# camera's barrel or pincushion distortion is removed before measurement,
# detection or recording.  The calibration belongs to one camera and lens,
# which is why the element lives with the cameras
#
# Usage
# ~~~~~
# cd src/aiko_services/elements/cameras
# aiko_pipeline create pipelines/depthai_pipeline_1.json -s 1  \
#     -p ImageDewarp.calibration_path <your camera's calibration>.json
#
# parameter: "calibration_path"  JSON file, see below (required)
# parameter: "alpha"             0.0 to 1.0 (default 0.0): 0 crops to the
#                                valid pixels, 1 keeps every source pixel
#                                with black borders
#
# Calibration JSON, the OpenCV pinhole model (cv2.calibrateCamera, or the
# device's own factory data converted to it) ...
# {
#   "camera_matrix": [[fx, 0, cx], [0, fy, cy], [0, 0, 1]],
#   "dist_coeffs":   [k1, k2, p1, p2, k3],   4, 5, 8, 12 or 14 values
#   "image_size":    [width, height],        optional: the size the fit
#                                            was made at
#   "source":        "free text"             optional provenance
# }
# When "image_size" is present and differs from the frame, the camera
# matrix is scaled: exact for scaled or stretched frames, approximate for
# centre-cropped ones.  data_in/calibration_identity.json is a zero
# distortion placeholder, a pass-through, for trying a Pipeline
#
# Shared state (observe via aiko_dashboard) ...
#   calibration_path  the file in use   image_size  from the file, or "-"
#   coefficients      count             alpha       in use
#   frames            images dewarped   maps        cached remap tables
#   last_error        <token>@UTC of the latest rejected update
#   Writable: alpha (rebuilds the maps on the next frame), calibration_path
#   (reloads; a bad file publishes last_error and keeps the current maps).
#   The framework reads a share item before the element parameter of the
#   same name, so a written value also applies to the next Stream
#
# To Do
# ~~~~~
# - A "camera_matrix" / "dist_coeffs" pair as parameters, without a file

import json
import os
from typing import Tuple

import numpy as np

import aiko_services as aiko
from aiko_services.elements.cameras import camera

__all__ = ["Dewarper", "ImageDewarp", "load_calibration",
           "scale_camera_matrix"]

_CV2_IMPORTED = False
try:
    import cv2
    _CV2_IMPORTED = True
except ModuleNotFoundError:
    cv2 = None
_CV2_DIAGNOSTIC = "image_dewarp.py: OpenCV is needed: "  \
                  "pip install opencv-python"

COEFFICIENT_COUNTS = (4, 5, 8, 12, 14)
INITIAL_SHARE = {                  # never a parameter name: the framework
    "image_size": "-", "coefficients": "0", "frames": "0",  # reads share
    "maps": "0", "last_error": "-"                          # first
}

# --------------------------------------------------------------------------- #

def load_calibration(path):
    """--> (camera_matrix 3x3 float64, dist_coeffs 1xN float64,
    image_size (w, h) or None).  Raises ValueError for a missing file, bad
    JSON or wrong shapes"""

    try:
        with open(os.path.expanduser(str(path))) as file:
            calibration = json.load(file)
    except OSError as os_error:
        raise ValueError(f'calibration "{path}": {os_error}')
    except ValueError as value_error:
        raise ValueError(f'calibration "{path}": bad JSON: {value_error}')
    if not isinstance(calibration, dict):
        raise ValueError(f'calibration "{path}": not a JSON object')
    try:
        camera_matrix = np.array(calibration["camera_matrix"], dtype=float)
        dist_coeffs = np.array(calibration["dist_coeffs"],
                               dtype=float).reshape(1, -1)
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f'calibration "{path}": camera_matrix (3x3) and '
                         f'dist_coeffs (a list) are required: {error}')
    if camera_matrix.shape != (3, 3):
        raise ValueError(f'calibration "{path}": camera_matrix must be 3x3')
    if dist_coeffs.shape[1] not in COEFFICIENT_COUNTS:
        raise ValueError(f'calibration "{path}": dist_coeffs must hold '
                         f'{", ".join(map(str, COEFFICIENT_COUNTS))} values')
    image_size = calibration.get("image_size")
    if image_size is not None:
        try:
            image_size = (int(image_size[0]), int(image_size[1]))
        except (TypeError, ValueError, IndexError):
            raise ValueError(
                f'calibration "{path}": image_size must be [width, height]')
        if image_size[0] <= 0 or image_size[1] <= 0:
            raise ValueError(f'calibration "{path}": image_size must be '
                             'positive')
    return camera_matrix, dist_coeffs, image_size

def scale_camera_matrix(camera_matrix, from_size, to_size):
    """The camera matrix for a frame of to_size (w, h) when the fit was
    made at from_size: fx and cx scale by the width ratio, fy and cy by
    the height ratio"""

    scaled = np.array(camera_matrix, dtype=float)
    width_ratio = to_size[0] / from_size[0]
    height_ratio = to_size[1] / from_size[1]
    scaled[0, 0] *= width_ratio
    scaled[0, 2] *= width_ratio
    scaled[1, 1] *= height_ratio
    scaled[1, 2] *= height_ratio
    return scaled

class Dewarper:
    """One calibration and its cached remap tables per frame size and
    alpha; the element delegates to it, so it is testable without a
    Pipeline.  Raises ValueError from load() and set_alpha()"""

    def __init__(self):
        self.path = None
        self.camera_matrix = None
        self.dist_coeffs = None
        self.image_size = None
        self.alpha = 0.0
        self._maps = {}

    def load(self, path):
        self.camera_matrix, self.dist_coeffs, self.image_size =  \
            load_calibration(path)
        self.path = str(path)
        self._maps.clear()

    def set_alpha(self, alpha):
        alpha = float(alpha)
        if not 0.0 <= alpha <= 1.0:
            raise ValueError(f"alpha {alpha} must be from 0.0 to 1.0")
        if alpha != self.alpha:
            self.alpha = alpha
            self._maps.clear()

    @property
    def loaded(self):
        return self.camera_matrix is not None

    @property
    def map_count(self):
        return len(self._maps)

    def maps(self, size):
        """(map_1, map_2) for a frame of size (w, h), cached"""

        key = (int(size[0]), int(size[1]), self.alpha)
        if key not in self._maps:
            if not _CV2_IMPORTED:
                raise RuntimeError(_CV2_DIAGNOSTIC)
            camera_matrix = self.camera_matrix
            if self.image_size and tuple(self.image_size) != key[:2]:
                camera_matrix = scale_camera_matrix(
                    camera_matrix, self.image_size, key[:2])
            new_matrix, _ = cv2.getOptimalNewCameraMatrix(
                camera_matrix, self.dist_coeffs, key[:2], self.alpha)
            self._maps[key] = cv2.initUndistortRectifyMap(
                camera_matrix, self.dist_coeffs, None, new_matrix, key[:2],
                cv2.CV_16SC2)
        return self._maps[key]

    def apply(self, image):
        image = np.asarray(image)
        map_1, map_2 = self.maps((image.shape[1], image.shape[0]))
        return cv2.remap(image, map_1, map_2, cv2.INTER_LINEAR)

# --------------------------------------------------------------------------- #

class ImageDewarp(aiko.PipelineElement):
    def __init__(self, context):
        context.set_protocol("image_dewarp:0")
        context.call_init(self, "PipelineElement", context)
        self.dewarper = Dewarper()
        self.frames = 0
        self._publishing = False
        self.share.update(dict(INITIAL_SHARE))
        self.ec_producer.add_handler(self._ec_producer_change_handler)

    def start_stream(self, stream, stream_id):
        if not _CV2_IMPORTED:
            return aiko.StreamEvent.ERROR, {"diagnostic": _CV2_DIAGNOSTIC}
        path, found = self.get_parameter("calibration_path", None)
        if not found or not path:
            diagnostic = 'ImageDewarp requires the "calibration_path" '  \
                         "parameter"
            return aiko.StreamEvent.ERROR, {"diagnostic": diagnostic}
        alpha, _ = self.get_parameter("alpha", 0.0)
        try:
            if str(path) != self.dewarper.path:
                self.dewarper.load(path)
            self.dewarper.set_alpha(alpha)
        except ValueError as value_error:
            self._publish_error(value_error)
            diagnostic = f"ImageDewarp: {value_error}"
            return aiko.StreamEvent.ERROR, {"diagnostic": diagnostic}
        self._publish_calibration()
        return aiko.StreamEvent.OKAY, {}

    def process_frame(self, stream, images) -> Tuple[aiko.StreamEvent, dict]:
        if not self.dewarper.loaded:
            diagnostic = "ImageDewarp: no calibration loaded"
            return aiko.StreamEvent.ERROR, {"diagnostic": diagnostic}
        images_dewarped = [self.dewarper.apply(image) for image in images]
        self.frames += len(images_dewarped)
        self._publish("frames", self.frames)
        if str(self.dewarper.map_count) != self.share.get("maps"):
            self._publish("maps", self.dewarper.map_count)
        return aiko.StreamEvent.OKAY, {"images": images_dewarped}

    # Shared state --------------------------------------------------------- #

    def _publish(self, key, value):
        self._publishing = True
        try:
            self.ec_producer.update(key, str(value))
        finally:
            self._publishing = False

    def _publish_calibration(self):
        dewarper = self.dewarper
        self._publish("calibration_path", dewarper.path)
        self._publish("image_size", "-" if dewarper.image_size is None
                      else f"{dewarper.image_size[0]}x"
                           f"{dewarper.image_size[1]}")
        self._publish("coefficients", dewarper.dist_coeffs.shape[1])
        self._publish("alpha", dewarper.alpha)
        self._publish("maps", dewarper.map_count)

    def _publish_error(self, error):
        self._publish("last_error", f"{camera.share_token(error)}@"
                                    f"{camera.utc_now()}")

    def _ec_producer_change_handler(self, command, item_name, item_value):
        if command != "update" or self._publishing:
            return
        try:
            if item_name == "alpha":
                self.dewarper.set_alpha(item_value)
                self._publish("alpha", self.dewarper.alpha)
                self._publish("maps", self.dewarper.map_count)
            elif item_name == "calibration_path":
                if str(item_value) != self.dewarper.path:
                    self.dewarper.load(item_value)
                    self._publish_calibration()
        except (TypeError, ValueError) as error:
            self._publish_error(error)
            self.logger.warning(
                f"share update {item_name}={item_value!r} rejected: {error}")

# --------------------------------------------------------------------------- #
