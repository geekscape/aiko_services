# Usage
# ~~~~~
# pytest [-s] unit/test_video_io_mp4_repair.py
#
# Unit tests for the handling, in elements/media/video_io.py, of an H.264
# MP4 file whose first sample holds only the parameter sets (SPS, PPS),
# as the Raspberry Pi hardware encoder writes it (mp4_repair.py).
#
# - VideoWriteFile and VideoWriteFiles repair each file after release()
# - VideoReadFile does not stop at a failed read while the file still has
#   frames.  OpenCV's first read() of such a file fails and the next one
#   succeeds, so a loop that stops at the first failure reads no frame
#
# The writers are tested with MP4 files built in memory, and the reader
# with a scripted capture object and a stand-in for the three cv2 names
# it uses.  So no encoder, no video file and no OpenCV is needed, and the
# tests run where the "test" extra is installed without "video".

import types

import numpy as np
import pytest

import aiko_services.elements.media.video_io as video_io
from aiko_services.elements.media.video_io import (
    VideoReadFile, VideoWriteFile, VideoWriteFiles, _READ_FAILURES_MAXIMUM
)
from aiko_services.tests.unit.test_mp4_repair import (
    build, encoder_shape, frame, key_frame, parameter_sets
)

cv2 = types.SimpleNamespace(
    CAP_PROP_FRAME_COUNT=7, CAP_PROP_POS_FRAMES=1, COLOR_BGR2RGB=4,
    cvtColor=lambda image, code: image[..., ::-1])

@pytest.fixture(autouse=True)
def without_opencv(monkeypatch):
    monkeypatch.setattr(video_io, "cv2", cv2, raising=False)

# VideoReadFile.video_frame_iterator() --------------------------------------- #

class ScriptedCapture:
    """A cv2.VideoCapture stand-in: each read() takes the next result.
    The position advances on every read, as OpenCV's does"""

    def __init__(self, results, frame_count):
        self.results = list(results)
        self.frame_count = frame_count
        self.position = 0
        self.reads = 0

    def read(self):
        self.reads += 1
        self.position += 1
        if not self.results:
            return False, None
        return self.results.pop(0)

    def get(self, property_id):
        if property_id == cv2.CAP_PROP_FRAME_COUNT:
            return float(self.frame_count)
        if property_id == cv2.CAP_PROP_POS_FRAMES:
            return float(self.position)
        raise AssertionError(f"unexpected property {property_id}")

IMAGE = np.zeros((4, 6, 3), np.uint8)
GOOD = (True, IMAGE)
FAIL = (False, None)

def frames_read(capture):
    return len(list(VideoReadFile.video_frame_iterator(None, capture)))

def test_a_failed_first_read_is_passed_over():
    capture = ScriptedCapture([FAIL] + [GOOD] * 10, frame_count=11)
    assert frames_read(capture) == 10

def test_a_file_that_reads_cleanly_yields_every_frame():
    capture = ScriptedCapture([GOOD] * 10, frame_count=10)
    assert frames_read(capture) == 10

def test_the_end_of_the_file_stops_at_once():
    capture = ScriptedCapture([GOOD] * 10, frame_count=10)
    frames_read(capture)
    assert capture.reads == 11          # ten frames and one failed read

def test_a_stream_with_no_frame_count_stops_at_the_first_failure():
    capture = ScriptedCapture([FAIL] + [GOOD] * 5, frame_count=0)
    assert frames_read(capture) == 0

def test_failed_reads_in_a_row_are_bounded():
    failures = [FAIL] * (_READ_FAILURES_MAXIMUM + 1)
    capture = ScriptedCapture(failures + [GOOD] * 5, frame_count=100)
    assert frames_read(capture) == 0
    assert capture.reads == _READ_FAILURES_MAXIMUM + 1

def test_the_bound_counts_failures_in_a_row_only():
    script = ([FAIL] * _READ_FAILURES_MAXIMUM + [GOOD]) * 3
    capture = ScriptedCapture(script, frame_count=100)
    assert frames_read(capture) == 3

def test_frames_are_converted_to_rgb():
    bgr = np.zeros((2, 2, 3), np.uint8)
    bgr[..., 0] = 255                   # blue, in OpenCV's BGR order
    capture = ScriptedCapture([FAIL, (True, bgr)], frame_count=2)
    image = next(VideoReadFile.video_frame_iterator(None, capture))
    assert image[0, 0].tolist() == [0, 0, 255]

# VideoWriteFile and VideoWriteFiles ----------------------------------------- #

class FakeWriter:
    def __init__(self):
        self.released = False

    def release(self):
        self.released = True

class FakeLogger:
    def __init__(self):
        self.infos, self.warnings = [], []

    def info(self, message):
        self.infos.append(message)

    def warning(self, message):
        self.warnings.append(message)

class Element:
    """Only what the writers' release paths touch.  The methods are called
    unbound, so the code under test is the real one"""

    def __init__(self):
        self.logger = FakeLogger()

    def my_id(self):
        return "element"

class FakeStream:
    def __init__(self, variables):
        self.variables = variables

def clean_file():
    samples = [parameter_sets() + key_frame()] + [frame(i) for i in range(9)]
    return build(samples, [2048] * 10, [1], [(1, 10, 1)])

def stop_video_write_file(tmp_path, data):
    path = tmp_path / "video.mp4"
    path.write_bytes(data)
    element, writer = Element(), FakeWriter()
    stream = FakeStream({"video_writer": writer, "video_path": str(path)})
    VideoWriteFile.stop_stream(element, stream, 0)
    return element, writer, stream, path

def test_video_write_file_repairs_on_stop(tmp_path):
    data, _ = encoder_shape()
    element, writer, stream, path = stop_video_write_file(tmp_path, data)
    assert writer.released and stream.variables["video_writer"] is None
    assert len(path.read_bytes()) == len(data) - 12
    assert len(element.logger.infos) == 1

def test_video_write_file_leaves_a_clean_file_alone(tmp_path):
    data = clean_file()
    element, _, _, path = stop_video_write_file(tmp_path, data)
    assert path.read_bytes() == data
    assert element.logger.infos == []

def test_video_write_file_with_no_writer_checks_nothing(tmp_path):
    element = Element()
    stream = FakeStream({"video_writer": None,
                         "video_path": str(tmp_path / "missing.mp4")})
    VideoWriteFile.stop_stream(element, stream, 0)
    assert element.logger.infos == [] and element.logger.warnings == []

def test_video_write_files_repairs_when_a_file_closes(tmp_path):
    data, _ = encoder_shape()
    path = tmp_path / "00m_00s.mp4"
    path.write_bytes(data)
    element = Element()
    stream = FakeStream({"video_writer": FakeWriter(),
                         "video_pathname": str(path)})
    VideoWriteFiles._destroy_video_writer(element, stream)
    assert stream.variables["video_writer"] is None
    assert len(path.read_bytes()) == len(data) - 12

def test_a_file_that_cannot_be_read_is_logged_not_raised(tmp_path):
    element = Element()
    stream = FakeStream({"video_writer": FakeWriter(),
                         "video_pathname": str(tmp_path / "missing.mp4")})
    VideoWriteFiles._destroy_video_writer(element, stream)
    assert len(element.logger.warnings) == 1
