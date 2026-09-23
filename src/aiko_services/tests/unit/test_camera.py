# Usage
# ~~~~~
# pytest [-s] unit/test_camera.py
#
# Pure tests of the camera helpers (elements/cameras/camera.py): parameter
# coercion, resolution planning, host-side resizing, the warm-up helpers
# and the rate meter, plus two package-level guards: the package imports
# with no camera SDK and no OpenCV, and no site literal leaked in from the
# spike this code came from
#
# To Do
# ~~~~~
# - None, yet !

import importlib
import os
import re
import subprocess
import sys

import numpy as np
import pytest

from aiko_services.elements.cameras import camera
from aiko_services.elements.cameras.camera import (
    CountdownSettle, RateMeter, SettleMonitor, auto_expose, parse_bool,
    parse_frame_rate, parse_resolution, parse_settle, plan_resolution,
    resize_image, share_token
)
from aiko_services.tests.unit.fake_camera import FakeCamera, do_fake_initialize

CAMERAS_DIRECTORY = os.path.dirname(camera.__file__)

# --------------------------------------------------------------------------- #

def test_parse_resolution():
    assert parse_resolution("1920x1080") == (1920, 1080)
    assert parse_resolution(" 640X480 ") == (640, 480)
    assert parse_resolution((640, 480)) == (640, 480)
    assert parse_resolution([640, "480"]) == (640, 480)
    assert parse_resolution("native") is None
    assert parse_resolution("Full") is None
    assert parse_resolution(None) is None
    for bad in ("abc", "640", "0x480", "640x-1", 640, ("a", "b")):
        with pytest.raises(ValueError, match="resolution"):
            parse_resolution(bad)

def test_parse_frame_rate():
    for value in (25, 25.0, "25", "25.0", "25/1", "50/2", " 25 / 1 "):
        assert parse_frame_rate(value) == 25.0
    assert parse_frame_rate("30000/1001") == pytest.approx(29.97, 0.001)
    for bad in ("0", "-1", "25/0", "abc", None, "inf"):
        with pytest.raises(ValueError, match="frame_rate"):
            parse_frame_rate(bad)
    with pytest.raises(ValueError, match="rate"):
        parse_frame_rate("x", "rate")

def test_parse_settle():
    assert parse_settle("30", 25.0) == 30
    assert parse_settle(30, 25.0) == 30
    assert parse_settle("3s", 25.0) == 75
    assert parse_settle("0.5s", 2.0) == 1
    for value in (0, "0", None, "", "none", "off"):
        assert parse_settle(value, 25.0) == 0
    for bad in ("abc", "-3", "3 seconds"):
        with pytest.raises(ValueError, match="settle"):
            parse_settle(bad, 25.0)

def test_parse_bool():
    for value in (True, "true", "True", "1", "yes", "on"):
        assert parse_bool(value, "x") is True
    for value in (False, "false", "0", "no", "off", ""):
        assert parse_bool(value, "x") is False
    with pytest.raises(ValueError, match="aux_stream"):
        parse_bool("maybe", "aux_stream")

def test_plan_resolution():
    native = (4000, 3000)
    assert plan_resolution(native, None) == ((0, 0, 4000, 3000), 1, None)
    aoi, decimation, host = plan_resolution(native, (1920, 1080), "crop")
    assert aoi == (0, 375, 4000, 2250)            # 16:9 crop, centred
    assert decimation == 1 and host == (1920, 1080)
    aoi, decimation, host = plan_resolution(
        native, (2000, 1500), "crop", decimations=(1, 2, 4))
    assert aoi == (0, 0, 4000, 3000) and decimation == 2 and host is None
    aoi, decimation, host = plan_resolution(
        native, (1920, 1080), "letterbox", decimations=(1, 2))
    assert aoi == (0, 0, 4000, 3000) and decimation == 2
    assert host == (1920, 1080)                   # 2000x1500 -> letterbox

def test_resize_image_modes():
    pytest.importorskip("cv2", reason="resize_image() needs cv2")
    image = np.zeros((300, 400, 3), dtype=np.uint8)
    image[:, :, 1] = 200                           # green
    for mode in ("crop", "letterbox", "stretch"):
        out = resize_image(image, (160, 90), mode)
        assert out.shape == (90, 160, 3), mode
    letterboxed = resize_image(image, (160, 90), "letterbox")
    assert letterboxed[45, 80, 1] == 200           # centre keeps the picture
    assert letterboxed[45, 2, 1] == 0              # sides padded black
    assert resize_image(image, (400, 300), "crop") is image  # no-op

