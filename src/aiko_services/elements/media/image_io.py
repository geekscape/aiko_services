# Usage
# ~~~~~
# cd aiko_services/elements
# aiko_pipeline create pipeline_image_io.json --stream_id 1  \
#   --stream_parameters width 320 -sp ImageReadFile.path image.jpeg
#
# To Do
# ~~~~~
# - PE_Metrics: Consider what to measure ?
#   choices of data type to transfer via function parameters

from typing import Tuple
from pathlib import Path
from PIL import Image

import aiko_services as aiko

# --------------------------------------------------------------------------- #
# To Do
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
# * Replace "raise SystemExit" with "return False, {}"
#
# * PipelineElement.process_frame() returns STATE, not boolean
#
# * pipeline.py (and everywhere) change from "context" to "stream"
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
#   * Haplomic: image/raw
#
# ---------------------------------------------------------------------- #

class ImageReadFile(aiko.PipelineElement):

    def __init__(self, context: aiko.ContextPipelineElement):
        context.get_implementation("PipelineElement").__init__(self, context)
        test = self.get_parameter("test", 0)

    def start_stream(self, stream, stream_id):
        width, found = self.get_parameter("width")  # TODO: Just testing

        path, found = self.get_parameter("path")
        if not found:
            raise SystemExit('Must provide stream "path" parameter')

        self.logger.info(f"{self._id(stream)}: image path: {path}")

        if not Path(path).exists():
            raise SystemExit(f"{path} does not exist")

        self.create_frame(stream, {"path": path})

    def process_frame(self, stream, path) -> Tuple[bool, dict]:
        if stream["stream_id"] == 0:  # TODO: "stream_required"
            raise SystemExit("Must create a stream")

        try:
            image = Image.open(path)
        except Exception as exception:
            raise SystemExit(f"Error loading image: {exception}")

        self.logger.info(f"image shape: {image.size}")
        return True, {"image": image}

# ---------------------------------------------------------------------- #
