# Usage
# ~~~~~
# pytest [-s] unit/test_gigev_io.py
#
# In-process Pipeline test of VideoReadGigE with a FakeCamera registered
# as the "fake" backend of the deployed "gigev://" DataScheme: no camera,
# no SDK, no MQTT broker.  See test_depthai_io.py for the pacing and the
# reason every parameter lives in the element definitions.  Skipped when
# OpenCV is absent: ImageSink's package imports it
#
# To Do
# ~~~~~
# - None, yet !

import pytest
pytest.importorskip("cv2",
    reason="aiko_services.elements.media needs cv2 (video_io.py)")

from aiko_services.elements.cameras import scheme_gigev
from aiko_services.tests.unit import do_create_pipeline
from aiko_services.tests.unit.fake_camera import FakeCamera, do_fake_initialize
from aiko_services.tests.unit.image_sink import do_results_initialize

PIPELINE_DEFINITION = """{
  "version": 0, "name": "p_test_gigev_io", "runtime": "python",
  "graph": ["(VideoReadGigE CaptureLimit ImageSink)"],
  "parameters": {"_create_stream_": "1"},
  "elements": [
    { "name":   "VideoReadGigE",
      "parameters": {
        "data_sources": "(gigev://)", "backend": "fake",
        "resolution": "64x48", "frame_rate": 1000.0, "rate": 20.0,
        "exposure_us": 20000, "settle": 0
      },
      "input":  [{"name": "images", "type": "[image]"}],
      "output": [{"name": "images", "type": "[image]"}],
      "deploy": {
        "local": {"module": "aiko_services.elements.cameras.gigev_io"}}
    },
    { "name":   "CaptureLimit", "input": [], "output": [],
      "parameters": {"frame_count": 3},
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

def test_gigev_pipeline_delivers_frames(monkeypatch):
    do_fake_initialize()
    monkeypatch.setitem(scheme_gigev.BACKENDS, "fake", FakeCamera)
    results = do_results_initialize()
    do_create_pipeline(PIPELINE_DEFINITION, frame_data=None)
    assert not results["watchdog"], "Stream did not stop: watchdog fired"
    assert results["stopped"], "ImageSink.stop_stream() was not invoked"
    assert results["frame_ids"] == [0, 1, 2]
    assert results["shapes"] == [(48, 64, 3)] * 3
    instance = FakeCamera.INSTANCES[-1]
    assert instance.opened and instance.closed
    assert instance.exposures == [20000.0]
    do_fake_initialize()
