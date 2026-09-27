#!/usr/bin/env python3
#
# Aiko Services: OLED display Actor
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# An SSD1306 128x64 OLED as a display Actor (protocol "display:0"): a
# canvas that any client draws on with the same S-expressions the
# MicroPython aiko_engine_mp OLED accepts, settings that the Aiko Dashboard
# reads and writes, and applets that run on the display, above all a
# status display for headless hosts.  On a desktop without the panel, the
# OLED is emulated in a window, in the terminal or in a PNG file.
#
# The protocol is the composite of three aspect Interfaces, each advertised
# as a tag (canvas=0 screen=0 interaction=0) beside device=oled:
#   Canvas       drawing: clear log pixel pixels line text
#   Screen       the screen: its settings in the shared state, and the leased
#                frame mirror (mirror TOPIC SECONDS) for the Dashboard plug-in
#   Interaction  what runs on the display: applet, key (the key map is here)
#
# Usage
# ~~~~~
#   export AIKO_MQTT_HOST=localhost
#   aiko_display [-n NAME] [-t SECONDS] SUBCOMMAND ...   (-n: the Actor to run or command)
#   aiko_display run [-o oled -a 0x3C] [--applet status] [--standalone]
#   aiko_display exit | list
#   aiko_display clear | log WORDS | text X Y WORDS | pixels X Y ... | line X0 Y0 X1 Y1
#   aiko_display set KEY VALUE          # contrast 128, invert on, title Aiko, font 10 ...
#   aiko_display applet NAME [ARGS ...] | applet -l | stop | key NAME [tap|down|up]
#   aiko_display keys                   # interactive console: see console.py, keys.py
#
#   mosquitto_pub -t $TOPIC_IN -m "(oled:text 0 0 hello)"     # aiko_engine_mp style
#   mosquitto_pub -t $TOPIC_IN -m "(text 0 8 second row)"
#   mosquitto_pub -t $TOPIC_CONTROL -m "(update contrast 64)"  # what the Dashboard does
#
# Wire commands (one-way: outcomes are observed in the shared state)
# ~~~~~~~~~~~~~
#   (clear)                     (oled:clear)     erase the canvas
#   (log WORDS ...)             (oled:log ...)   scroll up, write on the bottom row
#   (pixel X Y)                 (oled:pixel ...) light a pixel, origin bottom-left
#   (pixels X Y X Y ...)        (oled:pixels ..) light pixels, at most 256 pairs
#   (line X0 Y0 X1 Y1)                           draw a line
#   (text X Y WORDS ...)        (oled:text ...)  write text, cell bottom-left at (X, Y)
#   (exit)                      = (stop)         blank the display and terminate
#   (applet NAME [ARGS ...])                run an applet; "none" shows the canvas
#   (key NAME [tap|down|up])                     a key in the map runs its preset,
#                                                any other goes to the applet
#   (mirror TOPIC SECONDS)                       a leased feed of raw frames to TOPIC
#   Anything else on the "in" topic is rejected (P12), including "(run)".
#
# Shared state (aiko_dashboard shows it; the RW keys can be edited there)
# ~~~~~~~~~~~~
#   backend device panels size origin depth settings keys.* connection
#   mirrors applets applet(RW)
#   applet_detail fps speed(RW) font(RW) contrast(RW) invert(RW)
#   power(RW) all_on(RW) title(RW: text, on, off) blank_after(RW)
#   foreground(RW) background(RW: colors of an emulated display) heartbeat
#   last_error log_count log_pending metrics.commands metrics.rejected metrics.frames
#   metrics.frame_ms metrics.errors metrics.mirrored
#
# Bounds (P9): log ring 8 lines (oldest dropped); 256 pixel pairs per
# command; 128 characters of text per command; 64 characters per
# applet argument; 5 keys held.  A frame is shown at most once per
# tick (30 Hz) and only when it changed.
#
# Coordinates: origin bottom-left, y upwards (aiko_engine_mp compatible);
# the only y flip is graphics.Canvas._device_y()
#
# Protocol: display:0 (aspects canvas:0 screen:0 interaction:0)
#
# To Do
# ~~~~~
# - Dashboard plug-in; convergence with aiko_engine_mp (protocol oled:0)

from abc import abstractmethod
import collections
from typing import NamedTuple
import os
import random
import re
import signal
import threading
import time
import traceback

import textwrap

import click
from PIL import ImageColor

import aiko_services as aiko
from aiko_services.main.connection import ConnectionState
from aiko_services.main.lease import Lease
from aiko_services.main.utilities import get_hostname, parse

from aiko_services.actors.display.applets import (
    APPLETS, AppletDone, Host, fits, parse_applet_args,
)
from aiko_services.actors.display import drawings, faces, games  # noqa: F401 (they register applets)
from aiko_services.actors.display import status as status_screens  # noqa: F401 (registers status)
from aiko_services.actors.display.outputs import (
    ADDRESSES, OUTPUTS, DisplayNotFound, NullOutputImpl, choose_output,
    output_args, parse_colors, scan_i2c,
)
from aiko_services.actors.display.graphics import (
    HEIGHT, WIDTH, FrameBuffer, blank, parse_font_size, title_strip,
)
from aiko_services.actors.display import keys as keymap  # the emulator window's keys

__all__ = [
    "ASPECT_TAGS", "Canvas", "Display", "Interaction", "DisplayImpl", "PROTOCOL",
    "PROTOCOL_TYPE", "SETTINGS", "SETTINGS_SPEC", "Screen", "Setting",
    "WIRE_COMMANDS", "main", "service_tags",
]

_VERSION = 0
PROTOCOL_TYPE = "display"
PROTOCOL = f"{aiko.SERVICE_PROTOCOL_AIKO}/{PROTOCOL_TYPE}:{_VERSION}"

# aiko_engine_mp names its commands "oled:clear" etc: the same methods
_ALIASES = {f"oled:{name}": name
    for name in ("clear", "log", "pixel", "pixels", "text")}
_ALIASES["exit"] = "stop"       # the framework's stop() terminates; the CLI blanks

LOG_LINES = 8                 # the log ring: oldest line dropped
PIXEL_PAIRS_MAXIMUM = 256     # per (pixels ...) command
TEXT_LENGTH_MAXIMUM = 128     # characters per (text ...) or (log ...)
TITLE_LENGTH_MAXIMUM = 32
KEYS_HELD_MAXIMUM = 5
KEY_NAMES = ("up", "down", "left", "right")  # plus any single character
KEY_STATES = ("tap", "down", "up")
KEY_HOLD = 0.15               # seconds a tapped key stays held (MQTT latency)
MIRROR_LEASES_MAXIMUM = 4     # holders of the frame feed
MIRROR_TOPIC_LENGTH_MAXIMUM = 128
MIRROR_SECONDS_MAXIMUM = 300
SPEED_MINIMUM, SPEED_MAXIMUM = 0.1, 10.0
BLANK_AFTER_MAXIMUM = 86400   # seconds

TICK_PERIOD = 1 / 30          # the frame timer; applets run at fps × speed
HEARTBEAT_PERIOD = 1.0
METRICS_PERIOD = 2.0
REOPEN_PERIOD = 10.0          # retry a failed display this often
TIMEOUT = 5.0                 # CLI: seconds to wait for the OLED Actor
DEFAULT_APPLET = "status"

# Settings: shared state that anyone may write with "(update KEY VALUE)" on
# the control topic; the change handler applies them through one setter each
DEFAULT_COLORS = ("white", "black")  # of an emulated display: lit, unlit

class Setting(NamedTuple):
    """One declared setting: what the share key accepts.  The kinds: int
    and float (low..high), flag (on/off), applet, title, font, color"""

    name: str
    kind: str
    default: str
    low: float
    high: float
    values: str        # the grammar, for help
    description: str

