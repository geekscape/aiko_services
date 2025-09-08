import tempfile
import threading
from typing import Tuple

import aiko_services as aiko


PIPELINE_DEFINITION = """{
  "version": 0, "name": "p_test", "runtime": "python",
  "graph": ["(FrameGeneratorException)"],
  "elements": [
    { "name":   "FrameGeneratorException", "input":  [], "output": [],
      "deploy": {
        "local": { "module": "aiko_services.tests.unit.test_stream_lock_release" }
      }
    }
  ]
}"""


class FrameGeneratorException(aiko.PipelineElement):
    def __init__(self, context):
        context.set_protocol("frame_generator_exception:0")
        context.get_implementation("PipelineElement").__init__(self, context)
        self.frame_count = 0

    def start_stream(self, stream, stream_id):
        """Start stream with a frame generator that will throw an exception"""
        # Use create_frames to start the problematic _create_frames_generator thread
        test_result = self.get_parameter("test_result")[0]
        test_result["stream_lock"] = stream.lock
        self.create_frames(stream, self.failing_frame_generator, rate=10.0)
        return aiko.StreamEvent.OKAY, {}

    def failing_frame_generator(self, stream, frame_id):
        """Frame generator that throws an exception after a few frames"""
        self.frame_count += 1

        if self.frame_count <= 2:
            # Generate a couple of successful frames first
            return aiko.StreamEvent.OKAY, {"frame": self.frame_count}
        else:
            # Now throw an exception that will leave the lock unreleased
            raise RuntimeError("Simulated frame generator exception - this should cause unreleased lock!")

    def process_frame(self, stream, **kwargs) -> Tuple[aiko.StreamEvent, dict]:
        return aiko.StreamEvent.OKAY, {}

    def stop_stream(self, stream, stream_id):
        return aiko.StreamEvent.OKAY, {}


def test_create_frames_generator_lock_not_released_on_exception():
    """Test that the lock is released when _create_frames_generator encounters exception"""

    test_result = {"pipeline": None, "stream_lock": None}

    def run_pipeline():
        with tempfile.NamedTemporaryFile(delete=True, mode="w") as file:
            file.write(PIPELINE_DEFINITION)
            file.flush()
            pipeline_definition =  \
                aiko.PipelineImpl.parse_pipeline_definition(file.name)
            pipeline = aiko.PipelineImpl.create_pipeline(
                None, pipeline_definition, name=None, graph_path=None,
                stream_id=0, parameters={"test_result": test_result},
                frame_id=0, frame_data=None,
                grace_time=None)
            test_result["pipeline"] = pipeline
            pipeline.run(mqtt_connection_required=False)

    pipeline_thread = threading.Thread(target=run_pipeline, daemon=True)
    pipeline_thread.start()
    pipeline_thread.join(timeout=5.0)

    assert test_result["stream_lock"].in_use() is None, "Lock should be released after exception in frame generator"

    print("Test completed - Lock was released")
