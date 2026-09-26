#!/usr/bin/env python3
#
# Aiko Services: OLED Actor
# ~~~~~~~~~~~~~~~~~~~~~~~~~
# An SSD1306 128x64 OLED as an Actor: a canvas that any client draws on
# with the same S-expressions the MicroPython aiko_engine_mp OLED accepts,
# settings that the Aiko Dashboard reads and writes, and applications that
# run on the display, above all a status display for headless hosts.  On a
# desktop without the panel, the OLED is emulated in a window, in the
# terminal or in a PNG file.
#
# Usage
# ~~~~~
#   export AIKO_MQTT_HOST=localhost
#   aiko_oled run [-o oled -a 0x3D] [--application status] [--standalone]
#   aiko_oled exit | list
#   aiko_oled clear | log WORDS | text X Y WORDS | pixels X Y ... | line X0 Y0 X1 Y1
#   aiko_oled set KEY VALUE          # contrast 128, invert on, title Aiko, font 10 ...
#   aiko_oled application NAME [ARGS ...] | stop | key NAME [tap|down|up]
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
#   (exit)                                       blank the display and terminate
#   (application NAME [ARGS ...])                run an application; "none" shows the canvas
#   (key NAME [tap|down|up])                     a key for the running application
#   Anything else on the "in" topic is rejected (P12), including "(run)".
#
# Shared state (aiko_dashboard shows it; the RW keys can be edited there)
# ~~~~~~~~~~~~
#   backend device size origin connection applications application(RW)
#   application_detail fps speed(RW) font(RW) contrast(RW) invert(RW)
#   power(RW) all_on(RW) title(RW) blank_after(RW) heartbeat last_error
#   log_count metrics.commands metrics.rejected metrics.frames
#   metrics.frame_ms metrics.errors
#
# Bounds (P9): log ring 8 lines (oldest dropped); 256 pixel pairs per
# command; 128 characters of text per command; 64 characters per
# application argument; 5 keys held.  A frame is shown at most once per
# tick (30 Hz) and only when it changed.
#
# Coordinates: origin bottom-left, y upwards (aiko_engine_mp compatible);
# the only y flip is graphics.Canvas._device_y()
#
# Protocol: oled:0
#
# To Do
# ~~~~~
# - Phase 1: status application, help; Phase 2: games, forklift, drawings,
#   demo, "aiko_oled keys" console
# - Dashboard plug-in; convergence with aiko_engine_mp (protocol oled:0)
# - Promote into src/aiko_services/main/oled/ (then aiko_oled ships in the wheel)

from abc import abstractmethod
import collections
import os
import random
import re
import signal
import threading
import time
import traceback

import click

import aiko_services as aiko
from aiko_services.main.utilities import get_hostname, parse

from aiko_services.examples.oled.applications import (
    APPLICATIONS, ApplicationDone, Host, parse_application_args,
)
from aiko_services.examples.oled.display import (
    ADDRESSES, OUTPUTS, DisplayNotFound, NullDisplay, choose_display,
    parse_colors, scan_i2c,
)
from aiko_services.examples.oled.graphics import (
    HEIGHT, WIDTH, Canvas, parse_font_size, title_strip,
)

__all__ = [
    "OLED", "OLEDApplications", "OLEDImpl", "PROTOCOL", "PROTOCOL_TYPE",
    "SETTINGS", "WIRE_COMMANDS", "main",
]

_VERSION = 0
PROTOCOL_TYPE = "oled"
PROTOCOL = f"{aiko.SERVICE_PROTOCOL_AIKO}/{PROTOCOL_TYPE}:{_VERSION}"

# aiko_engine_mp names its commands "oled:clear" etc: the same methods
_ALIASES = {f"oled:{name}": name
    for name in ("clear", "log", "pixel", "pixels", "text")}

