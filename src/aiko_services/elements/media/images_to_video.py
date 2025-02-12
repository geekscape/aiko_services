#!/usr/bin/env python3
#
# Usage
# ~~~~~
# LOG_LEVEL=DEBUG ./images_to_video.py

import aiko_services as aiko

FRAME_RATE = 0   # Process flat-out without delay
IMAGE_INPUT_PATHNAME = "z_input/image_{:06d}.jpg"
VIDEO_FRAME_RATE = 29.97
VIDEO_OUTPUT_PATHNAME = "z_output.mp4"

ELEMENTS_VIDEO = "aiko_services.elements.video_io"
ELEMENTS_IMAGE = "aiko_services.elements.image_io"

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

# if __name__ == "__main__":
#   Pipeline_2020(pipeline_definition, FRAME_RATE).run()
