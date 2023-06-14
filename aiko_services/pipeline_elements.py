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
        implementations, name, protocol, tags, transport,
        definition, pipeline):

        protocol = "increment:0"  # data_source:0
        implementations["PipelineElement"].__init__(self,
            implementations, name, protocol, tags, transport,
            definition, pipeline)

    def process_frame(self, context, a) -> Tuple[bool, dict]:
        b = int(a) + 1
        _LOGGER.info(f"PE_0: {context}, in a: {a}, out b: {b}")
        return True, {"b": b}

class PE_1(PipelineElement):
    def __init__(self,
        implementations, name, protocol, tags, transport,
        definition, pipeline):

        protocol = "increment:0"
        implementations["PipelineElement"].__init__(self,
            implementations, name, protocol, tags, transport,
            definition, pipeline)

    def process_frame(self, context, b) -> Tuple[bool, dict]:
        c = int(b) + 1
        _LOGGER.info(f"PE_1: {context}, in b: {b}, out c: {c}")
        return True, {"c": c}

class PE_2(PipelineElement):
    def __init__(self,
        implementations, name, protocol, tags, transport,
        definition, pipeline):

        protocol = "increment:0"
        implementations["PipelineElement"].__init__(self,
            implementations, name, protocol, tags, transport,
            definition, pipeline)

    def process_frame(self, context, c) -> Tuple[bool, dict]:
        d = int(c) + 1
        _LOGGER.info(f"PE_2: {context}, in c: {c}, out d: {d}")
        return True, {"d": d}

class PE_3(PipelineElement):
    def __init__(self,
        implementations, name, protocol, tags, transport,
        definition, pipeline):

        protocol = "increment:0"
        implementations["PipelineElement"].__init__(self,
            implementations, name, protocol, tags, transport,
            definition, pipeline)

    def process_frame(self, context, c) -> Tuple[bool, dict]:
        e = int(c) + 1
        _LOGGER.info(f"PE_2: {context}, in c: {c}, out d: {e}")
        return True, {"e": e}

class PE_4(PipelineElement):
    def __init__(self,
        implementations, name, protocol, tags, transport,
        definition, pipeline):

        protocol = "sum:0"
        implementations["PipelineElement"].__init__(self,
            implementations, name, protocol, tags, transport,
            definition, pipeline)

    def process_frame(self, context, d, e) -> Tuple[bool, dict]:
        f = int(d) + int(e)
        _LOGGER.info(f"PE_3: {context}, in d, e {d} {e}, out: d + e = f: {f}")
        return True, {"f": f}
