# Usage: File
# ~~~~~~~~~~~
# aiko_pipeline create pipelines/image_pipeline_0.json -s 1 -sr -ll debug
#
# aiko_pipeline create pipelines/image_pipeline_0.json -s 1 -p rate 1.0
#
# aiko_pipeline create pipelines/image_pipeline_0.json -s 1  \
#   -p ImageReadFile.data_batch_size 8
#
# aiko_pipeline create pipelines/image_pipeline_0.json -s 1  \
#   -p ImageReadFile.data_sources file://data_in/in_{}.jpeg
#
# aiko_pipeline create pipelines/image_pipeline_0.json -s 1  \
#   -p ImageWriteFile.path "file://data_out/out_{:02d}.jpeg"
#
# aiko_pipeline create pipelines/image_pipeline_0.json -s 1  \
#   -p ImageReadFile.data_sources file://data_in/in_00.jpeg  \
#   -p ImageResize.resolution 320x240                        \
#   -p ImageWriteFile.data_targets file://data_out/out_00.jpeg
#
# aiko_pipeline create pipelines/image_pipeline_1.json -s 1
#
# Usage: ZMQ
# ~~~~~~~~~~
# aiko_pipeline create pipelines/image_zmq_pipeline_0.json -s 1 -sr  \
#            -ll debug -gt 10
# aiko_pipeline create pipelines/image_zmq_pipeline_0.json -s 1 -sr  \
#            -p ImageReadZMQ.data_sources zmq://0.0.0.0:6502
#
# aiko_pipeline create pipelines/image_zmq_pipeline_1.json -s 1 -sr  \
#            -ll debug                                               \
#            -p ImageReadFile.rate 2.0                               \
#            -p ImageWriteZMQ.data_targets zmq://192.168.0.1:6502
#
# To Do
# ~~~~~
# - Support for "media type" encoding details for "image"
#   - Consider additional encoding information in out-of-band image records ?
#     - "frame_id" and/or "image:length:content", "image/jpeg:length:content" ?
#
# - Consolidate multiple "media_pipeline_?.json" files into Graph Path(s) !
# - ImageResize: {"scale": "1/3"} or {"scale": 2} or {"resolution": 640}
#
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
# - Metrics: Determine what to metrics to capture, e.g frame rates ?

from PIL import Image
import io
from typing import Tuple
import zlib

import aiko_services as aiko

__all__ = [
    "convert_image_to_numpy", "convert_image_to_pil",
    "ImageOutput", "ImageOverlay", "ImageOverlayFilter",
    "ImageReadFile", "ImageReadZMQ", "ImageResize",
    "ImageWriteFile", "ImageWriteZMQ"
]

_LOGGER = aiko.get_logger(__name__)

_CV2_IMPORTED = False
try:
    import cv2
    _CV2_IMPORTED = True
except ModuleNotFoundError:  # TODO: Optional warning flag
    diagnostic = "image_io.py: Couldn't import cv2 module"
#   print(f"WARNING: {diagnostic}")
#   _LOGGER.warning(diagnostic)
#   raise ModuleNotFoundError(
#       'opencv-python package not installed.  '
#       'Install aiko_services with --extras "opencv" '
#       'or install opencv-python manually to use the "image_io" module')

_NUMPY_IMPORTED = False
try:
    import numpy as np
    _NUMPY_IMPORTED = True
except ModuleNotFoundError:  # TODO: Optional warning flag
    diagnostic = "image_io.py: Couldn't import numpy module"
#   print(f"WARNING: {diagnostic}")
#   _LOGGER.warning(diagnostic)

# --------------------------------------------------------------------------- #
# str: "JPEG" or "PNG"

def image_to_bytes(image: Image.Image, format: str="JPEG") -> bytes:
    with io.BytesIO() as image_bytes_io:
        image = convert_image_to_pil(image)
        if not image:
            raise ValueError(
                f"image_to_bytes(): Unknown image type: {type(image)}")
        image.save(image_bytes_io, format=format)
        return image_bytes_io.getvalue()

def bytes_to_image(image_bytes: bytes) -> Image.Image:
    image_bytes_io = io.BytesIO(image_bytes)
    image = Image.open(image_bytes_io)
    image.load()
    image_bytes_io.close()
    return image

def convert_image_to_numpy(image):
    if not isinstance(image, np.ndarray):
        if isinstance(image, Image.Image):
            image = np.array(image)  # RGB
        else:
            image = None
    return image

def convert_image_to_pil(image):
    if not isinstance(image, Image.Image):
        if isinstance(image, np.ndarray):  # TODO: Check NUMPY_IMPORTED
            image = Image.fromarray(image.astype("uint8"), "RGB")
        else:
            image = None
    return image

convert_image_handlers = {
    "numpy": convert_image_to_numpy,
    "pil": convert_image_to_pil
}

def convert_image(image, type):
    if type not in convert_image_handlers:
        raise ValueError(f"image_io:convert_image(): Unknown type: {type}")
    return convert_image_handlers[type](image)

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
                    if confidence >= self.threshold:
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

