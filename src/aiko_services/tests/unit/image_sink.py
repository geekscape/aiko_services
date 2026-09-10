# ImageSink: records the Frames that reach the end of a test Pipeline and
# stops the test when its Stream is destroyed.  Not a test module itself
#
# The shared state lives here, not in the test module: pytest imports
# "test_*.py" as "unit.test_*", while a PipelineDefinition deploys
# "aiko_services.tests.unit.test_*", which is a second module object
#
# The Aiko Services event loop and its mailboxes are one per process, and
# pytest runs every test in that process.  A frame generator of an earlier
# test can still post Frames, so each ImageSink keeps the "run_id" of its
# own test run and ignores every other run

from typing import Tuple

import aiko_services as aiko

__all__ = ["ImageSink", "RESULTS", "do_results_initialize"]

RESULTS = {}
_run_id = 0

def do_results_initialize():
    global _run_id
    _run_id += 1
    RESULTS.clear()
    RESULTS.update({"run_id": _run_id, "frame_ids": [], "shapes": [],
                    "stopped": False, "watchdog": False})
    return RESULTS

do_results_initialize()

class ImageSink(aiko.PipelineElement):
    def __init__(self, context):
        context.set_protocol("image_sink:0")
        context.call_init(self, "PipelineElement", context)
        self.run_id = RESULTS["run_id"]
        self.watchdog_armed = False

    def start_stream(self, stream, stream_id):
        watchdog_time, _ = self.get_parameter("watchdog_time", 5.0)
        aiko.add_timer_handler(self._watchdog_handler, float(watchdog_time))
        self.watchdog_armed = True
        return aiko.StreamEvent.OKAY, {}

    def process_frame(self, stream, images) -> Tuple[aiko.StreamEvent, dict]:
        if self.run_id == RESULTS["run_id"]:
            RESULTS["frame_ids"].append(stream.frame_id)
            RESULTS["shapes"].append(tuple(images[0].shape))
        return aiko.StreamEvent.OKAY, {}

    def stop_stream(self, stream, stream_id):  # graceful destroy_stream()
        if self.run_id == RESULTS["run_id"]:
            RESULTS["stopped"] = True
            self._stop_test()
        return aiko.StreamEvent.OKAY, {}

    def _watchdog_handler(self):
        if self.run_id == RESULTS["run_id"]:
            RESULTS["watchdog"] = True
            self._stop_test()

    def _stop_test(self):
        if self.watchdog_armed:
            aiko.remove_timer_handler(self._watchdog_handler)
            self.watchdog_armed = False
        aiko.process.terminate()  # TODO: Improve Aiko Services Process exit
