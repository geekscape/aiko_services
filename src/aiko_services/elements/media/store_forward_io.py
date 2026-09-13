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
# To Do
# ~~~~~
# - fMP4 (fragmented MP4) segments, so a partially received segment plays
# - Announce each closed segment to the Actor with "(send_segment ...)"
# - VideoReadStoreForward: a DataSource reading segments from an inbox

import os
import time
from typing import Tuple

import numpy as np

import aiko_services as aiko
from aiko_services.main.store_forward.store_forward_message import (
    utc_now, valid_segment_name
)
import aiko_services.elements.media.scheme_store_forward  # "store_forward://"

__all__ = ["VideoWriteStoreForward"]

_CV2_IMPORTED = False
try:
    import cv2
    _CV2_IMPORTED = True
except ModuleNotFoundError:  # TODO: Optional warning flag
    diagnostic = "store_forward_io.py: Couldn't import cv2 module"
#   print(f"WARNING: {diagnostic}")

_LOGGER = aiko.process.logger(__name__)

DEFAULT_FORMAT = "mp4v"         # the fourcc tag OpenCV uses for MP4
DEFAULT_FRAME_RATE = 15.0       # must match the source "rate"
DEFAULT_SEGMENT_SECONDS = 10.0  # close a segment after this many seconds
DEFAULT_SEGMENT_FRAMES = 0      # or after this many frames (0: unused)

# --------------------------------------------------------------------------- #
# VideoWriteStoreForward is a DataTarget at the end of a video Pipeline.  It
# groups the "[image]" frames it receives into video segments (MP4 files)
# and writes each closed segment into an outbox directory that a
# SegmentStoreForward Actor (main/store_forward) forwards to another host.
#
# parameter: "data_targets"     "(store_forward://OUTBOX_DIRECTORY)"
# parameter: "segment_seconds"  close a segment after N seconds (10.0)
# parameter: "segment_frames"   or after N frames (0: unused); either bound
# parameter: "frame_rate"       encoded frames per second (15.0)
# parameter: "format"           OpenCV fourcc tag ("mp4v")
# parameter: "resolution"       "WxH", default: the first frame's shape
# parameter: "segment_prefix"   file name prefix ("segment"), see the scheme
#
# Segment file: <prefix>_<UTC>_<nnnnnn>.mp4, e.g
# segment_20260913T010203Z_000001.mp4, a name the Actor accepts.  Frames
# are NumPy uint8 HxWx3 RGB (converted to BGR for OpenCV).  The open
# segment is a dot-prefixed temporary file that the Actor's watcher
# ignores; it is renamed into place when it closes, on the last frame of a
# Stream too (stop_stream() runs after every in-flight Frame)
#
# Shared state: "outbox", "segment" (open segment name), "segments_written",
# "frames_written", "last_segment_utc"
#
# Note: Only supports Streams with "data_targets" parameter

class VideoWriteStoreForward(aiko.DataTarget):  # PipelineElement
    def __init__(self, context: aiko.ContextPipelineElement):
        context.set_protocol("video_write_store_forward:0")
        context.call_init(self, "PipelineElement", context)
        self.share.update({
            "outbox": "-", "segment": "-", "segments_written": "0",
            "frames_written": "0", "last_segment_utc": "-"
        })
        self._segments_written = 0
        self._frames_written = 0

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
        return aiko.StreamEvent.OKAY, {}

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
        if stream.variables.get("data_scheme"):    # guard: base has no check
            return super().stop_stream(stream, stream_id)
        return aiko.StreamEvent.OKAY, {}

    # Segment files -------------------------------------------------------- #

    def _open_segment(self, stream, image):
        outbox = stream.variables["target_outbox"]
        prefix = stream.variables["target_prefix"]
        stream.variables["target_segment_id"] += 1
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        segment_id = stream.variables["target_segment_id"]
        name = f"{prefix}_{stamp}_{segment_id:06d}.mp4"
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
