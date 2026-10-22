#!/usr/bin/env python3
#
# Aiko Services: WhisPlay Actor, the frame
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# One picture for the panel: the camera image, a line of text over the foot
# of it, and rows of text underneath.
#
# The camera resolution is 240x180 on purpose.  It fills the 240 pixel width
# of the panel exactly, which means no horizontal scaling, and it leaves
# 240x100 underneath for four rows of text.
#
# Each row has a left, a centre and a right part, so that a name and an
# address sit at the two ends of one row.
#
# The glass has rounded corners with no pixels.  The curve takes about the
# bottom 25 pixels, which is exactly the last row, so that row is inset
# further than the others.
#
# Every function here is pure.  Give it an image and some rows, and it
# returns a picture.  Nothing opens a device, so the tests need no hardware.
#
# To Do
# ~~~~~
# * Rows 3 and 4 are empty: the battery, and the newest log line
# * A font that scales with the text area, for a different panel

from PIL import Image, ImageDraw, ImageFont
import numpy

__all__ = [
    "CORNER_MARGIN", "CORNER_ROWS", "IMAGE_SIZE", "MARGIN", "PANEL_SIZE",
    "FIELD_PLACES", "ROW_HEIGHT", "TEXT_LINES", "TEXT_SIZE", "compose",
    "parse_resolution", "row_margin", "to_rgb565"
]

PANEL_SIZE = (240, 280)        # The WhisPlay panel, width x height
IMAGE_SIZE = (240, 180)        # The camera image, at the top
TEXT_SIZE = (240, 100)         # What is left for text, underneath

TEXT_LINES = 4                 # Rows under the image
ROW_HEIGHT = TEXT_SIZE[1] // TEXT_LINES                  # 25 pixels each
TEXT_SIZE_POINTS = ROW_HEIGHT - 5                        # Room for descenders
MARGIN = 6                     # From the sides, for a row clear of the curve
# The curve takes about the bottom 25 pixels, which is the last row exactly
CORNER_ROWS = 1
CORNER_MARGIN = 20             # How far that row is inset instead

OVERLAY_STROKE = 2             # An outline, so text over the image is legible

# A "fields" row holds three readings, each a prefix, a number and a
# suffix: ("C:", "100", "%").  The letters never move, and the number is
# right aligned, so one digit or three, the last digit is in the same
# place.  Measured at 20 point: "C:" 19px, "M:" 22px, "%" 15px, "C" 14px
# and the widest number "100" 36px, which leaves 12 and 15 pixels between
# the fields at their widest.  Each pair is (where the prefix starts,
# where the number ends)
FIELD_PLACES = ((6, 65), (92, 154), (184, 220))

def parse_resolution(text, default=IMAGE_SIZE):
    """(width, height) from "240x180".  Raises ValueError on anything else"""

    parts = str(text).lower().split("x")
    if len(parts) != 2:
        raise ValueError(f'resolution must be "WIDTHxHEIGHT", not "{text}"')
    width, height = (int(part) for part in parts)
    if width < 1 or height < 1:
        raise ValueError(f"resolution must be positive, not {width}x{height}")
    return width, height

def row_margin(row):
    """How far row "row" is inset from the sides.  The bottom rows are inset
    further, because the glass has rounded corners with no pixels"""

    return CORNER_MARGIN if row >= TEXT_LINES - CORNER_ROWS else MARGIN

def _draw_row(draw, parts, top, width, margin, font, fill, stroke=0,
    align="spread"):

    """One row: the left, centre and right parts of it.  Any may be None.

    align "spread" puts them at the left, the centre and the right.
    align "fields" takes three (prefix, number, suffix) readings and puts
    the letters at fixed places, with the number right aligned between
    them, so that a reading does not move as it gains a digit"""

    left, centre, right = (list(parts) + [None, None, None])[:3]
    outline = {"stroke_width": stroke, "stroke_fill": (0, 0, 0)} if stroke else {}
    if align == "fields":
        for part, (prefix_x, value_x) in zip(parts, FIELD_PLACES):
            if not part:
                continue
            prefix, value, suffix = (list(part) + ["", "", ""])[:3]
            if prefix:
                draw.text((prefix_x, top), str(prefix), font=font, fill=fill,
                          anchor="la", **outline)
            if value != "":
                draw.text((value_x, top), str(value), font=font, fill=fill,
                          anchor="ra", **outline)
            if suffix:
                draw.text((value_x, top), str(suffix), font=font, fill=fill,
                          anchor="la", **outline)
        return
    if left:
        draw.text((margin, top), str(left), font=font, fill=fill,
                  anchor="la", **outline)
    if centre:
        draw.text((width // 2, top), str(centre), font=font, fill=fill,
                  anchor="ma", **outline)
    if right:
        draw.text((width - margin, top), str(right), font=font, fill=fill,
                  anchor="ra", **outline)

def compose(image=None, rows=(), overlay=None, panel_size=PANEL_SIZE,
    image_size=IMAGE_SIZE, rotate=0, font=None, aligns=()):

    """The panel frame.

    image:      a PIL Image or a HxWx3 array of RGB, or None for no image
    rows:       the text rows, each a (left, centre, right) or one string
    overlay:    a (left, centre, right) drawn over the foot of the image
    rotate:     degrees to turn the camera image, 0, 90, 180 or 270
    aligns:     "spread" or "fields" for each row, "spread" where not given
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
    width = panel_size[0]

    if overlay:
        parts = [overlay] if isinstance(overlay, str) else overlay
        _draw_row(draw, parts, image_size[1] - ROW_HEIGHT, width, MARGIN,
                  font, (255, 255, 255), stroke=OVERLAY_STROKE)

    aligns = list(aligns) + ["spread"] * TEXT_LINES
    for row, parts in enumerate(list(rows)[:TEXT_LINES]):
        parts = [parts] if isinstance(parts, str) else parts
        _draw_row(draw, parts, image_size[1] + row * ROW_HEIGHT, width,
                  row_margin(row), font, (255, 255, 255),
                  align=aligns[row])
    return frame

def to_rgb565(image):
    """Big-endian RGB565 bytes, which is what the ST7789 reads"""

    pixels = numpy.asarray(image.convert("RGB"), dtype=numpy.uint16)
    red = (pixels[:, :, 0] >> 3) << 11
    green = (pixels[:, :, 1] >> 2) << 5
    blue = pixels[:, :, 2] >> 3
    return (red | green | blue).astype(">u2").tobytes()

# --------------------------------------------------------------------------- #
