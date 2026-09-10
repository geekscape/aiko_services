# Usage
# ~~~~~
# cd src/aiko_services/elements/media
#
# aiko_pipeline create pipelines/synthetic_pipeline_0.json -s 1  # display
#
# aiko_pipeline create pipelines/synthetic_pipeline_0.json -s 1  \
#   -p resolution 1920x1080 -p CaptureLimit.duration 30
#
# aiko_pipeline create pipelines/synthetic_pipeline_0.json -s 1  \
#   -p SyntheticVideoRead.data_sources  \
#      "(synth://video/plain?width=640&height=360&text=frame_id&color=orange)"
#
# aiko_pipeline create pipelines/synthetic_pipeline_0.json -s 1  \
#   -p CaptureLimit.frame_count 45
#
# aiko_pipeline create pipelines/synthetic_pipeline_1.json -s 1  # record
#
# aiko_pipeline create pipelines/synthetic_pipeline_1.json -s 1  \
#   -p rate 30 -p frame_rate 30  # keep both equal: real-time playback
#
# To Do
# ~~~~~
# - Publish "frame_id" progress in self.share[], as VideoReadWebcam does
# - SyntheticVideoWrite: a verifying DataTarget, see scheme_synth.py To Do
# - SyntheticImageRead, SyntheticTextRead, SyntheticAudioRead

from typing import Tuple

import aiko_services as aiko
from aiko_services.elements.media.image_io import convert_images
import aiko_services.elements.media.scheme_synth  # registers "synth://"

__all__ = ["SyntheticVideoRead"]

_LOGGER = aiko.process.logger(__name__)

# --------------------------------------------------------------------------- #
# SyntheticVideoRead is a DataSource that synthesizes video frames without a
# camera.  The "synth://" DataScheme (scheme_synth.py) renders the frames:
# by default the frame id and the timestamp as text on a black background
#
# parameter: "data_sources" is "(synth://)" or
#            "(synth://video/plain?width=W&height=H&text=...&color=...)"
# parameter: "rate"         frames per second (default 15.0), 0: unpaced
# parameter: "media_type"   optional "numpy" or "pil" conversion
#
# Note: Only supports Streams with "data_sources" parameter

class SyntheticVideoRead(aiko.DataSource):  # PipelineElement
    def __init__(self, context: aiko.ContextPipelineElement):
        context.set_protocol("synthetic_video_read:0")
        context.call_init(self, "PipelineElement", context)

    def process_frame(self, stream, images) -> Tuple[aiko.StreamEvent, dict]:
        media_type, _ = self.get_parameter("media_type", None)
        if media_type:
            images = convert_images(images, media_type)
        return aiko.StreamEvent.OKAY, {"images": images}

# --------------------------------------------------------------------------- #
