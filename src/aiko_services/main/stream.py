# Definition(s)
# ~~~~~~~~~~~~~
# swag: One's personal bundle of belongings (Australian lingo)
# SWAG: Stuff We All Get
# SWAG: https://en.wikipedia.org/wiki/Scientific_wild-ass_guess :)
#
# Notes
# ~~~~~
# - Watch out for "stream.py:Frame()" dataclass and
#   "dashboard.py" use of "asciimatics.widgets.Frame()"
#
# To Do
# ~~~~~
# - Refactor from "pipeline.py", extract Stream concepts including Parameters
#   - Review "../archive/main/stream_2020.py"

from dataclasses import dataclass, field
from typing import Any, Dict

__all__ = [
    "DEFAULT_STREAM_ID", "FIRST_FRAME_ID", "Frame", "Stream",
    "StreamEvent", "StreamEventName", "StreamState", "StreamStateName"
]

DEFAULT_STREAM_ID = "*"  # string (or bytes ?)
FIRST_FRAME_ID = 0       # integer

class StreamEvent:
    ERROR = -2  # Move to StreamState.ERROR
    STOP  = -1  # Move to StreamState.STOP
    OKAY  =  0  # Stay calm and keep on running

StreamEventName = {
    StreamEvent.ERROR: "Error",
    StreamEvent.OKAY:  "Okay",
    StreamEvent.STOP:  "Stop"
}

class StreamState:
    ERROR = -2  # Don't generate new frames and ignore queued frames
    STOP  = -1  # Don't generate new frames and process queued frames
    RUN   =  0  # Generate new frames and process queued frames

StreamStateName = {
    StreamState.ERROR: "Error",
    StreamState.STOP:  "Stop",
    StreamState.RUN:   "Run"
}

@dataclass
class Frame:
    frame_id: int = FIRST_FRAME_ID
    parameters: Dict[str, Any] = field(default_factory=dict)
    paused_pe_name: str = None
    metrics: Dict[str, Any] = field(default_factory=dict)
    swag: Dict[str, Any] = field(default_factory=dict)
    variables: Dict[str, Any] = field(default_factory=dict)

@dataclass
class Stream:
    stream_id: str = DEFAULT_STREAM_ID
    frame_id: int = FIRST_FRAME_ID  # main thread only
    frames: Dict[int, Frame] = field(default_factory=dict)
    parameters: Dict[str, Any] = field(default_factory=dict)  # initial
    state: StreamState = StreamState.RUN
#   topic_reponse