LOG_LINES = 8                 # the log ring: oldest line dropped
PIXEL_PAIRS_MAXIMUM = 256     # per (pixels ...) command
TEXT_LENGTH_MAXIMUM = 128     # characters per (text ...) or (log ...)
TITLE_LENGTH_MAXIMUM = 32
KEYS_HELD_MAXIMUM = 5
KEY_NAMES = ("up", "down", "left", "right")  # plus any single character
KEY_STATES = ("tap", "down", "up")
KEY_HOLD = 0.15               # seconds a tapped key stays held (MQTT latency)
SPEED_MINIMUM, SPEED_MAXIMUM = 0.1, 10.0
BLANK_AFTER_MAXIMUM = 86400   # seconds

TICK_PERIOD = 1 / 30          # the frame timer; applications run at fps × speed
HEARTBEAT_PERIOD = 1.0
METRICS_PERIOD = 2.0
REOPEN_PERIOD = 10.0          # retry a failed display this often
TIMEOUT = 5.0                 # CLI: seconds to wait for the OLED Actor
DEFAULT_APPLICATION = "none"  # Phase 1: "status"

# Settings: shared state that anyone may write with "(update KEY VALUE)" on
# the control topic; the change handler applies them through one setter each
SETTINGS = ("application", "contrast", "invert", "power", "all_on", "title",
            "font", "speed", "blank_after")

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

