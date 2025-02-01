# To Do
# ~~~~~
# - None, yet !

from abc import abstractmethod

import aiko_services as aiko

__all__ = ["DataScheme"]

# --------------------------------------------------------------------------- #

class DataScheme:
    LOOKUP = {}  # key: name, value: class

    def __init__(self, pipeline_element):
        self.pipeline_element = pipeline_element
        self.share = pipeline_element.share

    @classmethod
    def add_data_scheme(cls, name, data_scheme_class):
        if name in DataScheme.LOOKUP:
            raise RuntimeError(
                f'DataScheme.add_data_scheme(): scheme "{name}" already exists')
        DataScheme.LOOKUP[name] = data_scheme_class

    @classmethod
    def contains_all(cls, source: str, match: chr):
        return False not in [character in source for character in match]

    @abstractmethod
    def create_sources(self, stream, data_sources,
        frame_generator=None, use_create_frame=True):
        return aiko.StreamEvent.OKAY, {}

    def create_targets(self, stream, data_targets):
        return aiko.StreamEvent.OKAY, {}

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
