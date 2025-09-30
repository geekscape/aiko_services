# To Do
# ~~~~~
# - Replace "Terminate" PipelineElement with proper Pipeline terminate approach

import tempfile
from typing import Tuple

import aiko_services as aiko

FRAME_DATA = "()"
GRACE_TIME = 60
PARAMETERS = {}

all = ["do_create_pipeline"]

class Terminate(aiko.PipelineElement):
    def __init__(self, context):
        context.set_protocol("terminate:0")
        context.call_init(self, "PipelineElement", context)

    def process_frame(self, stream) -> Tuple[aiko.StreamEvent, dict]:
        self.logger.info(f"{self.my_id()}")
        aiko.process.terminate()  # TODO: Improve Aiko Services Process exit
        return aiko.StreamEvent.OKAY, {}

def do_create_pipeline(pipeline_definition_json, hooks=None,
                       frame_data=FRAME_DATA,
                       stream_id=None, parameters=None):
    file = None
    with tempfile.NamedTemporaryFile(delete=True, mode="w") as file:
        file.write(pipeline_definition_json)
        file.flush()

        pipeline_definition =  \
            aiko.PipelineImpl.parse_pipeline_definition(file.name)

        pipeline = aiko.PipelineImpl.create_pipeline(
            file.name, pipeline_definition, name=None, graph_path=None,
            stream_id=stream_id, parameters=parameters or PARAMETERS,
            frame_id=0, frame_data=frame_data,
            grace_time=GRACE_TIME, queue_response=None)

        if hooks is not None:
            for hook, hook_function in hooks.items():
                pipeline.add_hook_handler(hook, hook_function)

        pipeline.run(mqtt_connection_required=False)

        # Clean up global hooks
        if hooks is not None:
            for hook, hook_function in hooks.items():
                pipeline.remove_hook_handler(hook, hook_function)