# The settings, declared once: the "settings" share key, the setters, the
# help and the tests derive from this table (the shape of Pipeline
# Parameters: declared names with defaults, overridden live through share)
SETTINGS_SPEC = (
    Setting("applet", "applet", DEFAULT_APPLET, None, None,
            "NAME[,ARG,...] | none", "run an applet, or show the canvas"),
    Setting("contrast", "int", "255", 0, 255, "0..255", "brightness"),
    Setting("invert", "flag", "off", None, None, "on | off", "inverse video"),
    Setting("power", "flag", "on", None, None, "on | off", "display sleep (blank)"),
    Setting("all_on", "flag", "off", None, None, "on | off",
            "every pixel lit: a hardware test"),
    Setting("title", "title", "", None, None, "TEXT | on | off",
            "the title row; off: the whole panel"),
    Setting("font", "font", "5x7", None, None, "5x7 | 6..64",
            "the font: 5x7 bitmap, or TrueType size"),
    Setting("speed", "float", "1", SPEED_MINIMUM, SPEED_MAXIMUM, "0.1..10",
            "multiplies every applet's frame rate"),
    Setting("blank_after", "int", "0", 0, BLANK_AFTER_MAXIMUM, "SECONDS (0: never)",
            "sleep the display after inactivity; any command wakes it"),
    Setting("mirror_rate", "int", "5", 1, 10, "1..10",
            "frames a second to each mirror holder, at most"),
    Setting("foreground", "color", DEFAULT_COLORS[0], None, None, "COLOR | default",
            "lit pixels of an emulated display"),
    Setting("background", "color", DEFAULT_COLORS[1], None, None, "COLOR | default",
            "unlit pixels; default: as started (-c)"),
)
SETTINGS = tuple(setting.name for setting in SETTINGS_SPEC)
SETTINGS_BY_NAME = {setting.name: setting for setting in SETTINGS_SPEC}

# --------------------------------------------------------------------------- #

def _token(text, limit=32):
    """Reduce free text to one share-safe token: no whitespace or
    parentheses, and never starting with digits followed by a colon (the
    parser's canonical form), e.g. "no OLED found" -> "no_OLED_found" """

    token = re.sub(r"[^A-Za-z0-9_.@/:-]+", "_", str(text)).strip("_")[:limit]
    if re.match(r"\d+:", token):
        token = "_" + token
    return token or "-"

def _utc_now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

class _Reject(Exception):
    """A wire argument failed validation: reason is a share-safe token"""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason

def _int(value, name, low, high):
    try:
        number = int(str(value).strip())
    except ValueError:
        raise _Reject(f"{name}_not_int")
    if not low <= number <= high:
        raise _Reject(f"{name}_range")
    return number

def _flag(value, name):
    text = str(value).strip().lower()
    if text in ("on", "true", "1", "yes"):
        return True
    if text in ("off", "false", "0", "no"):
        return False
    raise _Reject(f"{name}_not_on_off")

def _words(words):
    if not words:
        raise _Reject("empty")
    if not all(isinstance(word, str) for word in words):
        raise _Reject("not_text")
    line = " ".join(words)
    if len(line) > TEXT_LENGTH_MAXIMUM:
        raise _Reject("too_long")
    return line

# --------------------------------------------------------------------------- #

class Canvas(aiko.Interface):
    """
    Drawing on a canvas: a one-bit frame buffer of "size" pixels, origin
    bottom-left and y upwards, wire-compatible with the aiko_engine_mp
    (MicroPython) OLED: "(oled:text ...)" and "(text ...)" are the same
    command.  Every method is one-way: a rejected command changes nothing
    but "metrics.rejected" and "last_error" in the shared state.  Drawing
    stops any running applet, except "log", whose lines the status applet
    shows itself.  Share: font and title (RW); size, origin, depth,
    log_count, log_pending.
    """

    PROTOCOL = f"{aiko.SERVICE_PROTOCOL_AIKO}/canvas:{_VERSION}"
    aiko.Interface.default("Canvas", "aiko_services.actors.display.display.DisplayImpl")

    @abstractmethod
    def clear(self):
        """Erase the canvas (the title row stays).
        Wire form: "(clear)" or "(oled:clear)".
        Outcome: the display shows a blank canvas.  Projection: command"""

    @abstractmethod
    def log(self, *words):
        """Scroll the canvas up one text row and write WORDS on the bottom
        row; the line is also kept (8 lines) for the status applet.
        Wire form: "(log WORDS ...)" or "(oled:log WORDS ...)"; runs of
        spaces collapse to one.  Outcome: share "log_count" +1.
        Projection: command"""

    @abstractmethod
    def pixel(self, x, y):
        """Light one pixel: x 0..width-1 left to right, y 0..height-1
        bottom to top.  Wire form: "(pixel X Y)" or "(oled:pixel X Y)".
        Rejected when out of range.  Projection: command"""

    @abstractmethod
    def pixels(self, *coordinates):
        """Light many pixels: an even number of integers, at most 256 pairs.
        Wire form: "(pixels X Y X Y ...)" or "(oled:pixels ...)".
        Rejected as a whole when any coordinate is bad.  Projection: command"""

    @abstractmethod
    def line(self, x0, y0, x1, y1):
        """Draw a line between two points (origin bottom-left).
        Wire form: "(line X0 Y0 X1 Y1)".  Projection: command"""

    @abstractmethod
    def text(self, x, y, *words):
        """Write WORDS in the current font with the text cell's bottom-left
        at (X, Y): Y=0 is the bottom row, Y=8 the row above with the 5x7
        font.  Wire form: "(text X Y WORDS ...)" or "(oled:text ...)".
        Projection: command"""

class Screen(aiko.Interface):
    """
    Controlling the screen: its settings are shared state, written with
    "(update KEY VALUE)" on the control topic (see SETTINGS_SPEC): contrast,
    invert, power, all_on, blank_after, foreground, background, mirror_rate.
    Observed: backend, device, panels, fps, mirrors, metrics.frames,
    metrics.frame_ms, metrics.mirrored.  One method: the leased frame
    mirror, in the vocabulary of a Stream (create, extend, destroy).
    """

    PROTOCOL = f"{aiko.SERVICE_PROTOCOL_AIKO}/screen:{_VERSION}"
    aiko.Interface.default("Screen", "aiko_services.actors.display.display.DisplayImpl")

    @abstractmethod
    def mirror(self, topic, seconds):
        """Create or extend a leased feed of the panel's frames to TOPIC:
        each frame as raw bytes (PIL mode "1", "size" pixels, row major,
        MSB first), published when it changes, at most "mirror_rate" a
        second, until SECONDS pass without another request; SECONDS 0
        destroys the feed.  At most 4 holders.
        Wire form: "(mirror TOPIC SECONDS)".  Outcome: share "mirrors" (the
        holder count) and "metrics.mirrored".  Rejected: mirror_topic,
        mirror_seconds_not_int, mirror_seconds_range, mirror_full.
        Projection: command"""

class Interaction(aiko.Interface):
    """
    Controlling what runs on the display: applets are sources of frames
    that the Actor runs (status, games, drawings, demo ...), listed in
    share "applets"; keys reach the running applet, or run the display's
    own key map (share "keys.*").  Share: applet and speed (RW); applets,
    applet_detail.
    """

    PROTOCOL = f"{aiko.SERVICE_PROTOCOL_AIKO}/interaction:{_VERSION}"
    aiko.Interface.default(
        "Interaction", "aiko_services.actors.display.display.DisplayImpl")

    @abstractmethod
    def applet(self, name, *args):
        """Run an applet, replacing the running one; "(applet none)"
        stops it and shows the canvas.  ARGS are words and key=value options
        that the applet accepts, e.g. "(applet pong seed=1)".
        Outcome: share "applet", "applet_detail".
        Rejected when the name or an option is unknown.  Projection: command"""

    @abstractmethod
    def key(self, name, state="tap"):
        """A key: NAME is "up", "down", "left", "right" or one character;
        STATE is "tap" (default: held briefly), "down" or "up".  A key in
        the display's key map (share "keys.*") runs its preset or changes
        its setting, on "tap" or "down"; any other key goes to the running
        applet.  Wire form: "(key NAME [STATE])".  Projection: command"""

class Display(aiko.Actor, Canvas, Screen, Interaction):
    """
    A display: the composite of the Canvas, Screen and Interaction aspects,
    the registered protocol "display:0".  No methods of its own beyond the
    Actor's; the aspects are advertised as tags (see ASPECT_TAGS).  Share:
    connection, heartbeat, last_error, settings, metrics.commands,
    metrics.rejected, metrics.errors.
    """

    PROTOCOL = PROTOCOL
    aiko.Interface.default("Display", "aiko_services.actors.display.display.DisplayImpl")

ASPECTS = (Canvas, Screen, Interaction)

def _aspect_tag(aspect):
    """"canvas=0" from the aspect's contract id ".../canvas:0" """

    name, _, version = aspect.PROTOCOL.rpartition("/")[2].partition(":")
    return f"{name}={version}"

