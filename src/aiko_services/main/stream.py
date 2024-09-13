# Definition(s)
# ~~~~~~~~~~~~~
# swag: One's personal bundle of belongings (Australian lingo)
# SWAG: Stuff We All Get
# SWAG: https://en.wikipedia.org/wiki/Scientific_wild-ass_guess :)
#
# Notes
# ~~~~~
# - Watch out for "stream.py:Frame" dataclass and
#   "dashboard.py" use of "asciimatics.widgets.Frame()" class
#
# To Do
# ~~~~~
# - Implement dataclass "Class Metrics" to replace "metrics" dictionary
#
# - Refactor from "pipeline.py", extract Stream concepts including Parameters
#   - Review "../archive/main/stream_2020.py"

from dataclasses import dataclass, field
import queue
from typing import Any, Dict

__all__ = [
    "DEFAULT_STREAM_ID", "FIRST_FRAME_ID", "Frame", "Stream",
    "StreamEvent", "StreamEventName", "StreamState", "StreamStateName"
]

DEFAULT_STREAM_ID = "*"  # string
FIRST_FRAME_ID = 0       # integer

class StreamEvent:
    ERROR =   -2  # Move to StreamState.ERROR
    STOP  =   -1  # Move to StreamState.STOP
    OKAY  =    0  # Stay calm and keep on running
    USER  = 1000  # User defined custom StreamEvents start from here

StreamEventName = {
    StreamEvent.ERROR: "Error",
    StreamEvent.OKAY:  "Okay",
    StreamEvent.STOP:  "Stop",
    StreamEvent.USER:  "User"
}

class StreamState:
    ERROR =   -2  # Don't generate new frames and ignore queued frames
    STOP  =   -1  # Don't generate new frames and process queued frames
    RUN   =    0  # Generate new frames and process queued frames
    USER  = 1000  # User defined custom StreamStates start from here

StreamStateName = {
    StreamState.ERROR: "Error",
    StreamState.STOP:  "Stop",
    StreamState.RUN:   "Run",
    StreamState.USER:  "User"
}

@dataclass
class Frame:  # effectively a continuation :)
    metrics: Dict[str, Any] = field(default_factory=dict)  # TODO: Dataclass
    paused_pe_name: str = None  # remote PipelineElement that has been called
    swag: Dict[str, Any] = field(default_factory=dict)  # PipelineElement data

@dataclass
class Stream:
    stream_id: str = DEFAULT_STREAM_ID
    frame_id: int = FIRST_FRAME_ID  # only updated by Pipeline thread
    frames: Dict[int, Frame] = field(default_factory=dict)
    parameters: Dict[str, Any] = field(default_factory=dict)
    queue_response: queue = None
    state: StreamState = StreamState.RUN
    topic_response: str = None
    variables: Dict[str, Any] = field(default_factory=dict)

# https://docs.python.org/3/library/dataclasses.html#dataclasses.asdict
    def as_dict(self):
    #   return {key: str(value) for key, value in asdict(self).items()}
        return {"stream_id": self.stream_id, "frame_id": self.frame_id}

# https://docs.python.org/3/library/dataclasses.html#dataclasses.replace
    def update(self, stream_dict):
    #   self = replace(self, **stream_dict)
        self.stream_id = stream_dict.get("stream_id", self.stream_id)
        self.frame_id = int(stream_dict.get("frame_id", self.frame_id))
        self.parameters = stream_dict.get("parameters", self.parameters)
        self.state = stream_dict.get("state", StreamState.RUN)
