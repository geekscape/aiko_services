# Usage
# ~~~~~
# cd src/aiko_services/elements/media
# aiko_pipeline create pipeline_video_io.json --stream_id 1  \
#   -sp VideoReadFile.path video.mp4
#   -sp ImageResize.width 320 -sp ImageResize.height 240
#
# To Do
# ~~~~~
# - Refactor optional module import into common function (see image_io.py)
#
# - Implement start_frame, stop_frame, sample_rate parameters
# - Implement PipelineElement VideoSample()
#   - Provide video_sample() for use by VideoFileRead and VideoSample
#
# - Implement ...
#     video_capture = cv2.VideoCapture(path)
#     width = int(video_capture.get(cv2.CAP_PROP_FRAME_WIDTH))
#     height = int(video_capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
#     length = int(video_capture.get(cv2.CAP_PROP_FRAME_COUNT))
#     frame_rate = int(video_capture.get(cv2.CAP_PROP_FPS))
#
# - VideoReadFile should accept a DataSource type ...
#   - URL: "file://" and media_type: "mp4", etc
#
# - PE_Metrics: Determine what to measure ?
#
# - Design video windowing, i.e collecting multiple frame for ML processing
#   together, e.g gesture analysis
#
# - "Batching" images for CPU-GPU memory transfer efficiently for nVidia
#   - For both images and video ... depending upon ML model

from typing import Tuple
from pathlib import Path

import aiko_services as aiko
_LOGGER = aiko.get_logger(__name__)

_CV2_IMPORTED = False
try:
    import cv2
    _CV2_IMPORTED = True
except ModuleNotFoundError:  # TODO: Optional warning flag
    diagnostic = "image_io.py: Couldn't import numpy module"
    print(f"WARNING: {diagnostic}")
    _LOGGER.warning(diagnostic)
    raise ModuleNotFoundError(
        'opencv-python package not installed.  '
        'Install aiko_services with --extras "opencv" '
        'or install opencv-python manually to use the "video_io" module')

__all__ = ["VideoReadFile", "VideoShow", "VideoWriteFile"]

# --------------------------------------------------------------------------- #

class VideoReadFile(aiko.PipelineElement):
    def __init__(self, context: aiko.ContextPipelineElement):
        context.get_implementation("PipelineElement").__init__(self, context)
        self.stream = {}

    def start_stream(self, stream, stream_id):
        self.logger.debug(f"{self.my_id()} start_stream()")

        path, found = self.get_parameter("path")
        if not found:
            return aiko.StreamEvent.ERROR,  \
                   {"diagnostic": 'Must provide video "path" parameter'}
        if not Path(path).exists():
            return aiko.StreamEvent.ERROR,  \
                   {"diagnostic": f"path: {path} does not exist"}

        video_capture = cv2.VideoCapture(path)
        if (video_capture.isOpened() == False):
            return aiko.StreamEvent.ERROR,  \
                   {"diagnostic": f"Couldn't open video file: {path}"}

        self.stream.video_capture = video_capture
        self.create_frames(stream, self._create_frame_fn)
        return aiko.StreamEvent.OKAY, {}

    def _create_frame_fn(self, stream):
        self.logger.debug(f"{self.my_id()} _create_frame()")

        stream_id = stream.stream_id
        frame_id = stream.frame_id
        video_capture = self.stream.video_capture

        if video_capture.isOpened():
            success, image_bgr = video_capture.read()
            if success == True:
                self.logger.debug(f"{self.my_id()} frame_generator()")
                image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
                if frame_id % 10 == 0:
                    print(f"Frame Id: {frame_id}", end="\r")

                return aiko.StreamEvent.OKAY, {"image": image_rgb}
            else:
                return aiko.StreamEvent.ERROR,  \
                       {"diagnostic": f"Read video capture at {frame_id}"}
        return aiko.StreamEvent.STOP, {"diagnostic": "Video capture complete"}

    def process_frame(self, stream, image) -> Tuple[aiko.StreamEvent, dict]:
        self.logger.debug(f"{self.my_id()} <-- PROCESS_FRAME()")
        return aiko.StreamEvent.OKAY, {"image": image}

    def stop_stream(self, stream, stream_id):
        self.logger.debug(f"{self.my_id()} stop_stream()")

        video_capture = self.stream.video_capture
        if video_capture.isOpened():
            video_capture.release()

        return aiko.StreamEvent.OKAY, {}

# --------------------------------------------------------------------------- #

