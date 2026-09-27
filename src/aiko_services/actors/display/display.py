#!/usr/bin/env python3
#
# Aiko Services: OLED Display Actor
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# An SSD1306 128x64 OLED as a Display Actor (protocol "display:0"): a
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
import random
import re
import threading
import time
import traceback


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
    DisplayNotFound, NullOutputImpl, output_args,
)
from aiko_services.actors.display.graphics import (
    HEIGHT, WIDTH, FrameBuffer, blank, parse_font_size, title_strip,
)
from aiko_services.actors.display import keys as keymap  # the emulator window's keys

__all__ = [
    "ASPECT_TAGS", "Canvas", "Display", "Interaction", "DisplayImpl", "PROTOCOL",
    "PROTOCOL_TYPE", "SETTINGS", "SETTINGS_SPEC", "Screen", "Setting",
    "WIRE_COMMANDS", "service_filter", "service_tags",
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
KEY_DOWN_MAXIMUM = 2.0       # seconds a "down" holds a key, unless repeated:
                             # a lost "up" can't hold a key for ever (P9)
MIRROR_LEASES_MAXIMUM = 4     # holders of the frame feed
MIRROR_TOPIC_LENGTH_MAXIMUM = 128
MIRROR_SECONDS_MAXIMUM = 300
SPEED_MINIMUM, SPEED_MAXIMUM = 0.1, 10.0
BLANK_AFTER_MAXIMUM = 86400   # seconds

TICK_PERIOD = 1 / 30          # the frame timer; applets run at fps × speed
HEARTBEAT_PERIOD = 1.0
METRICS_PERIOD = 2.0
REOPEN_PERIOD = 10.0          # retry a failed display this often
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
        STATE is "tap" (default: held briefly), "down" or "up"; "down"
        holds the key for 2 seconds at most, so a client holding a key
        repeats "down" (a lost "up" can't hold it for ever).  A key in
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

def service_filter(name):
    """The discovery filter for the Display Actor named NAME (default: this
    host's name): protocol display:0, any namespace, owner, transport, tags"""

    return aiko.ServiceFilter("*", name or get_hostname(), PROTOCOL, "*", "*", "*")

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
            self._held[name] = time.monotonic() +  \
                (KEY_DOWN_MAXIMUM if state == "down" else KEY_HOLD)
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
