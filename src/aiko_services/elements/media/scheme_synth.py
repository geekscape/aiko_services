# DataSchemeSynthetic: the "synth://" DataScheme for synthetic data, which
# is generated internally instead of read from a device, file or network
#
# Synthetic data is a data provenance, not only test tooling: calibration,
# health checks, benchmarking, deterministic regression tests, demonstrations
# and CI all need a data source that exists without hardware
#
# URL grammar: synth://<kind>/<pattern>?<option>=<value>&...
# - "(synth://)"           defaults: video/plain, 1920x1080, the frame id and
#                          the timestamp as white text on black
# - "(synth://video/plain?width=640&height=360&text=frame_id&color=orange)"
#
# Kind "video", pattern "plain" options ...
# - width, height: positive integers (default 1920x1080).  The frame size is
#     a URL option, because "resolution" is already an ImageResize and
#     VideoWriteFile parameter, which a Pipeline-level value would feed too
# - text: comma list of "frame_id" and "timestamp" (default both), or "none"
# - color, background: Pillow color names ("white"), percent-encoded hex
#     ("%23ff8800") or bare hex ("ff8800"): default white text on black
#
# parameter: "rate"  frames per second (default 15.0), 0 or none: unpaced
#
# Frames are NumPy uint8 HxWx3 RGB rendered with Pillow: OpenCV not needed.
# The timestamp is the render time as ISO 8601 UTC with milliseconds, the
# same instant as stream.variables["timestamps"]
#
# Note: Unrelated to the "Mock" placeholder PipelineElement (elements.py),
#       which is a structural stand-in in the Pipeline graph.  Synthetic is
#       about where the data comes from.  The two combine freely
#
# To Do
# ~~~~~
# - Support "data_batch_size" (multiple images per frame)
# - More video patterns: "test_pattern" (color bars), "checkerboard",
#   a moving marker.  The text overlay options apply to every video pattern
# - Other kinds: "audio/sine", "image/...", "text/..."
# - A verifying "synth://" DataTarget (SyntheticVideoWrite) that decodes the
#   frame id from each image and checks that the sequence is complete and
#   monotonic: needs a machine-readable frame id (block code) in the image

from datetime import datetime, timezone
from functools import lru_cache
import re
import time
from urllib.parse import parse_qs, urlparse

import numpy as np
from PIL import Image, ImageColor, ImageDraw, ImageFont

import aiko_services as aiko

__all__ = ["DataSchemeSynthetic", "parse_synth_url", "render_text_frame"]

DEFAULT_KIND = "video"
DEFAULT_PATTERN = "plain"
DEFAULT_WIDTH, DEFAULT_HEIGHT = 1920, 1080
DEFAULT_RATE = 15.0               # frames per second, 0 or None: unpaced
DEFAULT_TEXT = ("frame_id", "timestamp")
DEFAULT_COLOR = (255, 255, 255)   # white text
DEFAULT_BACKGROUND = (0, 0, 0)    # black background

TEXT_ITEMS = ("frame_id", "timestamp")

_FONT_UNIT_SIZE = 100    # measuring size: text metrics scale linearly
_FRAME_ID_HEIGHT = 0.35  # frame id text height as a fraction of the frame
_TIMESTAMP_HEIGHT = 0.07 # timestamp text height as a fraction of the frame
_TEXT_WIDTH = 0.8        # never wider than this fraction of the frame
_LINE_GAP = 0.04         # gap between the two lines as a fraction

_LOGGER = aiko.process.logger(__name__)

# --------------------------------------------------------------------------- #
# Pure helpers: no Aiko Services dependency, no shared state, unit tested

