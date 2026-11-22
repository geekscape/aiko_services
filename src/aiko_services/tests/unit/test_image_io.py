# Usage
# ~~~~~
# pytest [-s] unit/test_image_io.py
#
# Tests of the ImageOverlay constructor (elements/media/image_io.py):
# defaults, parameter overrides, color parsing and fallback to defaults
# for invalid "color" and "font" parameters.  Skipped when OpenCV is absent
#
# To Do
# ~~~~~
# - Add tests for the rest of the file

import logging

import pytest

pytest.importorskip("cv2", reason="ImageOverlay needs cv2")
import cv2

import aiko_services as aiko
from aiko_services.elements.media.image_io import ImageOverlay
from aiko_services.main.pipeline import PipelineElementDefinition


def make_image_overlay(parameters=None):
    args = PipelineElementDefinition(
        name="ImageOverlay",
        input=[],
        output=[],
        parameters=parameters or {},
        deploy={}
    )
    init_args = aiko.pipeline_element_args("ImageOverlay", definition=args)
    return aiko.compose_instance(ImageOverlay, init_args)


# --------------------------------------------------------------------------- #

def test_defaults():
    overlay = make_image_overlay()
    assert overlay.color == ImageOverlay.DEFAULT_COLOR
    assert overlay.font == getattr(cv2, ImageOverlay.DEFAULT_FONT)
    assert overlay.font_scale == ImageOverlay.DEFAULT_FONT_SCALE
    assert overlay.thickness == ImageOverlay.DEFAULT_THICKNESS
    assert overlay.threshold == ImageOverlay.DEFAULT_THRESHOLD


def test_parameter_overrides():
    overlay = make_image_overlay(
        dict(
            color="#ff0000",
            font="FONT_HERSHEY_PLAIN",
            font_scale=1.5,
            thickness=4,
            threshold=0.5
        )
    )
    assert overlay.color == (255, 0, 0)
    assert overlay.font == cv2.FONT_HERSHEY_PLAIN
    assert overlay.font_scale == 1.5
    assert overlay.thickness == 4
    assert overlay.threshold == 0.5


@pytest.mark.parametrize("color, expected", [
    ("#f00", (255, 0, 0)),  # CSS short hex
    ("red", (255, 0, 0)),  # CSS named color
    ("#12345678", (18, 52, 86)),  # alpha channel is dropped
    ([1, 2, 3], (1, 2, 3)),  # non-string: list of RGB values
    ((9, 8, 7), (9, 8, 7)),  # non-string: tuple of RGB values
])
def test_color_accepted_forms(color, expected):
    assert make_image_overlay({"color": color}).color == expected


@pytest.mark.parametrize("color", ["notacolor", "#12", "rgb(1,2)"])
def test_invalid_color_uses_default(color, caplog):
    with caplog.at_level(logging.WARNING):
        overlay = make_image_overlay({"color": color})
    assert overlay.color == ImageOverlay.DEFAULT_COLOR
    assert "invalid parameter 'color" in caplog.text


@pytest.mark.parametrize("font", [
    "BOGUS",  # no "FONT_" prefix
    "FONT_DOES_NOT_EXIST",  # prefix, but not an attribute of cv2
    "FONT_HERSHEY_SIMPLEX_X",
    5,  # non-string
    None,
])
def test_invalid_font_uses_default(font, caplog):
    with caplog.at_level(logging.WARNING):
        overlay = make_image_overlay({"font": font})
    assert overlay.font == getattr(cv2, ImageOverlay.DEFAULT_FONT)
    assert "invalid parameter 'font" in caplog.text
