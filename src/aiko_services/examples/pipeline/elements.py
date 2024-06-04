# Usage
# ~~~~~
# cd ../examples/pipeline
# aiko_pipeline create pipeline_local.json
# aiko_pipeline create pipeline_remote.json
# aiko_pipeline create pipeline_test.json
#
# TOPIC=$NAMESPACE/$HOST/$PID/$SID/in
# mosquitto_pub -h $HOST -t $TOPIC -m "(create_stream 1)"
# mosquitto_pub -h $HOST -t $TOPIC -m "(process_frame (stream_id: 1) (a: 0))"
# mosquitto_pub -h $HOST -t $TOPIC -m "(destroy_stream 1)"
#
# To Do
# ~~~~~
# - PE_Metrics: Make visible to Aiko Dashboard via self.share[]
# - PE_Metrics: Store to file (JSON, CSV), SQLite, InfluxDB
# - PE_Metrics: Add run-time average calculation
#
# - Consider PE_DataDecode and PE_DataEncode using "kwargs" for flexible
#   choices of data type to transfer via function parameters

import base64
import copy
from io import BytesIO
import numpy as np
from threading import Thread
import time
from typing import Tuple

from aiko_services.main import aiko, PipelineElement

_LOGGER = aiko.logger(__name__)

# --------------------------------------------------------------------------- #
# TODO: Replace thread with "event.add_timer_handler()"

class PE_GenerateNumbers(PipelineElement):
    def __init__(self, context):
        context.get_implementation("PipelineElement").__init__(self, context)

    def process_frame(self, context, number) -> Tuple[bool, dict]:
        _LOGGER.debug(f"{self._id(context)}: in/out number: {number}")
        return True, {"number": number}

    def _run(self, context):
        frame_id = 0
        while not context["terminate"]:
            frame_context = copy.deepcopy(context)
            frame_context["frame_id"] = frame_id
            self.create_frame(frame_context, {"number": frame_id})
            frame_id += 1
            time.sleep(1.0)

    def start_stream(self, context, stream_id):
        context["terminate"] = False
        Thread(target=self._run, args=(context, )).start()

    def stop_stream(self, context, stream_id):
        context["terminate"] = True

# --------------------------------------------------------------------------- #

class PE_Metrics(PipelineElement):
    def __init__(self, context):
        context.set_protocol("metrics:0")
        context.get_implementation("PipelineElement").__init__(self, context)

    def process_frame(self, context) -> Tuple[bool, dict]:
        metrics = context["metrics"]
        metrics_elements = metrics["pipeline_elements"]
        for metrics_name, metrics_value in metrics_elements.items():
            metrics_value *= 1000
            _LOGGER.info(
                f"PE_Metrics: {metrics_name}: {metrics_value:.3f} ms")

        time_pipeline = metrics["time_pipeline"] * 1000
        _LOGGER.info(
            f"PE_Metrics: Pipeline total: {time_pipeline:.3f} ms")
        return True, {}

# --------------------------------------------------------------------------- #

class PE_0(PipelineElement):
    def __init__(self, context):
        context.set_protocol("increment:0")  # data_source:0
        context.get_implementation("PipelineElement").__init__(self, context)

    def process_frame(self, context, a) -> Tuple[bool, dict]:
        b = int(a) + 1
        _LOGGER.info(f"PE_0: {self._id(context)}, in a: {a}, out b: {b}")
        return True, {"b": b}

# --------------------------------------------------------------------------- #

class PE_1(PipelineElement):
    def __init__(self, context):
        context.set_protocol("increment:0")
        context.get_implementation("PipelineElement").__init__(self, context)

    def process_frame(self, context, b) -> Tuple[bool, dict]:
        increment = 1
        p_1, found = self.get_parameter("p_1")
        pe_1_inc, found = self.get_parameter("pe_1_inc", 1)
        c = int(b) + int(pe_1_inc)
        _LOGGER.info(f"PE_1: {self._id(context)}, in b: {b}, out c: {c}")
        _LOGGER.info(f"PE_1:            parameter pe_1_inc: {pe_1_inc}")
        return True, {"c": c}

# --------------------------------------------------------------------------- #

class PE_2(PipelineElement):
    def __init__(self, context):
        context.set_protocol("increment:0")
        context.get_implementation("PipelineElement").__init__(self, context)

    def process_frame(self, context, c) -> Tuple[bool, dict]:
        d = int(c) + 1
        _LOGGER.info(f"PE_2: {self._id(context)}, in c: {c}, out d: {d}")
        return True, {"d": d}

# --------------------------------------------------------------------------- #

class PE_3(PipelineElement):
    def __init__(self, context):
        context.set_protocol("increment:0")
        context.get_implementation("PipelineElement").__init__(self, context)

    def process_frame(self, context, c) -> Tuple[bool, dict]:
        e = int(c) + 1
        _LOGGER.info(f"PE_3: {self._id(context)}, in c: {c}, out e: {e}")
        return True, {"e": e}

# --------------------------------------------------------------------------- #

class PE_4(PipelineElement):
    def __init__(self, context):
        context.set_protocol("sum:0")
        context.get_implementation("PipelineElement").__init__(self, context)

    def process_frame(self, context, d, e) -> Tuple[bool, dict]:
        f = int(d) + int(e)
        _LOGGER.info(f"PE_4: {self._id(context)}, in d, e {d} {e}, out: d + e = f: {f}")
        return True, {"f": f}

# --------------------------------------------------------------------------- #

class PE_DataDecode(PipelineElement):
    def __init__(self, context):
        context.get_implementation("PipelineElement").__init__(self, context)

    def process_frame(self, context, data) -> Tuple[bool, dict]:
        data = base64.b64decode(data.encode("utf-8"))
        np_bytes = BytesIO(data)
        data = np.load(np_bytes, allow_pickle=True)
    #   _LOGGER.info(f"PE_DataDecode: {self._id(context)}, data: {data}")
        return True, {"data": data}

# --------------------------------------------------------------------------- #

class PE_DataEncode(PipelineElement):
    def __init__(self, context):
        context.get_implementation("PipelineElement").__init__(self, context)

    def process_frame(self, context, data) -> Tuple[bool, dict]:
    #   _LOGGER.info(f"PE_DataEncode: {self._id(context)}, data: {data}")
        if isinstance(data, str):
            data = str.encode(data)
        if isinstance(data, np.ndarray):
            np_bytes = BytesIO()
            np.save(np_bytes, data, allow_pickle=True)
            data = np_bytes.getvalue()
        data = base64.b64encode(data).decode("utf-8")
        return True, {"data": data}

# --------------------------------------------------------------------------- #
