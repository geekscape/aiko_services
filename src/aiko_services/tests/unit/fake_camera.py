# FakeCamera: a hardware-free camera for the camera DataScheme tests, and
# StubElement / StubProducer, a PipelineElement stand-in.  Not a test
# module itself
#
# The fake lives here, not in a test module: pytest imports "test_*.py" as
# "unit.test_*", while a PipelineDefinition deploys elements from
# "aiko_services.tests.unit.*", which is a second module object.  A test
# that injects the fake into the deployed scheme module must patch the same
# class object that the test asserts on
#
# FakeCamera follows the Camera contract of elements/cameras/camera.py.
# Class attributes control its behaviour for the next test:
# - FAIL_OPEN:     open() raises RuntimeError("no device found")
# - FRAME_LIMIT:   capture() raises after this many frames (None: never)
# - LENS_SETTLES:  lens_position reads 0 for the first two frames, then a
#                  stable value, so a SettleMonitor of 3+ frames converges
# - INSTANCES:     every FakeCamera constructed since do_fake_initialize()

import logging
import time

import numpy as np

from aiko_services.elements.cameras import camera

__all__ = ["FakeCamera", "StubElement", "StubProducer",
           "do_fake_initialize"]

class FakeCamera(camera.Camera):
    FAIL_OPEN = False
    FRAME_LIMIT = None
    LENS_SETTLES = True
    INSTANCES = []

    def __init__(self, address=None, resolution=None, frame_rate=None,
        resize_mode="crop", trigger="off", aux_stream=True, logger=None):

        super().__init__(address, resolution, frame_rate, resize_mode,
                         trigger, aux_stream, logger)
        self.opened = False
        self.closed = False
        self.captured = 0
        self.exposures = []
        self.gains = []
        FakeCamera.INSTANCES.append(self)

    @classmethod
    def sdk_version(cls) -> str:
        return "fake-1.0"

    def open(self):
        if FakeCamera.FAIL_OPEN:
            raise RuntimeError("no device found")
        self.opened = True
        if self._resolution is None:
            self._resolution = camera.NATIVE_RESOLUTION

    def capture(self, timeout_s=camera.CAPTURE_TIMEOUT_S):
        if not self.opened or self.closed:
            raise RuntimeError("fake camera is not open")
        if FakeCamera.FRAME_LIMIT is not None  \
            and self.captured >= FakeCamera.FRAME_LIMIT:
            raise RuntimeError("capture failed")
        if self._frame_rate:
            time.sleep(1.0 / self._frame_rate)     # the camera's own pace
        width, height = self._resolution
        image = np.zeros((height, width, 3), dtype=np.uint8)
        image[0, 0, 0] = self.captured % 256       # the frame index
        lens = 0 if FakeCamera.LENS_SETTLES and self.captured < 2 else 120
        metadata = {"exposure_us": 15000.0, "iso_sensitivity": 800,
                    "lens_position": lens, "gain": 1.0}
        self.captured += 1
        return image, metadata

    def close(self):
        self.closed = True

    def device_id(self):
        return "fake-0"

    def set_exposure(self, exposure_us):
        self.exposures.append(float(exposure_us))
        return float(exposure_us)

    def set_gain(self, gain):
        self.gains.append(float(gain))
        return float(gain)

def do_fake_initialize():
    FakeCamera.FAIL_OPEN = False
    FakeCamera.FRAME_LIMIT = None
    FakeCamera.LENS_SETTLES = True
    FakeCamera.INSTANCES.clear()

# --------------------------------------------------------------------------- #

class StubProducer:
    """Records ec_producer.update() into the share and keeps handlers"""

    def __init__(self, share):
        self.share = share
        self.handlers = []
        self.updates = []

    def add_handler(self, handler):
        self.handlers.append(handler)

    def remove_handler(self, handler):
        self.handlers.remove(handler)

    def get(self, item_name):
        return self.share.get(item_name)

    def update(self, item_name, item_value):
        self.share[item_name] = item_value
        self.updates.append((item_name, item_value))
        for handler in list(self.handlers):      # as ECProducerImpl does
            handler("update", item_name, item_value)

    def send(self, item_name, item_value):
        """A dashboard "(update ...)" reaching the handlers"""

        for handler in list(self.handlers):
            handler("update", item_name, item_value)

class StubElement:
    """What a DataScheme needs from its PipelineElement, without the
    framework: parameters, share, logger, ec_producer and create_frames()
    that records instead of starting a thread"""

    def __init__(self, parameters=None):
        self.parameters = parameters or {}
        self.share = {}
        self.logger = logging.getLogger("stub_element")
        self.ec_producer = StubProducer(self.share)
        self.create_frames_calls = []

    def get_parameter(self, name, default=None, **_):
        return self.parameters.get(name, default), name in self.parameters

    def create_frames(self, stream, frame_generator, rate=None, **_):
        self.create_frames_calls.append((frame_generator, rate))

# --------------------------------------------------------------------------- #
