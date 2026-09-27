#!/usr/bin/env python3
#
# Aiko Services: Dashboard plug-in page for a display Actor
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# One Aiko Dashboard page for a running display Actor (protocol display:0,
# the OLED example): a live mirror of the panel, the shared state, the
# process log, and the same keys as "aiko_oled keys".  Every key typed here
# is sent as "(key K tap)": the key map lives on the Actor.  The mirror is
# the leased frame feed "(mirror TOPIC SECONDS)" of the Screen aspect.
#
# Usage
# ~~~~~
#   aiko_dashboard -p aiko_services.main.dashboard_plugins \
#                  -p aiko_services.examples.oled.dashboard_plugin
#   Select the display Actor, press S.  D or Esc: back to the Dashboard.
#
# Keys on the page (the Actor's own keys, plus the page's)
# ~~~~~~~~~~~~~~~~
#   every letter, digit and symbol of the key map -> (key K tap); arrows too
#   m  demo (the Dashboard reserves D)     K  stop the Actor (confirmed)
#   H  this page's help (? is the Dashboard's)   Enter  edit a setting
#   L  log level     Esc Backspace q  back to the Dashboard     x  quit
#
# Design (P2, P5, CP-F)
# ~~~~~~
# - The mirror subscription is made once per Dashboard process, on the
#   Dashboard's own topic path, and never removed: the Actor's lease stops
#   the traffic.  Frames arrive on the event-loop thread; the handler only
#   swaps a bytes reference, and the widget renders on the TUI thread.
# - Sends are guarded by the connection state: publish() would block.
# - The page is rebuilt on every resize; nothing is subscribed in __init__.
# - Rendering reuses the terminal backend's half-block and Braille lines
#   and its emulation of power, all_on, invert, contrast and the colors.
#
# Not part of the Interface composition pattern (ADR-022 category
# Presentation and CLI shells) — see e_10 §2.16: a Dashboard shell.

import time

from asciimatics.event import KeyboardEvent
from asciimatics.exceptions import NextScene
from asciimatics.screen import Screen as AsciimaticsScreen
from asciimatics.widgets import (
    Label, Layout, MultiColumnListBox, PopUpDialog, TextBox, Widget,
)
from PIL import Image, ImageColor

import aiko_services as aiko
from aiko_services.main.connection import ConnectionState
from aiko_services.main.dashboard import LogLevelPopupMenu, LogUI, ServiceFrame

from aiko_services.examples.oled.display import TerminalDisplay, xterm_color
from aiko_services.examples.oled.oled import (
    Canvas, Display, Interaction, SETTINGS, SETTINGS_BY_NAME, Screen,
)

__all__ = ["DisplayFrame", "DisplayPage", "MirrorWidget", "plugins", "render_mirror"]

MIRROR_SECONDS = 30            # the lease the page asks for
MIRROR_RENEW_PERIOD = 10.0     # seconds between renewals
ARROW_PERIOD = 0.1             # seconds between repeats of one arrow key
ERROR_FLASH = 5.0              # seconds last_error shows red after a change
WIDE = (132, 48)               # columns, rows: half blocks and the full table
NARROW = (80, 24)              # Braille beside a state column
STATUS_KEYS = ("applet", "applet_detail", "fps", "speed", "font", "contrast",
               "invert", "power", "all_on", "foreground", "background", "last_error")
ALIASES = {"m": "D"}           # the Dashboard reserves D (demo), ? (help), x X

# The newest mirrored frame, shared by every page instance (the frame is
# rebuilt on resize): (topic_path, bytes, monotonic time)
_latest = {"frame": None, "at": 0.0}

def _mirror_handler(_aiko, topic, payload):
    """On the event-loop thread: keep the newest frame, nothing else"""

    if isinstance(payload, (bytes, bytearray)):
        _latest["frame"] = bytes(payload)
        _latest["at"] = time.monotonic()

