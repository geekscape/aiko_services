# To Do
# ~~~~~
# - Design refactor to disambiguate DataSource and DataScheme implementations
#   - In particular, aim to generalize "VideoReadFile,frame_generator()"
#
# - Implement DataTarget DataScheme(s)
#
# - Implement DataScheme "webcam://0" and "webcam://dev/video0"
#
# - Move DataSource and DataTarget into "aiko_services.main.data_source.py" ?
#   - Define "data_sources" and "data_targets" as Python data classes
#
# - Improve "aiko_services/main/utilties/parser.py:parse()" to combine
#     "command" and "parameters" into a single parameter !

from abc import abstractmethod
from enum import Enum

import aiko_services as aiko
from aiko_services.main.utilities import parse

__all__ = ["contains_all", "DataScheme", "DataSource", "DataTarget"]

# --------------------------------------------------------------------------- #

def contains_all(source: str, match: chr):
    return False not in [character in source for character in match]

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

class DataScheme:
    @abstractmethod
    def create_data_source(
        self, stream, stream_id, data_sources, pipeline_element,
        frame_generator=None, use_create_frame=True):
        pass

class DataSource(aiko.PipelineElement):
    DATA_SCHEME_LOOKUP = {}  # key: name, value: class

    @classmethod
    def add_data_scheme(cls, name, data_scheme_class):
        if name in DataSource.DATA_SCHEME_LOOKUP:
            raise RuntimeError(
                f'DataSource.add_data_scheme(): scheme "{name}" already exists')
        DataSource.DATA_SCHEME_LOOKUP[name] = data_scheme_class

    def _get_data_sources(self):
        data_sources, found = self.get_parameter("data_sources")
        if not found:
            raise KeyError('Must provide "data_sources" parameter')
        data_source, data_sources = parse(data_sources)
        data_sources.insert(0, data_source)
        scheme = self._parse_scheme(data_sources)
        return data_sources, scheme

    def _parse_scheme(self, data_source):
        if isinstance(data_source, list):
            data_source = data_source[0]
        tokens = data_source.split("://")  # URL "scheme://path"
        scheme = "file" if len(tokens) == 1 else tokens[0]
        return scheme.lower()

    def start_stream(self, stream, stream_id,
        frame_generator=None, use_create_frame=True):

        try:
            data_sources, scheme = self._get_data_sources()
        except KeyError as key_error:
            return aiko.StreamEvent.ERROR, {"diagnostic": key_error}

        if not scheme in DataSource.DATA_SCHEME_LOOKUP:
            diagnostic = f'DataSource URL scheme "{scheme}" is not supported'
            return aiko.StreamEvent.ERROR, {"diagnostic": diagnostic}

        data_scheme = DataSource.DATA_SCHEME_LOOKUP[scheme]()
        pipeline_element = self
        stream_event, diagnostic = data_scheme.create_data_source(
            stream, stream_id, data_sources, pipeline_element,
            frame_generator=frame_generator, use_create_frame=use_create_frame)
        return stream_event, diagnostic

# --------------------------------------------------------------------------- #
# DataTarget: PipelineElement that stores frames of data at given locations
#
# Parameters
# - data_targets: List of URLs that represent the locations to store data

class DataTarget(aiko.PipelineElement):
    def start_stream(self, stream, stream_id):
        data_targets, found = self.get_parameter("data_targets")
        if not found:
            diagnostic = 'Must provide file "data_targets" parameter'
            return aiko.StreamEvent.ERROR, {"diagnostic": diagnostic}

        tokens = data_targets.split("://")  # URL "file://path" or "path"
        if len(tokens) == 1:
            path = tokens[0]
        else:
            if tokens[0] != "file":
                diagnostic = 'DataSource scheme must be "file://"'
                return aiko.StreamEvent.ERROR, {"diagnostic": diagnostic}
            path = tokens[1]

        stream.variables["target_file_id"] = 0
        stream.variables["target_path"] = path
        return aiko.StreamEvent.OKAY, {}

# --------------------------------------------------------------------------- #
