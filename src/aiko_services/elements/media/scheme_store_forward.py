# To Do
# ~~~~~
# - Announce each closed segment to the SegmentStoreForward Actor with
#   "(send_segment ID NAME)" instead of relying on the outbox watcher

import os
import re

import aiko_services as aiko

__all__ = ["DataSchemeStoreForward"]

_PREFIX_RE = re.compile(r"^[A-Za-z0-9_-]{0,32}$")   # "": no prefix

def _directory(data_url):
    path = aiko.DataScheme.parse_url_path(data_url)
    return os.path.realpath(os.path.expanduser(path))

# --------------------------------------------------------------------------- #
# parameter: "data_targets" names the outbox directory that a
#            SegmentStoreForward Actor (main/store_forward) watches
# parameter: "data_sources" names the inbox directory that a
#            SegmentStoreForward Actor fills
# - "(store_forward://data_out/outbox)"            relative to the working
#                                                   directory
# - "(store_forward:///home/pi/store_forward/out)"  absolute path (three
#                                                   slashes)
# - "(store_forward://~/store_forward/out)"         home-relative path
#
# parameter: "segment_prefix" optional first part of every segment file
#            name (default "", none): [<prefix>_]<UTC open time>.mp4
#
# Target: the DataTarget element (store_forward_io.py,
# store_forward_base.py) writes each segment to a dot-prefixed temporary
# file in the outbox, which the Actor's watcher ignores, then renames it
# into place when the segment closes, so every segment appears complete
# and at once.
#
# Source: a ReadStoreForward element (store_forward_base.py) only.  It
# needs "work_directory", outside the inbox, for processing/, done/ and
# rejected/.  The scheme checks both directories, asks the element for its
# SegmentReader and starts the frame generator at "rate" polls per second

class DataSchemeStoreForward(aiko.DataScheme):
    def create_sources(self,
        stream, data_sources, frame_generator=None, use_create_frame=True):

        element = self.pipeline_element
        factory = stream.variables.get("store_forward_reader_factory")
        if factory is None or frame_generator is None:
            diagnostic = "store_forward:// sources need a ReadStoreForward "  \
                         "element, for example TextReadStoreForward"
            return aiko.StreamEvent.ERROR, {"diagnostic": diagnostic}

        inbox = _directory(data_sources[0])
        if not os.path.isdir(inbox):
            diagnostic = f'store_forward inbox "{inbox}" is not a directory'
            return aiko.StreamEvent.ERROR, {"diagnostic": diagnostic}
        if not os.access(inbox, os.R_OK | os.W_OK):
            diagnostic = f'store_forward inbox "{inbox}" needs read and write'
            return aiko.StreamEvent.ERROR, {"diagnostic": diagnostic}

        work_directory, _ = element.get_parameter("work_directory", None)
        if not work_directory:
            diagnostic = 'store_forward:// sources need "work_directory"'
            return aiko.StreamEvent.ERROR, {"diagnostic": diagnostic}
        work_directory = os.path.realpath(
            os.path.expanduser(str(work_directory)))
        if work_directory == inbox  \
                or work_directory.startswith(inbox + os.sep):
            diagnostic = f'work_directory "{work_directory}" must be '  \
                         f'outside the inbox "{inbox}"'
            return aiko.StreamEvent.ERROR, {"diagnostic": diagnostic}

        rate, _ = element.get_parameter("rate", 1.0)
        try:
            rate = float(rate)
            if rate <= 0:
                raise ValueError
            os.makedirs(work_directory, exist_ok=True)
            reader = factory(stream, inbox, work_directory)
        except (TypeError, ValueError) as error:
            diagnostic = f"store_forward source: {error or 'rate must be > 0'}"
            return aiko.StreamEvent.ERROR, {"diagnostic": diagnostic}
        except OSError as error:
            diagnostic = f"store_forward work_directory: {error}"
            return aiko.StreamEvent.ERROR, {"diagnostic": diagnostic}

        stream.variables["store_forward_reader"] = reader
        stream.variables["source_inbox"] = inbox
        ec_producer = getattr(element, "ec_producer", None)
        if ec_producer:
            ec_producer.update("inbox", inbox)
        element.create_frames(stream, frame_generator, rate=rate)
        return aiko.StreamEvent.OKAY, {}

    def create_targets(self, stream, data_targets):
        path = _directory(data_targets[0])
        if not os.path.isdir(path):
            diagnostic = f'store_forward outbox "{path}" is not a directory'
            return aiko.StreamEvent.ERROR, {"diagnostic": diagnostic}
        if not os.access(path, os.W_OK):
            diagnostic = f'store_forward outbox "{path}" is not writable'
            return aiko.StreamEvent.ERROR, {"diagnostic": diagnostic}

        prefix, _ = self.pipeline_element.get_parameter("segment_prefix", "")
        prefix = "" if prefix is None else str(prefix)
        if not _PREFIX_RE.match(prefix):
            diagnostic =  \
                f'segment_prefix "{prefix}" must be [A-Za-z0-9_-], 32 max'
            return aiko.StreamEvent.ERROR, {"diagnostic": diagnostic}

        stream.variables["target_outbox"] = path
        stream.variables["target_prefix"] = prefix
        ec_producer = getattr(self.pipeline_element, "ec_producer", None)
        if ec_producer:
            ec_producer.update("outbox", path)
        return aiko.StreamEvent.OKAY, {}

aiko.DataScheme.add_data_scheme("store_forward", DataSchemeStoreForward)

# --------------------------------------------------------------------------- #
