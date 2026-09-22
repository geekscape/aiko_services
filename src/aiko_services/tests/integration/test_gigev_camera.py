# Aiko Services cameras: a real GigE Vision camera through "gigev://"
#
# Needs a camera backend (IDS peak on Linux, or Aravis), a camera and an
# explicit opt-in ...
#
#   AIKO_TEST_GIGEV=1 pytest -s integration/test_gigev_camera.py
#   AIKO_TEST_GIGEV=<address> AIKO_TEST_GIGEV_BACKEND=peak pytest ...
#
# "1" takes the first camera found, an address selects one (a substring
# of the IDS display name or serial, or an Aravis device id).  Without
# the variable, a backend or a camera, the tests skip

import os

import pytest
pytest.importorskip("cv2",
    reason="aiko_services.elements.media needs cv2 (video_io.py)")

from aiko_services.elements.cameras.scheme_gigev import select_backend
from aiko_services.tests.unit import do_create_pipeline
from aiko_services.tests.unit.image_sink import do_results_initialize

ADDRESS = os.environ.get("AIKO_TEST_GIGEV")
BACKEND = os.environ.get("AIKO_TEST_GIGEV_BACKEND", "auto")
pytestmark = pytest.mark.skipif(not ADDRESS,
    reason="set AIKO_TEST_GIGEV=1 (first camera) or =<address> to run")

PIPELINE_DEFINITION = """{
  "version": 0, "name": "p_test_gigev_camera", "runtime": "python",
  "graph": ["(VideoReadGigE CaptureLimit ImageSink)"],
  "parameters": {"_create_stream_": "1"},
  "elements": [
    { "name":   "VideoReadGigE",
      "parameters": {
        "data_sources": "(URL)", "backend": "BACKEND",
        "resolution": "640x480", "frame_rate": 5.0
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
      "parameters": {"watchdog_time": 90.0},
      "deploy": {"local": {"module": "aiko_services.tests.unit.image_sink"}}
    }
  ]
}
"""

def _backend():
    try:
        return select_backend(BACKEND)
    except RuntimeError as runtime_error:
        pytest.skip(f"no GigE backend: {runtime_error}")

def test_open_capture_close():
    name, camera_class = _backend()
    address = None if ADDRESS == "1" else ADDRESS
    camera = camera_class(address=address, resolution=(640, 480),
                          frame_rate=1.0, trigger="software")
    try:
        camera.open()
    except Exception as exception:
        if ADDRESS == "1":
            pytest.skip(f"no GigE camera found through {name}: {exception}")
        raise
    try:
        image, metadata = camera.capture(timeout_s=10.0)
        assert image.shape == (480, 640, 3) and image.dtype.name == "uint8"
        assert "exposure_us" in metadata
    finally:
        camera.close()

def test_pipeline_delivers_frames():
    name, _ = _backend()
    url = "gigev://" if ADDRESS == "1" else f"gigev://{ADDRESS}"
    results = do_results_initialize()
    do_create_pipeline(PIPELINE_DEFINITION.replace("URL", url)
                       .replace("BACKEND", name), frame_data=None)
    if results["watchdog"] and ADDRESS == "1":
        pytest.skip("no frames within 90 s: is a camera connected?")
    assert not results["watchdog"], "no frames within 90 s"
    assert results["frame_ids"] == [0, 1, 2]
    assert results["shapes"] == [(480, 640, 3)] * 3
