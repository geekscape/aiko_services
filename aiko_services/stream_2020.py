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

from aiko_services import *
from aiko_services.utilities import *

__all__ = ["StreamElementState", "StreamElement", "StreamQueueElement"]

class StreamElementState(Enum):
    START = 0
    RUN = 1
    STOP = 2
    COMPLETE = 3

class StreamElement(abc.ABC):
    def __init__(self, name, parameters, predecessors, pipeline_state_machine):
        self.name = name
        self.parameters = parameters
        self.predecessors = predecessors
        if predecessors:
            self.predecessor = predecessors[0]
        self.pipeline_state_machine = pipeline_state_machine
        self.frame_count = 0
        self.handler = self.stream_start_handler
        self.logger = aiko.logger(self.name)
        self.stream_state = StreamElementState.START

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

    def stream_start_handler(self, stream_id, frame_id, swag):
        self.logger.debug(f"stream_start_handler(): stream_id: {stream_id}")
        return True, None

    def stream_frame_handler(self, stream_id, frame_id, swag):
        self.logger.debug(f"stream_frame_handler(): stream_id: {stream_id}, frame_id: {frame_id}")
        return True, None

    def stream_stop_handler(self, stream_id, frame_id, swag):
        self.logger.debug(f"stream_stop_handler(): stream_id: {stream_id}")
        return True, None

class StreamQueueElement(StreamElement):
    def __init__(self, name, parameters, predecessors, pipeline_state_machine):
        super().__init__(name, parameters, predecessors, pipeline_state_machine)
