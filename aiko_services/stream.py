# To Do
# ~~~~~
# - None, yet !
#
# Definition(s)
# ~~~~~~~~~~~~~
# swag: One's personal bundle of belongings (Australian lingo)
# SWAG: Stuff We All Get
# SWAG: Scientific Wild Arse Guess :)

import abc
from enum import Enum

from aiko_services.utilities import get_logger

__all__ = ["StreamElement", "StreamElementState"]

class StreamElementState(Enum):
    START = 0
    PROCESS = 1
    STOP = 2
    COMPLETE = 3

class StreamElement(abc.ABC):
    def __init__(self, name, predecessors):
        self.name = name
        self.predecessors = predecessors
        if predecessors:
            self.predecessor = predecessors[0]
        self.frame_id = 0
        self.handler = self.stream_start_handler
        self.logger = get_logger(self.name)
        self.state = StreamElementState.START

    def update_state(self, stream_processing):
        if stream_processing:
            if self.state == StreamElementState.START:
                self.handler = self.stream_frame_handler
                self.state = StreamElementState.PROCESS
            else:
                self.frame_id += 1
        else:
            if self.state == StreamElementState.STOP:
                self.handler = None
                self.state = StreamElementState.COMPLETE
            else:
                self.handler = self.stream_stop_handler
                self.state = StreamElementState.STOP

    def stream_start_handler(self, swag):
        self.logger.debug("stream_start_handler()")
        return True, None

    def stream_frame_handler(self, swag):
        self.logger.debug(f"stream_frame_handler(): frame_id: {self.frame_id}")
        return True, None

    def stream_stop_handler(self, swag):
        self.logger.debug("stream_stop()")
        return True, None
