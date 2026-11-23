# Usage
# ~~~~~
# cd src/aiko_services/elements/media
#
# Terminal 1: the recipient host, a server-role SegmentStoreForward Actor
#   mkdir -p ~/store_forward/in ~/store_forward/out
#   aiko_store_forward server  \
#       --inbox ~/store_forward/in --outbox ~/store_forward/out
#
# Terminal 2: the sending host, an edge-role Actor watching the outbox
#   mkdir -p ~/store_forward/in data_out/outbox
#   aiko_store_forward edge  \
#       --inbox ~/store_forward/in --outbox data_out/outbox  \
#       --server_url http://localhost:8080
#
# Terminal 3: a Pipeline writing 10 s video segments into that outbox
#   aiko_pipeline create pipelines/store_forward_pipeline_0.json -s 1
#
#   aiko_pipeline create pipelines/store_forward_pipeline_0.json -s 1  \
#     -p VideoWriteStoreForward.data_targets  \
#        "(store_forward://~/store_forward/out)"  \
#     -p VideoWriteStoreForward.segment_seconds 5 -p CaptureLimit.duration 20
#
# This element stops writing when the host says so (ADR-028 decision 14).
# The reason is the transfer queue: a host on its battery pack that keeps
# recording fills the queue with work nobody asked for, and then holds
# itself up to drain it.  A power manager that sees the supply gone says
# "writing_ok" is false, this element closes the segment in hand so it can
# go, and the frames after it are dropped.  A host with no power manager is
# unaffected, because the answer is true until something says otherwise.
#
# To Do
# ~~~~~
# - fMP4 (fragmented MP4) segments, so a partially received segment plays
# - Announce each closed segment to the Actor with "(send_segment ...)"
# - VideoReadStoreForward: a DataSource reading segments from an inbox
# - Move VideoWriteStoreForward onto store_forward_base.WriteStoreForward
#
# Text segments (TextWriteStoreForward, TextReadStoreForward) use the
# generic elements in store_forward_base.py with TextCodec, for example CSV
# records from a field host to a database writer:
#
#   (CSVSource TextWriteStoreForward ...)                 sending host
#   (TextReadStoreForward DatabaseWriter CommitStoreForward)  receiving host

from datetime import datetime, timezone
import gzip
import json
import os
import re
import time
from typing import Tuple

import numpy as np

import aiko_services as aiko
from aiko_services.main.store_forward.store_forward_message import (
    utc_now, valid_segment_name
)
from aiko_services.main.writing_client import WritingClient
from aiko_services.elements.media.mp4_repair import (
    merge_leading_parameter_sets
)
import aiko_services.elements.media.scheme_store_forward  # "store_forward://"
from aiko_services.elements.media.store_forward_base import (
    ReadStoreForward, SegmentCodec, WriteStoreForward
)

__all__ = [
    "TextCodec", "TextReadStoreForward", "TextWriteStoreForward",
    "VideoWriteStoreForward", "segment_file_name"
]

_CV2_IMPORTED = False
try:
    import cv2
    _CV2_IMPORTED = True
except ModuleNotFoundError:  # TODO: Optional warning flag
    diagnostic = "store_forward_io.py: Couldn't import cv2 module"
#   print(f"WARNING: {diagnostic}")

_LOGGER = aiko.process.logger(__name__)

DEFAULT_FORMAT = "avc1"         # H.264 in MP4: 35 ms per 1080p frame on
                                # an embedded ARM computer, mp4v 111 ms
DEFAULT_FRAME_RATE = 8.0        # must match the source "rate"
DEFAULT_SEGMENT_SECONDS = 10.0  # close a segment after this many seconds
DEFAULT_SEGMENT_FRAMES = 0      # or after this many frames (0: unused)

def segment_file_name(prefix="", now=None):
    """Segment file name from the UTC open time to the microsecond, one
    token that sorts in time order: "2026-09-15_03-00-07-413882.mp4", or
    "<prefix>_2026-09-15_03-00-07-413882.mp4" with a prefix"""

    now = now or datetime.now(timezone.utc)
    stamp = now.strftime("%Y-%m-%d_%H-%M-%S-%f")
    return f"{prefix}_{stamp}.mp4" if prefix else f"{stamp}.mp4"

