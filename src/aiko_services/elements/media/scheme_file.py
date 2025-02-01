# To Do
# ~~~~~
# - Fix ... paths.append((path, None))  # "None" --> should be "file_id" ?

import os
from pathlib import Path

import aiko_services as aiko

__all__ = ["DataSchemeFile"]

# --------------------------------------------------------------------------- #
# parameter: "data_sources" provides the file pathname(s)
# - "(file://pathname_0 file://pathname_1 ...)"
# - "(file://data_in/in_{}.txt)"
# - "(file://data_in/in_{}.jpeg)"
# - "(file://data_in/in_{}.mp4)"
#
# parameter: "data_targets" provides the file pathname(s)
# - "(file://pathname_0 file://pathname_1 ...)"
# - "(file://data_out/out{}.txt)"
# - "(file://data_out/out_{}.jpeg)"
# - "(file://data_out/out_{}.mp4)"

class DataSchemeFile(aiko.DataScheme):
    def create_sources(self,
        stream, data_sources, frame_generator=None, use_create_frame=True):

        if not frame_generator:
            frame_generator = self.frame_generator

        paths = []
        for data_source in data_sources:
            path = aiko.DataScheme.parse_data_url_path(data_source)
            file_glob = "*"
            if aiko.DataScheme.contains_all(path, "{}"):
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

        pipeline_element = self.pipeline_element
        if use_create_frame and len(paths) == 1:
            pipeline_element.create_frame(stream, {"paths": [path]})
        else:
            stream.variables["source_paths_generator"] = iter(paths)
            rate, _ = pipeline_element.get_parameter("rate", default=None)
            rate = float(rate) if rate else None
            pipeline_element.create_frames(stream, frame_generator, rate=rate)
        return aiko.StreamEvent.OKAY, {}

    def create_targets(self, stream, data_targets):
        path = aiko.DataScheme.parse_data_url_path(data_targets[0])
        target_path_template = aiko.DataScheme.contains_all(path, "{}")

        stream.variables["target_file_id"] = 0
        stream.variables["target_path"] = path
        stream.variables["target_path_template"] = target_path_template
        return aiko.StreamEvent.OKAY, {}

    def _file_glob_difference(self, file_glob, filename):
        difference = None
        tokens = file_glob.split("*")
        token_start = tokens[0]
        token_end = tokens[1] if len(tokens) > 1 else ""
        if filename.startswith(token_start) and filename.endswith(token_end):
            difference = filename[len(token_start):len(filename)-len(token_end)]
        return difference

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

aiko.DataScheme.add_data_scheme("file", DataSchemeFile)

# --------------------------------------------------------------------------- #
