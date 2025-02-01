# Usage: File
# ~~~~~~~~~~~
# aiko_pipeline create pipelines/webcam_pipeline_0.json -s 1 -ll debug
#
# aiko_pipeline create pipelines/webcam_pipeline_0.json -s 1  \
#   -p VideoReadWebcam.path /dev/video2
#
# aiko_pipeline create pipelines/webcam_pipeline_1.json -s 1
#
# Usage: ZMQ
# ~~~~~~~~~~
# aiko_pipeline create pipelines/image_zmq_pipeline_0.json  -s 1 -sr -gt 10
# aiko_pipeline create pipelines/image_zmq_pipeline_0.json  -s 1 -sr  \
#            -p ImageReadZMQ.data_sources zmq://0.0.0.0:6502
#
# aiko_pipeline create pipelines/webcam_zmq_pipeline_0.json -s 1 -sr \
#            -p VideoReadWebcam.rate 2.0
#            -p ImageWriteZMQ.data_targets zmq://192.168.0.1:6502
#
# Notes
# ~~~~~
# - See https://github.com/ultralytics/ultralytics/issues/3005
# pip uninstall av  # Prevent clash between AV (Ultralytics) and cv2.imshow()
# # pip install av --no-binary av
#
# To Do
# ~~~~~
# - Implement "VideoReadWebcam.data_batch_size" in "frame_generator()"
#
# - Implement "data_source scheme", e.g "webcam://0" or "webcam://dev/video0"
#
# - Move "import cv2" into a "source_target.py" function ?
#
# - Use "rate" (?) to control FPS (frames per seconds)
#
# - See https://docs.opencv.org/4.x/dd/d43/tutorial_py_video_display.html
#   - List available camera pathnames, e.g "/dev/video[02...]"
#   - cap.get(cv.CAP_PROP_FRAME_WIDTH),     cv.CAP_PROP_FRAME_HEIGHT
#   - cap.set(cv.CAP_PROP_FRAME_WIDTH,320), cv.CAP_PROP_FRAME_HEIGHT

import os
from typing import Tuple

import aiko_services as aiko

__all__ = ["VideoReadWebcam"]

_DEFAULT_CAMERA_PATHNAME = 0  # Linux: "/dev/video0"
_DEFAULT_FRAME_RATE = 10.0    # 10 Hz frames per second

_LOGGER = aiko.get_logger(__name__)

_CV2_IMPORTED = False
try:
    import cv2
    _CV2_IMPORTED = True
except ModuleNotFoundError:  # TODO: Optional warning flag
    diagnostic = "webcam_io.py: Couldn't import cv2 module"
#   print(f"WARNING: {diagnostic}")
#   _LOGGER.warning(diagnostic)
#   raise ModuleNotFoundError(
#       'opencv-python package not installed.  '
#       'Install aiko_services with --extras "opencv" '
#       'or install opencv-python manually to use the "webcam_io" module')

# --------------------------------------------------------------------------- #
# VideoReadWebcam is a DataSource which supports web cameras 
#
# parameter: "data_sources" is the read file path or device number
#
# Note: Only supports Streams with "data_sources" parameter

class VideoReadWebcam(aiko.DataSource):  # PipelineElement
    def __init__(self, context):
        context.set_protocol("webcam:0")
        context.get_implementation("PipelineElement").__init__(self, context)

        self.path_current = None
        self.stream_started = 0
        self.video_capture = None

        self.share["color"] = True
        self.share["flip"] = "none"  # "both", "horizontal", "vertical"
        self.share["frame_id"] = -1
        self.share["path"] = _DEFAULT_CAMERA_PATHNAME
        self.ec_producer.add_handler(self._ec_producer_change_handler)

    def _ec_producer_change_handler(self, command, item_name, item_value):
        if item_name == "color":
            if isinstance(item_value, str):
                self.share["color"] = item_value.lower() == "true"

        if item_name == "path":
            if isinstance(item_value, str) and item_value.isdigit():
                item_value = int(item_value)
            if item_value != self.path_current:
                self.logger.info(f"Camera path updated: {item_value}")
                self._open_camera(item_value)

    def _close_camera(self):
        self.logger.info(f"Close camera: {self.path_current}")
        self.video_capture.release()
        self.video_capture = None
        self.path_current = None

    def _open_camera(self, path):
        if self.stream_started > 0:
            if self.video_capture:
                self._close_camera()
            if isinstance(path, str) and path.isdigit():
                path = int(path)
            self.video_capture = cv2.VideoCapture(path)
            if self.video_capture and self.video_capture.isOpened():
                self.logger.info(f"Open camera: {path}")
                self.path_current = path
                self.share["path"] = path
            else:
                self.logger.error(f"Open camera: {path} failed")
                self.video_capture = None

    def start_stream(self, stream, stream_id):
        self.stream_started += 1
        path, _ = self.get_parameter("path", _DEFAULT_CAMERA_PATHNAME)
        self._open_camera(path)
        rate, _ = self.get_parameter("rate", _DEFAULT_FRAME_RATE)
        self.create_frames(stream, self.frame_generator, rate=float(rate))
        return aiko.StreamEvent.OKAY, {}

    def frame_generator(self, stream, frame_id):
        frame_data = None
        if self.video_capture and self.video_capture.isOpened():
            status, image_bgr = self.video_capture.read()
            if status:
                if frame_id % 10 == 0:
                    self.ec_producer.update("frame_id", frame_id)
                if self.share["color"]:
                    image = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
                else:
                    image = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
                flip = self.share["flip"]
                if flip == "both" or flip == "horizontal":
                    image = cv2.flip(image, 1)
                if flip == "both" or flip == "vertical":
                    image = cv2.flip(image, 0)
                frame_data = {"images": [image]}
        return aiko.StreamEvent.OKAY, frame_data

    # TODO: Test this ...
    #   return aiko.StreamEvent.STOP, {"diagnostic": "Camera stopped"}

    def process_frame(self, stream, images) -> Tuple[aiko.StreamEvent, dict]:
        self.logger.debug(f"{self.my_id()}: read image")
        return aiko.StreamEvent.OKAY, {"images": images}

    def stop_stream(self, stream, stream_id):
    #   self.create_frames_terminate(stream, self.frame_generator)
        self.stream_started -= 1
        self._close_camera()
        return aiko.StreamEvent.OKAY, {}

# --------------------------------------------------------------------------- #
