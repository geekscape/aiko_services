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
from aiko_services.__tokens import CLI_TOKEN, OUT_TOKEN

__all__ = ["StreamElementState", "StreamElement", "StreamQueueElement"]


class StreamElementState(Enum):
    START = 0
    RUN = 1
    STOP = 2
    COMPLETE = 3


class StreamElement(abc.ABC):

    parameter_names = ()

    def __init__(
        self,
        name,
        parameters,
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
        self.handler = self._stream_start_handler
        self.logger = get_logger(self.name)
        self.stream_state = StreamElementState.START

        # Dynamically setup attributes
        for parameter_name, val in parameters.items():
            if parameter_name.startswith(OUT_TOKEN):
                parameter_name = parameter_name[len(OUT_TOKEN) :]

                if (self.parameter_names) and (
                    parameter_name not in self.parameter_names
                ):
                    raise ValueError(
                        f"Unexpected parameter_name in {self.__class__.__name__} StreamElement declaration are not accounted for. Got: '{parameter_name}' expected: '{self.parameter_names}'"
                    )

                if isinstance(val, list):
                    # If both element and output_key are defined
                    element_name = val[0]
                    output_name = val[1]
                elif isinstance(val, str):
                    # If only output_key is defined assume predecessor

                    # ToDo make sure only 1 predecessor exists for this use
                    element_name = self.predecessor
                    output_name = val

                setattr(
                    StreamElement,
                    parameter_name,
                    property(
                        lambda StreamElement: self.get_element_from_swag(
                            element_name,
                            output_name,
                        )
                    ),
                )
            else:
                setattr(
                    StreamElement,
                    parameter_name,
                    val,
                )

    def get_element_from_swag(self, element_name, output_name):
        return self.swag[element_name][output_name]

    def get_stream_state(self):
        return self.stream_state

    def update_stream_state(self, stream_stop):
        if not stream_stop:
            if self.stream_state is StreamElementState.START:
                self.handler = self._stream_frame_handler
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
                self.handler = self._stream_stop_handler
                self.stream_state = StreamElementState.STOP

    def stream_start_handler(self, stream_id, frame_id, swag=None) -> Tuple[bool, Any]:
        return True, None

    def stream_frame_handler(self, stream_id, frame_id, swag=None) -> Tuple[bool, Any]:
        return True, None

    def stream_stop_handler(self, stream_id, frame_id, swag=None) -> Tuple[bool, Any]:
        return True, None

    def _stream_start_handler(self, stream_id, frame_id, swag):
        self.swag = swag
        self.logger.debug(f"stream_start_handler(): stream_id: {stream_id}")
        return self.stream_start_handler(stream_id, frame_id, swag=swag)

    def _stream_frame_handler(self, stream_id, frame_id, swag):
        self.swag = swag
        self.logger.debug(f"stream_frame_handler(): stream_id: {stream_id}")
        return self.stream_frame_handler(stream_id, frame_id, swag=swag)

    def _stream_stop_handler(self, stream_id, frame_id, swag):
        self.swag = swag
        self.logger.debug(f"stream_stop_handler(): stream_id: {stream_id}")
        return self.stream_stop_handler(stream_id, frame_id, swag=swag)


class StreamQueueElement(StreamElement):
    def __init__(self, name, parameters, predecessors, pipeline_state_machine):
        super().__init__(name, parameters, predecessors, pipeline_state_machine)
