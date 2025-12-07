# To Do
# ~~~~~
# - Improve "parse_data_url_*()" using ...
#     from urllib.parse import urlparse
#     url = urlparse(url_string)
#       url.scheme, url.netloc, url.path, url.query, url.fragment
#       url.hostname, url.port

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

# TODO: "def parse_url()", which returns "scheme", "authority", "path"

    @classmethod
    def parse_data_url_path(cls, url):  # data_source or data_target
        auth_path = url.split(":", 1)[1] if ":" in url else ""
        if auth_path.startswith("//"):
            auth_path = auth_path[2:] if len(auth_path) >= 3 else ""
        return auth_path  # TODO: Should only return "path"

    @classmethod
    def parse_url_path(cls, url):
        return DataScheme.parse_data_url_path(url)

    @classmethod
    def parse_data_url_scheme(cls, url):  # data_source or data_target
        return url.split(":")[0].lower() if ":" in url else "file"

    @classmethod
    def parse_url_scheme(cls, url):
        return DataScheme.parse_data_url_scheme(url)

# --------------------------------------------------------------------------- #
