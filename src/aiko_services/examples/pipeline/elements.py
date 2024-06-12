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
from io import BytesIO
import numpy as np
from typing import Tuple

import aiko_services as aiko

# --------------------------------------------------------------------------- #

class PE_GenerateNumbers(aiko.PipelineElement):
    def __init__(self, context):
        context.get_implementation("PipelineElement").__init__(self, context)

    def start_stream(self, stream, stream_id):
        def frame_data_producer(self, stream):
          return {"number": stream["frame_id"]}

        self.create_frames(stream, frame_data_producer, rate=1)

    def process_frame(self, stream, number) -> Tuple[bool, dict]:
        self.logger.info(f"{self._id(stream)}: in/out number: {number}")
        return True, {"number": number}

    def stop_stream(self, stream, stream_id):
        stream["terminate"] = True

# --------------------------------------------------------------------------- #

class PE_Metrics(aiko.PipelineElement):
    def __init__(self, context):
        context.set_protocol("metrics:0")
        context.get_implementation("PipelineElement").__init__(self, context)

    def process_frame(self, stream) -> Tuple[bool, dict]:
        metrics = stream["metrics"]
        metrics_elements = metrics["pipeline_elements"]
        for metrics_name, metrics_value in metrics_elements.items():
            metrics_value *= 1000
            self.logger.info(
                f"PE_Metrics: {metrics_name}: {metrics_value:.3f} ms")

        time_pipeline = metrics["time_pipeline"] * 1000
        self.logger.info(
            f"PE_Metrics: Pipeline total: {time_pipeline:.3f} ms")
        return True, {}

# --------------------------------------------------------------------------- #

class PE_0(aiko.PipelineElement):
    def __init__(self, context):
        context.set_protocol("increment:0")  # data_source:0
        context.get_implementation("PipelineElement").__init__(self, context)

    def process_frame(self, stream, a) -> Tuple[bool, dict]:
        b = int(a) + 1
        self.logger.info(f"PE_0: {self._id(stream)}, in a: {a}, out b: {b}")
        return True, {"b": b}

# --------------------------------------------------------------------------- #

class PE_1(aiko.PipelineElement):
    def __init__(self, context):
        context.set_protocol("increment:0")
        context.get_implementation("PipelineElement").__init__(self, context)

    def process_frame(self, stream, b) -> Tuple[bool, dict]:
        increment = 1
        p_1, found = self.get_parameter("p_1")
        pe_1_inc, found = self.get_parameter("pe_1_inc", 1)
        c = int(b) + int(pe_1_inc)
        self.logger.info(f"PE_1: {self._id(stream)}, in b: {b}, out c: {c}")
        self.logger.info(f"PE_1:            parameter pe_1_inc: {pe_1_inc}")
        return True, {"c": c}

# --------------------------------------------------------------------------- #

class PE_2(aiko.PipelineElement):
    def __init__(self, context):
        context.set_protocol("increment:0")
        context.get_implementation("PipelineElement").__init__(self, context)

    def process_frame(self, stream, c) -> Tuple[bool, dict]:
        d = int(c) + 1
        self.logger.info(f"PE_2: {self._id(stream)}, in c: {c}, out d: {d}")
        return True, {"d": d}

# --------------------------------------------------------------------------- #

class PE_3(aiko.PipelineElement):
    def __init__(self, context):
        context.set_protocol("increment:0")
        context.get_implementation("PipelineElement").__init__(self, context)

    def process_frame(self, stream, c) -> Tuple[bool, dict]:
        e = int(c) + 1
        self.logger.info(f"PE_3: {self._id(stream)}, in c: {c}, out e: {e}")
        return True, {"e": e}

# --------------------------------------------------------------------------- #

class PE_4(aiko.PipelineElement):
    def __init__(self, context):
        context.set_protocol("sum:0")
        context.get_implementation("PipelineElement").__init__(self, context)

    def process_frame(self, stream, d, e) -> Tuple[bool, dict]:
        f = int(d) + int(e)
        self.logger.info(
            f"PE_4: {self._id(stream)}, in d, e {d} {e}, out: d + e = f: {f}")
        return True, {"f": f}

# --------------------------------------------------------------------------- #

class PE_DataDecode(aiko.PipelineElement):
    def __init__(self, context):
        context.get_implementation("PipelineElement").__init__(self, context)

    def process_frame(self, stream, data) -> Tuple[bool, dict]:
        data = base64.b64decode(data.encode("utf-8"))
        np_bytes = BytesIO(data)
        data = np.load(np_bytes, allow_pickle=True)
    #   self.logger.info(f"PE_DataDecode: {self._id(stream)}, data: {data}")
        return True, {"data": data}

# --------------------------------------------------------------------------- #

class PE_DataEncode(aiko.PipelineElement):
    def __init__(self, context):
        context.get_implementation("PipelineElement").__init__(self, context)

    def process_frame(self, stream, data) -> Tuple[bool, dict]:
    #   self.logger.info(f"PE_DataEncode: {self._id(stream)}, data: {data}")
        if isinstance(data, str):
            data = str.encode(data)
        if isinstance(data, np.ndarray):
            np_bytes = BytesIO()
            np.save(np_bytes, data, allow_pickle=True)
            data = np_bytes.getvalue()
        data = base64.b64encode(data).decode("utf-8")
        return True, {"data": data}

# --------------------------------------------------------------------------- #
