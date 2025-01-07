# To Do
# ~~~~~
# - Design refactor to disambiguate DataSource and DataScheme implementations
#   - In particular, aim to generalize "VideoReadFile,frame_generator()"
#
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

class DataScheme:
    LOOKUP = {}  # key: name, value: class

    @classmethod
    def add_data_scheme(cls, name, data_scheme_class):
        if name in DataScheme.LOOKUP:
            raise RuntimeError(
                f'DataScheme.add_data_scheme(): scheme "{name}" already exists')
        DataScheme.LOOKUP[name] = data_scheme_class

    def __init__(self, pipeline_element):
        self.pipeline_element = pipeline_element
        self.share = pipeline_element.share

    @abstractmethod
    def create_sources(self, stream, data_sources,
        frame_generator=None, use_create_frame=True):
        pass

    def create_targets(self, stream, data_targets):
        pass

    def destroy_sources(self, stream):
        pass

    def destroy_targets(self, stream):
        pass

    @classmethod
    def parse_data_url_path(cls, data_url):  # data_source or data_target
        tokens = data_url.split("://")  # URL "scheme://path" or "path"
        path = tokens[0] if len(tokens) == 1 else tokens[1]
        return path

    @classmethod
    def parse_data_url_scheme(cls, data_url):  # data_source or data_target
        tokens = data_url.split("://")  # URL "scheme://path"
        scheme = "file" if len(tokens) == 1 else tokens[0]
        return scheme.lower()

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

# Each Pipeline Stream may have an individual DataSource DataScheme instance.
# Therefore, DataScheme instance variables are per-Stream variables :)

class DataSource(aiko.PipelineElementImpl):
    def _get_data_sources(self):
        data_sources, found = self.get_parameter("data_sources")
        if not found:
            raise KeyError('Must provide "data_sources" parameter')
        data_source, data_sources = parse(data_sources)
        data_sources.insert(0, data_source)
        scheme = DataScheme.parse_data_url_scheme(data_sources[0])
        return data_sources, scheme

    def start_stream(self, stream, stream_id,
        frame_generator=None, use_create_frame=True):

        stream.variables["data_scheme"] = None

        try:
            data_sources, scheme = self._get_data_sources()
        except KeyError as key_error:
            return aiko.StreamEvent.ERROR, {"diagnostic": key_error}

        if not scheme in DataScheme.LOOKUP:
            diagnostic = f'DataSource URL scheme "{scheme}" is not supported'
            return aiko.StreamEvent.ERROR, {"diagnostic": diagnostic}

        data_scheme = DataScheme.LOOKUP[scheme](self)
        stream.variables["data_scheme"] = data_scheme

        return data_scheme.create_sources(stream, data_sources,
            frame_generator=frame_generator,
            use_create_frame=use_create_frame)

    def stop_stream(self, stream, stream_id):
        if "data_scheme" in stream.variables:
            stream.variables["data_scheme"].destroy_sources(stream)
            del stream.variables["data_scheme"]
        return aiko.StreamEvent.OKAY, {}

# --------------------------------------------------------------------------- #
# DataTarget: PipelineElement that stores frames of data at given locations
#
# Parameters
# - data_targets: List of URLs that represent the locations to store data
#
# Each Pipeline Stream may have an individual DataTarget DataScheme instance.
# Therefore, DataScheme instance variables are per-Stream variables :)

class DataTarget(aiko.PipelineElementImpl):
    def _get_data_targets(self):
        data_targets, found = self.get_parameter("data_targets")
        if not found:
            raise KeyError('Must provide "data_targets" parameter')
        data_target, data_targets = parse(data_targets)
        data_targets.insert(0, data_target)
        scheme = DataScheme.parse_data_url_scheme(data_targets[0])
        return data_targets, scheme

    def start_stream(self, stream, stream_id):
        stream.variables["data_scheme"] = None

        try:
            data_targets, scheme = self._get_data_targets()
        except KeyError as key_error:
            return aiko.StreamEvent.ERROR, {"diagnostic": key_error}

        if not scheme in DataScheme.LOOKUP:
            diagnostic = f'DataTarget URL scheme "{scheme}" is not supported'
            return aiko.StreamEvent.ERROR, {"diagnostic": diagnostic}

        data_scheme = DataScheme.LOOKUP[scheme](self)
        stream.variables["data_scheme"] = data_scheme

        return data_scheme.create_targets(stream, data_targets)

    def stop_stream(self, stream, stream_id):
        if "data_scheme" in stream.variables:
            stream.variables["data_scheme"].destroy_targets(stream)
            del stream.variables["data_scheme"]
        return aiko.StreamEvent.OKAY, {}

# --------------------------------------------------------------------------- #