# --------------------------------------------------------------------------- #
# VideoWriteStoreForward is a DataTarget at the end of a video Pipeline.  It
# groups the "[image]" frames it receives into video segments (MP4 files)
# and writes each closed segment into an outbox directory that a
# SegmentStoreForward Actor (main/store_forward) forwards to another host.
#
# parameter: "data_targets"     "(store_forward://OUTBOX_DIRECTORY)"
# parameter: "segment_seconds"  close a segment after N seconds (10.0)
# parameter: "segment_frames"   or after N frames (0: unused); either bound
# parameter: "frame_rate"       encoded frames per second (8.0)
# parameter: "format"           OpenCV fourcc tag ("avc1": H.264).  The
#                               Pipeline holds the Stream lock while a
#                               frame is encoded, so the source is not
#                               read meanwhile: keep the encode well
#                               under the frame period (mp4v takes
#                               111 ms per 1080p frame on an embedded
#                               ARM computer, avc1 35 ms)
# parameter: "resolution"       "WxH", default: the first frame's shape
# parameter: "segment_prefix"   optional file name prefix (""), see the scheme
#
# Segment file: the UTC time the segment opened (its first frame arrived),
# to the microsecond, e.g 2026-09-15_03-00-07-413882.mp4, or with a prefix
# cam0_2026-09-15_03-00-07-413882.mp4: names sort in time order and the
# Actor accepts them.  Frames
# are NumPy uint8 HxWx3 RGB (converted to BGR for OpenCV).  The open
# segment is a dot-prefixed temporary file that the Actor's watcher
# ignores; it is renamed into place when it closes, on the last frame of a
# Stream too (stop_stream() runs after every in-flight Frame)
#
# Each closed segment is checked for a first sample that holds only the
# H.264 parameter sets, which the Raspberry Pi hardware encoder writes, and
# repaired before the rename (elements/media/mp4_repair.py).  Some readers
# fail on such a sample: cv2.VideoCapture.read() returns no frame first
#
# Shared state: "outbox", "segment" (open segment name), "segments_written",
# "segments_repaired", "frames_written", "last_segment_utc"
#
# Note: Only supports Streams with "data_targets" parameter

