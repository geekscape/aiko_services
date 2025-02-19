# Usage: File
# ~~~~~~~~~~~
# aiko_pipeline create pipelines/video_pipeline_0.json -s 1 -sr -ll debug
#
# aiko_pipeline create pipelines/video_pipeline_0.json -s 1 -p rate 4.0
#
# aiko_pipeline create pipelines/video_pipeline_0.json -s 1  \
#   -p VideoReadFile.data_batch_size 8
#
# aiko_pipeline create pipelines/video_pipeline_0.json -s 1  \
#   -p VideoReadFile.data_sources file://data_in/in_{}.mp4
#
# aiko_pipeline create pipelines/video_pipeline_0.json -s 1  \
#   -p VideoWriteFile.path "file://data_out/out_{:02d}.mp4"
#
# aiko_pipeline create pipelines/video_pipeline_0.json -s 1  \
#   -p VideoReadFile.data_sources file://data_in/in_00.mp4   \
#   -p ImageResize.resolution 320x240                        \
#   -p VideoWriteFile.data_targets file://data_out/out_00.mp4
#
# Drop frame test
# ~~~~~~~~~~~~~~~
# aiko_pipeline create pipelines/video_pipeline_1.json -s 1 -ll debug
#
# To Do
# ~~~~~
# - Implement "VideoReadFile.data_batch_size" in "frame_generator()"
#
# - Refactor optional module import into common function (see image_io.py)
#
# - Implement start_frame (first) and stop_frame (last) parameters
# - Improve PipelineElement VideoSample()
#   - Rather than sample by frame ... sample by image count in [images] input
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
# - Metrics: Determine what to metrics to capture, e.g frame rates ?
#
# - Design video windowing, i.e collecting multiple frame for ML processing
#   together, e.g gesture analysis
#
# - "Batching" images for CPU-GPU memory transfer efficiently for nVidia
#   - For both images and video ... depending upon ML model
#
# - Consider VideoShow() GUI ...
#   - Why aren't the cv2.imshow() graphical icons appearing about the image ?
#   - cv2.createTrackbar() ?
#   - Integrate with tkinter ?

from typing import Tuple
from pathlib import Path

import aiko_services as aiko

__all__ = [
    "VideoOutput", "VideoReadFile", "VideoSample", "VideoShow", "VideoWriteFile"
]

_LOGGER = aiko.get_logger(__name__)

_CV2_IMPORTED = False
try:
    import cv2
    _CV2_IMPORTED = True
except ModuleNotFoundError:  # TODO: Optional warning flag
    diagnostic = "video_io.py: Couldn't import cv2 module"
#   print(f"WARNING: {diagnostic}")
#   _LOGGER.warning(diagnostic)
#   raise ModuleNotFoundError(
#       'opencv-python package not installed.  '
#       'Install aiko_services with --extras "opencv" '
#       'or install opencv-python manually to use the "video_io" module')

_NUMPY_IMPORTED = False
try:
    import numpy as np
    _NUMPY_IMPORTED = True
except ModuleNotFoundError:  # TODO: Optional warning flag
    diagnostic = "video_io.py: Couldn't import numpy module"
#   print(f"WARNING: {diagnostic}")
#   _LOGGER.warning(diagnostic)

# --------------------------------------------------------------------------- #
# Useful for Pipeline output that should be all of the images processed

class VideoOutput(aiko.PipelineElement):
    def __init__(self, context: aiko.ContextPipelineElement):
        context.set_protocol("video_output:0")
        context.get_implementation("PipelineElement").__init__(self, context)

    def process_frame(self, stream, images) -> Tuple[aiko.StreamEvent, dict]:
        return aiko.StreamEvent.OKAY, {"images": images}

# --------------------------------------------------------------------------- #
# VideoReadFile is a DataSource which supports ...
# - Individual video files
# - Directory of video files with an optional filename filter
# - TODO: Archive (tgz, zip) of video files with an optional filename filter
#
# parameter: "data_sources" is the read file path, format variable: "video_id"
#
# Note: Only supports Streams with "data_sources" parameter

