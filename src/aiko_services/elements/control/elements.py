# Usage
# ~~~~~
# - aiko_pipeline create pipelines/factorial_pipeline.json -ll debug_all  \
#                                                          -fd "()"
#
# To Do
# ~~~~~
# - "PipelineElementLoop": Log debug for "define", "condition", "expression"

from typing import Tuple

import aiko_services as aiko
from aiko_services.elements.utilities import evaluate_condition, evaluate_define
from aiko_services.main.utilities import parse

__all__ = ["Loop"]

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
