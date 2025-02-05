# Usage
# ~~~~~
# pytest [-s] unit/test_stream_event.py
# pytest [-s] unit/test_stream_event.py::test_actor_args
#
# To Do
# ~~~~~
# - Improve Aiko Services Process exit
# - Test StreamEvent.OKAY, StreamEvent.STOP, StreamEvent.ERROR for ...
#   - create_stream, _create_frame_generator, process_frame, destroy_stream

import tempfile
from typing import Tuple

import aiko_services as aiko

FRAME_DATA = "()"
GRACE_TIME = 60
PARAMETERS = {}

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

def run_pipeline(pipeline_definition_json):
    file = None
    with tempfile.NamedTemporaryFile(delete=True, mode='w') as file:
        file.write(pipeline_definition_json)
        file.flush()

        pipeline_definition =  \
            aiko.PipelineImpl.parse_pipeline_definition(file.name)

        pipeline = aiko.PipelineImpl.create_pipeline(
            file.name, pipeline_definition, name=None, graph_path=None,
            stream_id=None, parameters=PARAMETERS,
            frame_id=0, frame_data=FRAME_DATA,
            grace_time=GRACE_TIME, queue_response=None)

        pipeline.run(mqtt_connection_required=False)

def test_stream_event():
    run_pipeline(PIPELINE_DEFINITION)