def mirror_topic():
    """The Dashboard's own topic for the feed (P5: its own topic path)"""

    return f"{aiko.process.topic_path}/display/mirror"

# --------------------------------------------------------------------------- #

def render_mirror(frame_bytes, size, cache, blocks, colours):
    """The frame as rows of (text, colour, attribute, background): the
    terminal backend's half blocks (blocks) or Braille, with the panel's
    emulation of power, all_on, invert, contrast and the colors, from the
    shared state.  Pure: no screen, no I/O"""

    width, height = size
    image = Image.frombytes("1", (width, height), frame_bytes)
    emulation = TerminalDisplay()                # never opened: a renderer
    emulation.blocks = blocks
    emulation.frame = image
    emulation.powered = cache.get("power", "on") != "off"
    emulation.all_lit = cache.get("all_on", "off") == "on"
    emulation.inverted = cache.get("invert", "off") == "on"
    try:
        emulation.brightness = max(0, min(255, int(cache.get("contrast", "255"))))
    except ValueError:
        pass
    for name in ("foreground", "background"):
        try:
            setattr(emulation, name, ImageColor.getrgb(cache.get(name, "white"
                if name == "foreground" else "black"))[:3])
        except ValueError:
            pass
    rows = emulation.lines(emulation.appearance())
    if colours >= 256:
        colour, background = xterm_color(emulation.lit_color()), xterm_color(emulation.background)
        attribute = AsciimaticsScreen.A_NORMAL
    else:                                        # 8 colours: white, bold when bright
        colour, background = AsciimaticsScreen.COLOUR_WHITE, AsciimaticsScreen.COLOUR_BLACK
        attribute = AsciimaticsScreen.A_BOLD if emulation.brightness >= 128 else AsciimaticsScreen.A_NORMAL
    return [(row, colour, attribute, background) for row in rows]

