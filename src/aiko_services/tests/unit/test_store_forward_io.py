# Usage
# ~~~~~
# pytest [-s] unit/test_store_forward_io.py
#
# In-process Pipeline test, no MQTT broker and no camera: SyntheticVideoRead
# feeds CaptureLimit, VideoWriteStoreForward writes MP4 segments into a
# temporary outbox, and ImageSink (image_sink.py) stops the test on
# destroy_stream().  The writer's stop_stream() runs before the sink's, so
# the last, short segment is closed before the test ends.  Skipped when
# OpenCV is absent
#
# Every parameter lives in the element definitions, not in the Stream: the
# event loop is process-global, a frame generator of an earlier run can
# post one more Frame after its Stream was destroyed, and the Pipeline then
# creates a Stream with no Stream parameters for it.  With the parameters
# in the definitions that stray Stream still starts, runs its frame_count
# and stops; without them start_stream() fails and restarts the generator
# without end
#
# To Do
# ~~~~~
# - None, yet !

from datetime import datetime, timezone
import os
import re

import pytest
pytest.importorskip("cv2",
    reason="aiko_services.elements.media needs cv2 (video_io.py)")
import cv2

from aiko_services.main.store_forward.store_forward_message import (
    valid_segment_name
)
from aiko_services.elements.media.store_forward_io import segment_file_name
from aiko_services.tests.unit import do_create_pipeline
from aiko_services.tests.unit.image_sink import do_results_initialize

SEGMENT_NAME_RE = re.compile(
    r"^(cam0_)?\d{4}-\d\d-\d\d_\d\d-\d\d-\d\d-\d{6}\.mp4$")

PIPELINE_DEFINITION = """{
  "version": 0, "name": "p_test_store_forward_io", "runtime": "python",
  "graph": ["(SyntheticVideoRead CaptureLimit VideoWriteStoreForward ImageSink)"],
  "parameters": {"_create_stream_": "1", "frame_rate": 5.0},
  "elements": [
    { "name":   "SyntheticVideoRead",
      "parameters": {
        "data_sources": "(synth://video/plain?width=64&height=48)",
        "rate": 5.0
      },
      "input":  [{"name": "images", "type": "[image]"}],
      "output": [{"name": "images", "type": "[image]"}],
      "deploy": {
        "local": {"module": "aiko_services.elements.media.synthetic_io"}}
    },
    { "name":   "CaptureLimit", "input": [], "output": [],
      "parameters": {"frame_count": FRAME_COUNT},
      "deploy": {
        "local": {"module": "aiko_services.elements.control.elements"}}
    },
    { "name":   "VideoWriteStoreForward",
      "parameters": {
        "data_targets":    "(store_forward://OUTBOX)",
        "segment_prefix":  "PREFIX",
        "segment_frames":  SEGMENT_FRAMES,
        "segment_seconds": SEGMENT_SECONDS
      },
      "input":  [{"name": "images", "type": "[image]"}], "output": [],
      "deploy": {
        "local": {"module": "aiko_services.elements.media.store_forward_io"}}
    },
    { "name":   "ImageSink",
      "input":  [{"name": "images", "type": "[image]"}], "output": [],
      "deploy": {"local": {"module": "aiko_services.tests.unit.image_sink"}}
    }
  ]
}
"""

def _frame_count(path):
    capture = cv2.VideoCapture(str(path))
    try:
        count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    finally:
        capture.release()
    return count, (width, height)

def _run(outbox, frame_count, segment_frames, segment_seconds, prefix=""):
    results = do_results_initialize()
    definition = PIPELINE_DEFINITION  \
        .replace("OUTBOX", str(outbox))  \
        .replace("PREFIX", prefix)  \
        .replace("FRAME_COUNT", str(frame_count))  \
        .replace("SEGMENT_FRAMES", str(segment_frames))  \
        .replace("SEGMENT_SECONDS", str(segment_seconds))
    do_create_pipeline(definition, frame_data=None)
    assert not results["watchdog"], "Stream did not stop: watchdog fired"
    assert results["stopped"], "ImageSink.stop_stream() was not invoked"
    names = sorted(os.listdir(outbox))
    assert not [name for name in names if name.startswith(".")],  \
        f"temporary segment left behind: {names}"
    for name in names:
        assert SEGMENT_NAME_RE.match(name), name
        assert valid_segment_name(name), name    # the Actor accepts it
    return results, names

def test_segments_by_frame_count(tmp_path):
    results, names = _run(tmp_path, 7, 3, 0, prefix="cam0")
    assert results["frame_ids"] == list(range(7))
    assert len(names) == 3
    counts = [_frame_count(tmp_path / name) for name in names]
    assert [count for count, _ in counts] == [3, 3, 1]  # sorted: time order
    assert all(size == (64, 48) for _, size in counts)
    assert all(name.startswith("cam0_") for name in names)

def test_segment_file_name():
    now = datetime(2026, 9, 15, 3, 0, 7, 413882, tzinfo=timezone.utc)
    assert segment_file_name(now=now) == "2026-09-15_03-00-07-413882.mp4"
    assert segment_file_name("cam0", now)  \
        == "cam0_2026-09-15_03-00-07-413882.mp4"
    assert valid_segment_name(segment_file_name("cam0", now))
    assert SEGMENT_NAME_RE.match(segment_file_name())        # now, UTC
    later = now.replace(microsecond=413883)
    assert segment_file_name(now=now) < segment_file_name(now=later)

def test_segments_by_seconds(tmp_path):
    results, names = _run(tmp_path, 7, 0, 0.45)
    # 5 fps: a segment closes on the frame at or after 0.45 s, so two to
    # four frames per segment depending on event-loop timing
    assert results["frame_ids"] == list(range(7))
    counts = [_frame_count(tmp_path / name)[0] for name in names]
    assert sum(counts) == 7
    assert 2 <= len(counts) <= 4
    assert all(1 <= count <= 4 for count in counts)