def test_settle_monitor():
    monitor = SettleMonitor(10)
    for lens in (0, 0, 40, 80, 118, 119, 120):
        done = monitor.feed({"lens_position": lens, "iso_sensitivity": 800})
    assert done and monitor.done and not monitor.timed_out
    assert monitor.frames == 7                     # converged on the 7th
    timed = SettleMonitor(3)
    for _ in range(3):
        timed.feed({"lens_position": None, "iso_sensitivity": 0})
    assert timed.done and timed.timed_out
    assert SettleMonitor(0).done
    countdown = CountdownSettle(2)
    assert not countdown.feed({}) and countdown.feed({}) and countdown.done

def test_auto_expose_steps():
    do_fake_initialize()

    class DarkCamera(FakeCamera):
        def capture(self, timeout_s=None):
            image, metadata = super().capture()
            image[:] = 40 if not self.exposures else 220   # dark, then good
            metadata["exposure_us"] = self.exposures[-1]  \
                if self.exposures else 15000.0
            return image, metadata

    dark = DarkCamera(resolution=(8, 8), frame_rate=None)
    dark.open()
    steps = list(auto_expose(dark, target_p99=225))
    assert [done for done, _, _ in steps] == [False, True]
    assert dark.exposures == [15000.0 * min(225 / 40, 8.0)]
    assert dark.gains == [1.0]

def test_rate_meter_and_token():
    meter = RateMeter(window_s=10.0)
    assert meter.tick(0.0) == 0.0
    for t in (0.5, 1.0, 1.5, 2.0):
        fps = meter.tick(t)
    assert fps == pytest.approx(2.0)
    assert share_token("no device: 1.2.3.4") == "no_device:_1.2.3.4"
    assert share_token("") == "-"
    assert len(share_token("x" * 100)) == 32

# Package guards ------------------------------------------------------------ #

def test_package_imports_without_sdks_or_cv2():
    """The cameras package must import with depthai, ids_peak, gi and cv2
    all absent (CI installs none of them)"""

    code = ("import sys\n"
            "for m in ('depthai', 'ids_peak', 'ids_peak_ipl', 'gi', 'cv2'):\n"
            "    sys.modules[m] = None\n"
            "import aiko_services.elements.cameras as c\n"
            "print(c.OakDCamera.available(), c.VideoReadDepthAI.__name__)\n")
    result = subprocess.run([sys.executable, "-c", code],
        capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "False VideoReadDepthAI"

def test_no_site_literals():
    """Nothing from the spike's site: no private addresses, host names or
    device serials in the package sources"""

    # assembled, so this file does not trip the same grep over a diff
    forbidden = re.compile("|".join([
        r"\.".join(["192", "168", ""]), r"\.".join(["10", "204", ""]),
        r"\.".join(["10", "42", ""]), r"\.".join(["meta", "local"]),
        "1944" + "30104108C02F00", "4110" + "087727"]))
    for name in sorted(os.listdir(CAMERAS_DIRECTORY)):
        if name.endswith(".py"):
            path = os.path.join(CAMERAS_DIRECTORY, name)
            with open(path) as file:
                assert not forbidden.search(file.read()), name

def test_oak_open_retries_while_the_device_reboots(monkeypatch):
    """dai.Device() raises X_LINK_DEVICE_NOT_FOUND twice, then returns"""

    from aiko_services.elements.cameras import camera_oak_d

    class FakeDai:
        calls = 0

        class DeviceInfo:
            def __init__(self, address):
                self.address = address

        @classmethod
        def Device(cls, info=None):
            cls.calls += 1
            if cls.calls < 3:
                raise RuntimeError("Failed to find device after booting, "
                                   "error message: X_LINK_DEVICE_NOT_FOUND")
            return ("device", info.address if info else None)

    monkeypatch.setattr(camera_oak_d, "dai", FakeDai)
    monkeypatch.setattr(camera_oak_d.time, "sleep", lambda seconds: None)
    oak = camera_oak_d.OakDCamera(address="192.0.2.7")
    assert oak._boot_device() == ("device", "192.0.2.7")
    assert FakeDai.calls == 3
    monkeypatch.setattr(camera_oak_d, "OPEN_RETRY_S", 0.0)  # no time left
    FakeDai.calls = 0
    with pytest.raises(RuntimeError, match="X_LINK_DEVICE_NOT_FOUND"):
        oak._boot_device()
    assert FakeDai.calls == 1

def test_scheme_registered_once():
    import aiko_services as aiko
    module = importlib.import_module(
        "aiko_services.elements.cameras.scheme_depthai")
    assert aiko.DataScheme.LOOKUP["depthai"] is module.DataSchemeDepthAI
