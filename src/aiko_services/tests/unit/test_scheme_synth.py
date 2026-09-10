# Usage
# ~~~~~
# pytest [-s] unit/test_scheme_synth.py
#
# Pure function tests for the "synth://" DataScheme helpers: URL parsing,
# option validation and frame rendering.  Skipped when OpenCV is absent:
# "aiko_services.elements.media" imports cv2 at module level (video_io.py)
#
# To Do
# ~~~~~
# - None, yet !

import pytest
pytest.importorskip("cv2",
    reason="aiko_services.elements.media needs cv2 (video_io.py)")

import numpy as np

import aiko_services as aiko
from aiko_services.elements.media.scheme_synth import (
    _FACTORIES, _format_timestamp, DataSchemeSynthetic,
    parse_synth_url, render_text_frame
)

TIMESTAMP = 1788000000.123  # 2026-08-29T10:40:00.123Z

# --------------------------------------------------------------------------- #

def _bounding_box(image, background=0):
    mask = (image != background).any(axis=2)
    rows = np.flatnonzero(mask.any(axis=1))
    columns = np.flatnonzero(mask.any(axis=0))
    return columns[0], rows[0], columns[-1], rows[-1]  # x0, y0, x1, y1

def test_default_frame_is_1080p_uint8():
    frame = render_text_frame(7, TIMESTAMP)
    assert frame.shape == (1080, 1920, 3)
    assert frame.dtype == np.uint8
    assert frame.flags.writeable

def test_frame_is_white_text_on_black():
    frame = render_text_frame(42, TIMESTAMP)
    assert np.array_equal(frame[..., 0], frame[..., 1])  # grey: no color
    assert np.array_equal(frame[..., 0], frame[..., 2])
    assert frame.max() == 255, "no white text pixels"
    assert (frame == 0).mean() > 0.9, "background must be pure black"

def test_frames_differ_by_frame_id_and_timestamp():
    assert not np.array_equal(
        render_text_frame(0, TIMESTAMP), render_text_frame(1, TIMESTAMP))
    assert not np.array_equal(
        render_text_frame(0, TIMESTAMP), render_text_frame(0, TIMESTAMP + 1))
    assert np.array_equal(
        render_text_frame(5, TIMESTAMP), render_text_frame(5, TIMESTAMP))

def test_custom_resolution():
    assert render_text_frame(3, TIMESTAMP, 640, 360).shape == (360, 640, 3)

@pytest.mark.parametrize("frame_id", [0, 999999, 123456789])
def test_text_fits_and_is_centered(frame_id):
    frame = render_text_frame(frame_id, TIMESTAMP)
    x0, y0, x1, y1 = _bounding_box(frame)
    assert x0 > 0 and y0 > 0 and x1 < 1919 and y1 < 1079, "text clipped"
    assert abs((x0 + x1) / 2 - 960) <= 1920 * 0.05
    assert abs((y0 + y1) / 2 - 540) <= 1080 * 0.05

def test_text_items():
    both = render_text_frame(1, TIMESTAMP, 320, 240)
    frame_id_only = render_text_frame(1, TIMESTAMP, 320, 240, ("frame_id",))
    timestamp_only = render_text_frame(1, TIMESTAMP, 320, 240, ("timestamp",))
    none = render_text_frame(1, TIMESTAMP, 320, 240, ())
    assert not none.any(), "text none must be a blank frame"
    assert (frame_id_only > 0).sum() < (both > 0).sum()
    assert (timestamp_only > 0).sum() < (both > 0).sum()
    assert not np.array_equal(frame_id_only, timestamp_only)

def test_colors():
    frame = render_text_frame(8, TIMESTAMP, 320, 240,
        color=(255, 136, 0), background=(0, 0, 64))
    assert tuple(frame[0, 0]) == (0, 0, 64)
    reds = frame[..., 0]
    assert reds.max() == 255 and tuple(frame[reds == 255][0]) == (255, 136, 0)

def test_format_timestamp():
    assert _format_timestamp(TIMESTAMP) == "2026-08-29T10:40:00.123Z"
    assert _format_timestamp(0) == "1970-01-01T00:00:00.000Z"

# --------------------------------------------------------------------------- #

def test_parse_synth_url_defaults():
    assert parse_synth_url("synth://") == ("video", "plain", {})
    assert parse_synth_url("synth://video") == ("video", "plain", {})
    assert parse_synth_url("synth://VIDEO/Plain") == ("video", "plain", {})

def test_parse_synth_url_options():
    kind, pattern, options = parse_synth_url(
        "synth://video/plain?width=640&height=360&text=frame_id&color=ff8800")
    assert (kind, pattern) == ("video", "plain")
    assert options == {
        "width": "640", "height": "360", "text": "frame_id", "color": "ff8800"}

def test_parse_synth_url_errors():
    with pytest.raises(ValueError):
        parse_synth_url("synth://video/a/b")
    with pytest.raises(ValueError):
        parse_synth_url("synth://video/plain?width=1&width=2")
    with pytest.raises(ValueError):
        parse_synth_url("file:data_in/in_00.jpeg")

def test_video_plain_factory():
    factory = _FACTORIES[("video", "plain")]
    render = factory({"width": "640", "height": "360", "text": "frame_id",
                      "color": "orange", "background": "000040"})
    frame_data = render(3, TIMESTAMP)
    assert list(frame_data) == ["images"]
    assert frame_data["images"][0].shape == (360, 640, 3)
    render = factory({"text": "none"})
    assert not render(0, TIMESTAMP)["images"][0].any()

@pytest.mark.parametrize("options", [
    {"width": "abc"}, {"width": "0"}, {"height": "-1"},
    {"text": "frame_id,bogus"}, {"color": "not_a_color"},
    {"background": "12345"}, {"resolution": "640x360"}])
def test_video_plain_factory_errors(options):
    with pytest.raises(ValueError):
        _FACTORIES[("video", "plain")](options)

def test_synth_scheme_registered():
    assert aiko.DataScheme.LOOKUP["synth"] is DataSchemeSynthetic
