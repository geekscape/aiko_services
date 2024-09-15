# Usage
# ~~~~~
# aiko_pipeline create image_pipeline_0.json -s 1 -sr -ll debug
#
# aiko_pipeline create image_pipeline_0.json -s 1 -sp rate 1.0
#
# aiko_pipeline create image_pipeline_0.json -s 1  \
#   -sp ImageReadFile.data_batch_size 8
#
# aiko_pipeline create image_pipeline_0.json -s 1  \
#   -sp ImageReadFile.data_sources file://data_in/in_{}.jpeg
#
# aiko_pipeline create image_pipeline_0.json -s 1  \
#     -sp ImageWriteFile.path "file://data_out/out_{:02d}.jpeg"
#
# aiko_pipeline create image_pipeline_0.json -s 1             \
#   -sp ImageReadFile.data_sources file://data_in/in_00.jpeg  \
#   -sp ImageResize.resolution 320x240                        \
#   -sp ImageWriteFile.data_targets file://data_out/out_00.jpeg
#
# aiko_pipeline create image_pipeline_1.json -s 1
#
# To Do
# ~~~~~
# - Refactor optional module import into common function (see video_io.py)
# - Provide checks around "cv2" and "numpy" usage to be optional
#
# - Consider what causes Stream to be closed, e.g single frame processed ?
#   - When all [data_sources] produced and not the default stream ?
#
# - Add Stream "parameter" for optional output Image numpy format
#
# - Document "DataSource" and "DataTarget" ...
#   - ImageReadFile:  start_stream() --> create_frames() --> process_frame()
#                     Therefore pass parameters as required
#   - ImageWriteFile: Mustn't use create_frame()
#                     Therefore get parameters in process_frame()
#
# - ImageReadFile should accept a list of DataSources type ...
#   - URL: "file://" and media_type: "jpeg", "png", etc
#
# - PE_Metrics: Determine what to metrics to capture, e.g frame rates ?

from PIL import Image
from typing import Tuple

import aiko_services as aiko
from aiko_services.elements.media import contains_all, DataSource, DataTarget

__all__ = [
    "ImageOutput", "ImageOverlay", "ImageReadFile",
    "ImageResize", "ImageWriteFile"
]

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
        'or install opencv-python manually to use the "image_io" module')

_NUMPY_IMPORTED = False
try:
    import numpy as np
    _NUMPY_IMPORTED = True
except ModuleNotFoundError:  # TODO: Optional warning flag
    diagnostic = "image_io.py: Couldn't import numpy module"
    print(f"WARNING: {diagnostic}")
    _LOGGER.warning(diagnostic)

# --------------------------------------------------------------------------- #
# Useful for Pipeline output that should be all of the images processed

class ImageOutput(aiko.PipelineElement):
    def __init__(self, context: aiko.ContextPipelineElement):
        context.set_protocol("image_output:0")
        context.get_implementation("PipelineElement").__init__(self, context)

    def process_frame(self, stream, images) -> Tuple[aiko.StreamEvent, dict]:
        return aiko.StreamEvent.OKAY, {"images": images}

# --------------------------------------------------------------------------- #
# TODO: Change color (text, boxes face / YOLO), font, line thickness
# TODO: Display camera name/path, date/time, FPS
# TODO: Display specified elipses, lines, mask, rectangles, polygons, text
# TODO: Display metrics
# TODO: Display pose stick figures

class ImageOverlay(aiko.PipelineElement):
    def __init__(self, context):
        context.set_protocol("image_overlay:0")
        context.get_implementation("PipelineElement").__init__(self, context)
        self.color = (0, 255, 255)
        self.font = cv2.FONT_HERSHEY_SIMPLEX
        self.font_scale = 0.75
        self.thickness = 2
        self.threshold = 0.0

    def process_frame(self, stream, images, overlay)  \
        -> Tuple[aiko.StreamEvent, dict]:

        images_overlaid = []
        for image in images:
            image_width = image.shape[1]
            grayscale = len(image.shape) == 2
            if grayscale:
                image_bgr = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
            else:
                image_bgr = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)

            if "rectangles" in overlay:
                rectangles = overlay["rectangles"]
                if "objects" in overlay:
                    objects = overlay["objects"]
                else:
                    objects = [{}] * len(rectangles)

                items = zip(objects, rectangles)
                for item in items:
                    object, rectangle = item
                    name = object.get("name", None)
                    confidence = object.get("confidence", 1.0)
                    if confidence > self.threshold:
                        x = int(rectangle["x"])
                        y = int(rectangle["y"])
                        w = int(rectangle["w"])
                        h = int(rectangle["h"])
                        top_left = (x, y)
                        bottom_right = (x + w, y + h)
                        if name:
                            text = f"{name}: {confidence:0.2f}"
                            width_height, _ = cv2.getTextSize(text,
                                self.font, self.font_scale, self.thickness)
                            tw, th = width_height
                            tx = x
                            if y > th * 1.5:
                                ty = int(y - th / 2 - 2)
                            else:
                                ty = y + h + th + 2
                            if x + tw > image_width:
                                tx = x - tw
                                ty = y + th
                            image_bgr = cv2.putText(image_bgr, text, (tx, ty),
                                self.font, self.font_scale, self.color,
                                self.thickness, cv2.LINE_AA)
                        image_bgr = cv2.rectangle(image_bgr,
                            top_left, bottom_right, self.color, self.thickness)

            if grayscale:
                image_overlaid = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
            else:
                image_overlaid = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
            images_overlaid.append(image_overlaid)

        return aiko.StreamEvent.OKAY, {"images": images_overlaid}

