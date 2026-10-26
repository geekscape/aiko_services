# Description
# ~~~~~~~~~~~
# The Aiko Dashboard's plug-in interface: what a page for one Service
# subclasses and reuses.
#
# A plug-in imports these from the package, not from this module ...
#
#   from aiko_services.ide.tui.dashboard import LogUI, ServiceFrame
#
# ... so that this file can be reorganized without touching a plug-in.
#
# - FrameCommon   state, colours and helpers shared by every Dashboard frame
# - ServiceFrame  the base class of a page for one selected Service
# - LogUI         the log pane, reusable as it is
#
# "LogLevelPopupMenu" is part of the interface as well, and a plug-in
# imports it from the package in the same way.  It is in "dashboard.py",
# because it asks DashboardFrame for the singleton, and the interface must
# not reach back into the application.
#
# "dashboard.py" holds the application: the Dashboard page, the Log page,
# the plug-in registry and the console script.
#
# To Do
# ~~~~~
# - Make the colours a theme declaration, instead of module constants
# - Give LogLevelPopupMenu the dashboard as an argument, so that it joins
#   the rest of the interface here

from collections import defaultdict, deque

from asciimatics.event import KeyboardEvent
from asciimatics.exceptions import NextScene, StopApplication
from asciimatics.screen import Screen
from asciimatics.widgets import Frame as asciimatics_Frame  # avoid confusion !
from asciimatics.widgets import (
    Label, Layout, MultiColumnListBox, PopUpDialog, Text, Widget
)
from asciimatics.widgets.utilities import THEMES

import aiko_services as aiko  # designed to be external to the main framework
from aiko_services.main.connection import ConnectionState
from aiko_services.main.utilities import get_mqtt_configuration

__all__ = ["FrameCommon", "LogUI", "ServiceFrame"]

_FRAME_UPDATE_RATE = 20 / 4  # 5 Hz (assuming update rate is roughly 20 Hz)
_LOG_RING_BUFFER_SIZE = 128

BLACK = Screen.COLOUR_BLACK
WHITE = Screen.COLOUR_WHITE
GREEN = Screen.COLOUR_GREEN
FONT_BOLD = Screen.A_BOLD
FONT_NORMAL = Screen.A_NORMAL

NICE_COLORS = defaultdict(lambda: (WHITE, FONT_NORMAL, BLACK))
NICE_COLORS["focus_button"] = (GREEN, FONT_BOLD, BLACK)
NICE_COLORS["selected_focus_field"] = (GREEN, FONT_BOLD, BLACK)
NICE_COLORS["title"] = (BLACK, FONT_BOLD, WHITE)
THEMES["nice"] = NICE_COLORS

class FrameCommon:
    def __init__(self, screen, height, width, has_border, name):
        super(FrameCommon, self).__init__(
            screen, height, width, has_border=has_border, name=name)
        self.adjust_palette_required = True

        mqtt_configuration = get_mqtt_configuration()
        server_up = mqtt_configuration[0]
        self.mqtt_host = mqtt_configuration[1]
        self.mqtt_port = mqtt_configuration[2]
        if not server_up:
            self.mqtt_host = "MQTT SERVER UNAVAILABLE"

        self.connection_popup = None
        self.connection_state_last = None
    #   aiko.process.connection.add_handler(self._connection_state_handler)

    def _add_service_bar(self):
        layout = Layout([1])
        self.add_layout(layout)
        service_title = Text()
        service_title.custom_colour = "title"
        service_title.disabled = True
        layout.add_widget(service_title)
        return service_title

    def _get_title(self, name=None, context=""):
        if name:
            title = f"{name}: "
        else:
            title = "AikoServices: "
        if context:
            title += context
        else:
            title += f"{self.mqtt_host[0:40]}:{self.mqtt_port}"
        return title

    def _add_title_bar(self):
        layout = Layout([3, 1])
        self.add_layout(layout)
        layout.add_widget(Label(self._get_title()), 0)
        layout.add_widget(Label('Press "?" for help', align=">"), 1)

    def _adjust_palette(self):
        self.palette = NICE_COLORS
        self.adjust_palette_required = False

    BLACK = 0
    RED = 1
    GREEN = 2
    YELLOW = 3
    BLUE = 4
    MAGENTA = 5
    CYAN = 6
    WHITE = 7

    # Reset: \x1b[0m  Color: \x1b[3?n

    def _color_text(self, color, text):
        return f"\x1b[3{color}m{text}"

    def _connection_state_handler(self, connection, connection_state):
        def _on_close(button_index):
            self.connection_popup = False

        if self.scene:
            self.connection_state_last = connection_state
            if connection.is_connected(ConnectionState.REGISTRAR):
                if self.connection_popup:
                      self.scene.remove_effect(self.connection_popup)
                      self.connection_popup = False
                raise NextScene("Dashboard")
            elif not self.connection_popup:
                self.connection_popup = PopUpDialog(self._screen,
                    "MQTT server and/or Aiko Registar not found",
                    ["OK"], on_close=_on_close, theme="nice")
                self.scene.add_effect(self.connection_popup)

    @property
    def frame_update_count(self):
        return _FRAME_UPDATE_RATE

    def _short_name(self, path):
        after_slash = path.rfind("/") + 1
        return path[after_slash:]

    def _update(self, frame_no):
        super(FrameCommon, self)._update(frame_no)
        connection = aiko.process.connection
        if frame_no <= 5:
            self.connection_state_last = connection.connection_state
        elif frame_no % _FRAME_UPDATE_RATE:  # roughly 1 Hz
            connection = aiko.process.connection
            connection_state = connection.connection_state
            if self.connection_state_last != connection_state:
                self._connection_state_handler(connection, connection_state)

    def _update_ecproducer_variable(self, topic_path, name, value):
        topic_path_control = topic_path + "/control"
        payload_out = f"(update {name} {value})"
        aiko.process.message.publish(topic_path_control, payload_out)

