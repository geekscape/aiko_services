# To Do
# ~~~~~
# - Fix ... paths.append((path, None))  # "None" --> should be "file_id" ?

import os
from pathlib import Path

import aiko_services as aiko
from aiko_services.elements.media import contains_all, DataScheme, DataSource

__all__ = ["DataSchemeFile"]

# --------------------------------------------------------------------------- #

class DataSchemeFile(DataScheme):
# parameter: "data_sources" provides the file pathname(s)
# - "(file://pathname_0 file://pathname_1)"
# - "(file://data_in/in_{}.txt)"

    def create_data_source(
        self, stream, stream_id, data_sources, pipeline_element,
        frame_generator=None, use_create_frame=True):

        if not frame_generator:
            frame_generator = self.frame_generator

        self.pipeline_element = pipeline_element

        paths = []
        for data_source in data_sources:
            try:
                path = self._parse_data_source(data_source)
            except RuntimeError as runtime_error:
                return aiko.StreamEvent.ERROR, {"diagnostic": runtime_error}

            file_glob = "*"
            if contains_all(path, "{}"):
                file_glob = os.path.basename(path).replace("{}", "*")
                path = os.path.dirname(path)

            path = Path(path)
            if not path.exists():
                diagnostic = f'path "{path}" does not exist'
                return aiko.StreamEvent.ERROR, {"diagnostic": diagnostic}

            if path.is_file():
                paths.append((path, None))  # "None" --> should be "file_id" ?
            elif path.is_dir():
                paths_sorted = sorted(path.glob(file_glob))
                file_ids = []
                for path in paths_sorted:
                    file_id = None
                    if file_glob != "*":
                        file_id = self._file_glob_difference(
                            file_glob, path.name)
                    file_ids.append(file_id)
                paths.extend(zip(paths_sorted, file_ids))
            else:
                diagnostic = f'"{path}" must be a file or a directory'
                return aiko.StreamEvent.ERROR, {"diagnostic": diagnostic}

        if use_create_frame and len(paths) == 1:
            pipeline_element.create_frame(stream, {"paths": [path]})
        else:
            stream.variables["source_paths_generator"] = iter(paths)
            rate, _ = pipeline_element.get_parameter("rate", default=None)
            rate = float(rate) if rate else None
            pipeline_element.create_frames(stream, frame_generator, rate=rate)
        return aiko.StreamEvent.OKAY, {}

    def frame_generator(self, stream, frame_id):
        data_batch_size, _ = self.pipeline_element.get_parameter(
            "data_batch_size", default=1)
        data_batch_size = int(data_batch_size)
        paths = []
        try:
            while (data_batch_size > 0):
                data_batch_size -= 1
                path, file_id = next(stream.variables["source_paths_generator"])
                path = Path(path)
                if not path.is_file():
                    diagnostic = f'path "{path}" must be a file'
                    return aiko.StreamEvent.ERROR, {"diagnostic": diagnostic}
                paths.append(path)
        except StopIteration:
            pass

        if len(paths):
            return aiko.StreamEvent.OKAY, {"paths": paths}
        else:
            return aiko.StreamEvent.STOP, {"diagnostic": "All frames generated"}

    def _file_glob_difference(self, file_glob, filename):
        difference = None
        tokens = file_glob.split("*")
        token_start = tokens[0]
        token_end = tokens[1] if len(tokens) > 1 else ""
        if filename.startswith(token_start) and filename.endswith(token_end):
            difference = filename[len(token_start):len(filename)-len(token_end)]
        return difference

    def _parse_data_source(self, data_source):
        tokens = data_source.split("://")  # URL "scheme://path" or "path"
        path = tokens[0] if len(tokens) == 1 else tokens[1]
        return path

DataSource.add_data_scheme("file", DataSchemeFile)

# --------------------------------------------------------------------------- #
