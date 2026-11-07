# Usage
# ~~~~~
# pytest [-s] unit/test_media_imports.py
#
# Unit tests for importing "elements.media" on a host with no OpenCV
# (elements/media/video_io.py).
#
# Every element in that package guards its own "import cv2" and reports a
# missing OpenCV from start_stream(), where a person can act on it.  One
# module then undid all of that: video_io.py built a table of cv2 constants
# at module level, outside the guard, so importing it raised a NameError
# and the whole package was unimportable.
#
# It went unnoticed because nothing imported the package without OpenCV
# until 2026-11-05.  Then one new test did, and every Python version in CI
# failed to collect.
#
# These tests need no OpenCV and must not gain a skip.  A skip here is the
# fault coming back.

import inspect


def test_the_package_imports_without_opencv():
    """It is imported by this test file either way, so reaching this line
    is the assertion.  The skip that every other test in this package
    needs is what this one must never have"""

    import aiko_services.elements.media  # noqa: F401


def test_the_writer_imports_without_opencv():
    from aiko_services.elements.media.store_forward_io import VideoWriteStoreForward

    assert VideoWriteStoreForward is not None


def test_no_opencv_constant_is_read_while_the_module_is_read():
    """The shape of the fault, and the guard against it returning.  A cv2
    name at the left margin runs at import, where the guard cannot help"""

    from aiko_services.elements.media import video_io

    source = inspect.getsource(video_io)
    offenders = []
    for number, line in enumerate(source.splitlines(), start=1):
        if line[:1] in (" ", "\t", "#", ""):
            continue  # Indented, a comment, or blank
        if line.startswith(("import ", "from ", "try:", "except", "def ", "class ", "@")):
            continue
        if "cv2." in line:
            offenders.append((number, line.strip()))
    assert offenders == [], offenders


# The back end lookup ------------------------------------------------------ #


def test_the_back_end_is_auto_select_without_opencv(monkeypatch):
    """0 is OpenCV's "choose for yourself".  Returning it means the one
    call that wants a camera fails at the camera, and not at an import.

    The guard is read rather than the environment, so this covers the case
    CI has even on a host where OpenCV is installed"""

    import aiko_services.elements.media.video_io as video_io

    monkeypatch.setattr(video_io, "_CV2_IMPORTED", False)
    assert video_io.camera_api("linux") == 0
    assert video_io.camera_api("darwin") == 0
    assert video_io.camera_api() == 0  # This platform, too


def test_an_unknown_platform_is_auto_select():
    from aiko_services.elements.media.video_io import camera_api

    assert camera_api("plan9") == 0


def test_each_platform_has_a_back_end_where_opencv_is_there():
    import aiko_services.elements.media.video_io as video_io

    if not video_io._CV2_IMPORTED:
        return  # Nothing to look up
    for system in ("darwin", "linux", "windows"):
        assert isinstance(video_io.camera_api(system), int), system
