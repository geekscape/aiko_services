# Usage
# ~~~~~
# pip install "aiko_services[depthai]"    # or: pip install depthai
# cd src/aiko_services/elements/cameras
#
# aiko_pipeline create pipelines/depthai_pipeline_0.json -s 1
# aiko_pipeline create pipelines/depthai_pipeline_0.json -s 1  \
#     -p VideoReadDepthAI.data_sources "(depthai://<camera-address>)"  \
#     -p VideoReadDepthAI.resolution 1280x720 -p VideoReadDepthAI.frame_rate 8
#
# To Do
# ~~~~~
# - A "depthai://" DataTarget is not planned: an OAK camera has no sink
# - Stereo depth and IMU outputs as further Frame data

from typing import Tuple

import aiko_services as aiko
import aiko_services.elements.cameras.scheme_depthai  # registers "depthai://"

__all__ = ["VideoReadDepthAI"]

INITIAL_SHARE = {                  # never a parameter name: the framework
    "state": "idle", "device_id": "-", "address": "-",  # reads share first
    "settled": "-", "frames": "0", "measured_fps": "0.0",
    "capture_timeouts": "0", "last_frame_utc": "-", "last_error": "-",
    "sensor": {}
}

# --------------------------------------------------------------------------- #
# VideoReadDepthAI is a DataSource that reads a Luxonis OAK camera through
# the "depthai://" DataScheme (scheme_depthai.py), which owns the camera,
# its warm-up and the shared state.  Frames are NumPy uint8 HxWx3 RGB
#
# parameter: "data_sources" is "(depthai://)" or "(depthai://<address>)"
# parameter: "resolution"   "WxH" (default "1920x1080"), "native" / "full"
# parameter: "frame_rate"   frames per second (default 25.0), "25/1" form
# parameter: "settle", "resize_mode", "aux_stream", "capture_timeout":
#            see scheme_depthai.py
# parameter: "media_type"   optional "numpy" or "pil" conversion
#
# Note: Only supports Streams with "data_sources" parameter

class VideoReadDepthAI(aiko.DataSource):  # PipelineElement
    def __init__(self, context: aiko.ContextPipelineElement):
        context.set_protocol("video_read_depthai:0")
        context.call_init(self, "PipelineElement", context)
        self.share.update(dict(INITIAL_SHARE))

    def process_frame(self, stream, images) -> Tuple[aiko.StreamEvent, dict]:
        media_type, _ = self.get_parameter("media_type", None)
        if media_type:
            from aiko_services.elements.media.image_io import convert_images
            images = convert_images(images, media_type)
        return aiko.StreamEvent.OKAY, {"images": images}

# --------------------------------------------------------------------------- #
