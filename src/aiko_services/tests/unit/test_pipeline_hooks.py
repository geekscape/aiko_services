import aiko_services as aiko
from aiko_services.main.pipeline import (
    _PIPELINE_HOOK_PROCESS_ELEMENT,
    _PIPELINE_HOOK_PROCESS_ELEMENT_POST,
    _PIPELINE_HOOK_PROCESS_FRAME,
    _PIPELINE_HOOK_PROCESS_FRAME_COMPLETE,
    _PIPELINE_HOOK_DESTROY_STREAM,
)
from aiko_services.main.stream import StreamEvent
from aiko_services.tests.unit import do_create_pipeline

PIPELINE_DEFINITION = """{
  "version": 0, "name": "p_test", "runtime": "python",
  "graph": ["(A)"],
  "elements": [
    { "name":   "A",
      "input":  [{ "name": "a", "type": "int" }],
      "output": [{ "name": "a", "type": "int" }],
      "deploy": {
        "local": { "module": "aiko_services.tests.unit.test_pipeline_hooks" }
      }
    }
  ]
}
"""

class A(aiko.PipelineElement):
    def __init__(self, context):
        context.call_init(self, "PipelineElement", context)

    def frame_generator(self, stream, frame_id):
        if frame_id == 0:
            return StreamEvent.OKAY, {"a": 1}
        else:
            return StreamEvent.STOP, {}

    def start_stream(self, stream, stream_id):
        self.create_frames(stream, frame_generator=self.frame_generator)
        return StreamEvent.OKAY, None

    def process_frame(self, stream, a):
        return StreamEvent.OKAY, {"a": a}

    def stop_stream(self, stream, stream_id):
        self.stop()
        return StreamEvent.OKAY, None


def test_pipeline_hooks():
    hooks_called = []

    def hook_process_frame(hook_name, component, logger, variables, options):
        hooks_called.append(hook_name)
        assert variables["frame_data_in"] == {"a": 1}

    def hook_process_element(hook_name, component, logger, variables, options):
        hooks_called.append(hook_name)
        assert variables["inputs"] == {"a": 1}

    def hook_process_element_post(hook_name, component, logger, variables, options):
        hooks_called.append(hook_name)
        assert variables["frame_data_out"] == {"a": 1}

    def hook_process_frame_complete(hook_name, component, logger, variables, options):
        hooks_called.append(hook_name)
        assert variables["frame_data_out"] == {"a": 1}

    def hook_destroy_stream(hook_name, component, logger, variables, options):
        hooks_called.append(hook_name)
        assert variables["diagnostic"] == None

    hooks = {
        _PIPELINE_HOOK_PROCESS_FRAME: hook_process_frame,
        _PIPELINE_HOOK_PROCESS_ELEMENT: hook_process_element,
        _PIPELINE_HOOK_PROCESS_ELEMENT_POST: hook_process_element_post,
        _PIPELINE_HOOK_PROCESS_FRAME_COMPLETE: hook_process_frame_complete,
        _PIPELINE_HOOK_DESTROY_STREAM: hook_destroy_stream,
    }
    do_create_pipeline(PIPELINE_DEFINITION, hooks=hooks, frame_data=None,
                       stream_id="0")
    assert hooks_called == list(hooks.keys())
