# Usage
# ~~~~~
# aiko_pipeline create pipelines/pipeline_observe.json -ll debug -fd "(b: 0)"
#
# To Do
# ~~~~~
# - Metrics: Make visible to Aiko Dashboard via self.share[]
# - Metrics: Store to file (JSON, CSV), SQLite, InfluxDB
# - Metrics: Add run-time average calculation

from typing import Tuple

import aiko_services as aiko
from aiko_services.elements.utilities import all_outputs
from aiko_services.main.utilities import parse

__all__ = ["Inspect", "Metrics"]

# --------------------------------------------------------------------------- #

class Inspect(aiko.PipelineElement):
    def __init__(self, context):
        context.set_protocol("inspect:0")
        context.get_implementation("PipelineElement").__init__(self, context)

    def _get_inspect_file(self, stream, target):
        inspect_file = stream.variables.get("inspect_file", None)
        if not inspect_file:
            _, inspect_filepath = target.split(":")
            inspect_file = open(inspect_filepath, "a")
            stream.variables["inspect_file"] = inspect_file
        return inspect_file

    def process_frame(self, stream) -> Tuple[aiko.StreamEvent, dict]:
        frame = stream.frames[stream.frame_id]

        enable, _ = self.get_parameter("enable", True)
        if enable:
            names, found = self.get_parameter("inspect")
            if found:
                name, names = parse(names)
                names.insert(0, name)
                if "*" in names:
                    names = frame.swag.keys()
            else:
                names = frame.swag.keys()

            target, _ = self.get_parameter("target", "log")
            if target.startswith("file:"):
                inspect_file = self._get_inspect_file(stream, target)

            for name in names:
                value = frame.swag.get(name, None)
                name_value = f"{self.my_id()} {name}: {value}"

                if target.startswith("file:"):
                    inspect_file.write(name_value + "\n")
                elif target == "log":
                    self.logger.info(name_value)
                elif target == "print":
                    print(name_value)
                else:
                    diagnostic =  \
                        "'target' parameter must be 'file', 'log' or 'print'"
                    return aiko.StreamEvent.ERROR, {"diagnostic": diagnostic}

            if target.startswith("file:"):
                inspect_file.flush()

        return aiko.StreamEvent.OKAY, all_outputs(self, stream)

    def stop_stream(self, stream, stream_id):
        inspect_file = stream.variables.get("inspect_file", None)
        if inspect_file:
            inspect_file.close()
        return aiko.StreamEvent.OKAY, {}

# --------------------------------------------------------------------------- #
# Metrics typically appears at the end of a Pipeline graph.
# So that child Pipeline responses can be returned to the parent Pipeline.
# The Metrics PipelineElement Definition can refer to any output
# produced by the prior PipelineElements in the Pipeline graph
#
# For example ... "output": [{ "name": "i", "type": "int" }]

class Metrics(aiko.PipelineElement):
    def __init__(self, context):
        context.set_protocol("metrics:0")
        context.get_implementation("PipelineElement").__init__(self, context)

    def process_frame(self, stream) -> Tuple[aiko.StreamEvent, dict]:
        enable, _ = self.get_parameter("enable", True)
        rate, _ = self.get_parameter("rate", default=1)
        if not enable or stream.frame_id % rate != 0:
            return aiko.StreamEvent.OKAY, all_outputs(self, stream)

        frame = stream.frames[stream.frame_id]
        metrics = frame.metrics
        metrics_elements = metrics["elements"]
        for name, value in metrics_elements.items():
            if name.endswith("_memory"):
                value /= 1000000
                self.logger.debug(f"{self.my_id()} "
                    f"{name:22s}: {value:.3f} Mb+")
            if name.endswith("_time"):
                value *= 1000
                self.logger.debug(f"{self.my_id()} "
                    f"{name:22s}: {value:.3f} ms")

        if "pipeline_time" in metrics:
            pipeline_time = metrics["pipeline_time"] * 1000
            self.logger.debug(f"{self.my_id()} "
                f"{'Pipeline time':22s}: {pipeline_time:.3f} ms")

        if "pipeline_memory" in metrics:
            pipeline_memory = metrics["pipeline_memory"] / 1000000
            self.logger.debug(f"{self.my_id()} "
                f"{'Pipeline memory':22s}: {pipeline_memory:.3f} Mb+")

        if "pipeline_start_memory" in metrics:
            process_memory = metrics["pipeline_start_memory"] / 1000000
            self.logger.debug(f"{self.my_id()} "
                f"{'Process  memory':22s}: {process_memory:.3f} Mb")

        return aiko.StreamEvent.OKAY, all_outputs(self, stream)

# --------------------------------------------------------------------------- #
