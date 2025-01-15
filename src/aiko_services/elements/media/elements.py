# Usage
# ~~~~~
# grep -A14 graph example.json  # Show PipelineDefinition Graph
# grep '{ "name"' example.json  # Show PipelineElements list
#
# To Do
# ~~~~~
# - Improve "Mock" --> "Code" and/or "LISP" :)
#   - Parameter "code": "{output} = {input} + {increment}"

from typing import Tuple

import aiko_services as aiko

__all__ = ["Mock", "NoOp"]

# --------------------------------------------------------------------------- #

class Mock(aiko.PipelineElement):
    def __init__(self, context):
        context.set_protocol("mock:0")
        context.get_implementation("PipelineElement").__init__(self, context)

    def process_frame(self, stream) -> Tuple[aiko.StreamEvent, dict]:
        label, _ = self.get_parameter("label", default="")
        self.logger.info(f"{self.my_id()} {label}")
        return aiko.StreamEvent.OKAY, {}

# --------------------------------------------------------------------------- #

class NoOp(aiko.PipelineElement):
    def __init__(self, context):
        context.set_protocol("noop:0")
        context.get_implementation("PipelineElement").__init__(self, context)

    def process_frame(self, stream) -> Tuple[aiko.StreamEvent, dict]:
        return aiko.StreamEvent.OKAY, {}

# --------------------------------------------------------------------------- #
