# Usage
# ~~~~~
# pytest [-s] unit/test_stream_lock.py
# pytest [-s] unit/test_stream_lock.py::test_stream_lock
#
# test_stream_lock()
# - See https://github.com/geekscape/aiko_services/pull/42
#
# To Do
# ~~~~~
# - Improve Aiko Services Process exit
#
# - Test StreamEvent.OKAY, StreamEvent.STOP, StreamEvent.ERROR for ...
#   - create_stream, _create_frame_generator, process_frame, destroy_stream
#   - Consolidate any overlap with "test_stream_event.py" ?

import threading
import time
from typing import Tuple

import aiko_services as aiko
from aiko_services.tests.unit import do_create_pipeline

PIPELINE_DEFINITION = """{
  "version": 0, "name": "p_test", "runtime": "python",
  "graph": ["(StreamLock_0 StreamLock_1 StreamLock_2)"],
  "elements": [
    { "name":   "StreamLock_0", "input":  [], "output": [],
      "deploy": {
        "local": { "module": "aiko_services.tests.unit.test_stream_lock" }
      }
    },
    { "name":   "StreamLock_1", "input":  [], "output": [],
      "deploy": {
        "local": { "module": "aiko_services.tests.unit.test_stream_lock" }
      }
    },
    { "name":   "StreamLock_2", "input":  [], "output": [],
      "deploy": {
        "local": { "module": "aiko_services.tests.unit.test_stream_lock" }
      }
    }
  ]
}
"""
# TODO: Does this need to be a DataSource to replicate the original problem ?

class StreamLock_0(aiko.PipelineElement):
    def __init__(self, context):
        context.set_protocol("stream_lock:0")
        context.call_init(self, "PipelineElement", context)

    def start_stream(self, stream, stream_id):
        self.logger.info(f"{self.my_id()} start_stream()")
        return aiko.StreamEvent.OKAY, {}

    def process_frame(self, stream) -> Tuple[aiko.StreamEvent, dict]:
        self.logger.info(f"{self.my_id()} process_frame()")
        return aiko.StreamEvent.OKAY, {}

# NOTE: This causes deliberately causes a StreamEvent.ERROR
#       in either start_stream() or process_frame()

class StreamLock_1(aiko.PipelineElement):
    def __init__(self, context):
        context.set_protocol("stream_lock:0")
        context.call_init(self, "PipelineElement", context)

    def start_stream(self, stream, stream_id):
        self.logger.info(f"{self.my_id()} start_stream()")
        diagnostic = "Deliberate aiko.StreamEvent.ERROR"
        return aiko.StreamEvent.ERROR, {"diagnostic": diagnostic}
    #   return aiko.StreamEvent.OKAY, {}

    def process_frame(self, stream) -> Tuple[aiko.StreamEvent, dict]:
        self.logger.info(f"{self.my_id()} process_frame()")
        diagnostic = "Deliberate aiko.StreamEvent.ERROR"
        return aiko.StreamEvent.ERROR, {"diagnostic": diagnostic}
    #   return aiko.StreamEvent.OKAY, {}

# NOTE: This is here to show whether a subsequent PipelineElement is processed

class StreamLock_2(aiko.PipelineElement):
    def __init__(self, context):
        context.set_protocol("stream_lock:0")
        context.call_init(self, "PipelineElement", context)

    def start_stream(self, stream, stream_id):
        self.logger.info(f"{self.my_id()} start_stream()")
        return aiko.StreamEvent.OKAY, {}

    def process_frame(self, stream) -> Tuple[aiko.StreamEvent, dict]:
        self.logger.info(f"{self.my_id()} process_frame()")
        aiko.process.terminate()  # TODO: Improve Aiko Services Process exit
        return aiko.StreamEvent.OKAY, {}

# NOTE: This has nothing to do with the test-case, here to ensure process exit

def thread_hack():
    time.sleep(0.5)
#   print()
#   print(f"{'Name':<15} {'ID':<10} {'Alive':<7} {'Daemon'}")
#   print("-" * 45)
#   for t in threading.enumerate():
#       print(f"{t.name:<15} {t.ident!s:<10} {t.is_alive():<7} {t.daemon}")
    aiko.process.terminate()

def test_stream_lock():
    threading.Thread(target=thread_hack).start()
    do_create_pipeline(PIPELINE_DEFINITION)