class OLED(aiko.Actor):
    """
    A 128x64 one-bit canvas on an OLED, wire-compatible with the
    aiko_engine_mp (MicroPython) OLED: "(oled:text ...)" and "(text ...)"
    are the same command.  Coordinates have their origin at the bottom-left,
    y upwards.  Every method is one-way: a rejected command changes
    nothing but "metrics.rejected" and "last_error" in the shared state.
    Drawing on the canvas stops any running application, except "log",
    whose lines the status application shows itself.
    """

    aiko.Interface.default("OLED", "aiko_services.examples.oled.oled.OLEDImpl")

    @abstractmethod
    def clear(self):
        """Erase the canvas (the title row stays).
        Wire form: "(clear)" or "(oled:clear)".
        Outcome: the display shows a blank canvas.  Projection: command"""

    @abstractmethod
    def log(self, *words):
        """Scroll the canvas up one text row and write WORDS on the bottom
        row; the line is also kept (8 lines) for the status application.
        Wire form: "(log WORDS ...)" or "(oled:log WORDS ...)"; runs of
        spaces collapse to one.  Outcome: share "log_count" +1.
        Projection: command"""

    @abstractmethod
    def pixel(self, x, y):
        """Light one pixel: x 0..127 left to right, y 0..63 bottom to top.
        Wire form: "(pixel X Y)" or "(oled:pixel X Y)".
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

    @abstractmethod
    def exit(self):
        """Blank the display and terminate the process.
        Wire form: "(exit)".  Projection: command"""

class OLEDApplications(aiko.Interface):
    """
    The higher-level features: applications are sources of frames that the
    Actor runs on the display (status, games, drawings, demo ...), listed
    in share "applications".  Their settings (speed, font) and everything
    else about the display are shared state, written with
    "(update KEY VALUE)" on the control topic: see SETTINGS.
    """

    aiko.Interface.default(
        "OLEDApplications", "aiko_services.examples.oled.oled.OLEDImpl")

    @abstractmethod
    def application(self, name, *args):
        """Run an application, replacing the running one; "(application none)"
        stops it and shows the canvas.  ARGS are words and key=value options
        that the application accepts, e.g. "(application pong seed=1)".
        Outcome: share "application", "application_detail".
        Rejected when the name or an option is unknown.  Projection: command"""

    @abstractmethod
    def key(self, name, state="tap"):
        """A key for the running application: NAME is "up", "down", "left",
        "right" or one character; STATE is "tap" (default: held briefly),
        "down" or "up".  Wire form: "(key NAME [STATE])".
        Projection: command"""

# The commands accepted on the "in" topic: the Interfaces' methods, plus the
# framework's log level and stop (P12: deny by default)
WIRE_COMMANDS = frozenset(name
    for interface in (OLED, OLEDApplications)
    for name, member in vars(interface).items()
    if getattr(member, "__isabstractmethod__", False)
    and not name.startswith("_")) | {"set_log_level", "stop"}

# --------------------------------------------------------------------------- #

class _Host(Host):
    """What applications see of the Actor"""

    def __init__(self, actor):
        self._actor = actor

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

    def log_lines(self):
        return list(self._actor._log)

    def keys_held(self):
        return self._actor._keys_held()

    def status(self, token):
        self._actor.ec_producer.update("application_detail", _token(token))

    def control(self, name, value):
        if name in ("contrast", "invert", "power", "all_on"):
            self._actor._setters[name](str(value))

class OLEDImpl(OLED, OLEDApplications):
    def __init__(self, context):
        context.call_init(self, "Actor", context)
        parameters = context.get_parameters() or {}

        self._display = parameters.get("display") or NullDisplay()
        self._display_ok = False
        self._reopening = False
        self._strict = bool(parameters.get("strict", False))
        self._font = parse_font_size(parameters.get("font", "5x7"))
        self._canvas = Canvas(self._font)
        self._log = collections.deque(maxlen=LOG_LINES)
        self._log_total = 0
        self._log_pending = False   # the "L" annunciator
        self._rng = random.Random()
        self._metrics = {"commands": 0, "rejected": 0, "frames": 0,
                         "frame_ms": 0, "errors": 0}
        self._speed = 1.0
        self._blank_after = 0
        self._blanked = False
        self._application = None
        self._default_application = str(
            parameters.get("application") or DEFAULT_APPLICATION)
        self._held = {}             # key name: held until (monotonic)
        self._host = _Host(self)
        self._last_frame = None     # bytes of the frame on the display
        self._started = time.monotonic()
        self._last_change = self._started
        self._frame_due = 0.0
        self._title_due = 0.0
        self._frames_at_flush, self._flushed_at = 0, self._started
        self._shut = False
        self.last_event_thread = None  # for tests: where handlers run

        title = str(parameters.get("title") or get_hostname())
        self._title_text = "" if title == "off" else title.replace("_", " ")
        self._canvas.title_rows = self._font.cell_height if self._title_text else 0

        self._setters = {
            "application": self._set_application,
            "contrast": self._set_contrast,
            "invert": lambda value: self._set_flag("invert", value),
            "power": lambda value: self._set_flag("power", value),
            "all_on": lambda value: self._set_flag("all_on", value),
            "title": self._set_title,
            "font": self._set_font,
            "speed": self._set_speed,
            "blank_after": self._set_blank_after,
        }
        self.share.update({
            "source_file": f"v{_VERSION}⇒ {__file__}",
            "backend": self._display.name,
            "device": "-",
            "size": f"{WIDTH}x{HEIGHT}",
            "origin": "bottom",
            "connection": _token(aiko.process.connection.get_state()),
            "applications": ",".join(sorted(APPLICATIONS)) or "none",
            "application": "none",
            "application_detail": "-",
            "fps": "0",
            "speed": "1",
            "font": self._font.token(),
            "contrast": "255",
            "invert": "off",
            "power": "on",
            "all_on": "off",
            "title": _token(title) if self._title_text else "off",
            "blank_after": "0",
            "heartbeat": "0",
            "last_error": "-",
            "log_count": "0",
            "metrics": {key: "0" for key in self._metrics},
        })
        self._applied = {key: self.share[key] for key in SETTINGS}
        self.ec_producer.add_handler(self._ec_producer_change_handler)

        self._open_display()
        aiko.process.connection.add_handler(self._connection_handler)
        aiko.event.add_timer_handler(self._tick, TICK_PERIOD)
        aiko.event.add_timer_handler(self._heartbeat, HEARTBEAT_PERIOD)
        aiko.event.add_timer_handler(self._metrics_flush, METRICS_PERIOD)
        self._present(self._canvas.image)
        if self._default_application != "none":
            self.application(self._default_application)
        self.logger.info(f"{self.name}: display {self.share['backend']} "
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

    # Wire commands: OLED (the canvas) -------------------------------------- #

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
        self._log_pending = True
        self._canvas.log(line)
        self.ec_producer.update("log_count", str(self._log_total))
        if self._application is None:
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

    def exit(self):
        self.logger.info(f"{self.name}: exit")
        self._metrics["commands"] += 1
        aiko.process.terminate()

    # Wire commands: OLEDApplications --------------------------------------- #

    def application(self, name, *args):
        name = str(name)
        if name == "none":
            self._metrics["commands"] += 1
            self._wake()
            self._stop_application()
            self._settle("application", "none")
            self._refresh()
            return
        application_class = APPLICATIONS.get(name)
        if application_class is None:
            return self._reject_setting("application", "application_unknown", name)
        try:
            words, options = parse_application_args(
                args, application_class.OPTIONS)
            instance = application_class(self._host, words, options)
        except ValueError as error:
            return self._reject_setting("application", "application_args", str(error))
        except Exception:
            self.logger.error(f"{self.name}: {name}: {traceback.format_exc()}")
            self._metrics["errors"] += 1
            return self._reject_setting("application", "application_failed", name)
        self._metrics["commands"] += 1
        self._wake()
        self._stop_application()
        self._application = instance
        self._frame_due = time.monotonic()
        self._settle("application", name)
        self.ec_producer.update("application_detail",
            _token(instance.description) if instance.description else "-")

    def key(self, name, state="tap"):
        name, state = str(name), str(state)
        if not (name in KEY_NAMES or len(name) == 1):
            return self._reject("key", "name", name[:20])
        if state not in KEY_STATES:
            return self._reject("key", "state", state[:20])
        self._metrics["commands"] += 1
        self._wake()
        if state == "up":
            self._held.pop(name, None)
        else:
            self._held[name] = float("inf") if state == "down"  \
                else time.monotonic() + KEY_HOLD
            while len(self._held) > KEYS_HELD_MAXIMUM:
                del self._held[next(iter(self._held))]
        if self._application is not None:
            self._guarded("key", lambda: self._application.key(name, state))

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

    def _set_application(self, value):
        self.application(*str(value).split(","))

    def _set_contrast(self, value):
        try:
            number = _int(value, "contrast", 0, 255)
        except _Reject as reject:
            return self._reject_setting("contrast", reject.reason)
        self._control_display("contrast", number)
        self._settle("contrast", str(number))

    def _set_flag(self, key, value):
        try:
            flag = _flag(value, key)
        except _Reject as reject:
            return self._reject_setting(key, reject.reason)
        if key == "power":
            self._blanked = False
            self._last_change = time.monotonic()
        self._control_display(key, flag)
        self._settle(key, "on" if flag else "off")

    def _set_title(self, value):
        text = str(value)
        if len(text) > TITLE_LENGTH_MAXIMUM:
            return self._reject_setting("title", "title_too_long")
        token = _token(text)
        self._title_text = "" if token in ("off", "-") else token.replace("_", " ")
        self._canvas.title_rows = self._font.cell_height if self._title_text else 0
        self._settle("title", token if self._title_text else "off")
        self._refresh()

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

    def _set_speed(self, value):
        try:
            speed = float(str(value))
        except ValueError:
            return self._reject_setting("speed", "speed_not_number")
        if not SPEED_MINIMUM <= speed <= SPEED_MAXIMUM:
            return self._reject_setting("speed", "speed_range")
        self._speed = speed
        self._settle("speed", f"{speed:g}")

    def _set_blank_after(self, value):
        try:
            seconds = _int(value, "blank_after", 0, BLANK_AFTER_MAXIMUM)
        except _Reject as reject:
            return self._reject_setting("blank_after", reject.reason)
        self._blank_after = seconds
        self._settle("blank_after", str(seconds))
        if not seconds:
            self._wake()

    # The display --------------------------------------------------------- #

    def _open_display(self):
        try:
            self._display.open()
        except DisplayNotFound as error:
            if self._strict:
                raise
            self.logger.warning(f"{self.name}: display {self._display.name}: {error}")
            self._note_error("display_not_found")
            self.ec_producer.update("device", "absent")
            self._start_reopening()
            return
        self._display_ok = True
        self.ec_producer.update("device", _token(self._display.device, 48))

    def _start_reopening(self):
        if not self._reopening:
            self._reopening = True
            aiko.event.add_timer_handler(self._reopen, REOPEN_PERIOD)

    def _reopen(self):
        self._guarded("reopen", self._try_reopen)

    def _try_reopen(self):
        try:
            self._display.open()
        except DisplayNotFound:
            return
        aiko.event.remove_timer_handler(self._reopen)
        self._reopening = False
        self._display_ok = True
        self.ec_producer.update("device", _token(self._display.device, 48))
        self.logger.info(f"{self.name}: display {self._display.name} back")
        self._control_display("contrast", int(self._applied["contrast"]))
        for key in ("invert", "power", "all_on"):
            self._control_display(key, self._applied[key] == "on")
        self._refresh()

    def _display_failed(self, reason):
        self._display_ok = False
        self.logger.error(f"{self.name}: display {self._display.name} failed: {reason}")
        self._note_error("display_failed")
        self.ec_producer.update("device", "absent")
        try:
            self._display.close(blank_first=False)
        except Exception:
            pass
        self._start_reopening()

    def _control_display(self, name, value):
        if not self._display_ok:
            return
        try:
            getattr(self._display, name)(value)
        except Exception as exception:
            self._display_failed(f"{name}: {exception}")

    def _title_strip(self):
        connection = self.share.get("connection", "NONE")
        annunciators = ("L" if self._log_pending else " ")  \
            + ("M" if connection in ("TRANSPORT", "REGISTRAR") else " ")  \
            + ("R" if connection == "REGISTRAR" else " ")
        return title_strip(self._font, self._title_text, annunciators,
            time.strftime("%H:%M"))

    def _present(self, image):
        """Show a frame, with the title row when it applies, if it changed"""

        if self._title_text and (self._application is None
                or self._application.wants_title):
            image = image.copy()
            image.paste(self._title_strip(), (0, 0))
        data = image.tobytes()
        if data == self._last_frame:
            return
        self._last_frame = data
        self._wake()
        if not self._display_ok:
            return
        started = time.monotonic()
        try:
            self._display.show(image)
        except Exception as exception:
            return self._display_failed(f"show: {exception}")
        self._metrics["frames"] += 1
        self._metrics["frame_ms"] = round((time.monotonic() - started) * 1000)

    def _refresh(self):
        """Show the canvas again (an application shows its next frame)"""

        self._last_frame = None
        if self._application is None:
            self._present(self._canvas.image)

    def _wake(self):
        """Activity: keep, or bring back, the display's power"""

        self._last_change = time.monotonic()
        if self._blanked:
            self._blanked = False
            if self._applied.get("power") == "on":
                self._control_display("power", True)

    def _canvas_command(self):
        """A drawing command: the canvas is what the display shows"""

        self._metrics["commands"] += 1
        self._wake()
        if self._application is not None:
            self._stop_application()
            self._settle("application", "none")
            self._last_frame = None

    # Applications ------------------------------------------------------- #

    def _stop_application(self):
        application, self._application = self._application, None
        if application is not None:
            try:
                application.stop()
            except Exception:
                self.logger.error(f"{self.name}: stop: {traceback.format_exc()}")
                self._metrics["errors"] += 1
            self._held.clear()
            self.ec_producer.update("application_detail", "-")

    def _application_finished(self):
        finished = self.share.get("application")
        self._stop_application()
        default = self._default_application
        if default != "none" and default != finished and default in APPLICATIONS:
            self.application(default)
        else:
            self.application("none")

    def _keys_held(self):
        now = time.monotonic()
        return {name for name, until in self._held.items() if until > now}

    # Timers (event-loop thread), every body guarded ------------------------ #

    def _guarded(self, what, function):
        """Run a timer or callback body: an exception must never unwind the
        event loop (it isn't caught there); it stops the application"""

        try:
            function()
        except Exception as exception:
            self.logger.error(f"{self.name}: {what}: {traceback.format_exc()}")
            self._metrics["errors"] += 1
            self._note_error(f"{what}_{type(exception).__name__}")
            if self._application is not None:
                self._stop_application()
                self._settle("application", "none")
                self._refresh()

    def _tick(self):
        self._guarded("tick", self._step)

    def _step(self):
        self.last_event_thread = threading.get_ident()
        now = time.monotonic()
        for event in self._display.poll():
            if event == "quit":
                self.exit()
            else:
                state, name = event
                self.key(name, state)
        application = self._application
        if application is not None and now >= self._frame_due:
            period = 1.0 / (max(application.fps, 0.001) * self._speed)
            self._frame_due = max(self._frame_due + period, now - period)
            try:
                frame = application.step()
            except ApplicationDone:
                self._application_finished()
                frame = None
            if frame is not None:
                self._present(frame)
        if self._title_text and now >= self._title_due:
            self._title_due = now + 1.0
            if self._application is None:
                self._present(self._canvas.image)
        if self._blank_after and not self._blanked  \
                and self._applied.get("power") == "on"  \
                and now - self._last_change >= self._blank_after:
            self._blanked = True
            self._control_display("power", False)

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
        self._stop_application()
        for timer in (self._tick, self._heartbeat, self._metrics_flush, self._reopen):
            try:
                aiko.event.remove_timer_handler(timer)
            except Exception:
                pass
        aiko.process.connection.remove_handler(self._connection_handler)
        try:
            self._display.close(blank_first=True)
        except Exception as exception:
            self.logger.warning(f"{self.name}: close: {exception}")

