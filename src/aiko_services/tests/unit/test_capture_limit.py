# Usage
# ~~~~~
# pytest [-s] unit/test_capture_limit.py
#
# In-process Pipeline tests, no MQTT broker and no hardware: the
# SyntheticVideoRead DataSource feeds CaptureLimit, and an ImageSink
# (image_sink.py) records what passes and stops the test on destroy_stream().
# Skipped when OpenCV is absent: "aiko_services.elements.media" imports cv2
# at module level (video_io.py)
#
# To Do
# ~~~~~
# - Test the "duration" bound with a controlled clock instead of real time

import pytest
pytest.importorskip("cv2",
    reason="aiko_services.elements.media needs cv2 (video_io.py)")

from aiko_services.elements.control.elements import _parse_seconds
from aiko_services.tests.unit import do_create_pipeline
from aiko_services.tests.unit.image_sink import RESULTS, do_results_initialize

PIPELINE_DEFINITION = """{
  "version": 0, "name": "p_test_capture_limit", "runtime": "python",
  "graph": ["(SyntheticVideoRead CaptureLimit ImageSink)"],
  "parameters": {"_create_stream_": "1"},
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
      "deploy": {
        "local": {"module": "aiko_services.elements.control.elements"}}
    },
    { "name":   "ImageSink",
      "input":  [{"name": "images", "type": "[image]"}], "output": [],
      "deploy": {"local": {"module": "aiko_services.tests.unit.image_sink"}}
    }
  ]
}
"""

def _run(parameters):
    results = do_results_initialize()
    do_create_pipeline(PIPELINE_DEFINITION,
        frame_data=None, parameters=parameters)
    assert not results["watchdog"], "Stream did not stop: watchdog fired"
    assert results["stopped"], "ImageSink.stop_stream() was not invoked"
    return results

def test_capture_limit_frame_count():
    results = _run({"CaptureLimit.frame_count": 3})
    assert results["frame_ids"] == [0, 1, 2]
    assert results["shapes"] == [(48, 64, 3)] * 3

def test_capture_limit_duration():
    results = _run({"CaptureLimit.duration": 0.45})
    # 5 fps: frames at 0, 200, 400, 600 ms.  Elapsed is measured when the
    # Frame is processed, so the bound fires at frame 3 (4 frames), or at
    # frame 2 (3 frames) when the event loop is late by 50 ms or more
    assert 3 <= len(results["frame_ids"]) <= 4
    assert results["frame_ids"] == list(range(len(results["frame_ids"])))

def test_capture_limit_run_time():
    results = _run({"CaptureLimit.run_time": 0.4, "frame_rate": 5})
    assert results["frame_ids"] == [0, 1]  # media time 0.4 s at 5 fps

def test_capture_limit_condition():
    results = _run({"CaptureLimit.condition": "((count<3))"})
    assert results["frame_ids"] == [0, 1, 2]

def test_parse_seconds():
    assert _parse_seconds(10) == 10.0
    assert _parse_seconds("10") == 10.0
    assert _parse_seconds("10s") == 10.0
    assert _parse_seconds("10m") == 600.0
    assert _parse_seconds("0.5h") == 1800.0
    with pytest.raises(ValueError):
        _parse_seconds("10x")
