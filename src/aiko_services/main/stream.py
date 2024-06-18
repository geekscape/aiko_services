# Definition(s)
# ~~~~~~~~~~~~~
# swag: One's personal bundle of belongings (Australian lingo)
# SWAG: Stuff We All Get
# SWAG: https://en.wikipedia.org/wiki/Scientific_wild-ass_guess :)
#
# To Do
# ~~~~~
# - Refactor from "pipeline.py", extract Stream concepts including Parameters
#   - Review "../archive/main/stream_2020.py"

from enum import Enum

__all__ = ["StreamEventDescription", "StreamEvent", "StreamState"]

class StreamEvent(Enum):
    ERROR = -1
    OKAY = 0
    STOP = 1

StreamEventDescription = {
    StreamEvent.ERROR: "Error",
    StreamEvent.OKAY: "Okay",
    StreamEvent.STOP: "Stop"
}

class StreamState(Enum):
    START = 0
    RUN = 1
    STOP = 2
    COMPLETE = 3
