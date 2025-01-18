# Usage
# ~~~~~
# grep -A8 '"graph"' ../robot_pipeline.json  # Show PipelineDefinition Graph
# grep   '{ "name"'  ../robot_pipeline.json  # Show PipelineElements list  }
#
# (cd ../virtual; ./world.py -gp World_ZMQ -frp 1)
# aiko_pipeline create ../../../elements/media/webcam_zmq_pipeline_0.json  \
#       -s 1 -p resolution 640x480
#
# aiko_pipeline create ../robot_pipeline.json -s 1 gt 3600 -ll warning
#
# To Do
# ~~~~~
# - Console (keyboard) input and output ... Aiko Dashboard plug-in ?
#   - Change Pipeline / PipelineElements debug level or set any parameter
#   - Select robot: None, One or All, e.g "/robot name" or "/r all"
#     - Prompt shows selected robot(s), i.e use "stream.variables[]"
#   - Emergency stop and robot commands (literal and direct)
#   - Show text response ... speech to human and commands to robot
#   - Subscribe to MQTT topic(s)
#
# - Provide Microphone     --> Speech-To-Text [push-to-talk]
# - Provide Text-To-Speech --> Speaker        [mute]

from typing import Tuple

import aiko_services as aiko

__all__ = []

# --------------------------------------------------------------------------- #
