# Usage
# ~~~~~
# cd aiko_services/elements
# aiko_pipeline create pipeline_image_io.json --stream_id 1  \
#   --stream_parameters width 320 -sp ImageReadFile.path image.jpeg
#
# To Do
# ~~~~~
# - ImageReadFile should also handle a DataSource type ...
#   - URL: "file://" and media_type: "jpeg", "png", etc
#
# - PE_Metrics: Consider what to measure ?
#   choices of data type to transfer via function parameters

from typing import Tuple
from pathlib import Path
from PIL import Image

import aiko_services as aiko

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
#
# --------------------------------------------------------------------------- #
# ImageReadFile is a DataSource with an image "path" string parameter
#
# Supports both Streams and direct process_frame() calls
#
# Test
# ~~~~
# export AIKO_LOG_LEVEL=DEBUG; export AIKO_LOG_MQTT=false
# aiko_pipeline create pipeline_image_io.json -fd "(path: z_00.jpeg)"
# aiko_pipeline create pipeline_image_io.json -s 1
# aiko_pipeline create pipeline_image_io.json -s 1  \
#                                             -sp ImageReadFile.path z_00.jpeg

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

    def process_frame(self, stream, path) -> Tuple[bool, dict]:
        self.logger.debug(f"{self._id(stream)}: image path: {path}")

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