def parse_synth_url(url):
    """'synth://kind/pattern?option=value&...' --> (kind, pattern, options)
    Defaults: kind "video", pattern "plain".  Raises ValueError"""

    parts = urlparse(url)
    if parts.scheme.lower() != "synth":
        raise ValueError(f'URL scheme must be "synth", not "{parts.scheme}"')
    kind = parts.netloc or DEFAULT_KIND
    segments = [segment for segment in parts.path.split("/") if segment]
    if len(segments) > 1:
        raise ValueError(
            f'URL path must be a single pattern name, not "{parts.path}"')
    pattern = segments[0] if segments else DEFAULT_PATTERN

    options = {}
    query = parse_qs(parts.query, keep_blank_values=True)
    for key, values in query.items():
        if len(values) > 1:
            raise ValueError(f'URL option "{key}" is repeated')
        options[key] = values[0]
    return kind.lower(), pattern.lower(), options

def _parse_positive_int(name, value):
    try:
        value = int(value)
    except (TypeError, ValueError):
        raise ValueError(f'option "{name}" must be an integer, not "{value}"')
    if value <= 0:
        raise ValueError(f'option "{name}" must be positive, not {value}')
    return value

def _parse_color(name, value):
    """Pillow color name, "#rrggbb" or bare "rrggbb" --> (r, g, b)"""

    if re.fullmatch(r"[0-9a-fA-F]{6}", value):
        value = f"#{value}"
    try:
        return ImageColor.getrgb(value)[:3]
    except ValueError:
        raise ValueError(
            f'option "{name}" must be a Pillow color name or hex, not "{value}"')

def _parse_text(value):
    """'frame_id,timestamp' --> tuple of text items, 'none' --> ()"""

    if value is None:
        return DEFAULT_TEXT
    if value.strip().lower() == "none":
        return ()
    items = []
    for item in value.split(","):
        item = item.strip().lower()
        if item not in TEXT_ITEMS:
            raise ValueError(f'option "text" item "{item}" must be one of '
                f'{", ".join(TEXT_ITEMS)} or "none"')
        if item not in items:
            items.append(item)
    return tuple(items)

def _format_timestamp(timestamp):
    """Seconds since the epoch --> ISO 8601 UTC with milliseconds"""

    moment = datetime.fromtimestamp(timestamp, timezone.utc)
    return f"{moment.strftime('%Y-%m-%dT%H:%M:%S')}.{moment.microsecond // 1000:03d}Z"

@lru_cache(maxsize=32)
def _font(size):  # Pillow's built-in scalable font: no TrueType file needed
    return ImageFont.load_default(size=size)

def _text_size(text, size):
    left, top, right, bottom = _font(size).getbbox(text)
    return right - left, bottom - top

def _font_size(text, width, height, height_fraction):
    unit_width, unit_height = _text_size(text, _FONT_UNIT_SIZE)
    scale = min(height_fraction * height / unit_height,
                _TEXT_WIDTH * width / unit_width)  # fits any value
    return max(1, int(_FONT_UNIT_SIZE * scale))

