# Usage
# ~~~~~
# pytest [-s] unit/test_depthai_io.py
#
# In-process Pipeline tests of VideoReadDepthAI with a FakeCamera injected
# into the deployed "depthai://" DataScheme: no camera, no SDK, no MQTT
# broker.  ImageSink (image_sink.py) records the frames and stops the test
# on destroy_stream().  Every parameter lives in the element definitions,
# not in the Stream (see test_store_forward_io.py for why).  The fake
# captures in a millisecond and "rate" paces delivery, so the Stream is
# destroyed while the generator sleeps between frames, not while a capture
# is in flight: an in-flight frame posted after the stop re-creates the
# Stream (framework behaviour, reported).  Skipped when OpenCV is absent:
# ImageSink's package imports it
#
# To Do
# ~~~~~
# - None, yet !

import pytest
pytest.importorskip("cv2",
    reason="aiko_services.elements.media needs cv2 (video_io.py)")

from aiko_services.elements.cameras import scheme_depthai
from aiko_services.tests.unit import do_create_pipeline
from aiko_services.tests.unit.fake_camera import FakeCamera, do_fake_initialize
from aiko_services.tests.unit.image_sink import do_results_initialize

PIPELINE_DEFINITION = """{
  "version": 0, "name": "p_test_depthai_io", "runtime": "python",
  "graph": ["(VideoReadDepthAI CaptureLimit ImageSink)"],
  "parameters": {"_create_stream_": "1"},
  "elements": [
    { "name":   "VideoReadDepthAI",
      "parameters": {
        "data_sources": "(depthai://)",
        "resolution": "64x48", "frame_rate": 1000.0, "settle": SETTLE,
        "rate": 20.0
      },
      "input":  [{"name": "images", "type": "[image]"}],
      "output": [{"name": "images", "type": "[image]"}],
      "deploy": {
        "local": {"module": "aiko_services.elements.cameras.depthai_io"}}
    },
    { "name":   "CaptureLimit", "input": [], "output": [],
      "parameters": {"frame_count": FRAME_COUNT},
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

@pytest.fixture
def fake(monkeypatch):
    do_fake_initialize()
    monkeypatch.setattr(scheme_depthai, "OakDCamera", FakeCamera)
    yield FakeCamera
    do_fake_initialize()

def _run(settle, frame_count):
    results = do_results_initialize()
    definition = PIPELINE_DEFINITION  \
        .replace("SETTLE", str(settle))  \
        .replace("FRAME_COUNT", str(frame_count))
    do_create_pipeline(definition, frame_data=None)
    assert not results["watchdog"], "Stream did not stop: watchdog fired"
    assert results["stopped"], "ImageSink.stop_stream() was not invoked"
    return results

def test_capture_limit_bounds_the_run(fake):
    results = _run(settle=0, frame_count=3)
    assert results["frame_ids"] == [0, 1, 2]
    assert results["shapes"] == [(48, 64, 3)] * 3
    instance = fake.INSTANCES[-1]
    assert instance.opened and instance.closed
    assert instance._resolution == (64, 48)

def test_settle_discards_then_capture_failure_stops(fake):
    """Warm-up frames are not delivered; a capture exception ends the
    Stream through STOP on the main event thread, not the watchdog"""

    fake.FRAME_LIMIT = 7                # 5 warm-up frames + 2 delivered
    results = _run(settle=10, frame_count=100)
    assert results["frame_ids"] == [0, 1]
    assert results["shapes"] == [(48, 64, 3)] * 2
    assert fake.INSTANCES[-1].captured == 7
