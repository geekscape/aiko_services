# Usage
# ~~~~~
# pytest [-s] unit/test_scheme_depthai.py
#
# Tests of the "depthai://" DataScheme with a FakeCamera injected in place
# of OakDCamera (fake_camera.py) and a StubElement in place of the
# PipelineElement: URL forms, parameter coercion, the diagnostics, the
# frame generator's warm-up, timeout and STOP paths, the shared state and
# the writable keys.  No camera, no SDK, no event loop
#
# To Do
# ~~~~~
# - None, yet !

import pytest

import aiko_services as aiko
from aiko_services.elements.cameras import camera
from aiko_services.elements.cameras import scheme_depthai
from aiko_services.elements.cameras.scheme_depthai import DataSchemeDepthAI
from aiko_services.tests.unit.fake_camera import (
    FakeCamera, StubElement, do_fake_initialize
)

ADDRESS = "192.0.2.10"        # RFC 5737 documentation address

# --------------------------------------------------------------------------- #

@pytest.fixture
def fake(monkeypatch):
    do_fake_initialize()
    monkeypatch.setattr(scheme_depthai, "OakDCamera", FakeCamera)
    yield FakeCamera
    do_fake_initialize()

def make_scheme(parameters=None):
    element = StubElement(parameters)
    scheme = DataSchemeDepthAI(element)
    stream = aiko.Stream(stream_id="1")
    return scheme, element, stream

def start(parameters=None, url="depthai://"):
    scheme, element, stream = make_scheme(parameters)
    event, detail = scheme.create_sources(stream, [url])
    return scheme, element, stream, event, detail

def stop(scheme, stream):
    scheme.destroy_sources(stream)
    assert not scheme._timer_armed and not scheme._handler_armed

# --------------------------------------------------------------------------- #

def test_scheme_registered():
    assert aiko.DataScheme.LOOKUP["depthai"] is DataSchemeDepthAI

def test_url_forms(fake):
    for url, expected in (("depthai://", None),
                          (f"depthai://{ADDRESS}", ADDRESS),
                          (f"depthai:{ADDRESS}", ADDRESS)):
        scheme, element, stream, event, _ = start(
            {"settle": 0, "frame_rate": 100}, url)
        assert event == aiko.StreamEvent.OKAY, url
        assert fake.INSTANCES[-1].address == expected
        assert element.share["address"] == (expected or "-")
        stop(scheme, stream)
    constructed = len(fake.INSTANCES)
    scheme, _, stream, event, detail = start(url="depthai://?fps=2")
    assert event == aiko.StreamEvent.ERROR
    assert "URL options" in detail["diagnostic"]
    assert len(fake.INSTANCES) == constructed       # rejected before open

def test_create_sources_with_fake_camera(fake):
    scheme, element, stream, event, _ = start({
        "resolution": "640x480", "frame_rate": "30/1", "settle": 0,
        "resize_mode": "letterbox", "aux_stream": "false"})
    assert event == aiko.StreamEvent.OKAY
    instance = fake.INSTANCES[-1]
    assert instance.opened and instance.address is None
    assert instance._resolution == (640, 480)
    assert instance._frame_rate == 30.0
    assert instance.resize_mode == "letterbox" and not instance.aux_stream
    assert element.create_frames_calls == [(scheme.frame_generator, None)]
    assert element.share["device_id"] == "fake-0"
    assert element.share["sdk_version"] == "fake-1.0"
    assert element.share["resolution"] == "640x480"     # the parameter
    assert element.share["sensor.resolution"] == "640x480"  # delivered
    assert element.share["frame_rate"] == "30.0"
    assert element.share["state"] == "streaming"    # settle 0
    assert element.share["settled"] == "off"
    assert scheme._timer_armed and scheme._handler_armed
    stop(scheme, stream)
    assert instance.closed
    assert element.share["state"] == "stopped"

def test_defaults_and_rate(fake):
    scheme, element, stream, event, _ = start({})
    assert event == aiko.StreamEvent.OKAY
    instance = fake.INSTANCES[-1]
    assert instance._resolution == (1920, 1080)
    assert instance._frame_rate == 25.0
    assert element.share["settle"] == "30"
    assert element.share["aux_stream"] == "true"
    assert element.share["capture_timeout"] == "1.0"
    assert element.share["state"] == "settling"
    assert element.share["settled"] == "waiting"
    stop(scheme, stream)

    scheme, element, stream, event, _ = start({"rate": "5", "fps": "2"})
    assert event == aiko.StreamEvent.OKAY
    assert fake.INSTANCES[-1]._frame_rate == 2.0    # deprecated alias
    assert element.create_frames_calls[0][1] == 5.0  # delivery throttle
    stop(scheme, stream)

def test_native_resolution(fake):
    scheme, element, stream, event, _ = start({"resolution": "native",
                                               "settle": 0})
    assert event == aiko.StreamEvent.OKAY
    assert fake.INSTANCES[-1]._resolution == camera.NATIVE_RESOLUTION
    assert element.share["resolution"] == "native"      # stays a parameter
    assert element.share["sensor.resolution"] == "4000x3000"
    stop(scheme, stream)

