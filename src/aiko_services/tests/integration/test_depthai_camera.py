# Aiko Services cameras: a real Luxonis OAK camera through "depthai://"
#
# Needs the depthai SDK, a camera and an explicit opt-in ...
#
#   AIKO_TEST_DEPTHAI=1 pytest -s integration/test_depthai_camera.py
#   AIKO_TEST_DEPTHAI=<address> pytest -s integration/test_depthai_camera.py
#
# "1" discovers the first camera (same subnet, UDP 11491; on macOS grant
# Local Network permission to the process and turn Wi-Fi off), an address
# selects one.  Without the variable, or without a camera, the tests skip
#
# The Pipeline test asserts the first three frames only: a capture in
# flight when CaptureLimit stops the Stream is posted after the stop and
# re-creates the Stream (framework behaviour, reported), so a real camera
# can deliver a frame or two more before the process ends

import os

import pytest
pytest.importorskip("cv2",
    reason="aiko_services.elements.media needs cv2 (video_io.py)")
depthai = pytest.importorskip("depthai",
    reason='pip install "aiko_services[depthai]" to run the OAK camera test')

from aiko_services.elements.cameras.camera_oak_d import OakDCamera
from aiko_services.tests.unit import do_create_pipeline
from aiko_services.tests.unit.image_sink import do_results_initialize

ADDRESS = os.environ.get("AIKO_TEST_DEPTHAI")
pytestmark = pytest.mark.skipif(not ADDRESS,
    reason="set AIKO_TEST_DEPTHAI=1 (discover) or =<address> to run")

PIPELINE_DEFINITION = """{
  "version": 0, "name": "p_test_depthai_camera", "runtime": "python",
  "graph": ["(VideoReadDepthAI CaptureLimit ImageSink)"],
  "parameters": {"_create_stream_": "1"},
  "elements": [
    { "name":   "VideoReadDepthAI",
      "parameters": {
        "data_sources": "(URL)",
        "resolution": "1280x720", "frame_rate": 30.0, "rate": 10.0,
        "settle": "2s"
      },
      "input":  [{"name": "images", "type": "[image]"}],
      "output": [{"name": "images", "type": "[image]"}],
      "deploy": {
        "local": {"module": "aiko_services.elements.cameras.depthai_io"}}
    },
    { "name":   "CaptureLimit", "input": [], "output": [],
      "parameters": {"frame_count": 3},
      "deploy": {
        "local": {"module": "aiko_services.elements.control.elements"}}
    },
    { "name":   "ImageSink",
      "input":  [{"name": "images", "type": "[image]"}], "output": [],
      "parameters": {"watchdog_time": 60.0},
      "deploy": {"local": {"module": "aiko_services.tests.unit.image_sink"}}
    }
  ]
}
"""

def _url():
    if ADDRESS != "1":
        return f"depthai://{ADDRESS}"
    if not depthai.Device.getAllAvailableDevices():
        pytest.skip("AIKO_TEST_DEPTHAI is set, but no OAK camera was found")
    return "depthai://"

def test_open_capture_close_three_times():
    address = None if ADDRESS == "1" else ADDRESS
    _url()
    for _ in range(3):
        camera = OakDCamera(address=address, resolution=(1280, 720),
                            frame_rate=10.0)
        camera.open()
        try:
            image, metadata = camera.capture(timeout_s=10.0)
            assert image.shape == (720, 1280, 3)
            assert image.dtype.name == "uint8"
            assert "exposure_us" in metadata
        finally:
            camera.close()

def test_pipeline_delivers_frames():
    results = do_results_initialize()
    do_create_pipeline(PIPELINE_DEFINITION.replace("URL", _url()),
                       frame_data=None)
    assert not results["watchdog"], "no frames within 60 s"
    assert results["stopped"]
    assert results["frame_ids"][:3] == [0, 1, 2]     # strays may follow
    assert all(shape == (720, 1280, 3) for shape in results["shapes"])