class ImageOverlayFilter(aiko.PipelineElement):
    def __init__(self, context):
        context.set_protocol("image_overlay_filter:0")
        context.get_implementation("PipelineElement").__init__(self, context)

    def process_frame(self, stream, overlay)  \
        -> Tuple[aiko.StreamEvent, dict]:

        deny, _ = self.get_parameter("deny", [])
        threshold, _ = self.get_parameter("threshold", 0.0)

        overlay_filtered = {"objects": [], "rectangles": []}
        objects_filtered = overlay_filtered["objects"]
        rectangles_filtered = overlay_filtered["rectangles"]

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

                if name not in deny and confidence >= threshold:
                    objects_filtered.append(object)
                    rectangles_filtered.append(rectangle)

        return aiko.StreamEvent.OKAY, {"overlay": overlay_filtered}

# --------------------------------------------------------------------------- #
# ImageReadFile is a DataSource which supports ...
# - Individual image files
# - Directory of image files with an optional filename filter
# - TODO: Archive (tgz, zip) of image files with an optional filename filter
#
# parameter: "data_sources" is the read file path, format variable: "frame_id"
#
# Note: Only supports Streams with "data_sources" parameter

class ImageReadFile(aiko.DataSource):  # PipelineElement
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
                diagnostic = f"Error loading image: {exception}"
                return aiko.StreamEvent.ERROR, {"diagnostic": diagnostic}

        return aiko.StreamEvent.OKAY, {"images": images}

# --------------------------------------------------------------------------- #
# ImageReadZMQ is a DataSource which supports ...
# - ImageWriteZMQ(DataTarget) ZMQ client --> ImageReadZMQ(DataSource) ZMQ server
#   - Individual image records produced by ZMQ client and consumed by ZMQ server
#
# parameter: "data_sources" is the ZMQ server bind details (scheme_zmq.py)
#            "media_type" is either "numpy" or "pil"
#            "compressed" (boolean) indicated whether to decompress the payload
#
# Note: Only supports Streams with "data_sources" parameter

class ImageReadZMQ(aiko.DataSource):  # PipelineElement
    def __init__(self, context: aiko.ContextPipelineElement):
        context.set_protocol("image_read_zmq:0")
        context.get_implementation("PipelineElement").__init__(self, context)

    def process_frame(self, stream, records) -> Tuple[aiko.StreamEvent, dict]:
        images = []
        media_type, _ = self.get_parameter("media_type", None)
        if media_type:
            tokens = media_type.split("/")
            media_type = tokens[0] if len(tokens) == 1 else tokens[1]

        compressed, _ = self.get_parameter("compressed", False)

        for record in records:
            record = zlib.decompress(record) if compressed else record
            image = bytes_to_image(record)
            self.logger.debug(f"{self.my_id()}: {len(record)} --> {image.size}")
    #       if image.startswith("image:"):  # TODO: "image:length:content" ?
    #           tokens = image.split(":")
    #           image = tokens[2:][0]      # just the "content"
            if media_type:
                image = convert_image(image, media_type)
            images.append(image)
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
        resolution, found = self.get_parameter("resolution")
        if not found:
            return aiko.StreamEvent.OKAY, {"images": images}

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

class ImageWriteFile(aiko.DataTarget):  # PipelineElement
    def __init__(self, context: aiko.ContextPipelineElement):
        context.set_protocol("image_write_file:0")
        context.get_implementation("PipelineElement").__init__(self, context)

    def process_frame(self, stream, images) -> Tuple[aiko.StreamEvent, dict]:
        for image in images:
            path = stream.variables["target_path"]
            if stream.variables["target_path_template"]:
                path = path.format(stream.variables["target_file_id"])
                stream.variables["target_file_id"] += 1
            self.logger.debug(f"{self.my_id()}: {path}")

            image = convert_image_to_pil(image)
            if not image:
                diagnostic = "UNKNOWN IMAGE TYPE"  # TODO: FIX ME !
                return aiko.StreamEvent.ERROR, {"diagnostic": diagnostic}
            try:
                image.save(path)
            except Exception as exception:
                diagnostic = f"Error saving image: {exception}"
                return aiko.StreamEvent.ERROR, {"diagnostic": diagnostic}

        return aiko.StreamEvent.OKAY, {}

# --------------------------------------------------------------------------- #
# ImageWriteZMQ is a DataTarget which supports ...
# - ImageWriteZMQ(DataTarget) ZMQ client --> ImageReadZMQ(DataSource) ZMQ server
#   - Individual image records produced by ZMQ client and consumed by ZMQ server
#
# parameter: "data_targets" is the ZMQ connect details (scheme_zmq.py)
#            "compressed" (boolean) indicated whether to compress the payload
#
# Note: Only supports Streams with "data_targets" parameter

class ImageWriteZMQ(aiko.DataTarget):  # PipelineElement
    def __init__(self, context: aiko.ContextPipelineElement):
        context.set_protocol("image_write_zmq:0")
        context.get_implementation("PipelineElement").__init__(self, context)

    def process_frame(self, stream, images) -> Tuple[aiko.StreamEvent, dict]:
        media_type = "image"                            # TODO: "image/zip" ?
        compressed, _ = self.get_parameter("compressed", False)

        for image in images:
     #      image = f"{media_type}:{len(image)}:{image}"  # "image:length:content" ?
            record = image_to_bytes(image)
            record = zlib.compress(record) if compressed else record
            self.logger.debug(f"{self.my_id()}: {image.size} --> {len(record)}")
            stream.variables["target_zmq_socket"].send(record)

        return aiko.StreamEvent.OKAY, {}

# --------------------------------------------------------------------------- #
