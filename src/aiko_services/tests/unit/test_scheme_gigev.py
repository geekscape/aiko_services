# Usage
# ~~~~~
# pytest [-s] unit/test_scheme_gigev.py
#
# Tests of the "gigev://" DataScheme with a FakeCamera registered as a
# backend (fake_camera.py) and a StubElement in place of the
# PipelineElement: backend selection, the trigger rule, the exposure
# warm-up, the frame generator and the writable keys.  No camera, no SDK,
# no event loop
#
# To Do
# ~~~~~
# - None, yet !

import pytest

import aiko_services as aiko
from aiko_services.elements.cameras import scheme_gigev
from aiko_services.elements.cameras.scheme_gigev import (
    DataSchemeGigE, select_backend
)
from aiko_services.tests.unit.fake_camera import (
    FakeCamera, StubElement, do_fake_initialize
)

# --------------------------------------------------------------------------- #

class Unavailable:
    @classmethod
    def available(cls):
        return False

    @classmethod
    def diagnostic(cls):
        return f"install {cls.__name__}"

class NoPeak(Unavailable):
    pass

class NoAravis(Unavailable):
    pass

@pytest.fixture
def fake(monkeypatch):
    do_fake_initialize()
    monkeypatch.setitem(scheme_gigev.BACKENDS, "fake", FakeCamera)
    yield FakeCamera
    do_fake_initialize()

def start(parameters=None, url="gigev://"):
    parameters = {"backend": "fake", **(parameters or {})}
    element = StubElement(parameters)
    scheme = DataSchemeGigE(element)
    stream = aiko.Stream(stream_id="1")
    event, detail = scheme.create_sources(stream, [url])
    return scheme, element, stream, event, detail

def stop(scheme, stream):
    scheme.destroy_sources(stream)
    assert not scheme._timer_armed and not scheme._handler_armed

# --------------------------------------------------------------------------- #

def test_scheme_registered():
    assert aiko.DataScheme.LOOKUP["gigev"] is DataSchemeGigE

def test_select_backend():
    backends = {"peak": NoPeak, "aravis": NoAravis, "fake": FakeCamera}
    assert select_backend("auto", backends) == ("fake", FakeCamera)
    assert select_backend("FAKE", backends) == ("fake", FakeCamera)
    with pytest.raises(RuntimeError, match="install NoPeak"):
        select_backend("peak", backends)
    with pytest.raises(RuntimeError, match="not one of auto"):
        select_backend("nonsense", backends)
    with pytest.raises(RuntimeError) as raised:
        select_backend("auto", {"peak": NoPeak, "aravis": NoAravis})
    assert "install NoPeak" in str(raised.value)
    assert "install NoAravis" in str(raised.value)

def test_backend_errors_reach_the_share(fake, monkeypatch):
    monkeypatch.setitem(scheme_gigev.BACKENDS, "peak", NoPeak)
    monkeypatch.setitem(scheme_gigev.BACKENDS, "aravis", NoAravis)
    scheme, element, stream, event, detail = start({"backend": "peak"})
    assert event == aiko.StreamEvent.ERROR
    assert "install NoPeak" in detail["diagnostic"]
    assert element.share["state"] == "error"
    assert fake.INSTANCES == []

def test_url_forms_and_shared_state(fake):
    scheme, element, stream, event, _ = start(
        {"exposure_us": 20000, "gain": 1.5, "settle": 0, "frame_rate": 25},
        "gigev://GV-1234")
    assert event == aiko.StreamEvent.OKAY
    instance = fake.INSTANCES[-1]
    assert instance.address == "GV-1234"
    assert instance.trigger == "off"                # 25 fps: free-running
    assert element.create_frames_calls == [(scheme.frame_generator, None)]
    assert element.share["backend"] == "fake"
    assert element.share["trigger"] == "off"
    assert element.share["exposure_us"] == "20000"  # the actual value
    assert element.share["gain"] == "1.50"
    assert instance.exposures == [20000.0] and instance.gains == [1.5]
    assert element.share["state"] == "streaming"
    stop(scheme, stream)
    assert instance.closed and element.share["state"] == "stopped"

