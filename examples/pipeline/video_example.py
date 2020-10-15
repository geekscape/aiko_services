#!/usr/bin/env python3
#
# Usage
# ~~~~~
# LOG_LEVEL=DEBUG ./video_example.py
#
# To Do
# ~~~~~
# - Add CLI arguments !
# - Put try...except around "import opencv" to provide simple error message
# - Split into video_opencv.py, video_scikit.py, video_gstreamer.py, etc
# - Ensure video_opencv.py uses asyncio and doesn't block !

import aiko_services.event as event
# import aiko_services.framework as aiko
from aiko_services.pipeline import Pipeline
from aiko_services.utilities import get_logger

# FRAME_RATE = 0   # Process flat-out without delay
FRAME_RATE = 0.05  # 20 FPS
VIDEO_INPUT_PATHNAME = "astra.mp4"
WINDOW_LOCATION = (50, 50)
WINDOW_TITLE = "Astra"

# TODO [Josh]: Import from module.path syntax
ELEMENTS_IMAGE = "../../aiko_services/media/image_io.py"
ELEMENTS_VIDEO = "../../aiko_services/media/video_io.py"

pipeline_definition = [
    {   "name": "VideoReadFile", "module": ELEMENTS_VIDEO,
        "successors": ["ImageAnnotate1", "ImageAnnotate2"],
        "parameters": {
            "video_pathname": VIDEO_INPUT_PATHNAME
        }
    },
    {   "name": "ImageAnnotate1", "module": ELEMENTS_IMAGE,
        "successors": ["ImageOverlay"]
    },
    {   "name": "ImageAnnotate2", "module": ELEMENTS_IMAGE,
        "successors": ["ImageOverlay"]
    },
    {   "name": "ImageOverlay", "module": ELEMENTS_IMAGE,
        "successors": ["VideoShow"]
    },
    {   "name": "VideoShow", "module": ELEMENTS_VIDEO,
        "parameters": {
            "window_location": WINDOW_LOCATION,
            "window_title": WINDOW_TITLE
        }
    }
]

_LOGGER = get_logger(__name__)
pipeline = Pipeline(pipeline_definition, FRAME_RATE)

def timer_test():
    _LOGGER.debug("Timer test")
# event.add_timer_handler(timer_test, 0.1)

_LOGGER.debug(f"pipeline: {pipeline}")
event.loop()  # aiko.process()