class VideoShow(aiko.PipelineElement):
    def stream_frame_handler(self, stream_id, frame_id, swag):
        self.logger.debug(f"{self.my_id()} stream_frame_handler()")
        title = self.parameters["window_title"]
        image_rgb = swag[self.predecessor]["image"]
        image_bgr = cv2.cvtColor(image_rgb, cv2.COLOR_BGR2RGB)
        cv2.imshow(title, image_bgr)
        if frame_id == 0:
            window_x = self.parameters["window_location"][0]
            window_y = self.parameters["window_location"][1]
            cv2.moveWindow(title, window_x, window_y)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            return False, None
        return True, {"image": image_rgb}

    def stream_stop_handler(self, stream_id, frame_id, swag):
        self.logger.debug(f"{self.my_id()} stream_stop_handler()")
        cv2.destroyAllWindows()
        return True, None

# --------------------------------------------------------------------------- #

# video_capture = self.stream[stream_id]

class VideoWriteFile(aiko.PipelineElement):
    def __init__(self, context: aiko.ContextPipelineElement):
        context.get_implementation("PipelineElement").__init__(self, context)
        self.stream = {}

    def start_stream(self, stream, stream_id):
        self.logger.debug(f"{self.my_id()} start_stream()")
        return aiko.StreamEvent.OKAY, {}

    def process_frame(self, stream, image) -> Tuple[aiko.StreamEvent, dict]:
        self.logger.debug(f"{self.my_id()} <-- PROCESS_FRAME()")
        return aiko.StreamEvent.OKAY, {}

    def stop_stream(self, stream, stream_id):
        return aiko.StreamEvent.OKAY, {}

"""
    def stream_start_handler(self, stream_id, frame_id, swag):
        self.logger.debug(f"{self.my_id()} stream_start_handler()")
        self.image_shape = None
        self.video_format = self.parameters.get("video_format", "AVC1")
        self.video_frame_rate = self.parameters["video_frame_rate"]
        self.video_pathname = self.parameters["video_pathname"]
        self.video_writer = None
        return True, None

    def _init_video_writer(self, video_pathname, video_format, frame_rate, image_shape):
        video_directory = Path(video_pathname).parent
        video_directory.mkdir(exist_ok=True, parents=True)
        return cv2.VideoWriter(
                video_pathname,
                cv2.VideoWriter_fourcc(*video_format),
                frame_rate,
                image_shape)

    def stream_frame_handler(self, stream_id, frame_id, swag):
        self.logger.debug(f"{self.my_id()} stream_frame_handler()")
        image_rgb = swag[self.predecessor]["image"]
        image_bgr = cv2.cvtColor(image_rgb, cv2.COLOR_BGR2RGB)

        if self.video_writer is None:
            if self.image_shape is None:
                self.image_shape = (image_rgb.shape[1], image_rgb.shape[0])
            self.video_writer = self._init_video_writer(
                    self.video_pathname,
                    self.video_format,
                    self.video_frame_rate,
                    self.image_shape)

        self.video_writer.write(image_bgr)
        return True, {"image": image_rgb}

    def stream_stop_handler(self, stream_id, frame_id, swag):
        self.logger.debug(f"{self.my_id()} stream_stop_handler()")
        if self.video_writer:
            self.video_writer.release()
            self.video_writer = None
        return True, None
"""

# --------------------------------------------------------------------------- #

class VideoWriteFileOld(aiko.PipelineElement):
    def stream_start_handler(self, stream_id, frame_id, swag):
        self.logger.debug(f"{self.my_id()} stream_start_handler()")
        self.image_shape = None
        self.video_format = self.parameters.get("video_format", "AVC1")
        self.video_frame_rate = self.parameters["video_frame_rate"]
        self.video_pathname = self.parameters["video_pathname"]
        self.video_writer = None
        return True, None

    def _init_video_writer(self, video_pathname, video_format, frame_rate, image_shape):
        video_directory = Path(video_pathname).parent
        video_directory.mkdir(exist_ok=True, parents=True)
        return cv2.VideoWriter(
                video_pathname,
                cv2.VideoWriter_fourcc(*video_format),
                frame_rate,
                image_shape)

    def stream_frame_handler(self, stream_id, frame_id, swag):
        self.logger.debug(f"{self.my_id()} stream_frame_handler()")
        image_rgb = swag[self.predecessor]["image"]
        image_bgr = cv2.cvtColor(image_rgb, cv2.COLOR_BGR2RGB)

        if self.video_writer is None:
            if self.image_shape is None:
                self.image_shape = (image_rgb.shape[1], image_rgb.shape[0])
            self.video_writer = self._init_video_writer(
                    self.video_pathname,
                    self.video_format,
                    self.video_frame_rate,
                    self.image_shape)

        self.video_writer.write(image_bgr)
        return True, {"image": image_rgb}

    def stream_stop_handler(self, stream_id, frame_id, swag):
        self.logger.debug(f"{self.my_id()} stream_stop_handler()")
        if self.video_writer:
            self.video_writer.release()
            self.video_writer = None
        return True, None

# --------------------------------------------------------------------------- #
