# Usage
# ~~~~~
# pytest [-s] unit/test_stream_event.py
# pytest [-s] unit/test_stream_event.py::test_stream_error
#
# test_stream_error()
# - PipelineElement.process_frame() returning StreamEvent.ERROR
#   causes Pipeline to "hang, due to Stream.lock contention.
#   See https://github.com/geekscape/aiko_services/pull/32
#
# To Do
# ~~~~~
# - Improve Aiko Services Process exit
# - Test StreamEvent.OKAY, StreamEvent.STOP, StreamEvent.ERROR for ...
#   - create_stream, _create_frame_generator, process_frame, destroy_stream

from typing import Tuple

import aiko_services as aiko
from aiko_services.tests.unit import do_create_pipeline

PIPELINE_DEFINITION = """{
  "version": 0, "name": "p_test", "runtime": "python",
  "graph": ["(StreamError)"],
  "elements": [
    { "name":   "StreamError", "input":  [], "output": [],
      "deploy": {
        "local": { "module": "aiko_services.tests.unit.test_stream_event" }
      }
    }
  ]
}
"""

class StreamError(aiko.PipelineElement):
    def __init__(self, context):
        context.set_protocol("stream_error:0")
        context.get_implementation("PipelineElement").__init__(self, context)

    def process_frame(self, stream) -> Tuple[aiko.StreamEvent, dict]:
        self.logger.info(f"process_frame(): {self.my_id()}")
        aiko.process.terminate()  # TODO: Improve Aiko Services Process exit
        diagnostic = "Testing StreamEvent.ERROR"
        return aiko.StreamEvent.ERROR, {"diagnostic": diagnostic}

def test_stream_error():
    do_create_pipeline(PIPELINE_DEFINITION)