# --------------------------------------------------------------------------- #
# Command line: a CLI shell (ADR-022, exempt from Interface composition)

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

def _remote(interface, name, timeout, command_handler):
    """Discover the OLED Actor and invoke one command on it"""

    _start_timeout(timeout, f"no OLED Actor named {name or get_hostname()}")
    aiko.do_command(interface, _service_filter(name), command_handler,
        terminate=True)
    aiko.process.run()

def _remote_options(command):
    command = click.option("--timeout", "-t", type=float, default=TIMEOUT,
        show_default=True, help="Seconds to wait for the OLED Actor")(command)
    command = click.option("--name", "-n", type=str, default=None,
        help="OLED Actor name, default is the local hostname")(command)
    return command

def _parse_address(ctx, param, value):
    try:
        return int(value, 0)
    except ValueError:
        raise click.BadParameter(f"{value!r} is not a number, e.g. 0x3D")

def _parse_colors(ctx, param, value):
    if value is None:
        return None
    try:
        return parse_colors(value)
    except ValueError as error:
        raise click.BadParameter(
            f"{value!r}: {error}, e.g. -c yellow or -c 'yellow navy'")

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

def main():
    """OLED Actor: run it, or send commands to the running one

    \b
    export AIKO_MQTT_HOST=localhost
    aiko_oled run -a 0x3D                # the OLED, or an emulation on a desktop
    aiko_oled text 0 0 hello             # from another terminal or host
    aiko_oled set contrast 64            # settings are shared state (Dashboard too)
    aiko_oled exit
    """

