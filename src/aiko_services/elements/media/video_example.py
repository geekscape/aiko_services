#!/usr/bin/env python3
#
# Usage
# ~~~~~
# LOG_LEVEL=DEBUG ./video_example.py
#
# To Do
# ~~~~~
# - timer_test() handler "alternate" state change, i.e implement state_action ?
# - Turn into an Aiko Service
# - CLI argument: --pause: Display first frame and pause
# - Interface: frame_rate(), run(), pause(), step(+/- frame_cout)
# - Video overlay: frame_id, statistics, etc
#
# - Put try...except around "import opencv" to provide simple error message
# - Split into video_opencv.py, video_scikit.py, video_gstreamer.py, etc
# - Ensure video_opencv.py uses asyncio and doesn't block !

import aiko_services as aiko

# FRAME_RATE = 0   # Process flat-out without delay
FRAME_RATE = 0.05  # 20 FPS

# VIDEO_INPUT_PATHNAME = "astra.mp4"
VIDEO_INPUT_PATHNAME = "astra_brief.mp4"
# VIDEO_INPUT_PATHNAME = "astra_short.mp4"

VIDEO_FRAME_RATE = 29.97
VIDEO_OUTPUT_PATHNAME = "z_output.mp4"
WINDOW_LOCATION = (50, 50)
WINDOW_TITLE = "Astra"

ELEMENTS_IMAGE = "aiko_services.elements.image_io"
ELEMENTS_VIDEO = "aiko_services.elements.video_io"

class StateMachineModel(object):
    states = [
        "start",
        "alternate"
    ]

    transitions = [
        {"source": "start", "trigger": "alternate", "dest": "alternate"}
    ]

pipeline_definition = [
    {   "name": "VideoReadFile", "module": ELEMENTS_VIDEO,
        "parameters": {
#           "state_action": (5, "alternate"),
            "video_pathname": VIDEO_INPUT_PATHNAME
        },
        "successors": {
                "default": ["ImageAnnotate1"],
                "alternate": ["ImageAnnotate2"]
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
        },
        "successors": ["ImageResize"]
    },
    {   "name": "ImageResize", "module": ELEMENTS_IMAGE,
        "parameters": {
            "new_width": 640,
            "new_height": 360
        },
        "successors": ["VideoWriteFile"]
    },
    {   "name": "VideoWriteFile", "module": ELEMENTS_VIDEO,
        "parameters": {
            "video_frame_rate": VIDEO_FRAME_RATE,
            "video_pathname": VIDEO_OUTPUT_PATHNAME
        }
    }
]

def timer_test():
    aiko.logger(__name__).info("Timer test")

# if __name__ == "__main__":
#   event.add_timer_handler(timer_test, 0.1)
#   state_machine = StateMachine(StateMachineModel())
#   Pipeline_2020(
#       pipeline_definition, FRAME_RATE, state_machine=state_machine).run()
