# To Do
# ~~~~~
# - None, yet !
#
# Definition(s)
# ~~~~~~~~~~~~~
# swag: One's personal bundle of belongings (Australian lingo)
# SWAG: Stuff We All Get
# SWAG: https://en.wikipedia.org/wiki/Scientific_wild-ass_guess :)

import abc
from enum import Enum
from typing import Tuple, Any

from aiko_services.utilities import get_logger
from aiko_services.__tokens import CLI_TOKEN

__all__ = ["StreamElementState", "StreamElement", "StreamQueueElement"]


class StreamElementState(Enum):
    START = 0
    RUN = 1
    STOP = 2
    COMPLETE = 3


class StreamElement(abc.ABC):

    expected_parameters: Tuple[str]
    expected_inputs: Tuple[str]
    expected_outputs: Tuple[str]

    def __init__(
        self,
        name,
        parameters,
        input_map,
        outputs,
        predecessors,
        pipeline_state_machine,
    ):

        self.name = name
        self.parameters = parameters
        self.predecessors = predecessors
        if predecessors:
            self.predecessor = predecessors[0]
        self.pipeline_state_machine = pipeline_state_machine
        self.frame_count = 0
        self.handler = self.stream_start_handler
        self.logger = get_logger(self.name)
        self.stream_state = StreamElementState.START

        # ToDo Sanity Check
        self.input_map = input_map
        self.outputs = outputs

        for expected_parameter in self.expected_parameters:
            if isinstance(expected_parameter, str):
                parameter_name = expected_parameter
                val = parameters[parameter_name]
            else:
                parameter_name, default_val = expected_parameter
                if parameter_name in parameters:
                    val = parameters[parameter_name]
                else:
                    val = default_val
            setattr(
                self,
                parameter_name,
                val,
            )

    def get_stream_state(self):
        return self.stream_state

    def update_stream_state(self, stream_stop):
        if not stream_stop:
            if self.stream_state is StreamElementState.START:
                self.handler = self.stream_frame_handler
                self.stream_state = StreamElementState.RUN
            elif self.stream_state is StreamElementState.RUN:
                self.frame_count += 1
        else:
            if self.stream_state is StreamElementState.COMPLETE:
                pass
            elif self.stream_state is StreamElementState.STOP:
                self.handler = None
                self.stream_state = StreamElementState.COMPLETE
            else:
                self.handler = self.stream_stop_handler
                self.stream_state = StreamElementState.STOP

    def stream_start_handler(self, stream_id, frame_id, inputs):
        self.logger.debug(f"stream_start_handler(): stream_id: {stream_id}")
        return True, None

    def stream_frame_handler(self, stream_id, frame_id, inputs):
        self.logger.debug(f"stream_frame_handler(): stream_id: {stream_id}")
        return True, None

    def stream_stop_handler(self, stream_id, frame_id, inputs):
        self.logger.debug(f"stream_stop_handler(): stream_id: {stream_id}")
        return True, None


class StreamQueueElement(StreamElement):
    def __init__(self, name, parameters, predecessors, pipeline_state_machine):
        super().__init__(name, parameters, predecessors, pipeline_state_machine)