@main.command(name="run")
@click.option("--name", "-n", type=str, default=None,
    help="OLED Actor name, default is the local hostname")
@click.option("--output", "-o", type=click.Choice(OUTPUTS), default="auto",
    show_default=True,
    help="oled: the SSD1306 over I2C; window (pygame), terminal, png: "
         "emulations; auto: the OLED if there is an I2C bus, else a window "
         "on a desktop with pygame, else the terminal")
@click.option("--address", "-a", default="0x3C", callback=_parse_address,
    help="I2C address of the OLED  [default: 0x3C]")
@click.option("--bus", "-b", type=int, default=1, show_default=True,
    help="I2C bus number")
@click.option("--application", default=DEFAULT_APPLICATION, show_default=True,
    help="Application to run at start; none: show the canvas")
@click.option("--font_size", "-fs", default="5x7", show_default=True,
    callback=_validate_font_size,
    help="5x7 bitmap font, or a TrueType font size in pixels, 6 to 64")
@click.option("--title", default=None,
    help="Title row text (use _ for spaces) or off  [default: the name]")
@click.option("--color", "-c", default=None, callback=_parse_colors,
    metavar="'FOREGROUND [BACKGROUND]'",
    help="Pixel colors of an emulated display, e.g. 'yellow navy'")
@click.option("--png", type=click.Path(dir_okay=False), default=None,
    help="File for -o png  [default: oled.png]")
