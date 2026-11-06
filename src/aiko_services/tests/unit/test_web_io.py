# Usage
# ~~~~~
# pytest [-s] unit/test_web_io.py
#
# FrameWebServer on a free local port, no Pipeline: nothing is encoded
# without a viewer, the stream is scaled and capped at max_fps, a snapshot
# is full size, and only the allowed keys are writable.  Then VideoShowWeb
# in an in-process Pipeline (no MQTT broker): every frame passes through
# unchanged.  Skipped when OpenCV is absent
#
# To Do
# ~~~~~
# - None, yet !

import json
import threading
import time
import urllib.error
import urllib.request

import numpy as np
import pytest
cv2 = pytest.importorskip("cv2", reason="VideoShowWeb encodes with cv2")

from aiko_services.elements.web.web_io import FrameWebServer
from aiko_services.tests.unit import do_create_pipeline
from aiko_services.tests.unit.image_sink import do_results_initialize

def _image(width=1280, height=720, value=90):
    image = np.full((height, width, 3), value, dtype=np.uint8)
    image[:, : width // 2, 0] = 200                 # red left half
    return image

@pytest.fixture
def server():
    calls = []
    web = FrameWebServer(port=0, host="127.0.0.1", title="Test <view>",
        max_fps=5.0, width=640,
        status_provider=lambda: {"source": "Cam",
                                 "elements": {"Cam": {"state": "ok"}}},
        update_handler=lambda *arguments: calls.append(arguments))
    web.calls = calls
    web.start()
    web.url = f"http://127.0.0.1:{web.port}"
    yield web
    web.stop()

def _get(url, timeout=3.0):
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return response.status, response.headers, response.read()

def _wait(condition, timeout_s=3.0):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.01)
    return False

def test_nothing_is_encoded_without_a_viewer(server):
    for _ in range(20):
        server.offer(_image())
    time.sleep(0.3)
    assert server.stats()["frames_offered"] == 20
    assert server.stats()["frames_encoded"] == 0
    status, headers, body = _get(server.url + "/")
    assert status == 200 and "text/html" in headers["Content-Type"]
    assert b"Test &lt;view&gt;" in body             # the title, escaped
    status, _, body = _get(server.url + "/status")
    status_json = json.loads(body)
    assert status_json["source"] == "Cam"
    assert status_json["elements"] == {"Cam": {"state": "ok"}}
    assert status_json["viewer"]["viewers"] == 0

def test_stream_is_scaled_and_rate_capped(server):
    stop = threading.Event()
    def feed():
        while not stop.is_set():
            server.offer(_image())
            time.sleep(0.01)                          # 100 fps offered
    feeder = threading.Thread(target=feed, daemon=True)
    feeder.start()
    try:
        response = urllib.request.urlopen(server.url + "/stream.mjpg",
                                          timeout=3.0)
        assert "multipart/x-mixed-replace" in response.headers["Content-Type"]
        data, started = b"", time.monotonic()
        while time.monotonic() - started < 1.2:
            data += response.read1(65536)
        response.close()
        parts = data.count(b"--frame")
        assert 3 <= parts <= 9, parts                 # about 5 per second
        start = data.index(b"\xff\xd8")
        end = data.index(b"\xff\xd9", start) + 2
        frame = cv2.imdecode(np.frombuffer(data[start:end], np.uint8),
                             cv2.IMREAD_COLOR)
        assert frame.shape == (360, 640, 3)           # scaled to width
        assert frame[180, 100, 2] > 150               # red stays red (BGR)
        assert _wait(lambda: server.stats()["viewers"] == 0)
        encoded = server.stats()["frames_encoded"]
        time.sleep(0.5)
        assert server.stats()["frames_encoded"] == encoded  # idle again
    finally:
        stop.set()
        feeder.join()

def test_snapshot_is_full_size(server):
    with pytest.raises(urllib.error.HTTPError) as raised:
        _get(server.url + "/snapshot.jpg")
    assert raised.value.code == 503                   # no frame yet
    server.offer(_image())
    status, headers, body = _get(server.url + "/snapshot.jpg")
    assert status == 200 and headers["Content-Type"] == "image/jpeg"
    frame = cv2.imdecode(np.frombuffer(body, np.uint8), cv2.IMREAD_COLOR)
    assert frame.shape == (720, 1280, 3)

def test_only_allowed_keys_are_writable(server):
    status, _, _ = _get(server.url +
        "/update?element=Cam&name=focus_assist&value=true")
    assert status == 204
    assert server.calls == [("Cam", "focus_assist", "true")]
    for query in ("element=Cam&name=exposure_us&value=10",
                  "element=Cam&name=focus_assist&value=a%20b",
                  "name=focus_assist&value=true"):
        with pytest.raises(urllib.error.HTTPError) as raised:
            _get(server.url + "/update?" + query)
        assert raised.value.code == 403, query
    assert len(server.calls) == 1
    with pytest.raises(urllib.error.HTTPError) as raised:
        _get(server.url + "/elsewhere")
    assert raised.value.code == 404

PIPELINE_DEFINITION = """{
  "version": 0, "name": "p_test_web_io", "runtime": "python",
  "graph": ["(SyntheticVideoRead CaptureLimit VideoShowWeb ImageSink)"],
  "parameters": {"_create_stream_": "1"},
  "elements": [
    { "name":   "SyntheticVideoRead",
      "parameters": {
        "data_sources": "(synth://video/plain?width=64&height=48)",
        "rate": 20.0},
      "input":  [{"name": "images", "type": "[image]"}],
      "output": [{"name": "images", "type": "[image]"}],
      "deploy": {
        "local": {"module": "aiko_services.elements.media.synthetic_io"}}
    },
    { "name":   "CaptureLimit", "input": [], "output": [],
      "parameters": {"frame_count": 5},
      "deploy": {
        "local": {"module": "aiko_services.elements.control.elements"}}
    },
    { "name":   "VideoShowWeb",
      "parameters": {"port": 0, "host": "127.0.0.1"},
      "input":  [{"name": "images", "type": "[image]"}],
      "output": [{"name": "images", "type": "[image]"}],
      "deploy": {"local": {"module": "aiko_services.elements.web.web_io"}}
    },
    { "name":   "ImageSink",
      "input":  [{"name": "images", "type": "[image]"}], "output": [],
      "deploy": {"local": {"module": "aiko_services.tests.unit.image_sink"}}
    }
  ]
}
"""

def test_every_frame_passes_through():
    results = do_results_initialize()
    do_create_pipeline(PIPELINE_DEFINITION, frame_data=None)
    assert not results["watchdog"], "Stream did not stop: watchdog fired"
    assert results["stopped"]
    assert results["frame_ids"] == [0, 1, 2, 3, 4]
    assert results["shapes"] == [(48, 64, 3)] * 5

def test_example_definitions_parse_and_deploy():
    import importlib
    import os
    import aiko_services as aiko
    from aiko_services.elements import web
    folder = os.path.join(os.path.dirname(web.__file__), "pipelines")
    names = sorted(name for name in os.listdir(folder)
                   if name.endswith(".json"))
    assert names == ["web_pipeline_0.json"]
    for name in names:
        path = os.path.join(folder, name)
        with open(path) as file:
            definition = json.load(file)
        aiko.PipelineImpl.parse_pipeline_definition(path)
        for element in definition["elements"]:
            module = importlib.import_module(
                element["deploy"]["local"]["module"])
            assert hasattr(module, element["name"]), element["name"]
