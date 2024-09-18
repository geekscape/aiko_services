# Usage
# ~~~~~
# aiko_pipeline create aruco_pipeline_0.json -s 1 -ll debug
#
# aiko_pipeline create aruco_pipeline_0.json -s 1  \
#   -sp VideoReadWebcam.path /dev/video2
#
# To Do
# ~~~~~
# - Implement "distance (tvec)" and overlay next to "marker id"
#
# - Determine image type, e.g PIL and/or numpy.ndarray ?
#
# - Integrate ArucoMarkerOverlay with ImageOverlay ?
#
# - Integrated camera calibration tool (CLI, desktop GUI) ...
#   - Capture webcam video for camera calibration
#   - Perform calibration
#   - Standard file naming and format with multiple camera calibrations
#   - Common function for loading camera calibration given camera type
#   * Generate Aruco Markers: Calibration board, page of six markers or just one

from typing import Tuple
import pickle

import aiko_services as aiko

__all__ = [ "ArucoMarkerDetector", "ArucoMarkerOverlay" ]

_LOGGER = aiko.get_logger(__name__)

_CV2_IMPORTED = False
try:
    import cv2
    _CV2_IMPORTED = True
except ModuleNotFoundError:  # TODO: Optional warning flag
    diagnostic = "aruco.py: Couldn't import numpy module"
    print(f"WARNING: {diagnostic}")
    _LOGGER.warning(diagnostic)
    raise ModuleNotFoundError(
        'opencv-python package not installed.  '
        'Install aiko_services with --extras "opencv" '
        'or install opencv-python manually to use the "aruco" module')

_NUMPY_IMPORTED = False
try:
    import numpy as np
    _NUMPY_IMPORTED = True
except ModuleNotFoundError:  # TODO: Optional warning flag
    diagnostic = "image_io.py: Couldn't import numpy module"
    print(f"WARNING: {diagnostic}")
    _LOGGER.warning(diagnostic)

# --------------------------------------------------------------------------- #

_ARUCO_MARKER_SIZE_CM = 70.0  # TODO: Make this a PipelineDefinition parameter
_DEFAULT_ARUCO_TAGS = "DICT_4X4_50"

_ARUCO_TAGS_TABLE = {
    "DICT_4X4_50": cv2.aruco.DICT_4X4_50,
    "DICT_4X4_100": cv2.aruco.DICT_4X4_100,
    "DICT_4X4_250": cv2.aruco.DICT_4X4_250,
    "DICT_4X4_1000": cv2.aruco.DICT_4X4_1000,
    "DICT_5X5_50": cv2.aruco.DICT_5X5_50,
    "DICT_5X5_100": cv2.aruco.DICT_5X5_100,
    "DICT_5X5_250": cv2.aruco.DICT_5X5_250,
    "DICT_5X5_1000": cv2.aruco.DICT_5X5_1000,
    "DICT_6X6_50": cv2.aruco.DICT_6X6_50,
    "DICT_6X6_100": cv2.aruco.DICT_6X6_100,
    "DICT_6X6_250": cv2.aruco.DICT_6X6_250,
    "DICT_6X6_1000": cv2.aruco.DICT_6X6_1000,
    "DICT_7X7_50": cv2.aruco.DICT_7X7_50,
    "DICT_7X7_100": cv2.aruco.DICT_7X7_100,
    "DICT_7X7_250": cv2.aruco.DICT_7X7_250,
    "DICT_7X7_1000": cv2.aruco.DICT_7X7_1000,
    "DICT_ARUCO_ORIGINAL": cv2.aruco.DICT_ARUCO_ORIGINAL
}

class ArucoMarkerDetector(aiko.PipelineElement):
    def __init__(self, context):
        context.set_protocol("aruco_marker_detector:0")
        context.get_implementation("PipelineElement").__init__(self, context)

        self.aruco_dict = cv2.aruco.getPredefinedDictionary(
            _ARUCO_TAGS_TABLE[_DEFAULT_ARUCO_TAGS])
        self.aruco_param = cv2.aruco.DetectorParameters()

