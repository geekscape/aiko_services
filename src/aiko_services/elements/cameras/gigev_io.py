# Usage
# ~~~~~
# pip install "aiko_services[ids_peak]"   # Linux, plus the native IDS peak SDK
# cd src/aiko_services/elements/cameras
#
# aiko_pipeline create pipelines/gigev_pipeline_0.json -s 1
# aiko_pipeline create pipelines/gigev_pipeline_0.json -s 1  \
#     -p VideoReadGigE.data_sources "(gigev://<camera-address>)"  \
#     -p VideoReadGigE.resolution native -p VideoReadGigE.frame_rate 1  \
#     -p VideoReadGigE.exposure_us 20000 -p VideoReadGigE.gain 2.0
#
# To Do
# ~~~~~
# - A "gigev://" DataTarget is not planned: a camera has no sink

from typing import Tuple

import aiko_services as aiko
import aiko_services.elements.cameras.scheme_gigev  # registers "gigev://"

__all__ = ["VideoReadGigE"]

INITIAL_SHARE = {                  # never a parameter name: the framework
    "state": "idle", "device_id": "-", "address": "-",  # reads share first
    "settled": "-", "frames": "0", "measured_fps": "0.0",
    "capture_timeouts": "0", "last_frame_utc": "-", "last_error": "-",
    "sensor": {}
}

# --------------------------------------------------------------------------- #
# VideoReadGigE is a DataSource that reads a GenICam GigE Vision camera
# through the "gigev://" DataScheme (scheme_gigev.py), which owns the
# camera backend (IDS peak, or Aravis as an experimental alternative),
# its exposure warm-up and the shared state.  Frames are NumPy uint8
# HxWx3 RGB
#
# parameter: "data_sources" is "(gigev://)" or "(gigev://<address>)"
# parameter: "backend"      auto | peak | aravis
# parameter: "resolution"   "WxH" (default "1920x1080"), "native" / "full"
# parameter: "frame_rate"   frames per second (default 25.0), "25/1" form
# parameter: "trigger"      auto | software | off
# parameter: "exposure_us", "gain", "settle", "resize_mode",
#            "capture_timeout": see scheme_gigev.py
# parameter: "media_type"   optional "numpy" or "pil" conversion
#
# Note: Only supports Streams with "data_sources" parameter

class VideoReadGigE(aiko.DataSource):  # PipelineElement
    def __init__(self, context: aiko.ContextPipelineElement):
        context.set_protocol("video_read_gigev:0")
        context.call_init(self, "PipelineElement", context)
        self.share.update(dict(INITIAL_SHARE))

    def process_frame(self, stream, images) -> Tuple[aiko.StreamEvent, dict]:
        media_type, _ = self.get_parameter("media_type", None)
        if media_type:
            from aiko_services.elements.media.image_io import convert_images
            images = convert_images(images, media_type)
        return aiko.StreamEvent.OKAY, {"images": images}

# --------------------------------------------------------------------------- #
