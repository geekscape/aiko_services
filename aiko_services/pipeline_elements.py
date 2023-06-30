# Usage
# ~~~~~
# AIKO_LOG_MQTT=false ./pipeline.py create pipeline_local.json
#
# PID=`ps ax | grep pipeline.py | grep create | grep -v grep |  \
#      tr -s " " | cut -d" " -f1`;  \
#      mosquitto_pub -h localhost -t aiko/spike/$PID/1/in  \
#                    -m "(process_frame (stream_id: 0 frame_id: 0) (a: 0))"
#
# mosquitto_pub -h localhost -t aiko/spike/$PID/1/in -m "(create_stream 1)"
# mosquitto_pub -h localhost -t aiko/spike/$PID/1/in -m "(destroy_stream 1)"

from threading import Thread
import time
from typing import Tuple

from aiko_services import aiko, PipelineElement

_LOGGER = aiko.logger(__name__)

# --------------------------------------------------------------------------- #
# TODO: Replace thread with "event.add_timer_handler()"

class PE_GenerateNumbers(PipelineElement):
    def __init__(self,
        implementations, name, protocol, tags, transport,
        definition, pipeline):

        implementations["PipelineElement"].__init__(self,
            implementations, name, protocol, tags, transport,
            definition, pipeline)

    def process_frame(self, context, number) -> Tuple[bool, dict]:
        _LOGGER.debug(f"{self._id(context)}: in/out number: {number}")
        return True, {"number": number}

    def _run(self, context):
        while not context["terminate"]:
            context["frame_id"] += 1
            self.pipeline.create_frame(context, {"number": context["frame_id"]})
            time.sleep(1.0)

    def start_stream(self, context, stream_id):
        context["terminate"] = False
        Thread(target=self._run, args=(context, )).start()

    def stop_stream(self, context, stream_id):
        context["terminate"] = True

# --------------------------------------------------------------------------- #

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

# --------------------------------------------------------------------------- #

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

# --------------------------------------------------------------------------- #

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

# --------------------------------------------------------------------------- #

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
        _LOGGER.info(f"PE_2: {context}, in c: {c}, out e: {e}")
        return True, {"e": e}

# --------------------------------------------------------------------------- #

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

# --------------------------------------------------------------------------- #