class VideoReadFile(aiko.DataSource):  # PipelineElement
    def __init__(self, context: aiko.ContextPipelineElement):
        context.set_protocol("video_read_file:0")
        context.get_implementation("PipelineElement").__init__(self, context)

    def start_stream(self, stream, stream_id):
        stream.variables["video_capture"] = None
        stream.variables["video_frame_generator"] = None
        return super().start_stream(stream, stream_id,
            frame_generator=self.frame_generator, use_create_frame=False)

    def video_frame_iterator(self, video_capture):
        while True:
            status, image_bgr = video_capture.read()
            if not status:
                break
            image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
            yield image_rgb

    def frame_generator(self, stream, frame_id):
        video_frame_generator = stream.variables["video_frame_generator"]
        while True:
            if not video_frame_generator:
                try:
                    path, file_id = next(
                        stream.variables["source_paths_generator"])
                except StopIteration:
                    stream.variables["source_paths_generator"] = None
                    diagnostic = "End of video file(s)"
                    return aiko.StreamEvent.STOP, {"diagnostic": diagnostic}

                if not path.is_file():
                    diagnostic = f'path "{path}" must be a file'
                    return aiko.StreamEvent.ERROR, {"diagnostic": diagnostic}

            # TODO: handle integer video "path" ... maybe ?
            #   if isinstance(path, str) and path.isdigit():
            #       path = int(str(path))

                video_capture = cv2.VideoCapture(str(path))
                if not video_capture.isOpened():
                    diagnostic = f"Couldn't open video file: {path}"
                    return aiko.StreamEvent.ERROR, {"diagnostic": diagnostic}
                stream.variables["video_capture"] = video_capture
                video_frame_generator = self.video_frame_iterator(video_capture)
                stream.variables["video_frame_generator"] =  \
                    video_frame_generator

            try:
                image_rgb = next(video_frame_generator)
                return aiko.StreamEvent.OKAY, {"images": [image_rgb]}
            except StopIteration:
                video_frame_generator = None
                stream.variables["video_frame_generator"] = None

    def process_frame(self, stream, images) -> Tuple[aiko.StreamEvent, dict]:
        self.logger.debug(f"{self.my_id()}")
        return aiko.StreamEvent.OKAY, {"images": images}

    def stop_stream(self, stream, stream_id):
        video_capture = stream.variables["video_capture"]
        if video_capture and video_capture.isOpened():
            video_capture.release()
            stream.variables["video_capture"] = None
        return aiko.StreamEvent.OKAY, {}

# --------------------------------------------------------------------------- #

class VideoSample(aiko.PipelineElement):
    def __init__(self, context):
        context.set_protocol("video_sample:0")
        context.get_implementation("PipelineElement").__init__(self, context)

    def process_frame(self, stream, images) -> Tuple[aiko.StreamEvent, dict]:
        sample_rate, _ = self.get_parameter("sample_rate", 1)
        if stream.frame_id % sample_rate:
            self.logger.debug(f"{self.my_id()}: frame dropped")
            return aiko.StreamEvent.DROP_FRAME, {}
        else:
            self.logger.debug(f"{self.my_id()}: frame not dropped")
            return aiko.StreamEvent.OKAY, {"images": images}

# --------------------------------------------------------------------------- #
# TODO: Change color, title and resolution

class VideoShow(aiko.PipelineElement):
    def __init__(self, context):
        context.set_protocol("video_show:0")
        context.get_implementation("PipelineElement").__init__(self, context)

