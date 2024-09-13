# To Do
# ~~~~~
# - Handle "data_source schemes" other than just "file://"
#   - Implement "data_source scheme" parser that validates the scheme type
#   - Update "DataSource.start_stream()" to hand more than just "file://"
#   - Include "webcam://0" and "webcam://dev/video0"
#
# - Move DataSource and DataTarget into "aiko_services.main.data_source.py" ?
#   - Define "data_sources" and "data_targets" as Python data classes
#
# - Improve "aiko_services/main/utilties/parser.py:parse()" to conbine
#     "command" and "parameters" into a single parameter !

import os
from pathlib import Path

import aiko_services as aiko
from aiko_services.main.utilities import parse

__all__ = ["contains_all", "file_glob_difference", "DataSource", "DataTarget"]

# --------------------------------------------------------------------------- #

def contains_all(source: str, match: chr):
    return False not in [character in source for character in match]

def file_glob_difference(file_glob, filename):
    difference = None
    tokens = file_glob.split("*")
    token_start = tokens[0]
    token_end = tokens[1] if len(tokens) > 1 else ""
    if filename.startswith(token_start) and filename.endswith(token_end):
        difference = filename[len(token_start):len(filename)-len(token_end)]
    return difference

# --------------------------------------------------------------------------- #
# DataSource: PipelineElement that loads frames of data from given locations
#
# Function arguments
# - use_create_frame: Enables using the more efficient (thread-less)
#     create_frame() method for a single path, rather than always using
#     create_frames() method and a "frame generator" (requires a thread)
#
# Parameters
# - data_sources: List of URLs that represent the locations to load data
# - data_batch_size: How many data items to be grouped per frame, default: 1
# - rate: How many frames to create per second, default: None (fast as possible)

class DataSource(aiko.PipelineElement):
    def start_stream(self, stream, stream_id, use_create_frame=True):
        data_sources, found = self.get_parameter("data_sources")
        if not found:
            return aiko.StreamEvent.ERROR,  \
                   {"diagnostic": 'Must provide "data_sources" parameter'}
        data_source, data_sources = parse(data_sources)
        data_sources.insert(0, data_source)

        paths = []
        for data_source in data_sources:
            tokens = data_source.split("://")  # URL "file://path" or "path"
            if len(tokens) == 1:
                path = tokens[0]
            else:
                if tokens[0] != "file":
                    return aiko.StreamEvent.ERROR,  \
                           {"diagnostic": 'DataSource scheme must be "file://"'}
                path = tokens[1]

            file_glob = "*"
            if contains_all(path, "{}"):
                file_glob = os.path.basename(path).replace("{}", "*")
                path = os.path.dirname(path)

            path = Path(path)
            if not path.exists():
                return aiko.StreamEvent.ERROR,  \
                       {"diagnostic": f'path "{path}" does not exist'}

            if path.is_file():
                paths.append((path, None))  # "None" --> should be "file_id" ?
            elif path.is_dir():
                paths_sorted = sorted(path.glob(file_glob))
                file_ids = []
                for path in paths_sorted:
                    file_id = None
                    if file_glob != "*":
                        file_id = file_glob_difference(file_glob, path.name)
                    file_ids.append(file_id)
                paths.extend(zip(paths_sorted, file_ids))
            else:
                return aiko.StreamEvent.ERROR,  \
                       {"diagnostic": f'"{path}" must be a file or a directory'}

        if use_create_frame and len(paths) == 1:
            self.create_frame(stream, {"paths": [path]})
        else:
            stream.variables["source_paths_generator"] = iter(paths)
            rate, _ = self.get_parameter("rate", default=None)
            rate = float(rate) if rate else None
            self.create_frames(stream, self.frame_generator, rate=rate)

        return aiko.StreamEvent.OKAY, {}

    def frame_generator(self, stream, frame_id):
        data_batch_size, _ = self.get_parameter("data_batch_size", default=1)
        data_batch_size = int(data_batch_size)
        paths = []
        try:
            while (data_batch_size > 0):
                data_batch_size -= 1
                path, file_id = next(stream.variables["source_paths_generator"])
                path = Path(path)
                if not path.is_file():
                    return aiko.StreamEvent.ERROR,  \
                           {"diagnostic": f'path "{path}" must be a file'}
                paths.append(path)
        except StopIteration:
            pass

        if len(paths):
            return aiko.StreamEvent.OKAY, {"paths": paths}
        else:
            return aiko.StreamEvent.STOP, {"diagnostic": "All frames generated"}

# --------------------------------------------------------------------------- #
# DataTarget: PipelineElement that stores frames of data at given locations
#
# Parameters
# - data_targets: List of URLs that represent the locations to store data

class DataTarget(aiko.PipelineElement):
    def start_stream(self, stream, stream_id):
        data_targets, found = self.get_parameter("data_targets")
        if not found:
            return aiko.StreamEvent.ERROR,  \
                   {"diagnostic": 'Must provide file "data_targets" parameter'}

        tokens = data_targets.split("://")  # URL "file://path" or "path"
        if len(tokens) == 1:
            path = tokens[0]
        else:
            if tokens[0] != "file":
                return aiko.StreamEvent.ERROR,  \
                       {"diagnostic": 'DataSource scheme must be "file://"'}
            path = tokens[1]

        stream.variables["target_file_id"] = 0
        stream.variables["target_path"] = path
        return aiko.StreamEvent.OKAY, {}

# --------------------------------------------------------------------------- #