# The aspects, advertised as Service tags until the Registrar matches
# several protocols per Service
ASPECT_TAGS = tuple(_aspect_tag(aspect) for aspect in ASPECTS)

def service_tags(device):
    """The tags the Actor registers with: shared state, the device kind
    (the display backend's name) and the aspects"""

    return ["ec=true", f"device={device}", *ASPECT_TAGS]

# The commands accepted on the "in" topic: the abstract methods of the
# aspects (never the framework's Actor and Service methods), plus the
# framework's log level and stop (P12: deny by default)
WIRE_COMMANDS = frozenset(name
    for interface in ASPECTS
    for name, member in vars(interface).items()
    if getattr(member, "__isabstractmethod__", False)
    and not name.startswith("_")) | {"set_log_level", "stop"}

# --------------------------------------------------------------------------- #

class _Host(Host):
    """What applets see of the Actor"""

    def __init__(self, actor):
        self._actor = actor

    @property
    def width(self):
        return self._actor._canvas.width

    @property
    def height(self):
        return self._actor._canvas.height

    @property
    def font(self):
        return self._actor._font

    @property
    def rng(self):
        return self._actor._rng

    @property
    def speed(self):
        return self._actor._speed

    def connection(self):
        return self._actor.share.get("connection", "NONE")

    @property
    def name(self):
        return self._actor.name

    def title_rows(self):
        return self._actor._canvas.title_rows

    def log_lines(self):
        return list(self._actor._log)

    def log_seen(self):
        self._actor._set_log_pending(False)

    def keys_held(self):
        return self._actor._keys_held()

    def status(self, token):
        self._actor.ec_producer.update("applet_detail", _token(token))

    def setting(self, name):
        return self._actor.share.get(name)

    def control(self, name, value):
        if name in ("contrast", "invert", "power", "all_on", "font", "speed"):
            self._actor._setters[name](str(value))