def render_text_frame(frame_id, timestamp,
    width=DEFAULT_WIDTH, height=DEFAULT_HEIGHT, text=DEFAULT_TEXT,
    color=DEFAULT_COLOR, background=DEFAULT_BACKGROUND):
    """Frame of "background" color with the frame id (large) and the
    timestamp (small, below) centered as "color" text: uint8 HxWx3 RGB.
    "timestamp" is seconds since the epoch, an argument for determinism"""

    lines = []  # (string, font size)
    if "frame_id" in text:
        string = str(int(frame_id))
        lines.append(
            (string, _font_size(string, width, height, _FRAME_ID_HEIGHT)))
    if "timestamp" in text:
        string = _format_timestamp(timestamp)
        lines.append(
            (string, _font_size(string, width, height, _TIMESTAMP_HEIGHT)))

    image = Image.new("RGB", (width, height), background)
    if lines:
        draw = ImageDraw.Draw(image)
        heights = [_text_size(string, size)[1] for string, size in lines]
        gap = int(height * _LINE_GAP) if len(lines) > 1 else 0
        y = (height - sum(heights) - gap * (len(lines) - 1)) // 2
        for (string, size), text_height in zip(lines, heights):
            draw.text((width // 2, y + text_height // 2), string,
                font=_font(size), fill=color, anchor="mm")  # centered
            y += text_height + gap
    return np.array(image)  # a writable copy, not a read-only view

def _video_plain(options):
    """Factory for the "video/plain" pattern: validate the URL options and
    return render(frame_id, timestamp) --> frame data"""

    options = dict(options)
    width = _parse_positive_int("width", options.pop("width", DEFAULT_WIDTH))
    height = _parse_positive_int(
        "height", options.pop("height", DEFAULT_HEIGHT))
    text = _parse_text(options.pop("text", None))
    color = DEFAULT_COLOR
    if "color" in options:
        color = _parse_color("color", options.pop("color"))
    background = DEFAULT_BACKGROUND
    if "background" in options:
        background = _parse_color("background", options.pop("background"))
    if options:
        raise ValueError(
            f'unknown option(s): {", ".join(sorted(options))}, expected '
            "width, height, text, color, background")

    def render(frame_id, timestamp):
        image = render_text_frame(
            frame_id, timestamp, width, height, text, color, background)
        return {"images": [image]}

    render.description = f"{width}x{height}"
    return render

_FACTORIES = {  # (kind, pattern): factory(options) --> render function
    ("video", "plain"): _video_plain
}

# --------------------------------------------------------------------------- #
# One DataSchemeSynthetic instance per Stream (see DataSource.start_stream()),
# so "render" and "stopped" are per-Stream state

class DataSchemeSynthetic(aiko.DataScheme):
    def create_sources(self,
        stream, data_sources, frame_generator=None, use_create_frame=False):

        pipeline_element = self.pipeline_element
        url = data_sources[0]
        try:
            kind, pattern, options = parse_synth_url(url)
            if (kind, pattern) not in _FACTORIES:
                supported = ", ".join(f"{k}/{p}" for k, p in _FACTORIES)
                raise ValueError(
                    f'"{kind}/{pattern}" is not supported, use: {supported}')
            self.render = _FACTORIES[(kind, pattern)](options)
        except ValueError as value_error:
            diagnostic = f'synth:// URL "{url}": {value_error}'
            return aiko.StreamEvent.ERROR, {"diagnostic": diagnostic}
        self.stopped = False

        rate, _ = pipeline_element.get_parameter("rate", DEFAULT_RATE)
        rate = float(rate) if rate not in (None, "", "None", "none") else None
        rate = rate or None  # 0.0: unpaced
        pipeline_element.logger.info(f"create_sources(): synth "
            f"{kind}/{pattern} {self.render.description} "
            f"at {rate or 'unpaced'} fps")

        pipeline_element.create_frames(
            stream, frame_generator or self.frame_generator, rate=rate)
        return aiko.StreamEvent.OKAY, {}

    def destroy_sources(self, stream):
        self.stopped = True  # frame_generator() returns STOP on its next call

    def frame_generator(self, stream, frame_id):
        if self.stopped:  # Stream destroyed: end the frame generator thread
            diagnostic = "Synthetic sources destroyed"
            return aiko.StreamEvent.STOP, {"diagnostic": diagnostic}
        timestamp = time.time()
        try:
            frame_data = self.render(frame_id, timestamp)
        except Exception as exception:
            # STOP, not ERROR: an ERROR here destroys the Stream on the
            # frame generator THREAD, where the _destroy_stream_exit_
            # SystemExit only kills that thread and the process lingers;
            # STOP posts a graceful destroy to the main event thread
            diagnostic = f"Synthetic render failed: {exception}"
            return aiko.StreamEvent.STOP, {"diagnostic": diagnostic}
        stream.variables["timestamps"] = [timestamp]
        return aiko.StreamEvent.OKAY, frame_data

aiko.DataScheme.add_data_scheme("synth", DataSchemeSynthetic)

# --------------------------------------------------------------------------- #