def test_sdk_missing_diagnostic(fake, monkeypatch):
    monkeypatch.setattr(FakeCamera, "available", classmethod(lambda c: False))
    monkeypatch.setattr(FakeCamera, "diagnostic",
                        classmethod(lambda c: "pip install depthai"))
    scheme, element, stream, event, detail = start({})
    assert event == aiko.StreamEvent.ERROR
    assert "pip install depthai" in detail["diagnostic"]
    assert fake.INSTANCES == []                     # nothing constructed
    assert element.share["state"] == "error"
    assert element.share["last_error"].startswith("pip_install_depthai@")

def test_device_not_found(fake):
    fake.FAIL_OPEN = True
    scheme, element, stream, event, detail = start({})
    assert event == aiko.StreamEvent.ERROR
    assert "no device found" in detail["diagnostic"]
    assert scheme.camera is None
    assert element.share["state"] == "error"
    assert element.create_frames_calls == []

def test_bad_parameters(fake):
    for parameters, word in (({"resolution": "abc"}, "resolution"),
                             ({"frame_rate": "0"}, "frame_rate"),
                             ({"settle": "x"}, "settle"),
                             ({"resize_mode": "zoom"}, "resize_mode"),
                             ({"data_batch_size": 2}, "data_batch_size"),
                             ({"capture_timeout": "0"}, "capture_timeout")):
        scheme, element, stream, event, detail = start(parameters)
        assert event == aiko.StreamEvent.ERROR, parameters
        assert word in detail["diagnostic"]
        assert fake.INSTANCES == [], parameters       # rejected before open

def test_frame_generator_settles_then_delivers(fake):
    scheme, element, stream, event, _ = start({"settle": 10,
                                               "frame_rate": 200})
    assert event == aiko.StreamEvent.OKAY
    events = []
    for _ in range(8):
        frame_event, data = scheme.frame_generator(stream, len(events))
        events.append(frame_event)
        if frame_event == aiko.StreamEvent.OKAY:
            break
    # lens 0, 0, 120, 120, 120: converged on the 5th frame, delivered 6th
    assert events == [aiko.StreamEvent.NO_FRAME] * 5 + [aiko.StreamEvent.OKAY]
    assert data["images"][0].shape == (1080, 1920, 3)
    assert stream.variables["timestamps"]
    scheme._publish_handler()                       # what the timer does
    assert element.share["settled"] == "5_frames"
    assert element.share["state"] == "streaming"
    assert element.share["frames"] == "1"
    assert element.share["sensor.lens_position"] == "120"
    assert element.share["last_frame_utc"].endswith("Z")
    stop(scheme, stream)

def test_frame_generator_stop_on_capture_exception(fake):
    scheme, element, stream, event, _ = start({"settle": 0,
                                               "frame_rate": 200})
    fake.FRAME_LIMIT = 1
    assert scheme.frame_generator(stream, 0)[0] == aiko.StreamEvent.OKAY
    frame_event, detail = scheme.frame_generator(stream, 1)
    assert frame_event == aiko.StreamEvent.STOP
    assert "capture failed" in detail["diagnostic"]
    scheme._publish_handler()
    assert element.share["state"] == "error"
    assert element.share["last_error"].startswith("RuntimeError@")
    stop(scheme, stream)

def test_frame_generator_timeouts(fake):
    scheme, element, stream, event, _ = start({"settle": 0,
                                               "frame_rate": 200})
    original = FakeCamera.capture

    def timing_out(self, timeout_s=None):
        raise camera.CaptureTimeout("no frame")

    FakeCamera.capture = timing_out
    try:
        results = [scheme.frame_generator(stream, i)[0]
                   for i in range(camera.CAPTURE_TIMEOUT_LIMIT)]
    finally:
        FakeCamera.capture = original
    assert results[:-1] == [aiko.StreamEvent.NO_FRAME] * (
        camera.CAPTURE_TIMEOUT_LIMIT - 1)
    assert results[-1] == aiko.StreamEvent.STOP
    scheme._publish_handler()
    assert element.share["capture_timeouts"] == str(
        camera.CAPTURE_TIMEOUT_LIMIT)
    assert element.share["last_error"].startswith("capture_timeout@")
    stop(scheme, stream)

def test_destroy_then_generator_stops(fake):
    scheme, element, stream, event, _ = start({"settle": 0})
    stop(scheme, stream)
    frame_event, detail = scheme.frame_generator(stream, 0)
    assert frame_event == aiko.StreamEvent.STOP
    assert "destroyed" in detail["diagnostic"]

def test_writable_keys(fake):
    scheme, element, stream, event, _ = start({"settle": 0})
    element.ec_producer.send("capture_timeout", "2.5")
    assert scheme.capture_timeout == 2.5
    element.ec_producer.send("log_frames", "true")
    assert scheme.log_frames is True
    element.ec_producer.send("capture_timeout", "-1")   # rejected, logged
    assert scheme.capture_timeout == 2.5
    element.ec_producer.send("unknown_key", "x")        # ignored
    stop(scheme, stream)
    assert element.ec_producer.handlers == []
