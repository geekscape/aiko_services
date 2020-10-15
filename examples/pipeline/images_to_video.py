#!/usr/bin/env python3
#
# Usage
# ~~~~~
# LOG_LEVEL=DEBUG ./images_to_video.py
#
# To Do
# ~~~~~
# - Add CLI arguments !

import aiko_services.event as event
# import aiko_services.framework as aiko
from aiko_services.pipeline import Pipeline
from aiko_services.utilities import get_logger

FRAME_RATE = 0   # Process flat-out without delay
IMAGE_INPUT_PATHNAME = "z_input/image_{:06d}.jpg"
VIDEO_FRAME_RATE = 29.97
VIDEO_OUTPUT_PATHNAME = "z_output.mp4"

ELEMENTS_VIDEO = "aiko_services.media.video_io"
ELEMENTS_IMAGE = "aiko_services.media.image_io"

pipeline_definition = [
    {   "name": "ImageReadFile", "module": ELEMENTS_IMAGE,
        "successors": ["VideoWriteFile"],
        "parameters": {
            "image_pathname": IMAGE_INPUT_PATHNAME
        }
    },
    {   "name": "VideoWriteFile", "module": ELEMENTS_VIDEO,
        "parameters": {
            "video_frame_rate": VIDEO_FRAME_RATE,
            "video_pathname": VIDEO_OUTPUT_PATHNAME
        }
    }
]

_LOGGER = get_logger(__name__)
pipeline = Pipeline(pipeline_definition, FRAME_RATE)

_LOGGER.debug(f"pipeline: {pipeline}")
event.loop()  # aiko.process()
