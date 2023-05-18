from typing import Tuple

from aiko_services import PipelineElement

class PE_0(PipelineElement):
    def __init__(self,
        implementations, name, protocol, tags, transport, definition):

        protocol = "pe_0:0"  # data_source:0
        implementations["PipelineElement"].__init__(self,
            implementations, name, protocol, tags, transport, definition)

    def process_frame(self, context, value_0) -> Tuple[bool, dict]:
        print(f"PE_0: context: {context}, value_0: {value_0}")
        return True, {"value_1": int(value_0) + 1}

class PE_1(PipelineElement):
    def __init__(self,
        implementations, name, protocol, tags, transport, definition):

        protocol = "pe_1:0"
        implementations["PipelineElement"].__init__(self,
            implementations, name, protocol, tags, transport, definition)

    def process_frame(self, context, value_1) -> Tuple[bool, dict]:
        print(f"PE_1: context: {context}, value_1: {value_1}")
        return True, {"value_2": value_1 + 1}