class VideoWriteStoreForward(aiko.DataTarget):  # PipelineElement
    def __init__(self, context: aiko.ContextPipelineElement):
        context.set_protocol("video_write_store_forward:0")
        context.call_init(self, "PipelineElement", context)
        self.share.update({
            "outbox": "-", "segment": "-", "segments_written": "0",
            "segments_repaired": "0",
            "frames_written": "0", "last_segment_utc": "-",
            # Why nothing is being written, when nothing is
            "writing_ok": True, "frames_skipped": "0"
        })
        self._segments_written = 0
        self._segments_repaired = 0
        self._frames_written = 0
        self._frames_skipped = 0
        # Whether this host wants to be written to.  True until a power
        # manager says otherwise, so a host without one is unaffected
        self._writing = None
        self._writing_was = True       # What was last published

    def start_stream(self, stream, stream_id):
        stream_event, diagnostic = super().start_stream(stream, stream_id)
        if stream_event != aiko.StreamEvent.OKAY:
            return stream_event, diagnostic
        if not _CV2_IMPORTED:
            diagnostic = "VideoWriteStoreForward needs OpenCV: pip install "  \
                         "opencv-python"
            return aiko.StreamEvent.ERROR, {"diagnostic": diagnostic}
        stream.variables["segment_writer"] = None
        stream.variables["segment_name"] = None
        stream.variables["segment_temp"] = None
        stream.variables["segment_frames"] = 0
        stream.variables["segment_started"] = None
        if self._writing is None:
            self._writing = WritingClient(self)
            self._writing.open()
        self._writing_was = True
        return aiko.StreamEvent.OKAY, {}

    def _skipping(self, stream, images):
        """Whether to drop these frames rather than write them.

        A host on its battery pack does not want a recording that nobody
        asked for: the transfer queue would grow with work that is not
        wanted, and then hold the host up to drain it.  So the segment in
        hand is closed, which lets it go, and the frames after it are
        dropped rather than queued.

        Dropping frames is not an error.  The stream carries on, and it
        writes again as soon as the host says so"""

        writing_ok = self._writing is None or self._writing.writing_ok()
        # Published here, and never from a handler of the client's.  A
        # change arrives on whichever thread delivered it, and the shared
        # state belongs to this element's own thread (P11).  This method
        # runs on that thread for every frame, so it is where a change is
        # noticed as well as where it is acted on
        if writing_ok != self._writing_was:
            self._writing_was = writing_ok
            self.ec_producer.update("writing_ok", writing_ok)
            self.logger.info(f"{self.my_id()}: writing "
                f"{'okay' if writing_ok else 'not okay'}")
        if writing_ok:
            return False
        if stream.variables.get("segment_writer") is not None:
            self._close_segment(stream)
        self._frames_skipped += len(images)
        self.ec_producer.update("frames_skipped", str(self._frames_skipped))
        return True

    def process_frame(self, stream, images) -> Tuple[aiko.StreamEvent, dict]:
        if images and not isinstance(images[0], np.ndarray):
            diagnostic = "Image media_type must be a numpy array"
            return aiko.StreamEvent.ERROR, {"diagnostic": diagnostic}

        segment_seconds, _ = self.get_parameter(
            "segment_seconds", DEFAULT_SEGMENT_SECONDS)
        segment_frames, _ = self.get_parameter(
            "segment_frames", DEFAULT_SEGMENT_FRAMES)
        segment_seconds = float(segment_seconds)  # parameters may be strings
        segment_frames = int(segment_frames)

        if self._skipping(stream, images):
            return aiko.StreamEvent.OKAY, {}

        for image in images:
            if stream.variables["segment_writer"] is None:
                stream_event, diagnostic = self._open_segment(stream, image)
                if stream_event != aiko.StreamEvent.OKAY:
                    return stream_event, diagnostic
            image_bgr = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
            stream.variables["segment_writer"].write(image_bgr)
            stream.variables["segment_frames"] += 1
            self._frames_written += 1

            elapsed = time.monotonic() - stream.variables["segment_started"]
            frames = stream.variables["segment_frames"]
            if (segment_frames > 0 and frames >= segment_frames)  \
                or (segment_seconds > 0 and elapsed >= segment_seconds):
                self._close_segment(stream)

        self.ec_producer.update("frames_written", str(self._frames_written))
        return aiko.StreamEvent.OKAY, {}

    def stop_stream(self, stream, stream_id):
        if stream.variables.get("segment_writer") is not None:
            self._close_segment(stream)
        if self._writing is not None:
            self._writing.close()
            self._writing = None
        if stream.variables.get("data_scheme"):    # guard: base has no check
            return super().stop_stream(stream, stream_id)
        return aiko.StreamEvent.OKAY, {}

    # Segment files -------------------------------------------------------- #

    def _open_segment(self, stream, image):
        outbox = stream.variables["target_outbox"]
        name = segment_file_name(stream.variables["target_prefix"])
        if not valid_segment_name(name):        # cannot happen: prefix checked
            diagnostic = f'segment name "{name}" rejected'
            return aiko.StreamEvent.ERROR, {"diagnostic": diagnostic}
        temp_path = os.path.join(outbox, f".{name}")

        format, _ = self.get_parameter("format", DEFAULT_FORMAT)
        frame_rate, _ = self.get_parameter("frame_rate", DEFAULT_FRAME_RATE)
        resolution, _ = self.get_parameter("resolution", None)
        if isinstance(resolution, str) and "x" in resolution:
            width, height = resolution.split("x")
            resolution = (int(width), int(height))
        else:
            resolution = (image.shape[1], image.shape[0])
        fourcc = cv2.VideoWriter_fourcc(*str(format))
        writer = cv2.VideoWriter(
            temp_path, fourcc, float(frame_rate), resolution)
        if not writer.isOpened():
            diagnostic = f'cannot open video writer "{temp_path}" '  \
                         f'({format} {resolution} {frame_rate} fps)'
            return aiko.StreamEvent.ERROR, {"diagnostic": diagnostic}

        stream.variables["segment_writer"] = writer
        stream.variables["segment_name"] = name
        stream.variables["segment_temp"] = temp_path
        stream.variables["segment_frames"] = 0
        stream.variables["segment_started"] = time.monotonic()
        self.ec_producer.update("segment", name)
        self.logger.debug(f"{self.my_id()}: segment {name} open")
        return aiko.StreamEvent.OKAY, {}

    def _close_segment(self, stream):
        writer = stream.variables["segment_writer"]
        name = stream.variables["segment_name"]
        temp_path = stream.variables["segment_temp"]
        frames = stream.variables["segment_frames"]
        stream.variables["segment_writer"] = None
        writer.release()
        if frames == 0:                         # nothing written: no segment
            try:
                os.remove(temp_path)
            except OSError:
                pass
            return
        self._repair_segment(temp_path)         # before it is visible
        final_path = os.path.join(stream.variables["target_outbox"], name)
        os.replace(temp_path, final_path)       # appears complete, at once
        size = os.path.getsize(final_path)
        self._segments_written += 1
        now = utc_now()
        self.ec_producer.update(
            "segments_written", str(self._segments_written))
        self.ec_producer.update("last_segment_utc", now)
        self.ec_producer.update("segment", "-")
        self.logger.info(
            f"{self.my_id()}: segment {name}: {frames} frames, {size} B")