def test_trigger_rule(fake):
    scheme, element, stream, event, _ = start(
        {"exposure_us": 20000, "settle": 0, "frame_rate": "1"})
    assert event == aiko.StreamEvent.OKAY
    assert fake.INSTANCES[-1].trigger == "software"   # stills regime
    assert element.create_frames_calls[0][1] == 1.0   # one trigger a frame
    stop(scheme, stream)

    scheme, element, stream, event, _ = start(
        {"exposure_us": 20000, "settle": 0, "frame_rate": "1",
         "trigger": "off", "rate": "2"})
    assert fake.INSTANCES[-1].trigger == "off"        # explicit override
    assert element.create_frames_calls[0][1] == 2.0
    stop(scheme, stream)

    scheme, _, _, event, detail = start({"trigger": "sometimes"})
    assert event == aiko.StreamEvent.ERROR
    assert "trigger" in detail["diagnostic"]
    scheme, _, _, event, detail = start({"exposure_us": "-5"})
    assert event == aiko.StreamEvent.ERROR
    assert "exposure_us" in detail["diagnostic"]

def test_auto_expose_warm_up_then_frames(fake):
    """No exposure_us: the generator runs the auto-expose steps (frames
    are all black, so it never converges and gives up after eight steps),
    then delivers"""

    scheme, element, stream, event, _ = start({"settle": 0,
                                               "frame_rate": 1000})
    assert event == aiko.StreamEvent.OKAY
    assert element.share["exposure_us"] == "auto"
    assert element.share["state"] == "settling"
    events = []
    for _ in range(12):
        frame_event, data = scheme.frame_generator(stream, len(events))
        events.append(frame_event)
        if frame_event == aiko.StreamEvent.OKAY:
            break
    assert events == [aiko.StreamEvent.NO_FRAME] * 9 + [aiko.StreamEvent.OKAY]
    instance = fake.INSTANCES[-1]
    assert len(instance.exposures) == 8             # eight adjustments
    scheme._publish_handler()
    assert element.share["exposure_us"] == f"{instance.exposures[-1]:.0f}"
    assert element.share["frames"] == "1"
    stop(scheme, stream)

def test_writable_exposure_and_gain(fake):
    scheme, element, stream, event, _ = start(
        {"exposure_us": 20000, "settle": 2, "frame_rate": 1000})
    instance = fake.INSTANCES[-1]
    for _ in range(2):                              # the settle frames
        assert scheme.frame_generator(stream, 0)[0]  \
            == aiko.StreamEvent.NO_FRAME
    assert scheme.frame_generator(stream, 2)[0] == aiko.StreamEvent.OKAY

    element.ec_producer.send("exposure_us", "30000")
    assert instance.exposures[-1] == 30000.0
    assert element.share["exposure_us"] == "30000"
    assert element.share["state"] == "settling"     # two frames again
    assert scheme.frame_generator(stream, 3)[0] == aiko.StreamEvent.NO_FRAME
    assert scheme.frame_generator(stream, 4)[0] == aiko.StreamEvent.NO_FRAME
    assert scheme.frame_generator(stream, 5)[0] == aiko.StreamEvent.OKAY
    assert len(instance.exposures) == 2             # no re-entrant set

    element.ec_producer.send("gain", "2.5")
    assert instance.gains[-1] == 2.5 and element.share["gain"] == "2.50"
    element.ec_producer.send("gain", "-1")          # rejected, logged
    assert instance.gains[-1] == 2.5
    element.ec_producer.send("exposure_us", "auto")
    assert scheme.warm_up_steps is not None
    assert element.share["exposure_us"] == "auto"
    stop(scheme, stream)