class DisplayPage:
    """The page's model, without asciimatics: what a key does, the mirror
    rows, the staleness of the feed, the last_error flash.  Pure, so tests
    run without a screen"""

    def __init__(self, blocks):
        self.blocks = blocks
        self.size = (128, 64)
        self.arrows_sent = {}            # arrow name: monotonic time sent
        self.error = "-"
        self.error_changed_at = -ERROR_FLASH
        self._rendered = (None, None)    # (key, rows)

    def action(self, key_code, now):
        """What a key does on the page: ("key", NAME), ("back",),
        ("stop",), ("help",), ("edit",), ("log_level",), or None for a key
        the Dashboard handles (D ? x X Tab) or an ignored one"""

        arrows = {AsciimaticsScreen.KEY_LEFT: "left", AsciimaticsScreen.KEY_RIGHT: "right",
                  AsciimaticsScreen.KEY_UP: "up", AsciimaticsScreen.KEY_DOWN: "down"}
        if key_code in arrows:
            name = arrows[key_code]
            if now - self.arrows_sent.get(name, -1.0) < ARROW_PERIOD:
                return ("consumed",)                     # a repeat: coalesced
            self.arrows_sent[name] = now
            return ("key", name)
        if key_code in (AsciimaticsScreen.KEY_ESCAPE, AsciimaticsScreen.KEY_BACK, ord("q")):
            return ("back",)
        if key_code in (10, 13):
            return ("edit",)
        if 32 <= key_code <= 126:
            character = chr(key_code)
            if character in ("D", "?", "x", "X"):
                return None                              # the Dashboard's keys
            if character == "K":
                return ("stop",)
            if character == "H":
                return ("help",)
            if character == "L":
                return ("log_level",)
            return ("key", ALIASES.get(character, character))
        return None

    def observe(self, cache, now):
        """Follow the shared state: the size, the last_error flash"""

        try:
            self.size = tuple(int(n) for n in cache.get("size", "128x64").split("x"))
        except ValueError:
            pass
        error = cache.get("last_error", "-")
        if error != self.error:
            self.error, self.error_changed_at = error, now

    def error_is_fresh(self, now):
        return self.error != "-" and now - self.error_changed_at < ERROR_FLASH

    def rows(self, cache, colours):
        """The mirror rows for the newest frame, rendered once per frame
        and per change of the settings that color it"""

        frame = _latest["frame"]
        if frame is None or len(frame) != (self.size[0] // 8) * self.size[1]:
            return None
        key = (id(frame), self.size, self.blocks, colours,
               tuple(cache.get(name) for name in ("power", "all_on", "invert",
                                                  "contrast", "foreground", "background")))
        if self._rendered[0] != key:
            self._rendered = (key, render_mirror(frame, self.size, cache, self.blocks, colours))
        return self._rendered[1]

    @staticmethod
    def staleness(now):
        return now - _latest["at"] if _latest["frame"] is not None else None

    def feed_status(self, cache, now, connected):
        """The service bar's suffix"""

        if not connected:
            return "MQTT down"
        if "mirrors" not in cache:
            return "mirror: not supported by this Actor"
        stale = self.staleness(now)
        if stale is None:
            return "mirror: waiting for frames"
        if stale > 4.0:
            return f"mirror: no frames {stale:.0f} s"
        return f"mirror {cache.get('mirror_rate', '5')} Hz  fps {cache.get('fps', '?')}"

# --------------------------------------------------------------------------- #

class MirrorWidget(Widget):
    """The panel, in half blocks or Braille, in the panel's colors"""

    def __init__(self, page, rows, name=None):
        super().__init__(name, tab_stop=False)
        self.page = page
        self.rows = rows
        self.cache = {}
        self.message = "mirror: waiting for frames"

    def update(self, frame_no):
        colours = self._frame.canvas.colours if hasattr(self._frame.canvas, "colours") else 8
        rows = self.page.rows(self.cache, colours) if self._frame.canvas.unicode_aware else None
        if rows is None:
            text = self.message if self._frame.canvas.unicode_aware  \
                else "the terminal is not Unicode aware: no mirror"
            self._frame.canvas.print_at(text[:self._w], self._x, self._y)
            return
        for i, (text, colour, attribute, background) in enumerate(rows[:self._h]):
            self._frame.canvas.print_at(text[:self._w], self._x, self._y + i,
                                        colour, attribute, background)

    def reset(self):
        pass

    def process_event(self, event):
        return event

    def required_height(self, offset, width):
        return self.rows

    @property
    def value(self):
        return None

class DisplayFrame(ServiceFrame):
    """The Dashboard page: the mirror, the shared state, the log, the keys"""

    _subscribed = False          # one binary subscription per Dashboard process

    def __init__(self, screen, dashboard):
        super().__init__(screen, dashboard, name="display_frame")
        self.wide = screen.width >= WIDE[0] and screen.height >= WIDE[1]
        self.fits = screen.width >= NARROW[0] and screen.height >= NARROW[1]
        self.page = DisplayPage(blocks=self.wide)
        self.canvas_proxy = self.interaction_proxy = None   # (Frame owns canvas)
        self.screen_proxy = self.display_proxy = None
        self.topic_path = None
        self.service_text = ""
        self.requested = False           # the feed asked for, once the state is known

        self.mirror_widget = MirrorWidget(self.page, 32 if self.wide else 16)
        if self.wide:
            layout = Layout([1])
            self.add_layout(layout)
            layout.add_widget(self.mirror_widget)
            self.state_widget = self._state_widget(max(6, screen.height - 43))
            layout = Layout([1])
            self.add_layout(layout)
            self.legend = Label("", height=2)
            layout.add_widget(self.legend)
            layout = Layout([1])
            self.add_layout(layout)
            layout.add_widget(self.state_widget)
        elif self.fits:
            layout = Layout([64, screen.width - 64])
            self.add_layout(layout)
            layout.add_widget(self.mirror_widget, 0)
            self.state_widget = MultiColumnListBox(16, ["<0"], options=[],
                titles=["name=value"], on_select=self._on_select_variable)
            layout.add_widget(self.state_widget, 1)
            layout = Layout([1])
            self.add_layout(layout)
            self.legend = Label("", height=1)
            layout.add_widget(self.legend)
        else:
            layout = Layout([1])
            self.add_layout(layout)
            layout.add_widget(Label(f"terminal too small for the mirror ({NARROW[0]}x{NARROW[1]})"))
            self.state_widget = self._state_widget(8)
            layout.add_widget(self.state_widget)
            self.legend = Label("", height=1)
            layout.add_widget(self.legend)
        self.log_ui = LogUI(self)
        self.fix()

    def _state_widget(self, height):
        return MultiColumnListBox(height, ["<22", "<0"], options=[],
            titles=["Variable", "Value"], on_select=self._on_select_variable)

    # The Service ------------------------------------------------------ #

    def _service_frame_start(self, service, service_ec_consumer):
        topic_path = service[0]
        if topic_path == self.topic_path:
            return                                       # idempotent
        if self.topic_path is not None:
            self._service_frame_stop(self.service)
        self.topic_path = topic_path
        self.service_text = self._service_title.value
        self.canvas_proxy = aiko.get_service_proxy(f"{topic_path}/in", Canvas)
        self.interaction_proxy = aiko.get_service_proxy(f"{topic_path}/in", Interaction)
        self.screen_proxy = aiko.get_service_proxy(f"{topic_path}/in", Screen)
        self.display_proxy = aiko.get_service_proxy(f"{topic_path}/in", Display)
        if not DisplayFrame._subscribed:
            aiko.process.add_message_handler(_mirror_handler, mirror_topic(), binary=True)
            DisplayFrame._subscribed = True
        _latest["frame"], _latest["at"] = None, 0.0
        self.requested = False
        aiko.event.add_timer_handler(self._renew, MIRROR_RENEW_PERIOD)
        self.log_ui._service_frame_start(service, service_ec_consumer)

    def _service_frame_stop(self, service):
        if self.topic_path is None:
            return
        aiko.event.remove_timer_handler(self._renew)
        if self._connected():
            self.screen_proxy.mirror(mirror_topic(), 0)        # destroy the feed
        self.log_ui._service_frame_stop(service)
        self.topic_path = None
        _latest["frame"], _latest["at"] = None, 0.0

    def _renew(self):
        """Ask for the feed, and keep asking: the lease outlives a page that
        exits without stop (x, a crash) by MIRROR_SECONDS at most.  Only
        once the shared state shows "mirrors": an older Actor has none"""

        if self.topic_path and self._connected() and "mirrors" in self._cache():
            self.screen_proxy.mirror(mirror_topic(), MIRROR_SECONDS)
            self.requested = True

    def _cache(self):
        consumer = self.dashboard.ec_consumer
        return consumer.cache if consumer is not None else {}

    @staticmethod
    def _connected():
        return aiko.process.connection.is_connected(ConnectionState.TRANSPORT)

    # Keys ----------------------------------------------------------- #

    def process_event(self, event):
        if isinstance(event, KeyboardEvent) and self.topic_path:
            action = self.page.action(event.key_code, time.monotonic())
            if action is not None:
                self._act(action)
                return None
        return super().process_event(event)

    def _act(self, action):
        kind = action[0]
        if kind == "key":
            if self._connected():
                self.interaction_proxy.key(action[1], "tap")
        elif kind == "back":
            self._service_frame_stop(self.service)
            self.dashboard.subscribed_service = None
            raise NextScene("Dashboard")
        elif kind == "stop":
            self._confirm_stop()
        elif kind == "help":
            self.scene.add_effect(PopUpDialog(self._screen, self._help(), ["OK"], theme="nice"))
        elif kind == "edit":
            self._on_select_variable()
        elif kind == "log_level":
            self.scene.add_effect(LogLevelPopupMenu(self._screen, self.state_widget, self.topic_path))

    def _confirm_stop(self):
        def _on_close(button_index):
            if button_index == 1 and self._connected():
                self.display_proxy.stop()

        self.scene.add_effect(PopUpDialog(self._screen, "Stop the display Actor?",
                                          ["Cancel", "Stop"], on_close=_on_close, theme="nice"))

    def _on_select_variable(self):
        """Enter on a state row: edit a setting, as the Dashboard does"""

        row = self.state_widget.value
        if row is None:
            return
        cells = self.state_widget.options[row][0]
        name, value = cells if len(cells) == 2 else cells[0].partition("=")[::2]
        if name not in SETTINGS:
            return
        text_box = TextBox(1, None, None, False, False)
        text_box.value[0] = value

        def _on_close(button_index):
            if button_index == 1 and self._connected():
                self._update_ecproducer_variable(self.topic_path, name, text_box.value[0])

        setting = SETTINGS_BY_NAME[name]
        popup = PopUpDialog(self._screen, f"Update {name} ({setting.values})" + " " * 24,
                            ["Cancel", "OK"], on_close=_on_close, theme="nice")
        layout = Layout([1])
        popup.add_layout(layout)
        layout.add_widget(text_box)
        popup.fix()
        self.scene.add_effect(popup)

    def _help(self):
        cache = self._cache()
        keys = cache.get("keys", {})
        applets = "  ".join(f"{key} {value.split('|')[0]}" for key, value in sorted(keys.items())
                            if key in ("s", "l", "p", "t", "d", "D", "P", "C", "e", "g", "G", "h"))
        return "\n".join([
            "The Actor's keys, sent as (key K tap):",
            applets or "s l p t d D P C e g G h  (applets)",
            "S status view  0-9 speed  f F font  T title  i invert  o power  a all_on",
            "+ - contrast  b B colors  c clear  R reset  arrows: the applet's",
            "",
            "This page: m demo (D is back)  K stop the Actor  Enter edit a setting",
            "L log level  H this help  Esc Backspace q back  x quit the Dashboard",
        ])

    # Drawing ---------------------------------------------------------- #

    @property
    def frame_update_count(self):
        stale = self.page.staleness(time.monotonic())
        return 2 if stale is not None and stale < 2.0 else 5

    def _update(self, frame_no):
        super()._update(frame_no)                        # may start the Service
        if self.topic_path is None:
            return
        now = time.monotonic()
        cache = self._cache()
        if not self.requested:
            self._renew()                                # the state arrived: ask now
        self.page.observe(cache, now)
        self.mirror_widget.cache = cache
        self.mirror_widget.message = self.page.feed_status(cache, now, self._connected())
        self._service_title.value = f"{self.service_text}    {self.mirror_widget.message}"
        rows = []
        names = sorted(cache) if self.wide else [name for name in STATUS_KEYS if name in cache]
        for name in names:
            value = cache[name]
            if isinstance(value, dict):
                for sub_name, sub_value in sorted(value.items()):
                    rows.append((f"{name}.{sub_name}", str(sub_value)))
            elif name != "source_file":
                text = str(value)
                if name == "last_error" and self.page.error_is_fresh(now):
                    text = self._color_text(self.RED, text)
                rows.append((name, text))
        if self.wide:
            self.state_widget.options = [((name, value), index)
                                         for index, (name, value) in enumerate(rows)]
        else:
            width = max(8, self.state_widget.width)
            self.state_widget.options = [((f"{name}={value}"[:width],), index)
                                         for index, (name, value) in enumerate(rows)]
        keys = cache.get("keys", {})
        self.legend.text = "keys: " + "  ".join(f"{key} {value.split('|')[0]}"
            for key, value in sorted(keys.items()) if len(key) == 1) if keys else ""
        self.log_ui._update(frame_no)

# plugin key: the protocol type of display:0
plugins = {"display": DisplayFrame}
