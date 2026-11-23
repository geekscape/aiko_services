# Test PipelineElements for test_store_forward_text.py
#
# TextFrames emits "frame_count" frames of CSV-like text with three named
# fields, then stops the Stream.  TextSink records every frame it receives
# and stops the test (aiko.process.terminate()) after "expected" frames,
# when its Stream stops, or when its watchdog fires.
#
# To Do
# ~~~~~
# - None, yet !

from typing import Tuple

import aiko_services as aiko

__all__ = ["RESULTS", "TextFrames", "TextSink", "do_results_initialize",
           "frame_text"]

RESULTS = {}
_run_id = 0

def do_results_initialize():
    global _run_id
    _run_id += 1
    RESULTS.clear()
    RESULTS.update({"run_id": _run_id, "frames": [], "stopped": False,
                    "watchdog": False})
    return RESULTS

do_results_initialize()

def frame_text(index):
    """Text for frame "index": two comma-separated rows, CRLF line endings."""

    return (f"2024-09-01T0{index}:00:00Z,{index},20.5\r\n"
            f"2024-09-01T0{index}:30:00Z,{index},21.0\r\n")

class TextFrames(aiko.PipelineElement):
    def __init__(self, context):
        context.set_protocol("text_frames:0")
        context.call_init(self, "PipelineElement", context)

    def start_stream(self, stream, stream_id):
        stream.variables["text_frames_index"] = 0
        self.create_frames(stream, self._frame_generator, rate=50.0)
        return aiko.StreamEvent.OKAY, {}

    def _frame_generator(self, stream, frame_id):
        frame_count, _ = self.get_parameter("frame_count", 3)
        index = stream.variables["text_frames_index"]
        if index >= int(frame_count):
            return aiko.StreamEvent.STOP, {"diagnostic": "frames done"}
        stream.variables["text_frames_index"] = index + 1
        return aiko.StreamEvent.OKAY, {"text": frame_text(index),
            "group": "group A", "location": "room 1",
            "sensor": "thermometer"}

    def process_frame(self, stream, text, group, location,
                      sensor) -> Tuple[aiko.StreamEvent, dict]:
        return aiko.StreamEvent.OKAY, {"text": text,
            "group": group,
            "location": location, "sensor": sensor}

class TextSink(aiko.PipelineElement):
    def __init__(self, context):
        context.set_protocol("text_sink:0")
        context.call_init(self, "PipelineElement", context)
        self.run_id = RESULTS["run_id"]
        self.watchdog_armed = False

    def start_stream(self, stream, stream_id):
        watchdog_time, _ = self.get_parameter("watchdog_time", 10.0)
        aiko.add_timer_handler(self._watchdog_handler, float(watchdog_time))
        self.watchdog_armed = True
        return aiko.StreamEvent.OKAY, {}

    def process_frame(self, stream, text, sensor)  \
            -> Tuple[aiko.StreamEvent, dict]:
        if self.run_id == RESULTS["run_id"]:
            RESULTS["frames"].append({"text": text, "sensor": sensor})
            expected, _ = self.get_parameter("expected", 0)
            if int(expected) and len(RESULTS["frames"]) >= int(expected):
                self._stop_test()
        return aiko.StreamEvent.OKAY, {}

    def stop_stream(self, stream, stream_id):
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
        aiko.process.terminate()
