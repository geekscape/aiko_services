# To Do
# ~~~~~
# - Replace "Terminate" PipelineElement with proper Pipeline terminate approach

import tempfile
from typing import Tuple

import aiko_services as aiko

FRAME_DATA = "()"
GRACE_TIME = 60
PARAMETERS = {}

all = ["do_compose_pipeline", "do_create_pipeline"]

class Terminate(aiko.PipelineElement):
    def __init__(self, context):
        context.set_protocol("terminate:0")
        context.call_init(self, "PipelineElement", context)

    def process_frame(self, stream) -> Tuple[aiko.StreamEvent, dict]:
        self.logger.info(f"{self.my_id()}")
        aiko.process.terminate()  # TODO: Improve Aiko Services Process exit
        return aiko.StreamEvent.OKAY, {}

# "stream_id" creates a Stream, which invokes PipelineElement.start_stream()
# and, for a DataSource, starts the frame_generator() thread.  This is the
# "aiko_pipeline create --stream_id" behavior.  Default: no Stream created
#
# "frame_data" is the single Frame that the Pipeline processes immediately.
# Use "frame_data=None" when a frame_generator() supplies all of the Frames

def do_compose_pipeline(pipeline_definition_json,
    stream_id=None, frame_data=None,
    parameters=PARAMETERS, grace_time=GRACE_TIME):

    file = None
    with tempfile.NamedTemporaryFile(delete=True, mode="w") as file:
        file.write(pipeline_definition_json)
        file.flush()

        pipeline_definition =  \
            aiko.PipelineImpl.parse_pipeline_definition(file.name)

        return aiko.PipelineImpl.create_pipeline(
            file.name, pipeline_definition, name=None, graph_path=None,
            stream_id=stream_id, parameters=parameters,
            frame_id=0, frame_data=frame_data,
            grace_time=grace_time, queue_response=None)

# do_create_pipeline() runs the Aiko Services Process event loop, which
# blocks until a PipelineElement invokes "aiko.process.terminate()"

def do_create_pipeline(pipeline_definition_json,
    stream_id=None, frame_data=FRAME_DATA,
    parameters=PARAMETERS, grace_time=GRACE_TIME):

    pipeline = do_compose_pipeline(pipeline_definition_json,
        stream_id=stream_id, frame_data=frame_data,
        parameters=parameters, grace_time=grace_time)

    pipeline.run(mqtt_connection_required=False)
    return pipeline
