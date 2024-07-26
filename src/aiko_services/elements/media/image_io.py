# Usage
# ~~~~~
# cd src/aiko_services/elements/media
# aiko_pipeline create pipeline_image_io.json --stream_id 1  \
#   -sp ImageReadFile.path image.jpeg
#   -sp ImageResize.width 320 -sp ImageResize.height 240
#
# To Do
# ~~~~~
# - Document "DataSource" and "DataTarget" ...
#   - ImageReadFile: start_stream() --> create_frame() --> process_frame()
#                    Therefore pass parameters as required
#   - ImageWriteFile: Mustn't use create_frame()
#                     Therefore get parameters in process_frame()
#
# - ImageReadFile should accept a DataSource type ...
#   - URL: "file://" and media_type: "jpeg", "png", etc
#
# - PE_Metrics: Determine what to measure ?

from typing import Tuple
from pathlib import Path
from PIL import Image

import aiko_services as aiko
_LOGGER = aiko.get_logger(__name__)

_NUMPY_IMPORTED = False
try:
    import numpy as np
    _NUMPY_IMPORTED = True
except:  # TODO: Optional warning flag to avoid being annoying !
    diagnostic = "image_io.py: Couldn't import numpy module"
    print(f"WARNING: {diagnostic}")
    _LOGGER.warning(diagnostic)

def containsAll(source: str, match: chr):
    return 0 not in [character in source for character in match]

# --------------------------------------------------------------------------- #
# Check
# ~~~~~
# * aiko_pipeline create -s 1 -sp path --> load the stream parameter data
#   - Overriding the PipelineDefinition
#   - Same for HL Serving Tasks and HL Live
#
# *#1 PE.set_parameter(): parameters --> self.share[] ?
#
# * Consider process_frame() updating stream parameters --> self.share[]
#
# * For "PipelineElement.create_frames()" ...
#   - Implement frame window, which has a maximum size to minimise frames
#   - Implement frame "push back" so subsequent PEs can manage frame flow
#
# * If DataSource has "stream_required" ...
#   - Each DataSource developer shouldn't have to do this
#
# - Try to remove the need to write PE.__init__(...) in every PE
#
# - Check HL Serving Task and HL Live
#   - process_datasources(stream_id, parameters, [data_sources])
#     - data_sources: URL and MediaType
#
# - aiko_pipeline argument options for AIKO_LOG_LEVEL / AIKO_LOG_MQTT
#   - AIKO_LOG_MQTT --> AIKO_LOG=mqtt,console,...
#
# - Return Pipeline result back to HL Serving Task
#
# - Read / Write, to/from File, to/from Stream
#
# - URLs
#   - file://, mqtt://, hl:// (pre-signed URL), s3://
#   - web_camera://, rtsp://, webrt://
#   - youtube:// uploaded video or live stream
#   * Haplomic: Shared memory, e.g shm://
#
# - MediaTypes
#   - image/raw|jpeg|png, video/h.264, audio/*, text/raw, pointcloud/2d|3d
#   * Laboratory camera: image/raw

# --------------------------------------------------------------------------- #
# ImageReadFile is a DataSource with an image "path" string parameter
#
# Supports both Streams and direct process_frame() calls
#
# To Do
# ~~~~~
# - Add Stream "parameter" for optional output Image numpy format
# - Consider what causes Stream to be closed, e.g single frame processed ?
#
# Test
# ~~~~
# export AIKO_LOG_LEVEL=DEBUG; export AIKO_LOG_MQTT=false
# aiko_pipeline create pipeline_image_io_0.json -fd "(path: z_data/in_00.jpeg)"
# aiko_pipeline create pipeline_image_io_0.json -s 1  \
#                                  -sp ImageReadFile.path z_data/in_00.jpeg

class ImageReadFile(aiko.PipelineElement):
    def __init__(self, context: aiko.ContextPipelineElement):
        context.get_implementation("PipelineElement").__init__(self, context)

    def start_stream(self, stream, stream_id):
        path, found = self.get_parameter("path")
        if not found:
            diagnostic = 'Must provide image "path" parameter'
            return aiko.StreamEvent.ERROR, diagnostic

        self.create_frame(stream, {"path": path})
        return aiko.StreamEvent.OKAY, None

    def process_frame(self, stream, path) -> Tuple[StreamEvent, dict]:
        self.logger.debug(f"{self.my_id()}: image path: {path}")

        if not Path(path).exists():
            diagnostic = f'Image "{path}" does not exist'
            return aiko.StreamEvent.ERROR, {"diagnostic": diagnostic}
        try:
            image = Image.open(path)
        except Exception as exception:
            diagnostic = f"Error loading image: {exception}"
            return aiko.StreamEvent.ERROR, {"diagnostic": diagnostic}

        self.logger.info(f"Image shape: {image.size}")
        return aiko.StreamEvent.OKAY, {"image": image}

# --------------------------------------------------------------------------- #
# ToDo: Display lines, mask, polygons, rectangles, text
# ToDo: Display Metrics
# ToDo: Display pose stick figures

class ImageOverlay(aiko.PipelineElement):
    pass

# --------------------------------------------------------------------------- #
# ToDo: Add logic for using different backends (opencv,...) or
#           different input types (np.ndarray, ...)
# ToDo: cv2.resize(image, dimensions, interpolation=cv2.INTER_CUBIC) ?

class ImageResize(aiko.PipelineElement):
    def __init__(self, context: aiko.ContextPipelineElement):
        context.get_implementation("PipelineElement").__init__(self, context)

    def process_frame(self, stream, image) -> Tuple[StreamEvent, dict]:
        width, _ = self.get_parameter("width")
        height, _ = self.get_parameter("height")

        image = image.resize((int(width), int(height)))
        return aiko.StreamEvent.OKAY, {"image": image}

# --------------------------------------------------------------------------- #
# ImageWriteFile is a DataTarget that writes an image to a file
#
# in:  "image" to be written to a file
# out: None
#
# parameter: "path" is the write file path, format variable: "frame_id"
#
# Supports both Streams and direct process_frame() calls
#
# Test
# ~~~~
# export AIKO_LOG_LEVEL=DEBUG; export AIKO_LOG_MQTT=false
# aiko_pipeline create pipeline_image_io_0.json -s 1  \
#                                  -sp ImageWriteFile.path z_data/out_01.jpeg

class ImageWriteFile(aiko.PipelineElement):
    def __init__(self, context: aiko.ContextPipelineElement):
        context.get_implementation("PipelineElement").__init__(self, context)

    def process_frame(self, stream, image) -> Tuple[StreamEvent, dict]:
        path, found = self.get_parameter("path")
        if not found:
            diagnostic = 'Must provide image write file "path" parameter'
            return aiko.StreamEvent.ERROR, diagnostic

        if containsAll(path, "{}"):
            path = path.format(stream["frame_id"])
        self.logger.debug(f"{self.my_id()}: image write file path: {path}")

        if not isinstance(image, Image.Image):
            if isinstance(image, np.ndarray):  # TODO: Check NUMPY_IMPORTED
                pass                           # TODO: numpy conversion
            else:
                diagnostic = "UNKNOWN IMAGE TYPE"  # FIX ME !
                return aiko.StreamEvent.ERROR, diagnostic

        try:
            image.save(path)
        except Exception as exception:
            diagnostic = f"Error saving image: {exception}"
            return aiko.StreamEvent.ERROR, {"diagnostic": diagnostic}

        self.logger.info(f"Image shape: {image.size}")
        return aiko.StreamEvent.OKAY, {}

# --------------------------------------------------------------------------- #
