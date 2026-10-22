#!/usr/bin/env python3
#
# Aiko Services: WhisPlay Actor, the camera
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# Where the picture comes from.  One Interface, two Implementations: a
# Raspberry Pi camera through picamera2, and a test pattern.
#
# picamera2 needs the libcamera Python bindings, which are an operating
# system package (python3-libcamera) and are not on PyPI.  So a virtual
# environment must be made with "--system-site-packages" to reach the
# camera.  The ReadMe beside this file says so, because the failure is a
# plain ImportError a long way from its cause.
#
# To Do
# ~~~~~
# * Take any video source, through the standard DataScheme and DataSource,
#   instead of only a Raspberry Pi camera.  Then this Interface goes away

from abc import abstractmethod

import numpy

import aiko_services as aiko

from aiko_services.actors.whisplay.frame import IMAGE_SIZE

__all__ = [
    "Camera", "CameraNotFound", "FakeCameraImpl", "Picamera2CameraImpl",
    "camera_args", "choose_camera"
]

class CameraNotFound(OSError):
    """No camera, or no bindings to reach one"""

class Camera(aiko.Interface):
    """Where frames come from.  open(size) acquires the camera at that
    resolution and raises CameraNotFound when it can't, capture() returns one
    HxWx3 array of RGB, and close() releases it.  Every function is called
    from the Actor's own worker thread, which owns this object"""

    aiko.Interface.default(
        "Camera", "aiko_services.actors.whisplay.camera.FakeCameraImpl")

    @abstractmethod
    def open(self, size=IMAGE_SIZE):
        """Acquire the camera; raises CameraNotFound"""

    @abstractmethod
    def capture(self):
        """One HxWx3 array of RGB"""

    @abstractmethod
    def close(self):
        """Release the camera"""

class FakeCameraImpl(Camera):
    """No camera: the default Impl, and the test double.  capture() returns
    a test pattern of the right shape, so the frame path is exercised"""

    device = "none"

    def __init__(self, context, **_):
        self.size = IMAGE_SIZE
        self.captures = 0

    def open(self, size=IMAGE_SIZE):
        self.size = size

    def capture(self):
        width, height = self.size
        frame = numpy.zeros((height, width, 3), dtype=numpy.uint8)
        frame[:, :, self.captures % 3] = 255       # A different plane each time
        self.captures += 1
        return frame

    def close(self):
        pass

class Picamera2CameraImpl(Camera):
    """A Raspberry Pi camera, through picamera2"""

    device = "picamera2"

    def __init__(self, context, **_):
        self.size = IMAGE_SIZE
        self._camera = None

    def open(self, size=IMAGE_SIZE):
        try:
            from picamera2 import Picamera2         # only needed here
        except ImportError as import_error:
            raise CameraNotFound(
                "picamera2 is not available: a virtual environment needs "
                f'"--system-site-packages" to reach it ({import_error})')

        self.size = size
        self._camera = Picamera2()
        self._camera.configure(self._camera.create_preview_configuration(
            main={"size": tuple(size), "format": "RGB888"}))
        self._camera.start()

    def capture(self):
        if self._camera is None:
            raise CameraNotFound("capture() before open()")
        return self._camera.capture_array("main")

    def close(self):
        if self._camera is not None:
            self._camera.stop()
            self._camera.close()
            self._camera = None

# Composition -------------------------------------------------------------- #

def camera_args(**parameters):
    """init_args for composing a Camera Impl"""

    return {"context": aiko.Context(), **parameters}

def choose_camera(camera="auto", **parameters):
    """The composed Camera.  "auto" is a Raspberry Pi camera where picamera2
    can be imported, and the test pattern everywhere else.  Nothing is opened
    here: see open()"""

    import importlib.util

    if camera == "auto":
        camera = "picamera2" if importlib.util.find_spec("picamera2") else "none"
    impls = {"picamera2": Picamera2CameraImpl, "none": FakeCameraImpl}
    if camera not in impls:
        raise ValueError(f'unknown camera "{camera}": one of {sorted(impls)}')
    return aiko.compose_instance(impls[camera], camera_args(**parameters))

# --------------------------------------------------------------------------- #