#       file = open("CameraCalibration.pckl", "rb")
#       (self.camera_matrix, self.dist_coeffs, _, _) = pickle.load(file)
#       file.close()
#       if camera_matrix is None or dist_coeffs is None:
#           raise SystemExit("camera calibration file missing matrix or coeffs")

    def process_frame(self, stream, images) -> Tuple[aiko.StreamEvent, dict]:
        overlays = []
        for image in images:
            (corners, ids, rejected) =  \
                cv2.aruco.detectMarkers(
                    image, self.aruco_dict, parameters=self.aruco_param)
            overlay = {"corners": corners, "ids": ids}
            overlays.append(overlay)

        #   marker_size = _ARUCO_MARKER_SIZE_CM
        #   rvec , tvec, _ =  \
        #       cv2.aruco.estimatePoseSingleMarkers(
        #           corners, marker_size, camera_matrix, dist_coeffs)

        #   if tvec is not None:
        #       a, b, c = rvec[0][0]
        #       x, y, z = tvec[0][0]
        #       print(f"{a:4.00f}, {b:4.00f}, {c:4.00f} - "  \
        #             f"{x:4.00f}, {y:4.00f}, {z:4.00f}")

        return aiko.StreamEvent.OKAY, {"overlays": overlays}

# --------------------------------------------------------------------------- #

COLOR_RED    = (  0,   0, 255)
COLOR_GREEN  = (  0, 255,   0)
COLOR_BLUE   = (255,   0,   0)
COLOR_PURPLE = (255,   0, 255)
COLOR_YELLOW = (  0, 255, 255)

COLOR_BOX    = COLOR_YELLOW
COLOR_CIRCLE = COLOR_RED
COLOR_TEXT   = COLOR_PURPLE

class ArucoMarkerOverlay(aiko.PipelineElement):
    def __init__(self, context):
        context.set_protocol("aruco_marker_overlay:0")
        context.get_implementation("PipelineElement").__init__(self, context)

    def process_frame(self, stream, images, overlays)  \
        -> Tuple[aiko.StreamEvent, dict]:

        image_id = 0
        images_overlayed = []
        for (image_rgb, overlay) in zip(images, overlays):
            corners = overlay["corners"]
            ids = overlay["ids"]
            if len(corners):
                if not isinstance(image_rgb, np.ndarray):
                    image_rgb = np.array(image)  # RGB
    
                grayscale = len(image_rgb.shape) == 2
                if grayscale:
                    image_bgr = cv2.cvtColor(image_rgb, cv2.COLOR_GRAY2BGR)
                else:
                    image_bgr = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2BGR)

                ids = ids.flatten()
                for (marker_corner, marker_id) in zip(corners, ids):
                    corners = marker_corner.reshape((4, 2))
                    (top_left, top_right, bottom_right, bottom_left) = corners

                    top_right = (int(top_right[0]), int(top_right[1]))
                    bottom_right = (int(bottom_right[0]), int(bottom_right[1]))
                    bottom_left = (int(bottom_left[0]), int(bottom_left[1]))
                    top_left = (int(top_left[0]), int(top_left[1]))

                    cv2.line(image_bgr, top_left, top_right, COLOR_BOX, 2)
                    cv2.line(image_bgr, top_right, bottom_right, COLOR_BOX, 2)
                    cv2.line(image_bgr, bottom_right, bottom_left, COLOR_BOX, 2)
                    cv2.line(image_bgr, bottom_left, top_left, COLOR_BOX, 2)

                    center_x = int((top_left[0] + bottom_right[0]) / 2.0)
                    center_y = int((top_left[1] + bottom_right[1]) / 2.0)
                    cv2.circle(
                        image_bgr, (center_x, center_y), 4, COLOR_CIRCLE, -1)

                    cv2.putText(image_bgr, str(marker_id),
                        (top_left[0], top_left[1] - 15),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.0, COLOR_TEXT, 4)
                    image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
            image_id += 1
            images_overlayed.append(image_rgb)
        return aiko.StreamEvent.OKAY, {"images": images_overlayed}

# --------------------------------------------------------------------------- #