@click.option("--standalone", is_flag=True,
    help="Run without an MQTT broker (status display only)")
@click.option("--strict", is_flag=True,
    help="Exit when the display can't be opened, instead of retrying")

def run_command(name, output, address, bus, application, font_size, title,
    color, png, standalone, strict):
    """Run the OLED Actor (foreground; append & or use aiko_process create)"""

    name = name or get_hostname()
    if output == "terminal":  # console logging would scribble on the picture
        os.environ.setdefault("AIKO_LOG_MQTT", "true")
    display = choose_display(output, address, bus, png, color)
    parameters = {
        "display": display, "application": application, "font": font_size,
        "title": title or name, "strict": strict,
    }
    init_args = aiko.actor_args(
        name, parameters=parameters, protocol=PROTOCOL, tags=["ec=true"])
    signal.signal(signal.SIGTERM, lambda *_: aiko.process.terminate())
    actor = None
    try:
        actor = aiko.compose_instance(OLEDImpl, init_args)
        display.message(f"{name}: {actor.topic_in}")
        if display.name != "terminal":
            click.echo(f"OLED Actor {name}: {actor.topic_in}")
        aiko.process.run(mqtt_connection_required=not standalone)
    except DisplayNotFound as error:
        raise click.ClickException(f"{error}\n{_display_hint(bus)}")
    finally:
        if actor:
            actor._shutdown()