# --------------------------------------------------------------------------- #

    def _repair_segment(self, path):
        """Join a leading parameter-sets-only sample to the key frame.

        The Raspberry Pi hardware encoder writes one at the start of every
        segment.  A segment that cannot be repaired is still sent: the
        frames in it are intact, and only some readers fail on it"""

        try:
            repaired = merge_leading_parameter_sets(path)
        except OSError as error:
            self.logger.warning(
                f"{self.my_id()}: segment not checked: {error}")
            return
        if repaired:
            self._segments_repaired += 1
            self.ec_producer.update(
                "segments_repaired", str(self._segments_repaired))
# Text segments ------------------------------------------------------------ #
# TextCodec writes one frame per segment: a header line, then the frame's
# text verbatim (UTF-8, line endings kept, a leading BOM removed).
#
#   #store_forward_text:0 {"fields": {...}, "writer": "host3", ...}
#   2024-09-01T00:00:00Z,1,20.5
#
# "fields" holds every frame field except the text, so the reader restores
# the frame exactly.  With "compress" "gzip" the whole file (header too) is
# gzip compressed and the extension gains ".gz".  A text larger than
# "max_segment_bytes" is split at line boundaries into consecutive
# segments, each with the same fields.  An empty text writes no segment.

TEXT_HEADER = "#store_forward_text:0 "
DEFAULT_MAX_SEGMENT_BYTES = 32 * 1024 * 1024   # the Actor refuses 64 MiB
_EXTENSION_RE = re.compile(r"^[A-Za-z0-9]{1,8}$")

