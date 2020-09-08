#!/usr/bin/env python3
#
# Usage
# ~~~~~
# LOG_LEVEL=DEBUG ./test_pipeline.py
#
# To Do
# ~~~~~
# - None, yet !


import aiko_services.event as event
# import aiko_services.framework as aiko
from aiko_services.pipeline import Pipeline
from aiko_services.utilities import get_logger

_LOGGER = get_logger(__name__)

VIDEO_PATHNAME = "astra.mp4"
WINDOW_TITLE = "Astra"
WINDOW_LOCATION = (50, 50)

SOURCE_COMPONENT_VIDEO = "../../aiko_services/video.py"

pipeline_definition = [
    {   "name": "VideoReadFile", "source": SOURCE_COMPONENT_VIDEO,
        "successors": ["ImageAnnotate1", "ImageAnnotate2"],
        "parameters": {
            "video_pathname": VIDEO_PATHNAME
        }
    },
    {   "name": "ImageAnnotate1", "source": SOURCE_COMPONENT_VIDEO,
        "successors": ["ImageOverlay"]
    },
    {   "name": "ImageAnnotate2", "source": SOURCE_COMPONENT_VIDEO,
        "successors": ["ImageOverlay"]
    },
    {   "name": "ImageOverlay", "source": SOURCE_COMPONENT_VIDEO,
        "successors": ["ImageShow"]
    },
    {   "name": "ImageShow", "source": SOURCE_COMPONENT_VIDEO,
        "successors": None,
        "parameters": {
            "window_title": WINDOW_TITLE,
            "window_x": WINDOW_LOCATION[0],
            "window_y": WINDOW_LOCATION[1]
        }
    }
]

def timer_test():
    _LOGGER.debug("Timer test")
# event.add_timer_handler(timer_test, 0.1)

pipeline = Pipeline(pipeline_definition, 0.05)
_LOGGER.debug(f"pipeline: {pipeline}")
event.loop()  # aiko.process()
