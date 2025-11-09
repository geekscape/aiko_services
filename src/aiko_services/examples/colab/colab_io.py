# Usage: Colab
# ~~~~~~~~~~~~
# aiko_pipeline create pipelines/webcam_pipeline_0.json -s 1 -ll debug
#
# To Do
# ~~~~~
# - Consider DataScheme "mqtt://" ... can create own MQTT Connection
# - Plain web server / browser combination that works outside of Google Colab

from typing import Tuple

import aiko_services as aiko
from aiko_services.elements.media import convert_images

__all__ = ["VideoReadColab"]

_LOGGER = aiko.process.logger(__name__)

# --------------------------------------------------------------------------- #
# VideoReadColab is a DataSource supporting web cameras running in Google Colab
#
# parameter: "data_sources" is the read file path or device number
#
# Note: Only supports Streams with "data_sources" parameter

class VideoReadColab(aiko.DataSource):  # PipelineElement
    def __init__(self, context):
        context.set_protocol("colab:0")
        context.call_init(self, "PipelineElement", context)

    def process_frame(self, stream, images) -> Tuple[aiko.StreamEvent, dict]:
        media_type, _ = self.get_parameter("media_type", None)
        if media_type:
            images = convert_images(images, media_type)
        return aiko.StreamEvent.OKAY, {"images": images}

# --------------------------------------------------------------------------- #