class TextCodec(SegmentCodec):
    def __init__(self, text_field="text", extension="csv", compress="none",
                 max_segment_bytes=DEFAULT_MAX_SEGMENT_BYTES):
        if not _EXTENSION_RE.match(str(extension)):
            raise ValueError(
                f'segment_extension "{extension}" must be [A-Za-z0-9], 1 to 8')
        if compress not in ("none", "gzip"):
            raise ValueError(f'compress "{compress}" must be none or gzip')
        if int(max_segment_bytes) < 1024:
            raise ValueError("max_segment_bytes must be 1024 or more")
        self.text_field = str(text_field)
        self.compress = compress
        self.max_segment_bytes = int(max_segment_bytes)
        self._extension = f".{extension}" + (".gz" if compress == "gzip" else "")
        self._path = None
        self._header = None

    def extension(self):
        return self._extension

    def split(self, fields):
        text = fields.get(self.text_field)
        if text is None or text == "":
            return []
        text = str(text)
        if text.startswith("﻿"):
            text = text[1:]
        if len(text.encode("utf-8")) <= self.max_segment_bytes:
            return [dict(fields, **{self.text_field: text})]
        parts, lines, size = [], [], 0
        for line in text.splitlines(keepends=True):
            length = len(line.encode("utf-8"))
            if length > self.max_segment_bytes:
                raise ValueError("one line is larger than max_segment_bytes")
            if size + length > self.max_segment_bytes:
                parts.append("".join(lines))
                lines, size = [], 0
            lines.append(line)
            size += length
        if lines:
            parts.append("".join(lines))
        return [dict(fields, **{self.text_field: part}) for part in parts]

    def open(self, path, header):
        self._path = path
        self._header = dict(header)

    def append(self, fields):
        header = dict(self._header, text_field=self.text_field, fields={
            name: value for name, value in fields.items()
            if name != self.text_field})
        line = TEXT_HEADER + json.dumps(
            header, ensure_ascii=False, sort_keys=True, default=str)
        with self._open(self._path, "w") as file:
            file.write(line + "\n")
            file.write(fields[self.text_field])
        return True

    def close(self):
        self._path = None
        self._header = None

    def read_header(self, path):
        with self._open(path, "r") as file:
            line = file.readline(1024 * 1024)
        return self._parse_header(line)

    def read(self, path):
        with self._open(path, "r") as file:
            header = self._parse_header(file.readline(1024 * 1024))
            text = file.read()
        frame = dict(header.get("fields", {}))
        frame[header.get("text_field", self.text_field)] = text
        return header, [frame]

    def _open(self, path, mode):
        if str(path).endswith(".gz"):
            return gzip.open(path, mode + "t", encoding="utf-8", newline="")
        return open(path, mode, encoding="utf-8", newline="")

    @staticmethod
    def _parse_header(line):
        if not line.startswith(TEXT_HEADER) or not line.endswith("\n"):
            raise ValueError("no store_forward_text:0 header line")
        header = json.loads(line[len(TEXT_HEADER):])
        if not isinstance(header, dict)  \
                or not isinstance(header.get("fields", {}), dict):
            raise ValueError("header is not a JSON object with fields")
        return header

def _text_codec(element):
    text_field, _ = element.get_parameter("text_field", "text")
    extension, _ = element.get_parameter("segment_extension", "csv")
    compress, _ = element.get_parameter("compress", "none")
    max_bytes, _ = element.get_parameter(
        "max_segment_bytes", DEFAULT_MAX_SEGMENT_BYTES)
    return TextCodec(str(text_field), str(extension), str(compress),
                     int(float(max_bytes)))

# --------------------------------------------------------------------------- #
# TextWriteStoreForward: WriteStoreForward with TextCodec.
#
# parameter: "data_targets", "segment_prefix", "state_directory" as for
#            WriteStoreForward (store_forward_base.py)
# parameter: "text_field"         frame field that holds the text ("text")
# parameter: "segment_extension"  file name extension ("csv")
# parameter: "compress"           "none" or "gzip" ("none")
# parameter: "max_segment_bytes"  split larger texts (33554432)
#
# Inputs: the text field and every other field to carry, for example
#         text, group, location, sensor

class TextWriteStoreForward(WriteStoreForward):
    CODEC = _text_codec

    def __init__(self, context: aiko.ContextPipelineElement):
        context.set_protocol("text_write_store_forward:0")
        WriteStoreForward.__init__(self, context)

# --------------------------------------------------------------------------- #
# TextReadStoreForward: ReadStoreForward with TextCodec.  The reader takes
# the text field name from each segment's header.
#
# parameter: as for ReadStoreForward (store_forward_base.py), plus
#            "segment_extension" and "compress", which select the files
#            to read: "*.csv" or "*.csv.gz"
#
# Outputs: the writer's fields and "segment"

class TextReadStoreForward(ReadStoreForward):
    CODEC = _text_codec

    def __init__(self, context: aiko.ContextPipelineElement):
        context.set_protocol("text_read_store_forward:0")
        ReadStoreForward.__init__(self, context)

# --------------------------------------------------------------------------- #
