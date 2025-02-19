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
# - If required, Stream.remote_graph_path() used to determine remote Graph Path
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

from aiko_services.main.utilities import *

__all__ = [
    "DEFAULT_STREAM_ID", "FIRST_FRAME_ID", "Frame", "Stream",
    "StreamEvent", "StreamEventName", "StreamState", "StreamStateName"
]

DEFAULT_STREAM_ID = "*"  # string
FIRST_FRAME_ID = 0       # integer

class StreamEvent:
    ERROR      =   -2  # Move to StreamState.ERROR
    STOP       =   -1  # Move to StreamState.STOP
    OKAY       =    0  # Stay calm and keep on running
    NO_FRAME   =    1  # No frame to process and keep on running
    DROP_FRAME =    2  # No longer process this frame and keep on running
    USER       = 1024  # User defined custom StreamEvents start from here

StreamEventName = {
    StreamEvent.DROP_FRAME: "DropFrame",
    StreamEvent.ERROR:      "Error",
    StreamEvent.NO_FRAME:   "NoFrame",
    StreamEvent.OKAY:       "Okay",
    StreamEvent.STOP:       "Stop",
    StreamEvent.USER:       "User"
}

class StreamState:
    ERROR       =   -2  # Don't generate new frames and ignore queued frames
    STOP        =   -1  # Don't generate new frames and process queued frames
    RUN         =    0  # Generate new frames and process queued frames
    NO_FRAME    =    1  # No frame to process, then back to RUN state
    DROP_FRAME  =    2  # Stop processing current frame, then back to RUN state
    USER        = 1024  # User defined custom StreamStates start from here

StreamStateName = {
    StreamState.DROP_FRAME: "DropFrame",
    StreamState.ERROR:      "Error",
    StreamState.NO_FRAME:   "NoFrame",
    StreamState.STOP:       "Stop",
    StreamState.RUN:        "Run",
    StreamState.USER:       "User"
}

@dataclass
class Frame:  # effectively a continuation :)
    metrics: Dict[str, Any] = field(default_factory=dict)  # TODO: Dataclass
    paused_pe_name: str = None  # remote PipelineElement that has been called
### self.pipeline_graph.iterate_after(frame.paused_pe_name, frame.graph_path)
### graph_path: str = None  # Graph path (head_node_name)
    swag: Dict[str, Any] = field(default_factory=dict)  # PipelineElement data

@dataclass
class Stream:
    stream_id: str = DEFAULT_STREAM_ID
    frame_id: int = FIRST_FRAME_ID  # only updated by Pipeline thread
    frames: Dict[int, Frame] = field(default_factory=dict)
    graph_path: str = None  # Graph path (head_node_name), default: first path
    lock: Lock = field(init=False)
    parameters: Dict[str, Any] = field(default_factory=dict)
    queue_response: queue = None
    state: StreamState = StreamState.RUN
    topic_response: str = None
    variables: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        self.lock = Lock(f"{__name__}_{self.stream_id}")

    def set_state(self, state):
        if state == StreamState.ERROR and self.state > StreamState.ERROR:
            self.state = state
        if state == StreamState.STOP and self.state > StreamState.STOP:
            self.state = state
        else:
            self.state = state

# https://docs.python.org/3/library/dataclasses.html#dataclasses.asdict
    def as_dict(self):
    #   return {key: str(value) for key, value in asdict(self).items()}
        return {
            "stream_id": self.stream_id,
            "frame_id": self.frame_id,
            "graph_path": self.graph_path
        }

# https://docs.python.org/3/library/dataclasses.html#dataclasses.replace
    def update(self, stream_dict):
        if not isinstance(stream_dict, dict):
            return False
    #   self = replace(self, **stream_dict)
        self.stream_id = str(stream_dict.get("stream_id", self.stream_id))
        self.frame_id = int(stream_dict.get("frame_id", self.frame_id))
        self.graph_path = stream_dict.get("graph_path", self.graph_path)
        self.parameters = stream_dict.get("parameters", self.parameters)
        self.state = int(stream_dict.get("state", StreamState.RUN))
        return True