#   def slider_handler(self, value):
#       print(f"slider: {value}")
#       cv2.imshow(title, image_bgr)  # TODO: "title" ?!?

    def process_frame(self, stream, images) -> Tuple[aiko.StreamEvent, dict]:
        for image in images:
            if not isinstance(image, np.ndarray):
                image = np.array(image)  # RGB

            grayscale = len(image.shape) == 2
            if grayscale:
                image_bgr = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
            else:
                image_bgr = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)

            title, _ = self.get_parameter("title", "Video")
            cv2.namedWindow(title)
        #   cv2.createTrackbar("Slider", title, 0, 9, self.slider_handler)
            cv2.imshow(title, image_bgr)
            if stream.frame_id == 0:
                position, _ = self.get_parameter("position", "1280:0")
                position_x, position_y = position.split(":")
                cv2.moveWindow(title, int(position_x), int(position_y))
            if cv2.waitKey(1) & 0xFF == ord("x"):
                system_exit, _ = self.get_parameter("system_exit", False)
                diagnostic = "VideoShow exit"
                if system_exit:
                    raise SystemExit(diagnostic)
                else:
                    return aiko.StreamEvent.STOP, {"diagnostic": diagnostic}
        return aiko.StreamEvent.OKAY, {}

    def stream_stop_handler(self, stream, stream_id):
        cv2.destroyAllWindows()  # TODO: when all Streams stopped
        return aiko.StreamEvent.OKAY, {}

# --------------------------------------------------------------------------- #
# VideoWriteFile is a DataTarget that writes images to a video file
#
# parameter: "data_targets" is the write file path, format variable: "frame_id"
#
# Note: Only supports Streams with "data_targets" parameters

class VideoWriteFile(aiko.DataTarget):  # PipelineElement
    def __init__(self, context: aiko.ContextPipelineElement):
        context.set_protocol("video_write_file:0")
        context.get_implementation("PipelineElement").__init__(self, context)

    def start_stream(self, stream, stream_id):
        stream_event, diagnostic = super().start_stream(stream, stream_id)

        if stream_event == aiko.StreamEvent.OKAY:
            path = stream.variables["target_path"]
            if stream.variables["target_path_template"]:
                path = path.format(stream.variables["target_file_id"])
            self.logger.debug(f"{self.my_id()}: {path}")
            stream.variables["video_path"] = path
            stream.variables["video_writer"] = None
            stream_event = aiko.StreamEvent.OKAY
            diagnostic = {}
        return stream_event, diagnostic

# Show codec list by invoking cv2.VideoWriter(..., fourcc=-1)
# video_output.avi: format: XVID
# video_output.mp4: format: MP4V, DIVX, H264, X264
# Linux:   DIVX, XVID, MJPG, X264, WMV1, WMV2
# WIndows: DIVX

    def _create_video_writer(
        self, path, resolution, format="MP4V", frame_rate=30.0):

        format, _ = self.get_parameter("format", format)
        format = cv2.VideoWriter_fourcc(*format)
        frame_rate, _ = self.get_parameter("frame_rate", frame_rate)
        resolution, _ = self.get_parameter("resolution", resolution)
        if isinstance(resolution, str):
            width, height = resolution.split("x")
            resolution = (int(width), int(height))
        parent_path = Path(path).parent
        parent_path.mkdir(exist_ok=True, parents=True)
        path = str(path)
        video_writer = cv2.VideoWriter(
            path, format, float(frame_rate), resolution)
        return video_writer

    def process_frame(self, stream, images) -> Tuple[aiko.StreamEvent, dict]:
        self.logger.debug(f"{self.my_id()}")

        if stream.variables["video_writer"]:
            video_writer = stream.variables["video_writer"]
        else:
            path = stream.variables["video_path"]
            resolution = (images[0].shape[1], images[0].shape[0])
            video_writer = self._create_video_writer(path, resolution)
            stream.variables["video_writer"] = video_writer

        for image in images:
            image_bgr = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
            video_writer.write(image_bgr)

        return aiko.StreamEvent.OKAY, {}

    def stop_stream(self, stream, stream_id):
        if stream.variables["video_writer"]:
            stream.variables["video_writer"].release()
            stream.variables["video_writer"] = None
        return aiko.StreamEvent.OKAY, {}

# --------------------------------------------------------------------------- #
