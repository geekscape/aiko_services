# Usage
# ~~~~~
# aiko_pipeline create pipelines/rtsp_pipeline_0.json -s 1 -ll debug_all
#  -p VideoReadRTSP.data_sources rtsp://username:password@host:port
#  -p VideoReadRTSP.resolution 640x480  # width x height
#  -p VideoReadRTSP.format     RGB
#  -p VideoReadRTSP.frame_rate 25/1     # frames / second
#
# To Do
# ~~~~~
# - PipelineElement: "avahi-browser" discovery (filter1) --> Device Registrar
#   - Provide static configuration for any device type, e.g ESP32, Host, Robot
#   - Dynamically create Actors for each device (filter2) --> Service Registrar
#   - Start with network cameras (Dahua, HikVision)
#   - Maybe https://pypi.org/project/zeroconf ?
#
# - Design and implement RTSP DataScheme
#   - Consider whether "VideoRTSPStore" is-a DataSource, creating video files ?

from typing import Tuple

import aiko_services as aiko
from aiko_services.elements.media import convert_images
from aiko_services.main.utilities import *

__all__ = ["VideoReadRTSP"]

# --------------------------------------------------------------------------- #
# VideoReadRTSP is a DataSource which supports ...
# - RTSP server, e.g network camera
#
# parameter: "data_sources" is the RTSP server URL, format variable: "frame_id"
#
# Note: Only supports Streams with "data_sources" parameter

class VideoReadRTSP(aiko.DataSource):  # PipelineElement
    def __init__(self, context: aiko.ContextPipelineElement):
        context.set_protocol("video_read_rtsp:0")
        context.call_init(self, "PipelineElement", context)

    def process_frame(self, stream, images) -> Tuple[aiko.StreamEvent, dict]:
        timestamp = -3.0
        if "timestamps" in stream.variables:
            timestamp = stream.variables["timestamps"][0]  # Unix time
            timestamp = timestamp if timestamp else -4.0
        self.logger.debug(f"{self.my_id()}: process_frame(): {timestamp:.2f}")

        media_type, _ = self.get_parameter("media_type", None)
        if media_type:
            images = convert_images(images, media_type)
    #   print_memory_used("VideoReadRTSP.process_frame(): ")
        return aiko.StreamEvent.OKAY, {"images": images}

# --------------------------------------------------------------------------- #
