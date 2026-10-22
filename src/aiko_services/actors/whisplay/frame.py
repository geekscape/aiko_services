#!/usr/bin/env python3
#
# Aiko Services: WhisPlay Actor, the frame
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# One picture for the panel: the camera image above a block of text.
#
# The camera resolution is 240x180 on purpose.  It fills the 240 pixel width
# of the panel exactly, which means no horizontal scaling, and it leaves
# 240x100 underneath for the text: state, battery level, IP address.
#
# Every function here is pure.  Give it an image and some lines, and it
# returns a picture.  Nothing opens a device, so the tests need no hardware.
#
# To Do
# ~~~~~
# * A font size that follows the text area, instead of one constant
# * Right-aligned values, for a two column layout

from PIL import Image, ImageDraw, ImageFont
import numpy

__all__ = [
    "IMAGE_SIZE", "PANEL_SIZE", "TEXT_LINES", "TEXT_SIZE", "compose",
    "parse_resolution", "to_rgb565"
]

PANEL_SIZE = (240, 280)        # The WhisPlay panel, width x height
IMAGE_SIZE = (240, 180)        # The camera image, at the top
TEXT_SIZE = (240, 100)         # What is left for text, underneath
TEXT_MARGIN = 4
TEXT_SIZE_POINTS = 14
TEXT_LEADING = 3
TEXT_LINES = 4                 # What fits in 100 pixels at this size

def parse_resolution(text, default=IMAGE_SIZE):
    """(width, height) from "240x180".  Raises ValueError on anything else"""

    parts = str(text).lower().split("x")
    if len(parts) != 2:
        raise ValueError(f'resolution must be "WIDTHxHEIGHT", not "{text}"')
    width, height = (int(part) for part in parts)
    if width < 1 or height < 1:
        raise ValueError(f"resolution must be positive, not {width}x{height}")
    return width, height

def compose(image=None, lines=(), panel_size=PANEL_SIZE,
    image_size=IMAGE_SIZE, rotate=0, font=None):

    """The panel frame: the camera image at the top, text underneath.

    image:       a PIL Image or a HxWx3 array of RGB, or None for no image
    lines:       the text lines, in order, from the top of the text area
    panel_size:  the panel, width x height
    image_size:  where the camera image goes, at the top
    rotate:      degrees to turn the camera image, 0, 90, 180 or 270
    font:        a PIL font, or None for the default at TEXT_SIZE_POINTS
    """

    frame = Image.new("RGB", panel_size, (0, 0, 0))
    if image is not None:
        if not isinstance(image, Image.Image):
            image = Image.fromarray(numpy.asarray(image)[:, :, :3], "RGB")
        if rotate:
            image = image.rotate(rotate, expand=True)
        if image.size != tuple(image_size):
            image = image.resize(tuple(image_size))
        frame.paste(image, (0, 0))

    if font is None:
        font = ImageFont.load_default(size=TEXT_SIZE_POINTS)
    draw = ImageDraw.Draw(frame)
    y = image_size[1] + TEXT_MARGIN
    for line in list(lines)[:TEXT_LINES]:
        draw.text((TEXT_MARGIN, y), str(line), font=font, fill=(255, 255, 255))
        y += TEXT_SIZE_POINTS + TEXT_LEADING
    return frame

def to_rgb565(image):
    """Big-endian RGB565 bytes, which is what the ST7789 reads"""

    pixels = numpy.asarray(image.convert("RGB"), dtype=numpy.uint16)
    red = (pixels[:, :, 0] >> 3) << 11
    green = (pixels[:, :, 1] >> 2) << 5
    blue = pixels[:, :, 2] >> 3
    return (red | green | blue).astype(">u2").tobytes()

# --------------------------------------------------------------------------- #
