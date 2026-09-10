# Usage
# ~~~~~
# - aiko_pipeline create pipelines/factorial_pipeline.json -ll debug_all  \
#                                                          -fd "()"
#
# - CaptureLimit, from src/aiko_services/elements/media ...
#   aiko_pipeline create pipelines/synthetic_pipeline_0.json -s 1  \
#     -p CaptureLimit.frame_count 45
#   aiko_pipeline create pipelines/synthetic_pipeline_1.json -s 1  \
#     -p CaptureLimit.duration 10m
#
# To Do
# ~~~~~
# - "PipelineElementLoop": Log debug for "define", "condition", "expression"
# - CaptureLimit: a timer so the "duration" bound fires between Frames

import re
import time
from typing import Tuple

import aiko_services as aiko
from aiko_services.elements.utilities import (
    all_outputs, evaluate_condition, evaluate_define
)
from aiko_services.main.utilities import parse

__all__ = ["CaptureLimit", "Loop"]

# --------------------------------------------------------------------------- #

class Loop(aiko.PipelineElementLoop):
    def __init__(self, context):
        context.set_protocol("loop:0")
        context.call_init(self, "PipelineElement", context)

    def process_frame(self, stream) -> Tuple[aiko.StreamEvent, dict]:
        self.logger.debug(f"{self.my_id()}")
        swag = stream.frames[stream.frame_id].swag

        if stream.variables.get("loop_boundary", None) is None:
            boundary, _ = self.get_parameter("boundary", "")
            stream.variables["loop_boundary"] = boundary

            expression, found = self.get_parameter("define")
            if found:
                expression = parse(expression, car_cdr=False)
                evaluate_define(expression, swag)

        condition, found = self.get_parameter("condition")
        if not found:
            diagnostic = 'Must provide a "condition" parameter'
            return aiko.StreamEvent.ERROR, {"diagnostic": diagnostic}

        condition = parse(condition, car_cdr=False)
        condition = evaluate_condition(condition, swag)
        if condition:
            expression, found = self.get_parameter("expression")
            if found:
                expression = parse(expression, car_cdr=False)
                evaluate_define(expression, swag)
            event = aiko.StreamEvent.OKAY
        else:
            self.logger.debug(f"End")
            event = aiko.StreamEvent.LOOP_END

        return event, {}

# --------------------------------------------------------------------------- #
# CaptureLimit: pass-through gate that stops the Stream when a bound is
# reached, whichever fires first ...
#
# - frame_count: number of Frames
# - duration:    wall-clock time since its first Frame: seconds, or a string
#                with a unit suffix "s", "m" or "h", e.g "10m"
# - run_time:    media time, count / "frame_rate" (the Pipeline-level
#                frame_rate parameter that VideoWriteFile also uses), for
#                sources that are not real-time, e.g unpaced or file reads
# - condition:   S-expression list in Loop style, evaluated over the Frame
#                swag plus "frame_id", "count", "elapsed" and "run_time":
#                the Stream continues while every expression is true,
#                e.g "((elapsed<600))".  No spaces inside an expression
#
# When no bound is given, the default is a duration of 10 seconds
#
# CaptureLimit is medium-neutral: declare "input": [] and "output": [] and
# the Frame swag is untouched, so the downstream PipelineElements still get
# their declared inputs (images, texts, ...).  Declared outputs, if any, are
# forwarded unchanged with all_outputs()
#
# - before the bound:  StreamEvent.OKAY, the Frame continues
# - the bounding Frame: StreamEvent.STOP, the Frame continues.  STOP does not
#                      skip the remaining PipelineElements of the current
#                      Frame (pipeline.py element loop only breaks on
#                      DROP_FRAME / ERROR), so the bounding Frame is still
#                      written, and a graceful destroy_stream() is posted
# - later Frames:      queued in-flight Frames are still processed until
#                      destroy_stream() lands, because a downstream OKAY
#                      resets the Stream state to RUN (stream.py set_state()).
#                      StreamEvent.DROP_FRAME skips the remaining
#                      PipelineElements of those Frames, so nothing more is
#                      written.  DROP_FRAME can not be used for the bounding
#                      Frame, because it never posts destroy_stream().  And
#                      the outputs can not be blanked, because a missing
#                      declared input is a fatal Pipeline error
#
# The time bounds only tick when Frames arrive: a single create_frame()
# source must use "frame_count".  Place CaptureLimit BEFORE any writer