@main.command(name="exit")
@_remote_options
@click.option("--all", "every", is_flag=True,
    help="Allow --name '*': exit every OLED Actor")

def exit_command(name, timeout, every):
    """Blank the display and terminate the OLED Actor"""

    if name == "*" and not every:
        raise click.BadParameter("--name '*' would exit every OLED Actor: add --all")
    _remote(OLED, name, timeout, lambda oled: oled.exit())

@main.command(name="list")
@click.option("--timeout", "-t", type=float, default=2.0, show_default=True,
    help="Seconds to collect the running OLED Actors")

def list_command(timeout):
    """List the running OLED Actors: name, topic path, tags"""

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

    aiko.do_discovery(OLED,
        aiko.ServiceFilter("*", "*", PROTOCOL, "*", "*", "*"), add_handler)
    aiko.event.add_timer_handler(done, timeout)
    aiko.process.run()

@main.command(name="clear")
@_remote_options

def clear_command(name, timeout):
    """Erase the canvas"""

    _remote(OLED, name, timeout, lambda oled: oled.clear())

@main.command(name="log", no_args_is_help=True)
@_remote_options
@click.argument("words", nargs=-1, required=True)

def log_command(name, timeout, words):
    """Scroll the canvas up and write WORDS on the bottom row"""

    _remote(OLED, name, timeout, lambda oled: oled.log(*words))

