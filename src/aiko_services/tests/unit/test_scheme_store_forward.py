# Usage
# ~~~~~
# pytest [-s] unit/test_scheme_store_forward.py
#
# Pure tests of the "store_forward://" DataScheme: URL forms, registration
# and the create_targets() boundary checks, with a stub PipelineElement.
# Skipped when OpenCV is absent: "aiko_services.elements.media" imports cv2
# at module level (video_io.py)
#
# To Do
# ~~~~~
# - None, yet !

import os

import pytest
pytest.importorskip("cv2",
    reason="aiko_services.elements.media needs cv2 (video_io.py)")

import aiko_services as aiko
from aiko_services.elements.media.scheme_store_forward import (
    DataSchemeStoreForward
)

class _StubElement:
    """The two things the scheme needs from its PipelineElement"""

    def __init__(self, parameters=None):
        self.parameters = parameters or {}
        self.share = {}

    def get_parameter(self, name, default=None, **_):
        return self.parameters.get(name, default), name in self.parameters

def test_store_forward_scheme_registered():
    assert aiko.DataScheme.LOOKUP["store_forward"] is DataSchemeStoreForward

def test_url_path_forms(tmp_path):
    outbox = tmp_path / "outbox"
    outbox.mkdir()
    for url in (f"store_forward://{outbox}",       # absolute: three slashes
                f"store_forward:{outbox}"):
        stream = aiko.Stream(stream_id="1")
        scheme = DataSchemeStoreForward(_StubElement())
        assert scheme.create_targets(stream, [url])[0]  \
            == aiko.StreamEvent.OKAY, url
        assert stream.variables["target_outbox"] == os.path.realpath(outbox)
        assert stream.variables["target_prefix"] == ""    # default: none
        assert "target_segment_id" not in stream.variables

def test_home_relative_url(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "st").mkdir()
    stream = aiko.Stream(stream_id="1")
    scheme = DataSchemeStoreForward(_StubElement({"segment_prefix": "cam0"}))
    assert scheme.create_targets(stream, ["store_forward://~/st"])[0]  \
        == aiko.StreamEvent.OKAY
    assert stream.variables["target_outbox"] == os.path.realpath(tmp_path / "st")
    assert stream.variables["target_prefix"] == "cam0"

def test_boundary_errors(tmp_path):
    stream = aiko.Stream(stream_id="1")
    scheme = DataSchemeStoreForward(_StubElement())
    event, detail = scheme.create_targets(
        stream, [f"store_forward://{tmp_path}/missing"])
    assert event == aiko.StreamEvent.ERROR
    assert "not a directory" in detail["diagnostic"]

    for prefix in ("a b", "x" * 33):
        scheme = DataSchemeStoreForward(
            _StubElement({"segment_prefix": prefix}))
        event, detail = scheme.create_targets(
            stream, [f"store_forward://{tmp_path}"])
        assert event == aiko.StreamEvent.ERROR, prefix
        assert "segment_prefix" in detail["diagnostic"]

    scheme = DataSchemeStoreForward(_StubElement({"segment_prefix": ""}))
    event, _ = scheme.create_targets(stream, [f"store_forward://{tmp_path}"])
    assert event == aiko.StreamEvent.OKAY          # explicit "": no prefix
    assert stream.variables["target_prefix"] == ""

    event, detail = scheme.create_sources(stream, ["store_forward://x"])
    assert event == aiko.StreamEvent.ERROR      # target-only scheme
