# Usage
# ~~~~~
# AIKO_LOG_MQTT=false ./pipeline.py create pipeline_local.json
#
# PID=`ps ax | grep pipeline.py | grep create | grep -v grep |  \
#      tr -s " " | cut -d" " -f1`;  \
#      mosquitto_pub -h localhost -t aiko/spike/$PID/1/in  \
#                    -m "(process_frame (stream_id: 0 frame_id: 0) (a: 0))"

from typing import Tuple

from aiko_services import aiko, PipelineElement

_LOGGER = aiko.logger(__name__)

class PE_0(PipelineElement):
    def __init__(self,
        implementations, name, protocol, tags, transport, definition):

        protocol = "pe_0:0"  # data_source:0
        implementations["PipelineElement"].__init__(self,
            implementations, name, protocol, tags, transport, definition)

    def process_frame(self, context, a) -> Tuple[bool, dict]:
        b = int(a) + 1
        _LOGGER.info(f"PE_0: {context}, in a: {a}, out b: {b}")
        return True, {"b": b}

class PE_1(PipelineElement):
    def __init__(self,
        implementations, name, protocol, tags, transport, definition):

        protocol = "pe_1:0"
        implementations["PipelineElement"].__init__(self,
            implementations, name, protocol, tags, transport, definition)

    def process_frame(self, context, b) -> Tuple[bool, dict]:
        c = b + 1
        _LOGGER.info(f"PE_1: {context}, in b: {b}, out c: {c}")
        return True, {"c": c}

class PE_2(PipelineElement):
    def __init__(self,
        implementations, name, protocol, tags, transport, definition):

        protocol = "pe_2:0"
        implementations["PipelineElement"].__init__(self,
            implementations, name, protocol, tags, transport, definition)

    def process_frame(self, context, b) -> Tuple[bool, dict]:
        d = b + 1
        _LOGGER.info(f"PE_2: {context}, in b: {b}, out d: {d}")
        return True, {"d": d}

class PE_3(PipelineElement):
    def __init__(self,
        implementations, name, protocol, tags, transport, definition):

        protocol = "pe_3:0"
        implementations["PipelineElement"].__init__(self,
            implementations, name, protocol, tags, transport, definition)

    def process_frame(self, context, c, d) -> Tuple[bool, dict]:
        e = c + d
        _LOGGER.info(f"PE_3: {context}, in c d: {c} {d}, out: c + d = e: {e}")
        return True, {"e": e}
