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

__all__ = ["StreamEvent", "StreamEventName", "StreamState", "StreamStateName"]

class StreamEvent:
    ERROR = -1  # Move to StreamState.ERROR
    OKAY  =  0  # Stay calm and keep on running
    STOP  =  1  # Move to StreamState.STOP

StreamEventName = {
    StreamEvent.ERROR: "Error",
    StreamEvent.OKAY:  "Okay",
    StreamEvent.STOP:  "Stop"
}

class StreamState:
    ERROR = -1  # Don't generate new frames and ignore queued frames
    RUN   =  0  # Generate new frames and process queued frames
    STOP  =  1  # Don't generate new frames and process queued frames

StreamStateName = {
    StreamState.ERROR: "Error",
    StreamState.RUN:   "Run",
    StreamState.STOP:  "Stop"
}
