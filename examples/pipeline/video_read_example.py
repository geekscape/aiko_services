#!/usr/bin/env python3
#
# Usage
# ~~~~~
# LOG_LEVEL=DEBUG ./video_read_example.py
#
# To Do
# ~~~~~
# - Add CLI arguments !

import aiko_services.event as event
# import aiko_services.framework as aiko
from aiko_services.pipeline import Pipeline
from aiko_services.utilities import get_logger

# FRAME_RATE = 0   # Process flat-out without delay
FRAME_RATE = 0.05  # 20 FPS
VIDEO_PATHNAME = "astra.mp4"
WINDOW_LOCATION = (50, 50)
WINDOW_TITLE = "Astra"

COMPONENT_SOURCE_VIDEO = "../../aiko_services/video.py"

pipeline_definition = [
    {   "name": "VideoReadFile", "source": COMPONENT_SOURCE_VIDEO,
        "successors": ["ImageAnnotate1", "ImageAnnotate2"],
        "parameters": {
            "video_pathname": VIDEO_PATHNAME
        }
    },
    {   "name": "ImageAnnotate1", "source": COMPONENT_SOURCE_VIDEO,
        "successors": ["ImageOverlay"]
    },
    {   "name": "ImageAnnotate2", "source": COMPONENT_SOURCE_VIDEO,
        "successors": ["ImageOverlay"]
    },
    {   "name": "ImageOverlay", "source": COMPONENT_SOURCE_VIDEO,
        "successors": ["ImageShow"]
    },
    {   "name": "ImageShow", "source": COMPONENT_SOURCE_VIDEO,
        "successors": None,
        "parameters": {
            "window_location": WINDOW_LOCATION,
            "window_title": WINDOW_TITLE
        }
    }
]

_LOGGER = get_logger(__name__)

def timer_test():
    _LOGGER.debug("Timer test")
# event.add_timer_handler(timer_test, 0.1)

pipeline = Pipeline(pipeline_definition, FRAME_RATE)
_LOGGER.debug(f"pipeline: {pipeline}")
event.loop()  # aiko.process()