@main.command(name="text", no_args_is_help=True)
@_remote_options
@click.argument("x", type=click.IntRange(0, WIDTH - 1))
@click.argument("y", type=click.IntRange(0, HEIGHT - 1))
@click.argument("words", nargs=-1, required=True)

def text_command(name, timeout, x, y, words):
    """Write WORDS with the text cell's bottom-left at X Y (origin bottom-left)"""

    _remote(OLED, name, timeout, lambda oled: oled.text(x, y, *words))

@main.command(name="pixels", no_args_is_help=True)
@_remote_options
@click.argument("coordinates", nargs=-1, type=int, required=True)

def pixels_command(name, timeout, coordinates):
    """Light pixels: X Y pairs, origin bottom-left"""

    if len(coordinates) % 2 or len(coordinates) > 2 * PIXEL_PAIRS_MAXIMUM:
        raise click.BadParameter(
            f"give X Y pairs, at most {PIXEL_PAIRS_MAXIMUM} of them")
    _remote(OLED, name, timeout, lambda oled: oled.pixels(*coordinates))

@main.command(name="line", no_args_is_help=True)
@_remote_options
@click.argument("x0", type=click.IntRange(0, WIDTH - 1))
@click.argument("y0", type=click.IntRange(0, HEIGHT - 1))
@click.argument("x1", type=click.IntRange(0, WIDTH - 1))
@click.argument("y1", type=click.IntRange(0, HEIGHT - 1))

def line_command(name, timeout, x0, y0, x1, y1):
    """Draw a line from X0 Y0 to X1 Y1 (origin bottom-left)"""

    _remote(OLED, name, timeout, lambda oled: oled.line(x0, y0, x1, y1))

@main.command(name="set", no_args_is_help=True)
@_remote_options
@click.argument("key", type=click.Choice(SETTINGS))
@click.argument("value")

def set_command(name, timeout, key, value):
    """Change a setting: the shared state that the Dashboard also edits

    \b
    contrast 0..255   invert on|off   power on|off   all_on on|off
    title WORDS_WITH_UNDERSCORES|off   font 5x7|6..64   speed 0.1..10
    blank_after SECONDS (0: never)   application NAME[,ARG,...]
    """

    if any(character.isspace() for character in value):
        raise click.BadParameter("no spaces in a value: use _ instead")
    what = f"no OLED Actor named {name or get_hostname()}"

    def add_handler(service_details, service):
        topic_path = service_details[0]
        aiko.process.message.publish(
            f"{topic_path}/control", f"(update {key} {value})")
        aiko.process.terminate()

    _start_timeout(timeout, what)
    aiko.do_discovery(OLED, _service_filter(name), add_handler)
    aiko.process.run()

@main.command(name="application", no_args_is_help=True)
@_remote_options
@click.argument("application_name")
@click.argument("arguments", nargs=-1)

def application_command(name, timeout, application_name, arguments):
    """Run an application, e.g. status, pong seed=1; none shows the canvas"""

    _remote(OLEDApplications, name, timeout,
        lambda oled: oled.application(application_name, *arguments))

@main.command(name="stop")
@_remote_options

def stop_command(name, timeout):
    """Stop the running application: the canvas is shown"""

    _remote(OLEDApplications, name, timeout, lambda oled: oled.application("none"))

@main.command(name="key", no_args_is_help=True)
@_remote_options
@click.argument("key_name")
@click.argument("state", type=click.Choice(KEY_STATES), default="tap")

def key_command(name, timeout, key_name, state):
    """Send a key to the running application: up, down, left, right or a character"""

    _remote(OLEDApplications, name, timeout,
        lambda oled: oled.key(key_name, state))

if __name__ == "__main__":
    main()
