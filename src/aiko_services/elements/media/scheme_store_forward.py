# To Do
# ~~~~~
# - DataSource side: read segments arriving in an inbox into a Pipeline
#   (frames from each segment file), so a recipient host can process them
# - Announce each closed segment to the SegmentStoreForward Actor with
#   "(send_segment ID NAME)" instead of relying on the outbox watcher

import os
import re

import aiko_services as aiko

__all__ = ["DataSchemeStoreForward"]

_PREFIX_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")

# --------------------------------------------------------------------------- #
# parameter: "data_targets" names the outbox directory that a
#            SegmentStoreForward Actor (main/store_forward) watches
# - "(store_forward://data_out/outbox)"            relative to the working
#                                                   directory
# - "(store_forward:///home/pi/store_forward/out)"  absolute path (three
#                                                   slashes)
# - "(store_forward://~/store_forward/out)"         home-relative path
#
# parameter: "segment_prefix" first part of every segment file name
#            (default "segment"): <prefix>_<UTC>_<nnnnnn>.mp4
#
# A target-only scheme: the DataTarget element (store_forward_io.py) writes
# each segment to a dot-prefixed temporary file in the outbox, which the
# Actor's watcher ignores, then renames it into place when the segment
# closes, so every segment appears complete and at once

class DataSchemeStoreForward(aiko.DataScheme):
    def create_sources(self,
        stream, data_sources, frame_generator=None, use_create_frame=True):

        diagnostic = "store_forward:// is a target-only scheme (for now)"
        return aiko.StreamEvent.ERROR, {"diagnostic": diagnostic}

    def create_targets(self, stream, data_targets):
        path = aiko.DataScheme.parse_url_path(data_targets[0])
        path = os.path.realpath(os.path.expanduser(path))
        if not os.path.isdir(path):
            diagnostic = f'store_forward outbox "{path}" is not a directory'
            return aiko.StreamEvent.ERROR, {"diagnostic": diagnostic}
        if not os.access(path, os.W_OK):
            diagnostic = f'store_forward outbox "{path}" is not writable'
            return aiko.StreamEvent.ERROR, {"diagnostic": diagnostic}

        prefix, _ = self.pipeline_element.get_parameter(
            "segment_prefix", "segment")
        prefix = str(prefix)
        if not _PREFIX_RE.match(prefix):
            diagnostic = f'segment_prefix "{prefix}" must be [A-Za-z0-9_-]'
            return aiko.StreamEvent.ERROR, {"diagnostic": diagnostic}

        stream.variables["target_outbox"] = path
        stream.variables["target_prefix"] = prefix
        stream.variables["target_segment_id"] = 0
        ec_producer = getattr(self.pipeline_element, "ec_producer", None)
        if ec_producer:
            ec_producer.update("outbox", path)
        return aiko.StreamEvent.OKAY, {}

aiko.DataScheme.add_data_scheme("store_forward", DataSchemeStoreForward)

# --------------------------------------------------------------------------- #