# TODO: Replace _process_event_common() with the following ...
# https://asciimatics.readthedocs.io/en/stable/widgets.html#global-key-handling
    def _process_event_common(self, event):
        if isinstance(event, KeyboardEvent):
            if event.key_code == ord("?"):
            # TODO: [h] History / Log multiple Services (toggle)
            # TODO: [p] Publish to Service
            # TODO: [K] Kill Service (dialog for terminate / kill, remote)
            #       [Delete] As above
            # TODO: [L] Show Log page: Support multiple Service logs
            # TODO: [N] New Service / Actor / Pipeline (parameters)
            # TODO: [S] Show Service page: Generic page, log level, subscribe
            #                              Parameters
            #       [Enter] As above
            # TODO: [T] Terminate Actor
                text = " Help   Aiko Services Dashboard\n"        \
                       " ----   -----------------------\n"        \
                       " Enter  Update variable value\n"          \
                       " Tab    Move to next section\n"           \
                       " c      Copy topic path to clipboard \n"  \
                       " f      Filter Service (toggle)\n"        \
                       " l      Log level change\n"               \
                       " s      Select Service (toggle)\n"        \
                       " C      Clear selection\n"                \
                       " D      Show Dashboard page\n"            \
                       " K      Kill Service (local)\n"           \
                       " L      Show Log page\n"                  \
                       " S      Show Service page\n"              \
                       " x      Exit"
                self.scene.add_effect(
                    PopUpDialog(self._screen, text, ["OK"], theme="nice"))
            if event.key_code in [ord("x"), ord("X"), Screen.ctrl("c")]:
                self.services_cache = None
                aiko.services_cache_delete()
                raise StopApplication("User quit request")

    def _update_field(self, list, name, value, width):  # wrap long lines
        value = str(value)
        padding = 0
        while len(value):
            if isinstance(name, str):
                field = (name, " "*padding + value[0:width-padding])
                name = ""
            else:
                field = (" "*padding + value[0:width-padding],)
            list.append(field)
            value = value[width-padding:]
            if padding == 0:
                padding = 2

