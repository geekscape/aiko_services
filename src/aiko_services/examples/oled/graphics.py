#!/usr/bin/env python3
#
# Aiko Services: OLED graphics
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# Pure drawing helpers for a 128x64 one-bit display: the classic 5x7 bitmap
# font (or a TrueType font at a size in pixels), image helpers, the Canvas
# that the wire commands draw on, and the inverse-video title row.
#
# Coordinates: the wire protocol (and aiko_engine_mp) put the origin at the
# BOTTOM-LEFT, y upwards.  PIL puts it at the top-left, y downwards.  The
# only place the two meet is Canvas._device_y().  Applets draw PIL
# frames directly and never use the Canvas.
#
# Not part of the Interface composition pattern (see ADR-022): pure
# presentation helpers, no Service state.
#
# To Do
# ~~~~~
# - 8x8 bitmap font for pixel parity with aiko_engine_mp (16 chars per row)

import math

from PIL import Image, ImageDraw, ImageFont

__all__ = [
    "FONT_5X7", "FONT_SIZES", "HEIGHT", "INK", "WIDTH",
    "Canvas", "Font", "blank", "parse_font_size", "paste_centred", "pixels",
    "sprite", "stamp", "title_strip",
]

WIDTH, HEIGHT = 128, 64
INK = 255
FONT_SIZES = ("5x7", 8, 10, 12, 16, 20, 24)  # the sizes that "font" steps through
SANS_FONTS = ("DejaVuSans.ttf", "Verdana.ttf", "Arial.ttf", "Helvetica.ttc")  # Linux first, then macOS
MONO_FONTS = ("DejaVuSansMono.ttf", "Menlo.ttc", "Monaco.ttf", "Courier New.ttf")
FONT_SIZE_MINIMUM, FONT_SIZE_MAXIMUM = 6, 64

# Classic 5x7 font for " " to "~": 5 columns per character, bit 0 is the top row
FONT_5X7 = bytes.fromhex("""
    0000000000 00005f0000 0007000700 147f147f14 242a7f2a12 2313086462 3649552250 0005030000
    001c224100 0041221c00 082a1c2a08 08083e0808 0050300000 0808080808 0060600000 2010080402
    3e5149453e 00427f4000 4261514946 2141454b31 1814127f10 2745454539 3c4a494930 0171090503
    3649494936 064949291e 0036360000 0056360000 0008142241 1414141414 4122140800 0201510906
    324979413e 7e1111117e 7f49494936 3e41414122 7f4141221c 7f49494941 7f09090101 3e41415132
    7f0808087f 00417f4100 2040413f01 7f08142241 7f40404040 7f0204027f 7f0408107f 3e4141413e
    7f09090906 3e4151215e 7f09192946 4649494931 01017f0101 3f4040403f 1f2040201f 7f2018207f
    6314081463 0304780403 6151494543 00007f4141 0204081020 41417f0000 0402010204 4040404040
    0001020400 2054545478 7f48444438 3844444420 384444487f 3854545418 087e090102 081454543c
    7f08040478 00447d4000 2040443d00 007f102844 00417f4000 7c04180478 7c08040478 3844444438
    7c14141408 081414187c 7c08040408 4854545420 043f444020 3c4040207c 1c2040201c 3c4030403c
    4428102844 0c5050503c 4464544c44 0008364100 00007f0000 0041360800 0804040804
""")

# --------------------------------------------------------------------------- #

def find_truetype(size, mono):
    """The first of the fonts that is installed (Pillow searches the system's
    font folders), else Pillow's own"""

    for name in MONO_FONTS if mono else SANS_FONTS:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default(size)

class Font:
    """The built-in 5x7 bitmap font, or a TrueType font (DejaVu Sans on
    Linux) at a size in pixels"""

    def __init__(self, size, mono=False):
        self.size = size
        self.truetype = None
        if size != "5x7":
            self.truetype = find_truetype(size, mono)
        # The rows that letters use, from the top of capitals to the bottom
        # of descenders
        _, self.top, _, self.bottom = (0, 0, 0, 7) if size == "5x7"  \
            else self.render("Ajgy").getbbox()
        self.line_height = self.bottom - self.top
        # The row pitch: what a text row occupies on the Canvas
        self.cell_height = 8 if size == "5x7" else self.line_height + 1
        self.cell_width = 6 if size == "5x7" else None  # None: proportional

    def mono(self):
        """This font with every character the same width"""

        return self if self.truetype is None else Font(self.size, mono=True)

    def token(self):
        """The share-safe name of this font: "5x7" or the size in pixels"""

        return str(self.size)

    def render(self, text):
        """Image of the text, as wide as the text and as high as the font"""

        if self.truetype is None:
            image = Image.new("1", (max(1, 6 * len(text) - 1), 7))
            for i, char in enumerate(text):
                code = ord(char if " " <= char <= "~" else "?") - 32
                for column, bits in enumerate(FONT_5X7[5 * code:5 * code + 5]):
                    for row in range(7):
                        if bits >> row & 1:
                            image.putpixel((6 * i + column, row), INK)
            return image
        ascent, descent = self.truetype.getmetrics()
        width = max(1, math.ceil(self.truetype.getlength(text)))
        image = Image.new("1", (width, ascent + descent))
        ImageDraw.Draw(image).text((0, 0), text, font=self.truetype, fill=INK)
        return image

    def render_line(self, text):
        """Image of the text, trimmed to the rows that letters use, for
        laying out lines"""

        image = self.render(text)
        return image.crop((0, self.top, image.width, self.bottom))