# --------------------------------------------------------------------------- #
# ImageReadFile is a DataSource which supports ...
# - Individual image files
# - Directory of image files with an optional filename filter
# - TODO: Archive (tgz, zip) of image files with an optional filename filter
#
# parameter: "data_sources" is the read file path, format variable: "frame_id"
#
# Note: Only supports Streams with "data_sources" parameter

class ImageReadFile(DataSource):  # common_io.py PipelineElement
    def __init__(self, context: aiko.ContextPipelineElement):
        context.set_protocol("image_read_file:0")
        context.get_implementation("PipelineElement").__init__(self, context)

    def process_frame(self, stream, paths) -> Tuple[aiko.StreamEvent, dict]:
        images = []
        for path in paths:
            try:
                image = Image.open(path)
                images.append(image)
                self.logger.debug(f"{self.my_id()}: {path} {image.size}")
            except Exception as exception:
                return aiko.StreamEvent.ERROR,  \
                       {"diagnostic": f"Error loading image: {exception}"}

        return aiko.StreamEvent.OKAY, {"images": images}

# --------------------------------------------------------------------------- #
# TODO: Add logic for using different backends (opencv,...) or
#           different input types (np.ndarray, ...)
#
# TODO: cv2.resize(image, dimensions, interpolation=cv2.INTER_CUBIC) ?
#       Shrink: INTER_AREA, enlarge: INTER_CUBIC (slow) or INTER_LINEAR (fast)
#       parameter: "speed": "fast" --> INTER_AREA or INTER_CUBIC
#       parameter: "speed": "slow" --> INTER_LINEAR
#       https://gist.github.com/georgeblck/e3e0274d725c858ba98b1c36c14e2835

class ImageResize(aiko.PipelineElement):
    def __init__(self, context: aiko.ContextPipelineElement):
        context.set_protocol("image_resize:0")
        context.get_implementation("PipelineElement").__init__(self, context)

    def process_frame(self, stream, images) -> Tuple[aiko.StreamEvent, dict]:
        resolution, _ = self.get_parameter("resolution")
        width, height = resolution.split("x")
        self.logger.debug(f"{self.my_id()}: resolution: {width}x{height}")

        images_resized = []
        for image in images:
            if isinstance(image, np.ndarray):  # TODO: Check CV2_IMPORTED
                image_resized = cv2.resize(image, (int(width), int(height)))
            else:
                image_resized = image.resize((int(width), int(height)))
            images_resized.append(image_resized)
        return aiko.StreamEvent.OKAY, {"images": images_resized}

# --------------------------------------------------------------------------- #
# ImageWriteFile is a DataTarget that writes images to files
#
# parameter: "data_targets" is the write file path, format variable: "frame_id"
#
# Note: Only supports Streams with "data_targets" parameter

class ImageWriteFile(DataTarget):  # common_io.py PipelineElement
    def __init__(self, context: aiko.ContextPipelineElement):
        context.set_protocol("image_write_file:0")
        context.get_implementation("PipelineElement").__init__(self, context)

    def process_frame(self, stream, images) -> Tuple[aiko.StreamEvent, dict]:
        for image in images:
            path = stream.variables["target_path"]
            if contains_all(path, "{}"):
                path = path.format(stream.variables["target_file_id"])
                stream.variables["target_file_id"] += 1
            self.logger.debug(f"{self.my_id()}: {path}")

            if not isinstance(image, Image.Image):
                if isinstance(image, np.ndarray):  # TODO: Check NUMPY_IMPORTED
                    image = Image.fromarray(image.astype("uint8"), "RGB")
                else:
                    return aiko.StreamEvent.ERROR,  \
                           {"diagnostic": "UNKNOWN IMAGE TYPE"}  # FIX ME !

            try:
                image.save(path)
            except Exception as exception:
                return aiko.StreamEvent.ERROR,  \
                       {"diagnostic": f"Error saving image: {exception}"}

        return aiko.StreamEvent.OKAY, {}

# --------------------------------------------------------------------------- #
