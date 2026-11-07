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

import os
import time
from datetime import datetime, timezone
from typing import Tuple

import numpy as np

import aiko_services as aiko
import aiko_services.elements.media.scheme_store_forward  # "store_forward://"
from aiko_services.main.store_forward.store_forward_message import utc_now, valid_segment_name
from aiko_services.main.writing_client import WritingClient

__all__ = ["VideoWriteStoreForward", "segment_file_name"]

_CV2_IMPORTED = False
try:
    import cv2

    _CV2_IMPORTED = True
except ModuleNotFoundError:  # TODO: Optional warning flag
    diagnostic = "store_forward_io.py: Couldn't import cv2 module"
#   print(f"WARNING: {diagnostic}")

_LOGGER = aiko.process.logger(__name__)

DEFAULT_FORMAT = "avc1"  # H.264 in MP4: 35 ms per 1080p frame on
# an embedded ARM computer, mp4v 111 ms
DEFAULT_FRAME_RATE = 8.0  # must match the source "rate"
DEFAULT_SEGMENT_SECONDS = 10.0  # close a segment after this many seconds
DEFAULT_SEGMENT_FRAMES = 0  # or after this many frames (0: unused)


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
# Shared state: "outbox", "segment" (open segment name), "segments_written",
# "frames_written", "last_segment_utc"
#
# Note: Only supports Streams with "data_targets" parameter


class VideoWriteStoreForward(aiko.DataTarget):  # PipelineElement
    def __init__(self, context: aiko.ContextPipelineElement):
        context.set_protocol("video_write_store_forward:0")
        context.call_init(self, "PipelineElement", context)
        self.share.update(
            {
                "outbox": "-",
                "segment": "-",
                "segments_written": "0",
                "frames_written": "0",
                "last_segment_utc": "-",
                # Why nothing is being written, when nothing is
                "writing_ok": True,
                "frames_skipped": "0",
            }
        )
        self._segments_written = 0
        self._frames_written = 0
        self._frames_skipped = 0
        # Whether this host wants to be written to.  True until a power
        # manager says otherwise, so a host without one is unaffected
        self._writing = None
        self._writing_was = True  # What was last published

    def start_stream(self, stream, stream_id):
        stream_event, diagnostic = super().start_stream(stream, stream_id)
        if stream_event != aiko.StreamEvent.OKAY:
            return stream_event, diagnostic
        if not _CV2_IMPORTED:
            diagnostic = "VideoWriteStoreForward needs OpenCV: pip install opencv-python"
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
            self.logger.info(f"{self.my_id()}: writing {'okay' if writing_ok else 'not okay'}")
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

        segment_seconds, _ = self.get_parameter("segment_seconds", DEFAULT_SEGMENT_SECONDS)
        segment_frames, _ = self.get_parameter("segment_frames", DEFAULT_SEGMENT_FRAMES)
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
            if (segment_frames > 0 and frames >= segment_frames) or (
                segment_seconds > 0 and elapsed >= segment_seconds
            ):
                self._close_segment(stream)

        self.ec_producer.update("frames_written", str(self._frames_written))
        return aiko.StreamEvent.OKAY, {}

    def stop_stream(self, stream, stream_id):
        if stream.variables.get("segment_writer") is not None:
            self._close_segment(stream)
        if self._writing is not None:
            self._writing.close()
            self._writing = None
        if stream.variables.get("data_scheme"):  # guard: base has no check
            return super().stop_stream(stream, stream_id)
        return aiko.StreamEvent.OKAY, {}

    # Segment files -------------------------------------------------------- #

    def _open_segment(self, stream, image):
        outbox = stream.variables["target_outbox"]
        name = segment_file_name(stream.variables["target_prefix"])
        if not valid_segment_name(name):  # cannot happen: prefix checked
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
        writer = cv2.VideoWriter(temp_path, fourcc, float(frame_rate), resolution)
        if not writer.isOpened():
            diagnostic = f'cannot open video writer "{temp_path}" ({format} {resolution} {frame_rate} fps)'
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
        if frames == 0:  # nothing written: no segment
            try:
                os.remove(temp_path)
            except OSError:
                pass
            return
        final_path = os.path.join(stream.variables["target_outbox"], name)
        os.replace(temp_path, final_path)  # appears complete, at once
        size = os.path.getsize(final_path)
        self._segments_written += 1
        now = utc_now()
        self.ec_producer.update("segments_written", str(self._segments_written))
        self.ec_producer.update("last_segment_utc", now)
        self.ec_producer.update("segment", "-")
        self.logger.info(f"{self.my_id()}: segment {name}: {frames} frames, {size} B")


# --------------------------------------------------------------------------- #