class DisplayImpl(Display):
    def __init__(self, context):
        context.call_init(self, "Actor", context)
        parameters = context.get_parameters() or {}

        self._output = parameters.get("output")  \
            or aiko.compose_instance(NullOutputImpl, output_args())
        self._output.add_handler(self._output_event)
        self._output_ok = False
        self._reopening = False
        self._strict = bool(parameters.get("strict", False))
        self._font = parse_font_size(parameters.get("font", "5x7"))
        width, height = parameters.get("size") or (WIDTH, HEIGHT)
        self._canvas = FrameBuffer(self._font, int(width), int(height))
        colors = [str(color) for color in (parameters.get("colors") or ()) if color]
        self._start_colors = {           # what "default" means for a color
            "foreground": colors[0] if colors else DEFAULT_COLORS[0],
            "background": colors[1] if len(colors) > 1 else DEFAULT_COLORS[1],
        }
        self._output.set_colors(*(ImageColor.getrgb(self._start_colors[key])[:3]
                                   for key in ("foreground", "background")))
        self._log = collections.deque(maxlen=LOG_LINES)
        self._log_total = 0
        self._log_pending = False   # the "L" annunciator
        self._rng = random.Random()
        self._metrics = {"commands": 0, "rejected": 0, "frames": 0,
                         "frame_ms": 0, "errors": 0, "mirrored": 0}
        self._speed = 1.0
        self._blank_after = 0
        self._blanked = False
        self._applet = None
        self._default_applet = str(
            parameters.get("applet") or DEFAULT_APPLET)
        self._held = {}             # key name: held until (monotonic)
        self._mirrors = {}          # topic: Lease, the frame feed's holders
        self._mirror_rate = 5
        self._mirror_due = 0.0
        self._mirror_pending = None # the newest frame not yet mirrored
        self._host = _Host(self)
        self._last_frame = None     # bytes of the frame on the display
        self._started = time.monotonic()
        self._last_change = self._started
        self._frame_due = 0.0
        self._title_due = 0.0
        self._frames_at_flush, self._flushed_at = 0, self._started
        self._shut = False
        self.last_event_thread = None  # for tests: where handlers run

        title = str(parameters.get("title") or self.name)
        self._title_text = "" if title == "off" else title.replace("_", " ")
        self._title_saved = self._title_text or self.name  # what "title on" restores
        self._canvas.title_rows = self._font.cell_height if self._title_text else 0

        self._setters = {setting.name: (lambda value, setting=setting:
                                        self._apply_setting(setting, value))
                         for setting in SETTINGS_SPEC}
        self.share.update({
            "source_file": f"v{_VERSION}⇒ {__file__}",
            "backend": self._output.name,
            "device": "-",
            "panels": "-",
            "mirrors": "0",
            "size": f"{self._canvas.width}x{self._canvas.height}",
            "origin": "bottom",
            "depth": "1",
            "settings": ",".join(SETTINGS),
            "keys": keymap.legend(),
            "connection": _token(aiko.process.connection.get_state()),
            "applets": self._applets_that_fit(),
            "applet": "none",
            "applet_detail": "-",
            "fps": "0",
            **{setting.name: setting.default for setting in SETTINGS_SPEC
               if setting.kind in ("int", "flag", "float")},
            "font": self._font.token(),
            "title": _token(title) if self._title_text else "off",
            "foreground": self._start_colors["foreground"],
            "background": self._start_colors["background"],
            "heartbeat": "0",
            "last_error": "-",
            "log_count": "0",
            "log_pending": "off",
            "metrics": {key: "0" for key in self._metrics},
        })
        self._applied = {key: self.share[key] for key in SETTINGS}
        self._local_keys = {"turns": {}, "current": None,   # the window's keys
                            "settings": self.share, "base_font": self.share["font"]}
        self.ec_producer.add_handler(self._ec_producer_change_handler)

        self._open_output()
        aiko.process.connection.add_handler(self._connection_handler)
        aiko.event.add_timer_handler(self._tick, TICK_PERIOD)
        aiko.event.add_timer_handler(self._heartbeat, HEARTBEAT_PERIOD)
        aiko.event.add_timer_handler(self._metrics_flush, METRICS_PERIOD)
        self._present(self._canvas.image)
        if self._default_applet != "none":
            self.applet(*self._default_applet.split(","))
        self.logger.info(f"{self.name}: output {self.share['backend']} "
                         f"{self.share['device']}, topic {self.topic_in}")

    # Dispatch (event-loop thread): aliases, parse guard, allow-list -------- #

    def _topic_in_handler(self, _aiko, topic, payload_in):
        try:
            command, parameters = parse(payload_in)
        except Exception:                  # the parser raises on odd tokens
            return self._reject("dispatch", "parse_error", payload_in[:80])
        command = _ALIASES.get(command, command)
        if command not in WIRE_COMMANDS or not isinstance(parameters, list):
            return self._reject("dispatch", "unknown_command", str(command)[:40])
        self._post_message(aiko.ActorTopic.IN, command, parameters)

    # Wire commands: Canvas -------------------------------------- #

    def clear(self):
        self._canvas_command()
        self._canvas.clear()
        self._present(self._canvas.image)

    def log(self, *words):
        try:
            line = _words(words)
        except _Reject as reject:
            return self._reject("log", reject.reason)
        self._metrics["commands"] += 1
        self._wake()
        self._log.append(line)
        self._log_total += 1
        self._set_log_pending(True)
        self._canvas.log(line)
        self.ec_producer.update("log_count", str(self._log_total))
        if self._applet is None:
            self._present(self._canvas.image)

    def pixel(self, x, y):
        try:
            x = _int(x, "x", 0, WIDTH - 1)
            y = _int(y, "y", 0, HEIGHT - 1)
        except _Reject as reject:
            return self._reject("pixel", reject.reason)
        self._canvas_command()
        self._canvas.pixel(x, y)
        self._present(self._canvas.image)

    def pixels(self, *coordinates):
        try:
            if not coordinates or len(coordinates) % 2  \
                    or len(coordinates) > 2 * PIXEL_PAIRS_MAXIMUM:
                raise _Reject("count")
            numbers = [_int(value, "xy", 0, max(WIDTH, HEIGHT) - 1)
                       for value in coordinates]
            pairs = list(zip(numbers[0::2], numbers[1::2]))
            if any(x >= WIDTH or y >= HEIGHT for x, y in pairs):
                raise _Reject("range")
        except _Reject as reject:
            return self._reject("pixels", reject.reason)
        self._canvas_command()
        self._canvas.pixels(pairs)
        self._present(self._canvas.image)

    def line(self, x0, y0, x1, y1):
        try:
            x0, x1 = (_int(value, "x", 0, WIDTH - 1) for value in (x0, x1))
            y0, y1 = (_int(value, "y", 0, HEIGHT - 1) for value in (y0, y1))
        except _Reject as reject:
            return self._reject("line", reject.reason)
        self._canvas_command()
        self._canvas.line(x0, y0, x1, y1)
        self._present(self._canvas.image)

    def text(self, x, y, *words):
        try:
            x = _int(x, "x", 0, WIDTH - 1)
            y = _int(y, "y", 0, HEIGHT - 1)
            line = _words(words)
        except _Reject as reject:
            return self._reject("text", reject.reason)
        self._canvas_command()
        self._canvas.text(x, y, line)
        self._present(self._canvas.image)

    # Wire commands: Interaction --------------------------------------- #

    def applet(self, name, *args):
        name = str(name)
        if name == "none":
            self._metrics["commands"] += 1
            self._wake()
            self._stop_applet()
            self._settle("applet", "none")
            self._refresh()
            return
        applet_class = APPLETS.get(name)
        if applet_class is None:
            return self._reject_setting("applet", "applet_unknown", name)
        if not self._fits(applet_class):
            return self._reject_setting("applet", "applet_too_small", name)
        try:
            words, options = parse_applet_args(
                args, applet_class.OPTIONS)
            instance = applet_class(self._host, words, options)
        except ValueError as error:
            return self._reject_setting("applet", "applet_args", str(error))
        except Exception:
            self.logger.error(f"{self.name}: {name}: {traceback.format_exc()}")
            self._metrics["errors"] += 1
            return self._reject_setting("applet", "applet_failed", name)
        self._metrics["commands"] += 1
        self._wake()
        self._stop_applet()
        self._applet = instance
        self._frame_due = time.monotonic()
        self._settle("applet", name)
        self.ec_producer.update("applet_detail",
            _token(instance.description) if instance.description else "-")

    def key(self, name, state="tap"):
        name, state = str(name), str(state)
        if not (name in KEY_NAMES or len(name) == 1):
            return self._reject("key", "name", name[:20])
        if state not in KEY_STATES:
            return self._reject("key", "state", state[:20])
        self._metrics["commands"] += 1
        self._wake()
        if name in keymap.MAPPED_KEYS:       # the display's own key map
            if state != "up":
                self._run_key_map(name)
            return
        if state == "up":
            self._held.pop(name, None)
        else:
            self._held[name] = float("inf") if state == "down"  \
                else time.monotonic() + KEY_HOLD
            while len(self._held) > KEYS_HELD_MAXIMUM:
                del self._held[next(iter(self._held))]
        if self._applet is not None:
            self._guarded("key", lambda: self._applet.key(name, state))

    # Wire commands: Screen -------------------------------------------- #

    def mirror(self, topic, seconds):
        topic = str(topic)
        if not 0 < len(topic) <= MIRROR_TOPIC_LENGTH_MAXIMUM  \
                or any(character in topic for character in "+# \t"):
            return self._reject("mirror", "topic", topic[:40])
        try:
            seconds = _int(seconds, "seconds", 0, MIRROR_SECONDS_MAXIMUM)
        except _Reject as reject:
            return self._reject("mirror", reject.reason)
        self._metrics["commands"] += 1
        self._wake()
        lease = self._mirrors.get(topic)
        if seconds == 0:                             # destroy
            if lease is not None:
                lease.terminate()
                del self._mirrors[topic]
                self._publish_mirrors()
            return
        if lease is not None:                        # extend
            lease.extend(seconds)
            return
        if len(self._mirrors) >= MIRROR_LEASES_MAXIMUM:
            return self._reject("mirror", "full", topic[:40])
        self._mirrors[topic] = Lease(                # create
            seconds, topic, lease_expired_handler=self._mirror_expired)
        self._publish_mirrors()
        self._mirror_pending = self._last_frame      # the holder sees the panel now
        self._mirror_due = 0.0

    def _mirror_expired(self, topic):
        if self._mirrors.pop(topic, None) is not None:
            self._publish_mirrors()

    def _publish_mirrors(self):
        self.ec_producer.update("mirrors", str(len(self._mirrors)))

    def _mirror_frame(self, data):
        """Send a frame to the mirror holders when one is due, else keep it
        as the one pending frame (the latest wins: bound 1 frame)"""

        if not self._mirrors or data is None:
            self._mirror_pending = None
            return
        now = time.monotonic()
        if now < self._mirror_due:
            self._mirror_pending = data
            return
        self._mirror_pending = None
        self._mirror_due = now + 1.0 / self._mirror_rate
        if not aiko.process.connection.is_connected(ConnectionState.TRANSPORT):
            return                                   # publish() would block
        for topic in list(self._mirrors):
            aiko.process.message.publish(topic, data)
        self._metrics["mirrored"] += 1

    # Settings: applied through the shared state ---------------------------- #

    def _ec_producer_change_handler(self, command, item_name, item_value):
        if command not in ("add", "update") or item_name not in self._setters:
            return
        value = str(item_value)
        if value == self._applied.get(item_name):
            return                         # our own update echoed back
        self._setters[item_name](value)

    def _settle(self, key, token):
        """Record and publish an applied setting"""

        self._applied[key] = token
        self.ec_producer.update(key, token)

    def _reject_setting(self, key, reason, detail=""):
        """Reject a setting and publish the value still in force, so that
        a bad Dashboard edit converges back"""

        self._reject("set", reason, detail)
        self.ec_producer.update(key, self._applied[key])

    def _set_applet(self, value):
        self.applet(*str(value).split(","))

    def _apply_setting(self, setting, value):
        """Apply a declared setting (SETTINGS_SPEC) by its kind; a bad value
        is rejected and the value in force published again"""

        kind, name = setting.kind, setting.name
        if kind == "applet":
            return self._set_applet(value)
        if kind == "title":
            return self._set_title(value)
        if kind == "font":
            return self._set_font(value)
        if kind == "color":
            return self._set_color(name, value)
        if kind == "flag":
            return self._set_flag(name, value)
        if kind == "float":
            try:
                number = float(str(value))
            except ValueError:
                return self._reject_setting(name, f"{name}_not_number")
            if not setting.low <= number <= setting.high:
                return self._reject_setting(name, f"{name}_range")
            if name == "speed":
                self._speed = number
            return self._settle(name, f"{number:g}")
        try:                                             # kind == "int"
            number = _int(value, name, setting.low, setting.high)
        except _Reject as reject:
            return self._reject_setting(name, reject.reason)
        if name == "contrast":
            self._control_output("contrast", number)
        elif name == "blank_after":
            self._blank_after = number
            if not number:
                self._wake()
        elif name == "mirror_rate":
            self._mirror_rate = number
        self._settle(name, str(number))

    def _set_flag(self, key, value):
        try:
            flag = _flag(value, key)
        except _Reject as reject:
            return self._reject_setting(key, reject.reason)
        if key == "power":
            self._blanked = False
            self._last_change = time.monotonic()
        self._control_output(key, flag)
        self._settle(key, "on" if flag else "off")

    def _set_title(self, value):
        """The title row: "off" hides it (the whole panel for the canvas or
        an applet), "on" shows it again with the last text, anything else
        is the text (underscores are spaces)"""

        text = str(value)
        if len(text) > TITLE_LENGTH_MAXIMUM:
            return self._reject_setting("title", "title_too_long")
        token = _token(text)
        if token in ("off", "-"):
            self._title_text = ""
        elif token == "on":
            self._title_text = self._title_saved
        else:
            self._title_text = token.replace("_", " ")
        self._title_saved = self._title_text or self._title_saved
        self._canvas.title_rows = self._font.cell_height if self._title_text else 0
        self._settle("title", _token(self._title_text) if self._title_text else "off")
        self._refresh()

    def _set_log_pending(self, pending):
        """The "L" annunciator: log lines arrived that no applet has shown"""

        if pending != self._log_pending:
            self._log_pending = pending
            self.ec_producer.update("log_pending", "on" if pending else "off")

    def _set_font(self, value):
        try:
            font = parse_font_size(value)
        except ValueError:
            return self._reject_setting("font", "font_range")
        self._font = self._canvas.font = font
        if self._title_text:
            self._canvas.title_rows = font.cell_height
        self._settle("font", font.token())
        self._refresh()

    def _set_color(self, key, value):
        """The colors of lit ("foreground") and unlit ("background") pixels
        on an emulated display (the OLED's color is fixed): a name such as
        yellow, or #rrggbb; "default" is the color the Actor started with"""

        token = str(value).strip()
        if token == "default":
            token = self._start_colors[key]
        try:
            if not re.fullmatch(r"[#A-Za-z0-9]+", token):
                raise ValueError(token)
            rgb = ImageColor.getrgb(token)[:3]
        except ValueError:
            return self._reject_setting(key, f"{key}_not_color")
        self._control_output("set_colors", **{key: rgb})
        self._settle(key, token)

    def _fits(self, applet_class):
        """Whether the applet's MIN_SIZE, if it has one, fits the canvas"""

        return fits(applet_class, self._canvas.width, self._canvas.height)

    def _applets_that_fit(self):
        return ",".join(sorted(name for name, applet_class in APPLETS.items()
                               if self._fits(applet_class))) or "none"

    def _centered(self, image):
        """A smaller frame (a game's fixed field) centered on the canvas"""

        frame = blank(width=self._canvas.width, height=self._canvas.height)
        frame.paste(image, ((frame.width - image.width) // 2,
                            (frame.height - image.height) // 2))
        return frame

    # The output ---------------------------------------------------------- #

    def _open_output(self):
        try:
            self._output.open()
        except DisplayNotFound as error:
            if self._strict:
                raise
            self.logger.warning(f"{self.name}: output {self._output.name}: {error}")
            self._note_error("display_not_found")
            self._set_device("absent")
            self._start_reopening()
            return
        self._output_ok = True
        self._set_device(_token(self._output.device, 48))

    def _set_device(self, token):
        """What is open: "device" summarizes, "panels" lists (one panel
        until Epic 1 phase 4)"""

        self.ec_producer.update("device", token)
        self.ec_producer.update("panels", token)

    def _start_reopening(self):
        if not self._reopening:
            self._reopening = True
            aiko.event.add_timer_handler(self._reopen, REOPEN_PERIOD)

    def _reopen(self):
        self._guarded("reopen", self._try_reopen)

    def _try_reopen(self):
        try:
            self._output.open()
        except DisplayNotFound:
            return
        aiko.event.remove_timer_handler(self._reopen)
        self._reopening = False
        self._output_ok = True
        self._set_device(_token(self._output.device, 48))
        self.logger.info(f"{self.name}: output {self._output.name} back")
        self._control_output("contrast", int(self._applied["contrast"]))
        for key in ("invert", "power", "all_on"):
            self._control_output(key, self._applied[key] == "on")
        self._refresh()

    def _output_failed(self, reason):
        self._output_ok = False
        self.logger.error(f"{self.name}: output {self._output.name} failed: {reason}")
        self._note_error("display_failed")
        self._set_device("absent")
        try:
            self._output.close(blank_first=False)
        except Exception:
            pass
        self._start_reopening()

    def _control_output(self, name, *args, **kwargs):
        if not self._output_ok:
            return
        try:
            getattr(self._output, name)(*args, **kwargs)
        except Exception as exception:
            self._output_failed(f"{name}: {exception}")

    def _title_strip(self):
        connection = self.share.get("connection", "NONE")
        annunciators = ("L" if self._log_pending else " ")  \
            + ("M" if connection in ("TRANSPORT", "REGISTRAR") else " ")  \
            + ("R" if connection == "REGISTRAR" else " ")
        return title_strip(self._font, self._title_text, annunciators,
            time.strftime("%H:%M:%S"))

    def _present(self, image):
        """Show a frame, with the title row when it applies, if it changed"""

        if image.size != (self._canvas.width, self._canvas.height):
            image = self._centered(image)
        if self._title_text and (self._applet is None
                or self._applet.wants_title):
            image = image.copy()
            image.paste(self._title_strip(), (0, 0))
        data = image.tobytes()
        if data == self._last_frame:
            return
        self._last_frame = data
        self._mirror_frame(data)
        self._wake()
        if not self._output_ok:
            return
        started = time.monotonic()
        try:
            self._output.show(image)
        except Exception as exception:
            return self._output_failed(f"show: {exception}")
        self._metrics["frames"] += 1
        self._metrics["frame_ms"] = round((time.monotonic() - started) * 1000)

    def _refresh(self):
        """Show the canvas again (an applet shows its next frame)"""

        self._last_frame = None
        if self._applet is None:
            self._present(self._canvas.image)

    def _wake(self):
        """Activity: keep, or bring back, the display's power"""

        self._last_change = time.monotonic()
        if self._blanked:
            self._blanked = False
            if self._applied.get("power") == "on":
                self._control_output("power", True)

    def _canvas_command(self):
        """A drawing command: the canvas is what the display shows"""

        self._metrics["commands"] += 1
        self._wake()
        if self._applet is not None:
            self._stop_applet()
            self._settle("applet", "none")
            self._last_frame = None

    # Applets ------------------------------------------------------- #

    def _stop_applet(self):
        applet, self._applet = self._applet, None
        if applet is not None:
            try:
                applet.stop()
            except Exception:
                self.logger.error(f"{self.name}: stop: {traceback.format_exc()}")
                self._metrics["errors"] += 1
            self._held.clear()
            self.ec_producer.update("applet_detail", "-")

    def _applet_finished(self):
        finished = self.share.get("applet")
        self._stop_applet()
        default, *arguments = self._default_applet.split(",")
        if default != "none" and default != finished and default in APPLETS  \
                and self._fits(APPLETS[default]):
            self.applet(default, *arguments)
        else:
            self.applet("none")

    def _keys_held(self):
        now = time.monotonic()
        return {name for name, until in self._held.items() if until > now}

    # Timers (event-loop thread), every body guarded ------------------------ #

    def _guarded(self, what, function):
        """Run a timer or callback body: an exception must never unwind the
        event loop (it isn't caught there); it stops the applet"""

        try:
            function()
        except Exception as exception:
            self.logger.error(f"{self.name}: {what}: {traceback.format_exc()}")
            self._metrics["errors"] += 1
            self._note_error(f"{what}_{type(exception).__name__}")
            if self._applet is not None:
                self._stop_applet()
                self._settle("applet", "none")
                self._refresh()

    def _tick(self):
        self._guarded("tick", self._step)

    def _step(self):
        self.last_event_thread = threading.get_ident()
        now = time.monotonic()
        self._control_output("pump")          # the window's events, if any
        applet = self._applet
        if applet is not None and now >= self._frame_due:
            period = 1.0 / (max(applet.fps, 0.001) * self._speed)
            self._frame_due = max(self._frame_due + period, now - period)
            try:
                frame = applet.step()
            except AppletDone:
                self._applet_finished()
                frame = None
            if frame is not None:
                self._present(frame)
        if self._mirror_pending is not None and now >= self._mirror_due:
            self._mirror_frame(self._mirror_pending)     # the end of a burst
        if self._title_text and now >= self._title_due:
            self._title_due = now + 1.0
            if self._applet is None:
                self._present(self._canvas.image)
        if self._blank_after and not self._blanked  \
                and self._applied.get("power") == "on"  \
                and now - self._last_change >= self._blank_after:
            self._blanked = True
            self._control_output("power", False)

    def _output_event(self, event):
        """An event from the output (the emulator window), delivered by
        pump(): "quit" and the window's own exit keys stop the Actor; every
        other key is a key() on the display, like any client's"""

        if event == "quit" or (event[0] == "tap" and event[1] in ("x", "q", "X")):
            self.stop()
        else:
            state, name = event
            self.key(name, state)

    def _run_key_map(self, key):
        """A key in the key map (keys.py), run here on the device so that
        every client sends the same "(key K)": its preset, or its setting"""

        state = self._local_keys
        commands = keymap.reset_commands(state) if key == "R"  \
            else keymap.key_command(key, state)
        for command in commands:
            if command[0] == "update":
                self._setters[command[1]](command[2])
            elif command[0] == "applet":
                self.applet(*command[1])
            elif command[0] == "key":
                self.key(*command[1])
            elif command[0] == "clear":
                self.clear()

    def _heartbeat(self):
        self._guarded("heartbeat", lambda: self.ec_producer.update(
            "heartbeat", str(int(time.monotonic() - self._started))))

    def _metrics_flush(self):
        self._guarded("metrics", self._flush_metrics)

    def _flush_metrics(self):
        now = time.monotonic()
        frames = self._metrics["frames"]
        fps = round((frames - self._frames_at_flush)
                    / max(now - self._flushed_at, 1e-6))
        self._frames_at_flush, self._flushed_at = frames, now
        if str(fps) != self.share.get("fps"):
            self.ec_producer.update("fps", str(fps))
        published = self.share.get("metrics", {})
        for key, value in self._metrics.items():
            if published.get(key) != str(value):
                self.ec_producer.update(f"metrics.{key}", str(value))

    # Callbacks from other threads: post, never touch state --------------- #

    def _connection_handler(self, connection, connection_state):
        self._post_message(
            aiko.ActorTopic.IN, "_connection_changed", [str(connection_state)])

    def _connection_changed(self, connection_state):
        self.ec_producer.update("connection", _token(connection_state))
        self._title_due = 0.0

    # Rejections, errors, shutdown --------------------------------------- #

    def _reject(self, method, reason, detail=""):
        diagnostic = f"{self.name}: {method} rejected: {reason}"
        self.logger.warning(f"{diagnostic} ({detail})" if detail else diagnostic)
        self._metrics["rejected"] += 1
        self._note_error(f"{method}_{reason}")

    def _note_error(self, what):
        self.ec_producer.update("last_error", f"{_token(what, 40)}@{_utc_now()}")

    def _shutdown(self):
        """Stop timers and blank the display; called by the CLI after the
        event loop ends (exit, Ctrl-C, SIGTERM) and by tests"""

        if self._shut:
            return
        self._shut = True
        self._stop_applet()
        for lease in self._mirrors.values():
            lease.terminate()
        self._mirrors.clear()
        for timer in (self._tick, self._heartbeat, self._metrics_flush, self._reopen):
            try:
                aiko.event.remove_timer_handler(timer)
            except Exception:
                pass
        aiko.process.connection.remove_handler(self._connection_handler)
        try:
            self._output.close(blank_first=True)
        except Exception as exception:
            self.logger.warning(f"{self.name}: close: {exception}")

# --------------------------------------------------------------------------- #
# Command line: a CLI shell (ADR-022 category Presentation and CLI shells)

def _service_filter(name):
    return aiko.ServiceFilter("*", name or get_hostname(), PROTOCOL, "*", "*", "*")

def _start_timeout(seconds, what):
    """The framework's do_command() and do_discovery() wait for ever: give up
    with exit status 1 after the timeout (P3: every request has a deadline)"""

    def timed_out():
        aiko.event.remove_timer_handler(timed_out)
        click.echo(f"Timeout after {seconds:g} s: {what}", err=True)
        aiko.process.terminate(1)

    aiko.event.add_timer_handler(timed_out, seconds)

def _remote(interface, options, command_handler):
    """Discover the OLED Actor named in the group options (-n, -t) and
    invoke one command on it"""

    name, timeout = options["name"], options["timeout"]
    _start_timeout(timeout, f"no OLED Actor named {name or get_hostname()}")
    aiko.do_command(interface, _service_filter(name), command_handler,
        terminate=True)
    aiko.process.run()

def _parse_address(ctx, param, value):
    try:
        return int(value, 0)
    except ValueError:
        raise click.BadParameter(f"{value!r} is not a number, e.g. 0x3D")

def _parse_colors(ctx, param, value):
    """-c 'FOREGROUND [BACKGROUND]': the color names (or #rrggbb), checked"""

    if value is None:
        return None
    try:
        parse_colors(value)
    except ValueError as error:
        raise click.BadParameter(
            f"{value!r}: {error}, e.g. -c yellow or -c 'yellow navy'")
    return str(value).replace(",", " ").split()

def _validate_font_size(ctx, param, value):
    try:
        parse_font_size(value)
    except ValueError as error:
        raise click.BadParameter(str(error))
    return value

def _display_hint(bus):
    found = scan_i2c(bus)
    if found:
        return ("An SSD1306 answers at "
            + " and ".join(f"0x{address:02X}" for address in found) + ": use -a")
    return ("No SSD1306 answers at "
        + " or ".join(f"0x{address:02X}" for address in ADDRESSES)
        + ": check the wiring and that I2C is enabled")

@click.group()
@click.option("--name", "-n", type=str, default=None,
    help="The OLED Actor: the one to run, or the one to command  "
         "[default: the local hostname]")
@click.option("--timeout", "-t", type=float, default=TIMEOUT, show_default=True,
    help="Seconds to wait for the OLED Actor (for list: to collect them)")
@click.pass_context

def main(ctx, name, timeout):
    """OLED Actor: run it, or send commands to the running one

    An SSD1306 128x64 OLED as an Aiko Services Actor (protocol oled:0): a
    status display for a headless host, a canvas any client draws on with
    the same S-expressions as the aiko_engine_mp OLED, settings the Aiko
    Dashboard reads and writes, and applets (games, drawings, a clock, eyes,
    a demo) that run on the display.  Without the panel, a desktop window,
    the terminal or a PNG file emulates it.

    \b
    export AIKO_MQTT_HOST=localhost       # the broker; aiko_registrar must run
    aiko_display run -a 0x3C                 # the OLED, or emulated on a desktop
    aiko_display text 0 0 hello            # from another terminal: the bottom row
    aiko_display log Hello from nomad        # scrolls; the status applet shows it
    aiko_display set contrast 64           # a setting: the Dashboard edits it too
    aiko_display applet pong                 # an applet; applet -l lists them
    aiko_display keys                        # an interactive console
    aiko_display -n w3029f1 -t 3 applet eyes  # another host, 3 s to find it
    aiko_display exit
    """

    ctx.obj = {"name": name, "timeout": timeout}

@main.command(name="run")
@click.option("--output", "-o", type=click.Choice(OUTPUTS), default="auto",
    show_default=True,
    help="oled: the SSD1306 over I2C; window (pygame), terminal, png: "
         "emulations; auto: the OLED if there is an I2C bus, else a window "
         "on a desktop with pygame, else the terminal")
@click.option("--address", "-a", default="0x3C", callback=_parse_address,
    help="I2C address of the OLED  [default: 0x3C]")
@click.option("--bus", "-b", type=int, default=1, show_default=True,
    help="I2C bus number")
@click.option("--applet", default=DEFAULT_APPLET, show_default=True,
    help="Applet to run at start; none: show the canvas")
@click.option("--font_size", "-fs", default="5x7", show_default=True,
    callback=_validate_font_size,
    help="5x7 bitmap font, or a TrueType font size in pixels, 6 to 64")
@click.option("--title", default=None,
    help="Title row text (use _ for spaces) or off  [default: the Actor name]")
@click.option("--color", "-c", default=None, callback=_parse_colors,
    metavar="'FOREGROUND [BACKGROUND]'",
    help="Colors of an emulated display, e.g. 'yellow navy': the settings "
         "foreground and background, which the keys b and B step through")
@click.option("--png", type=click.Path(dir_okay=False), default=None,
    help="File for -o png  [default: oled.png]")
@click.option("--standalone", is_flag=True,
    help="Run without an MQTT broker (status display only)")
@click.option("--strict", is_flag=True,
    help="Exit when the display can't be opened, instead of retrying")

@click.pass_obj

def run_command(options, output, address, bus, applet, font_size, title,
    color, png, standalone, strict):
    """Run the OLED Actor in the foreground (append & for the background, or
    start it with "aiko_process create")

    \b
    The display (-o):
      oled      the SSD1306 over I2C: -a address (0x3C, or 0x3D with SA0
                high), -b bus; needs "pip install luma.oled"
      window    an emulated OLED in a pygame window, 5x with pixel gaps;
                the keys work as in "aiko_display keys"; Esc, x or q exits
      terminal  half-block characters, 128x34 (Braille dots when smaller)
      png       the latest frame in a PNG file (--png, at most once a second)
      none      no display: the Actor still runs (shared state, applets)
      auto      oled when /dev/i2c-N exists, else window on a desktop with
                pygame, else terminal

    \b
    At start the Actor shows --applet (status: IP address, CPU and memory,
    disk and network, load, temperature and fan, uptime, the newest log line;
    status,screen=wifi: the Wi-Fi link; view=cpu_mem: a chart) under
    the title row: the Actor's name (-n, default the hostname; --title TEXT
    with _ for spaces, or off), the annunciators L (log lines not yet
    shown), M (connected to the broker) and R (registered), and the clock.
    -fs is the text font (5x7, or a TrueType size 6..64).  -c colors an
    emulated display, e.g. -c 'yellow navy': the settings "foreground" and
    "background", which the keys b and B step through while it runs.

    \b
    --standalone runs without an MQTT broker: the status display still
    works.  --strict exits when the display can't be opened, instead of
    reporting "device absent" and retrying every 10 s.  Ctrl-C, SIGTERM,
    "(exit)" and "aiko_display exit" all blank the display on the way out.
    """

    name = options["name"] or get_hostname()
    if output == "terminal":  # console logging would scribble on the picture
        os.environ.setdefault("AIKO_LOG_MQTT", "true")
    backend = choose_output(output, address, bus, png)
    parameters = {
        "output": backend, "applet": applet, "font": font_size,
        "title": title, "strict": strict, "colors": color,
    }
    init_args = aiko.actor_args(
        name, parameters=parameters, protocol=PROTOCOL,
        tags=service_tags(backend.name))
    signal.signal(signal.SIGTERM, lambda *_: aiko.process.terminate())
    actor = None
    try:
        actor = aiko.compose_instance(DisplayImpl, init_args)
        backend.message(f"{name}: {actor.topic_in}")
        if backend.name != "terminal":
            click.echo(f"OLED Actor {name}: {actor.topic_in}")
        aiko.process.run(mqtt_connection_required=not standalone)
    except DisplayNotFound as error:
        raise click.ClickException(f"{error}\n{_display_hint(bus)}")
    finally:
        if actor:
            actor._shutdown()

@main.command(name="exit")
@click.option("--all", "every", is_flag=True,
    help="Allow -n '*': exit every OLED Actor")
@click.pass_obj

def exit_command(options, every):
    """Blank the display and terminate the OLED Actor

    The Actor named with -n (default: the local hostname).  -n '*' with
    --all exits every OLED Actor on the broker.  Exit status 1 after -t
    seconds when no Actor answers.  The same as "(exit)", the framework's
    "(stop)", on the in topic: the display blanks on the way out.
    """

    if options["name"] == "*" and not every:
        raise click.BadParameter("-n '*' would exit every OLED Actor: add --all")
    _remote(Display, options, lambda display: display.stop())

@main.command(name="list")
@click.pass_obj

def list_command(options):
    """List the running OLED Actors: name, topic path, tags

    Every display:0 Actor on the broker (or the one named with -n), collected
    for -t seconds through the Registrar.  Exit status 1 when none is found:
    check AIKO_MQTT_HOST, that aiko_registrar runs, and for a stale retained
    Registrar announcement (see the test guide).
    """

    name, timeout = options["name"] or "*", options["timeout"]
    found = []

    def add_handler(service_details, service):
        found.append(service_details)

    def done():
        aiko.event.remove_timer_handler(done)
        for details in found:
            click.echo(f"{details[1]}  {details[0]}  {' '.join(details[5])}")
        if not found:
            click.echo("No OLED Actors found", err=True)
        aiko.process.terminate(0 if found else 1)

    aiko.do_discovery(Display,
        aiko.ServiceFilter("*", name, PROTOCOL, "*", "*", "*"), add_handler)
    aiko.event.add_timer_handler(done, timeout)
    aiko.process.run()

@main.command(name="clear")

@click.pass_obj

def clear_command(options):
    """Erase the canvas (the title row stays)

    Drawing commands (clear, text, pixels, line) stop a running applet so
    that the canvas shows; "aiko_display applet status" brings the status
    display back.  The same as "(clear)" or aiko_engine_mp's "(oled:clear)".
    """

    _remote(Canvas, options, lambda oled: oled.clear())

@main.command(name="log", no_args_is_help=True)
@click.argument("words", nargs=-1, required=True)

@click.pass_obj

def log_command(options, words):
    """Scroll the canvas up one text row and write WORDS on the bottom row

    The line is also kept (the last eight) for the status applet, which
    shows the newest, and the log applet, which shows them all; until one
    of them shows it, the title row's L annunciator is on (shared state
    log_pending).  A running applet keeps running.  At most 128 characters.
    The same as "(log WORDS ...)" or aiko_engine_mp's "(oled:log ...)".
    """

    _remote(Canvas, options, lambda oled: oled.log(*words))

@main.command(name="text", no_args_is_help=True)
@click.argument("x", type=int)
@click.argument("y", type=int)
@click.argument("words", nargs=-1, required=True)

@click.pass_obj

def text_command(options, x, y, words):
    """Write WORDS on the canvas with the text cell's bottom-left at X Y

    X is 0..127 left to right and Y 0..63 bottom to top, as on the
    aiko_engine_mp OLED: "text 0 0 hello" is the bottom row, "text 0 8 ..."
    the row above with the 5x7 font (8 pixel rows, 21 characters across).
    The font is the "font" setting.  Quote a word that starts with digits
    and a colon ("12:30").  Stops a running applet so the canvas shows.
    The same as "(text X Y WORDS ...)" or "(oled:text ...)".
    """

    _remote(Canvas, options, lambda oled: oled.text(x, y, *words))

@main.command(name="pixels", no_args_is_help=True)
@click.argument("coordinates", nargs=-1, type=int, required=True)

@click.pass_obj

def pixels_command(options, coordinates):
    """Light pixels at X Y pairs, origin bottom-left

    X 0..127, Y 0..63; at most 256 pairs; all or nothing when a coordinate
    is out of range.  The same as "(pixels X Y X Y ...)" or "(oled:pixels
    ...)"; one pixel is "(pixel X Y)".
    """

    if len(coordinates) % 2 or len(coordinates) > 2 * PIXEL_PAIRS_MAXIMUM:
        raise click.BadParameter(
            f"give X Y pairs, at most {PIXEL_PAIRS_MAXIMUM} of them")
    _remote(Canvas, options, lambda oled: oled.pixels(*coordinates))

@main.command(name="line", no_args_is_help=True)
@click.argument("x0", type=int)
@click.argument("y0", type=int)
@click.argument("x1", type=int)
@click.argument("y1", type=int)

@click.pass_obj

def line_command(options, x0, y0, x1, y1):
    """Draw a line from X0 Y0 to X1 Y1, origin bottom-left

    The same as "(line X0 Y0 X1 Y1)" (not in aiko_engine_mp).
    """

    _remote(Canvas, options, lambda oled: oled.line(x0, y0, x1, y1))

@main.command(name="set", no_args_is_help=True)
@click.argument("key", type=click.Choice(SETTINGS))
@click.argument("value")

@click.pass_obj

def set_command(options, key, value):
    """Change a setting: shared state that the Aiko Dashboard also edits

    Sends "(update KEY VALUE)" on the Actor's control topic, exactly what
    the Dashboard does when a variable is edited.  A bad value is rejected
    (last_error tells why) and the value in force is published again.
    Values are single tokens: _ stands for a space in a title.
    """

    if any(character.isspace() for character in value):
        raise click.BadParameter("no spaces in a value: use _ instead")
    name, timeout = options["name"], options["timeout"]
    what = f"no OLED Actor named {name or get_hostname()}"

    def add_handler(service_details, service):
        topic_path = service_details[0]
        aiko.process.message.publish(
            f"{topic_path}/control", f"(update {key} {value})")
        aiko.process.terminate()

    _start_timeout(timeout, what)
    aiko.do_discovery(Display, _service_filter(name), add_handler)
    aiko.process.run()

@main.command(name="applet")
@click.option("--list", "-l", "list_applets", is_flag=True,
    help="List the applets and their options, without an Actor")
@click.argument("applet_name", required=False)
@click.argument("arguments", nargs=-1)

@click.pass_obj

def applet_command(options, list_applets, applet_name, arguments):
    """Run an applet, e.g. status, pong seed=1; none shows the canvas"""

    if list_applets:
        width = max(len(applet_name) for applet_name in APPLETS)
        for applet_name, applet_class in sorted(APPLETS.items()):
            options = " ".join(f"{option}=" for option in applet_class.OPTIONS)
            summary = applet_class.summary or " ".join((applet_class.__doc__ or "").split())
            click.echo(f"{applet_name:{width}}  {summary}"
                       + (f"  [{options}]" if options else ""))
        return
    if not applet_name:
        raise click.UsageError("give an applet name, or --list")
    _remote(Interaction, options,
        lambda oled: oled.applet(applet_name, *arguments))

@main.command(name="stop")

@click.pass_obj

def stop_command(options):
    """Stop the running applet: the canvas is shown again

    The same as "aiko_display applet none" or "(applet none)".
    """

    _remote(Interaction, options, lambda oled: oled.applet("none"))

@main.command(name="mirror")
@click.argument("topic")
@click.argument("seconds", type=int, default=30)
@click.pass_obj

def mirror_command(options, topic, seconds):
    """Ask the Actor to publish its frames to TOPIC: a leased feed

    Raw frames (1024 bytes at 128x64: PIL mode "1", row major, MSB first) go
    to TOPIC whenever the panel changes, at most "mirror_rate" a second, for
    SECONDS (default 30, at most 300; repeat to extend); 0 stops.  At most
    4 holders.  The same as "(mirror TOPIC SECONDS)".  The Dashboard plug-in
    uses this for its live mirror; "mosquitto_sub -t TOPIC" shows the bytes.
    """

    _remote(Screen, options, lambda screen: screen.mirror(topic, seconds))

@main.command(name="keys")

@click.pass_obj

def keys_command(options):
    """Interactive console: keys switch applets and settings, arrows play

    \b
    s status screens (host, wifi)  S the next view of that screen (charts)
    l log  p pattern  t text  d draw  D demo  P blink  C clock  e eyes
    g games (pong, asteroids, invaders, forklift)  G forklift game
    h or ? help (the same applet key again: its next options)
    arrows: keys for the applet   0-9 speed (4 normal)   f F next/previous font
    T title  i invert  o power  a all pixels on  +/- contrast  b B color
    c clear  R reset   x or q quit the console   X exit the OLED Actor
    """

    from aiko_services.actors.display.console import KeysConsole  # (imports this module)
    KeysConsole(options["name"], options["timeout"]).run()

@main.command(name="key", no_args_is_help=True)
@click.argument("key_name")
@click.argument("state", type=click.Choice(KEY_STATES), default="tap")

@click.pass_obj

def key_command(options, key_name, state):
    """Send a key to the running display Actor

    KEY_NAME is up, down, left, right or one character; STATE is tap (held
    briefly, the default), down or up.  A key in the Actor's key map runs its
    preset or changes its setting ("key g" starts pong, "key 5" halves the
    speed, "key R" resets); any other key goes to the running applet:
    forklift_game: left and right drive, up and down lift; help: right and
    left turn the pages.  The same as "(key NAME [STATE])"; "aiko_display keys"
    sends every key this way.
    """

    _remote(Interaction, options,
        lambda oled: oled.key(key_name, state))

# --------------------------------------------------------------------------- #
# Reference text for --help, made from the same tables the code uses

def _block(lines):
    return "\b\n" + "\n".join(lines)

def _applets_reference():
    width = max(len(name) for name in APPLETS)
    lines = ["Applets  (aiko_display applet NAME [WORDS ...] [key=value ...]; -l lists them)"]
    for name, applet_class in sorted(APPLETS.items()):
        options = " ".join(f"{option}=" for option in applet_class.OPTIONS)
        text = applet_class.summary + (f"  [{options}]" if options else "")
        lines += textwrap.wrap(text, width=75, initial_indent=f"  {name:{width}}  ",
                               subsequent_indent=" " * (width + 4))
    return _block(lines)

def _settings_reference():
    lines = ["Settings  (aiko_display set KEY VALUE, or (update KEY VALUE) on the control",
             "           topic; the Aiko Dashboard edits them; a bad value converges back)"]
    cells = [f"{setting.name:12} {setting.values}" for setting in SETTINGS_SPEC]
    for left, right in zip(cells[0::2], cells[1::2] + [""]):
        lines.append(f"  {left:37}{right}".rstrip())
    return _block(lines)

_SETTINGS_REFERENCE = _settings_reference()
_STATE_REFERENCE = _block([
    "Shared state  (aiko_dashboard, or (share TOPIC SECONDS *) on control)",
    "  backend device panels size origin depth settings keys.* connection",
    "  mirrors applets applet applet_detail fps",
    "  speed font contrast invert power all_on title blank_after foreground",
    "  background heartbeat last_error log_count log_pending metrics.commands",
    "  metrics.rejected metrics.frames metrics.frame_ms metrics.errors",
    "  metrics.mirrored",
])
_WIRE_REFERENCE = _block([
    "Wire commands on the in topic  (mosquitto_pub -t TOPIC/in -m '...')",
    "  origin bottom-left; the aiko_engine_mp names in brackets",
    "  (clear)                  [(oled:clear)]    erase the canvas",
    "  (log WORDS ...)          [(oled:log ..)]   scroll up, write the bottom row",
    "  (pixel X Y)              [(oled:pixel ..)] light a pixel",
    "  (pixels X Y X Y ...)     [(oled:pixels .)] at most 256 pairs",
    "  (line X0 Y0 X1 Y1)                         draw a line",
    "  (text X Y WORDS ...)     [(oled:text ..)]  text with its bottom-left at X Y",
    "  (exit)                   = (stop)          blank the display and terminate",
    "  (applet NAME [ARGS ...])                   run an applet; none: the canvas",
    "  (key NAME [tap|down|up])                   a mapped key runs its preset,",
    "                                             any other goes to the applet",
    "  (mirror TOPIC SECONDS)                     a leased feed of raw frames to",
    "                                             TOPIC (the Dashboard plug-in)",
    "  Anything else is rejected (last_error, metrics.rejected).",
])

def _preset_text(commands):
    words = []
    for command in commands:
        if command[0] == "update":
            words.append(f"{command[1]} {command[2]}")
        else:
            words.append(" ".join(command[1]))
    return " ".join(words)

def _keys_reference():
    lines = ["Keys  (the map lives on the Actor: \"(key K)\" from the console, the",
             "       emulator window, the plug-in or \"aiko_display key\"; the same key",
             "       again: the next preset)"]
    for key, presets in keymap.PRESETS.items():
        text = " | ".join(_preset_text(preset) for preset in presets)
        lines += textwrap.wrap(text, width=75, initial_indent=f"  {key}  ",
                               subsequent_indent="     ")
    lines += [
        "  S  the next view of the status screen shown: text, then its charts",
        "  arrows  (key left|right|up|down) for the applet: the forklift game, help",
        "  0-9  speed: 0 fastest (x4), 4 normal, 9 slowest   f F  next/previous font",
        "  T title on/off   i invert   o power   a all pixels on   + - contrast by 16",
        "  b B  the next foreground / background color (emulated displays)  c clear",
        "  R  reset the settings and the colors, show status   ? the same as h",
        "  x q  quit the console   X  exit the OLED Actor (then y to confirm)",
        "  The same keys work in the emulator window (-o window); x q X exit there",
    ]
    return _block(lines)

def _reference():
    return "\n\n".join([_applets_reference(), _SETTINGS_REFERENCE, _STATE_REFERENCE,
                        _WIRE_REFERENCE, _keys_reference()])

main.epilog = _reference()
main.commands["applet"].help = (
    "Run an applet on the display, replacing the running one; ARGS are words and\n"
    "key=value options.  \"none\" shows the canvas; --list lists the applets without\n"
    "an Actor.  Every applet is deterministic for a seed= (no clocks, only frame\n"
    "counts); \"set speed\" changes their pace.\n\n" + _applets_reference())
def _set_help():
    rows = [f"{'KEY':12} {'VALUE':22} MEANING"]
    for setting in SETTINGS_SPEC:
        rows += textwrap.wrap(setting.description, width=76,
            initial_indent=f"{setting.name:12} {setting.values:22} ",
            subsequent_indent=" " * 36)
    return main.commands["set"].help.rstrip() + "\n\n\b\n" + "\n".join(rows)

main.commands["set"].help = _set_help()
main.commands["keys"].help = (
    "Interactive console for the running OLED Actor: keys typed here become wire\n"
    "commands and settings, and a status line follows the Actor's shared state.\n"
    "Needs a terminal.  x or q quits the console; the Actor keeps running.\n\n"
    + _keys_reference())

if __name__ == "__main__":
    main()
