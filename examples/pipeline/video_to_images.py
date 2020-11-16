#!/usr/bin/env python3
#
# Usage
# ~~~~~
# LOG_LEVEL=DEBUG ./video_to_images.py

from aiko_services.pipeline import Pipeline

FRAME_RATE = 0   # Process flat-out without delay
IMAGE_OUTPUT_PATHNAME = "z_output/image_{:06d}.jpg"
VIDEO_INPUT_PATHNAME = "astra_brief.mp4"

ELEMENTS_VIDEO = "aiko_services.elements.video_io"
ELEMENTS_IMAGE = "aiko_services.elements.image_io"

pipeline_definition = [
    {   "name": "VideoReadFile", "module": ELEMENTS_VIDEO,
        "successors": ["ImageOverlay"],
        "parameters": {
            "video_pathname": VIDEO_INPUT_PATHNAME
        }
    },
    {   "name": "ImageOverlay", "module": ELEMENTS_IMAGE,
        "successors": ["ImageWriteFile"],
        "parameters": {
        "colors": {
            "astra": (100, 0, 0),
            "bailey": (0, 100, 0),
            "ty": (0, 0, 100)
            },
        "text_color": "yellow"
        }
    },
    {   "name": "ImageWriteFile", "module": ELEMENTS_IMAGE,
        "parameters": {
            "image_pathname": IMAGE_OUTPUT_PATHNAME
        }
    }
]

if __name__ == "__main__":
    Pipeline(pipeline_definition, FRAME_RATE).run()
