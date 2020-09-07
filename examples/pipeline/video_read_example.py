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

VIDEO_SOURCE = "../../aiko_services/video.py"

pipeline_definition = [
    {   "name": "VideoReadFile", "source": VIDEO_SOURCE,
        "successors": ["ImageAnnotate1", "ImageAnnotate2"],
        "parameters": {
            "stream_id": "stream_0"
        }
    },
    {   "name": "ImageAnnotate1", "source": VIDEO_SOURCE,
        "successors": ["ImageOverlay"]
    },
    {   "name": "ImageAnnotate2", "source": VIDEO_SOURCE,
        "successors": ["ImageOverlay"]
    },
    {   "name": "ImageOverlay", "source": VIDEO_SOURCE,
        "successors": ["ImageShow"]
    },
    {   "name": "ImageShow", "source": VIDEO_SOURCE,
        "successors": None
    }
]

def timer_test():
    _LOGGER.debug("Timer test")
# event.add_timer_handler(timer_test, 0.1)

pipeline = Pipeline(pipeline_definition, 0.05)
_LOGGER.debug(f"pipeline: {pipeline}")
event.loop()  # aiko.process()