class ServiceFrame(FrameCommon, asciimatics_Frame):
    def __init__(self, screen, dashboard, name="service_frame"):
        super(ServiceFrame, self).__init__(
            screen, screen.height, screen.width, has_border=False, name=name
        )

        self.dashboard = dashboard
        self.service = None
        self._add_title_bar()
        self._service_title = self._add_service_bar()
    #   self._value_width = self._service_widget.width

    def _update(self, frame_no):
        if self.adjust_palette_required:
            self._adjust_palette()

        if self.dashboard.selected_service != self.dashboard.subscribed_service:
            self.dashboard.subscribed_service = self.dashboard.selected_service
            self.service = self.dashboard.selected_service
            topic_path = aiko.ServiceTopicPath.parse(self.service[0]).terse
            name = self._short_name(self.service[1])
            self._service_title.value = f"Service: {topic_path}: {name}"
        # Plugins that add handlers to the ec_consumer must also remove them !
            self._service_frame_start(self.service, self.dashboard.ec_consumer)

        super(ServiceFrame, self)._update(frame_no)

    def _service_frame_start(self, service, service_ec_consumer):
        pass

    def _service_frame_stop(self, service):
        pass

    def process_event(self, event):
        if isinstance(event, KeyboardEvent):
            if event.key_code == ord("D"):
                self._service_frame_stop(self.service)
                self.dashboard.subscribed_service = None
                raise NextScene("Dashboard")
        self._process_event_common(event)
        return super(ServiceFrame, self).process_event(event)

# Re-usable logging user interface  # TODO: Consider turning into a Widget ?
# https://asciimatics.readthedocs.io/en/stable/widgets.html#custom-widgets

class LogUI:
    def __init__(self, parent, height=Widget.FILL_FRAME):
        self.parent = parent
        self.log_buffer = None
        self.log_show_latest = True
        self.recorder = None
        self.topic_paths = {}

        self._log_widget = MultiColumnListBox(
            height, ["<0"], options=[],
            titles=["Date       Time        Log level Message"]
        )
        layout_0 = Layout([1])
        parent.add_layout(layout_0)
        recorder_label = Label(f"Log Recorder: TOPIC_PATH")
        recorder_label.custom_colour = "title"
        layout_0.add_widget(recorder_label)
        layout_1 = Layout([1], fill_frame=True)
        parent.add_layout(layout_1)
        layout_1.add_widget(self._log_widget)

    def _add_topic_path(self, topic_path):
        if topic_path not in self.topic_paths:
            self.topic_paths[topic_path] = topic_path
            topic_path, _, _ = topic_path.rpartition("/")
            topic_path += "/0/log"  # TODO: Use correct Service Id
            aiko.process.add_message_handler(
                self._topic_log_handler, topic_path)

    def process_event(self, event):
        if isinstance(event, KeyboardEvent):
            widget = self._log_widget
            if len(widget._options) > 0 and event.key_code == Screen.KEY_HOME:
                self.log_show_latest = False
                widget._line = 0
                widget.value = widget.options[widget._line][1]
            if len(widget._options) > 0 and event.key_code == Screen.KEY_END:
                self.log_show_latest = True
                widget._line = len(widget._options) - 1
                widget.value = widget.options[widget._line][1]
            if event.key_code in [Screen.KEY_UP, Screen.KEY_PAGE_UP]:
                self.log_show_latest = False
            if event.key_code in [Screen.KEY_DOWN, Screen.KEY_PAGE_DOWN]:
                if widget._line == len(widget._options) - 1:
                    self.log_show_latest = True

    def _remove_topic_path(self, topic_path):
        if topic_path in self.topic_paths:
            del self.topic_paths[topic_path]
            topic_path, _, _ = topic_path.rpartition("/")
            topic_path += "/0/log"  # TODO: Use correct Service Id
            aiko.process.remove_message_handler(
                self._topic_log_handler, topic_path)

    def _service_frame_start(self, service, service_ec_consumer):
        self.log_buffer = deque(maxlen=_LOG_RING_BUFFER_SIZE)
        self._add_topic_path(service[0])

    def _service_frame_stop(self, service):
        topic_paths = self.topic_paths.copy()
        for topic_path in topic_paths:
            self._remove_topic_path(topic_path)
        self.log_buffer = None
        self.topic_paths = {}

    def _topic_log_handler(self, _aiko, topic, payload_in):
        self.log_buffer.append(payload_in)

    def _update(self, frame_no):
        widget = self._log_widget
        if self.log_show_latest and len(widget._options) > 0:
            widget._line = len(widget._options) - 1
            widget.value = widget.options[widget._line][1]

        log_records = []
        if self.log_buffer:
            for log_record in self.log_buffer:
            #   log_records.append((log_record,))  # No record line wrapping
                self.parent._update_field(         # With record line wrapping
                    log_records, None, log_record, self._log_widget.width)
        self._log_widget.options = [
            (log_record, row_index)
            for row_index, log_record in enumerate(log_records)
        ]