def parse_font_size(text):
    """Font for a wire or command-line value: "5x7", or a size in pixels
    from 6 to 64.  Raises ValueError otherwise"""

    text = str(text)
    if text == "5x7":
        return Font(text)
    if not text.isdigit() or  \
            not FONT_SIZE_MINIMUM <= int(text) <= FONT_SIZE_MAXIMUM:
        raise ValueError(
            f"{text!r} is neither 5x7 nor a size from "
            f"{FONT_SIZE_MINIMUM} to {FONT_SIZE_MAXIMUM}")
    return Font(int(text))

# --------------------------------------------------------------------------- #

def blank(fill=0, width=WIDTH, height=HEIGHT):
    return Image.new("1", (width, height), fill)

def pixels(lit, width=WIDTH, height=HEIGHT):
    """Image with the pixels lit where lit(x, y) is true"""

    image = blank(width=width, height=height)
    image.putdata(
        [INK if lit(x, y) else 0 for y in range(height) for x in range(width)])
    return image

def sprite(rows):
    """Image from rows of "#" (lit) and "." (unlit)"""

    image = Image.new("1", (len(rows[0]), len(rows)))
    image.putdata([INK if char == "#" else 0 for row in rows for char in row])
    return image

def stamp(image, mask, x, y):
    """Light the pixels of the mask on the image at (x, y), top-left"""

    image.paste(INK, (round(x), round(y)), mask)

def paste_centred(image, text, font):
    """Draw text with its actual lit pixels centred on the image, on a
    cleared background"""

    ink = font.render(text)
    ink = ink.crop(ink.getbbox())
    x = (image.width - ink.width) // 2
    y = (image.height - ink.height) // 2
    ImageDraw.Draw(image).rectangle(
        (x - 2, y - 2, x + ink.width + 1, y + ink.height + 1), fill=0)
    stamp(image, ink, x, y)

# --------------------------------------------------------------------------- #

class Canvas:
    """The frame buffer that the wire commands draw on (event-loop thread
    only).  Origin bottom-left, as aiko_engine_mp: the only y flip is
    _device_y().  When a title row is shown, "title_rows" pixel rows at the
    top are reserved: clear() and scroll_up() leave them alone"""

    def __init__(self, font, width=WIDTH, height=HEIGHT):
        self.font = font
        self.width, self.height = width, height
        self.title_rows = 0
        self._image = blank(width=width, height=height)

    @property
    def image(self):
        """A copy of the canvas"""

        return self._image.copy()

    def _device_y(self, y, height=1):
        """PIL row of the top of something "height" rows high whose bottom
        is at wire row y (y=0 is the bottom row of the display)"""

        return self.height - height - y

    def clear(self):
        ImageDraw.Draw(self._image).rectangle(
            (0, self.title_rows, self.width - 1, self.height - 1), fill=0)

    def pixel(self, x, y):
        self._image.putpixel((x, self._device_y(y)), INK)

    def pixels(self, pairs):
        for x, y in pairs:
            self.pixel(x, y)

    def line(self, x0, y0, x1, y1):
        ImageDraw.Draw(self._image).line(
            (x0, self._device_y(y0), x1, self._device_y(y1)), fill=INK)

    def text(self, x, y, string):
        """Write a string with its text cell's bottom-left at wire (x, y);
        pixels off the right edge are lost"""

        stamp(self._image, self.font.render_line(string),
            x, self._device_y(y, self.font.cell_height))

    def scroll_up(self, rows):
        """Move everything below the title row up, clearing the bottom"""

        region = self._image.crop(
            (0, self.title_rows + rows, self.width, self.height))
        ImageDraw.Draw(self._image).rectangle(
            (0, self.title_rows, self.width - 1, self.height - 1), fill=0)
        self._image.paste(region, (0, self.title_rows))

    def log(self, string):
        """Scroll up one text row and write the string on the bottom row"""

        self.scroll_up(self.font.cell_height)
        self.text(0, 0, string)

def title_strip(font, title, annunciators="", clock="", width=WIDTH):
    """The inverse-video title row: the title (9 characters with the 5x7
    font), the annunciators (3), a space, and the clock (hh:mm:ss) at the
    right.  Its height is the font's cell height"""

    strip = blank(INK, width=width, height=font.cell_height)
    if font.cell_width:  # fixed layout: 9 + 3 + 1 + 8 = 21 columns of 6 pixels
        text = f"{title[:9]:9s}{annunciators[:3]:3s} {clock[:8]:>8s}"
        ink = font.render_line(text)
        strip.paste(0, (0, 0), ink)
    else:
        ink = font.render_line(f"{title} {annunciators}".rstrip())
        strip.paste(0, (0, 0), ink)
        if clock:
            ink = font.render_line(clock)
            strip.paste(0, (max(0, width - ink.width), 0), ink)
    return strip
