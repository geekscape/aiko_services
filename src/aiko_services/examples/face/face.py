#!/usr/bin/env python3
#
# RT_PATH=$HOME/venvs/venv_3.10.7/lib/python3.10/site-packages/tensorrt_libs
# export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:$RT_PATH
#
# aiko_pipeline create face_pipeline.json -s 1  # aiko_dashboard --> logging
#
# AIKO_LOG_LEVEL=DEBUG aiko_pipeline create face_pipeline.json -s 1
#
# aiko_pipeline create face_pipeline.json -s 1  \
#   -p VideoReadWebcam.path /dev/video2
#
# Resources
# ~~~~~~~~~
# - https://github.com/serengil/deepface
# - https://developer.apple.com/metal/tensorflow-plugin
#   python -m pip install tensorflow-metal  # Python 3.9 or 3.10 required ?
#
# To Do
# ~~~~~
# - Image should already be RGB ... is BGR --> RGB even required here ?
#   - Move OpenCV RGB-->BGR image conversion into "elements/media/common_io.py"
#
# - Detector:    Inference rate (ignore frames ?)
# - Performance: Using GPU efficiently ?

# import os
from typing import Tuple

import aiko_services as aiko

__all__ = [ "FaceDetector" ]

_CV2_IMPORTED = False
try:
    import cv2
    _CV2_IMPORTED = True
except ModuleNotFoundError:  # TODO: Optional warning flag
    diagnostic = "face.py: Couldn't import cv2 module"
    print(f"WARNING: {diagnostic}")
    _LOGGER = aiko.logger(__name__)
    _LOGGER.warning(diagnostic)
    raise ModuleNotFoundError(
        'opencv-python package not installed.  '
        'Install aiko_services with --extras "opencv" '
        'or install opencv-python manually to use the "face" module')

# --------------------------------------------------------------------------- #

from deepface.DeepFace import extract_faces

class FaceDetector(aiko.PipelineElement):
    def __init__(self, context):
        context.set_protocol("face_detector:0")
        context.call_init(self, "PipelineElement", context)
    #   os.environ["TF_ENABLE_ONEDNN_OPTS"] = "0"
        self.detector_backend = "retinaface"
        self.share["detections"] = 0

    def process_frame(self, stream, images) -> Tuple[aiko.StreamEvent, dict]:
        overlay = {"rectangles": []}

        image_id = 0
        for image in images:
            rectangles = overlay["rectangles"]
            try:
                if len(image.shape) == 2:
                    image_bgr = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
                else:
                    image_bgr = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)

                faces = extract_faces(image_bgr)
                if faces:
                #   self.logger.info(f"{self.my_id()} Face(s) detected")
                    detections_count = self.share["detections"] + len(faces)
                    self.ec_producer.update("detections", detections_count)

                    face_id = 0
                    for face in faces:
                    #   self.logger.debug(f"Face: {face['facial_area']}")
                        rectangles.append(face["facial_area"])
                        face_id += 1
            except ValueError as value_error:
                pass
            image_id += 1

        return aiko.StreamEvent.OKAY, {"overlay": overlay}

# --------------------------------------------------------------------------- #