_DEFAULT_DURATION = 10.0  # seconds, when no bound is given
_SECONDS_PER_UNIT = {"": 1.0, "s": 1.0, "m": 60.0, "h": 3600.0}

def _parse_seconds(value):
    """10, "10", "10s", "10m", "0.5h" --> seconds (float).  Raises ValueError"""

    if isinstance(value, (int, float)):
        return float(value)
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*([smh]?)\s*", str(value))
    if not match:
        raise ValueError(
            f'time "{value}" must be seconds or a number with suffix s, m or h')
    return float(match.group(1)) * _SECONDS_PER_UNIT[match.group(2)]

class CaptureLimit(aiko.PipelineElement):
    def __init__(self, context):
        context.set_protocol("capture_limit:0")
        context.call_init(self, "PipelineElement", context)

    def process_frame(self, stream, **kwargs) -> Tuple[aiko.StreamEvent, dict]:
        frame_count, found_count = self.get_parameter("frame_count", None)
        duration, found_duration = self.get_parameter("duration", None)
        run_time, found_run_time = self.get_parameter("run_time", None)
        condition, found_condition = self.get_parameter("condition", None)
        if not (found_count or found_duration or found_run_time
                or found_condition):
            duration, found_duration = _DEFAULT_DURATION, True

        variables = stream.variables
        now = time.monotonic()
        count = variables.get("capture_limit_count", 0) + 1
        variables["capture_limit_count"] = count
        start = variables.setdefault("capture_limit_start", now)
        elapsed = now - start

        run_time_now = None
        if found_run_time or found_condition:
            frame_rate, found_frame_rate = self.get_parameter("frame_rate")
            if found_frame_rate:
                run_time_now = count / float(frame_rate)
            elif found_run_time:
                diagnostic = 'CaptureLimit "run_time" needs "frame_rate"'
                return aiko.StreamEvent.ERROR, {"diagnostic": diagnostic}

        try:  # parameters may arrive as strings: coerce and validate
            reason = None
            if found_count and count >= int(frame_count):
                reason = f"frame limit {int(frame_count)} reached"
            elif found_duration and elapsed >= _parse_seconds(duration):
                reason = f"time limit {_parse_seconds(duration):g} s "  \
                         f"reached after {count} frames"
            elif found_run_time and run_time_now >= _parse_seconds(run_time):
                reason = f"run time limit {_parse_seconds(run_time):g} s "  \
                         f"reached after {count} frames"
            elif found_condition:
                arguments = dict(stream.frames[stream.frame_id].swag)
                arguments.update({"frame_id": stream.frame_id,
                    "count": count, "elapsed": elapsed,
                    "run_time": run_time_now})
                expressions = parse(condition, car_cdr=False)
                if not evaluate_condition(expressions, arguments):
                    reason = f"condition {condition} false after "  \
                             f"{count} frames"
        except (TypeError, ValueError) as error:
            diagnostic = f"CaptureLimit parameter error: {error}"
            return aiko.StreamEvent.ERROR, {"diagnostic": diagnostic}

        outputs = all_outputs(self, stream)
        if not reason:
            return aiko.StreamEvent.OKAY, outputs

        diagnostic = f"CaptureLimit: {reason}"
        if not variables.get("capture_limit_stopped"):
            variables["capture_limit_stopped"] = True  # bounding Frame passes
            self.logger.info(f"{self.my_id()}: {diagnostic}")
            outputs["diagnostic"] = diagnostic
            return aiko.StreamEvent.STOP, outputs
        return aiko.StreamEvent.DROP_FRAME, {"diagnostic": diagnostic}

# --------------------------------------------------------------------------- #
