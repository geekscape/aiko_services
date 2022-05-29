#!/usr/bin/env python3
#
# Note
# ~~~~
# Debugging: aiko.public.message.publish("DASHBOARD", f"Debug message")
#
# To Do
# ~~~~~
# * BUG: Dashboard isn't terminating ECConsumer lease extend timer :(
#
# *** Press "L" key to get Dashboard local log circular buffer on screen ***
#
# * Turn Registrar into an ECProducer
# * Integrate into Ray HLActor ... Service, Actor, ECProducer, ECConsumer
#
# * Provide Historical Service add / remove section (circular buffer)
# - Consider how to efficiently provide Service summary lifecycle states
#
# - Selecting (mouse or tab key) Service allows ...
#   * Toggle show/hide Services with specific field values (query * * * *)
#   - Service to be terminated / killed ("k" key)
#   * Subscribe to MQTT messages ("s" key) from topic (/#, /out, /state, /log)
#   *** Subscribe to "+/+/+/log" ("l" key), circular buffer --> new page ?
#   - Publish MQTT message ("p" key) to topic (/#, /in, /control, ...)
#
# - Service variable details should sort variable names alphabetically
#   - Toggle show/hide of Service variables "services.*" visually redundant
#   - Toggle show/hide Service variables with specific names (regex)
# - Selecting (mouse or tab key) a Service variable allows ...
#   * Service variable value updating, e.g enable debug logging !
# - Allow Service variables to be added and removed
#
# - Dashboard Web browser (JavaScript) implementation using MQTT / WebSockets
#   - Service / ECProducer / ECConsumer JavaScript implementation
#   - Integrate Dashboard into HighLighter Web !
#
# Service variables that Services should have ...
# - lifecycle state: ...
# - log level: none, debug
# - statistics: busy/idle time, mailbox queue size, message count, uptime
#
# Actors that should have interesting variables ...
# - MQTT: statistics / variables ?
# - Host / Containers (root ProcessManager)
# - Registrar(s), LifeCycleManager(s), StorageManager(s), HyperSpace
# - Pipeline(s) / PipelineElement(s)
# - Ray node(s)

from collections import defaultdict, deque

from asciimatics.event import KeyboardEvent
from asciimatics.exceptions import (
    NextScene, ResizeScreenError, StopApplication
)
from asciimatics.scene import Scene
from asciimatics.screen import Screen
from asciimatics.widgets import (
    Divider, Frame, Label, Layout, MultiColumnListBox, PopUpDialog, Widget
)
from asciimatics.widgets.utilities import THEMES

from aiko_services import *

BLACK = Screen.COLOUR_BLACK
WHITE = Screen.COLOUR_WHITE
GREEN = Screen.COLOUR_GREEN
FONT_BOLD = Screen.A_BOLD
FONT_NORMAL = Screen.A_NORMAL

_LOG_RING_BUFFER_SIZE = 128

_SERVICE_SELECTED = None  # written by Dashboard._on_change_services()
_SERVICE_SUBSCRIBED = None  # written by LogFrame._update() and process_event()

class FrameCommon:
    def __init__(self, screen, height, width, has_border, name):
        super(FrameCommon, self).__init__(
            screen, height, width, has_border=has_border, name=name)
        self.adjust_palette_required = True
        self._create_nice_colors()
        THEMES["nice"] = self._nice_colors

    def _adjust_palette(self):
        self.palette = self._nice_colors
        self.adjust_palette_required = False

    def _create_nice_colors(self):
        self._nice_colors = defaultdict(lambda: (WHITE, FONT_NORMAL, BLACK))
        self._nice_colors["selected_focus_field"] = (GREEN, FONT_BOLD, BLACK)
        self._nice_colors["title"] = (BLACK, FONT_BOLD, WHITE)

    @property
    def frame_update_count(self):
        return 4  # assuming 20 FPS, then refresh screen at 5 Hz

# TODO: Replace _process_event_common() with the following ...
# https://asciimatics.readthedocs.io/en/stable/widgets.html#global-key-handling
    def _process_event_common(self, event):
        if isinstance(event, KeyboardEvent):
            if event.key_code in [ord("?")]:
                message ="Help\n"  \
                         "D: Show Dashboard page\n"  \
                         "L: Show Log page"
                self.scene.add_effect(
                    PopUpDialog(self._screen, message, ["OK"], theme="nice"))
            if event.key_code in [ord("q"), ord("Q"), Screen.ctrl("c")]:
                self.services_cache = None
                service_cache_delete()
                raise StopApplication("User quit request")

    def _update_field(self, list, name, value, width):  # wrap long lines
        value = str(value)
        padding = 0
        while len(value):
            if type(name) == str:
                field = (name, " "*padding + value[0:width-padding])
                name = ""
            else:
                field = (" "*padding + value[0:width-padding],)
            list.append(field)
            value = value[width-padding:]
            if padding == 0:
                padding = 2

class DashboardFrame(FrameCommon, Frame):
    def __init__(self, screen):
        super(DashboardFrame, self).__init__(
            screen, screen.height, screen.width, has_border=False,
            name="AikoServices Dashboard"
        )
        self.ec_consumer = None
        self.service_cache = {}
        self.service_row = -1
        self.service_tags = None
        self.services_cache = service_cache_create_singleton(True)

        self._services_widget = MultiColumnListBox(
            screen.height * 1 // 3,
            ["<24", "<16", "<12", "<8", "<0"],
            options=[],
            titles=["Service", "Protocol", "Transport", "Owner", "Tags"],
            on_change=self._on_change_services
        )
        self._service_widget = MultiColumnListBox(
            Widget.FILL_FRAME,
            ["<16", "<0"],
            options=[],
            titles=["Variable name", "Value"]
        )
        layout_0 = Layout([1, 1])
        self.add_layout(layout_0)
        layout_0.add_widget(Label("AikoServices Dashboard"), 0)
        layout_0.add_widget(Label('Press "?" for help', align=">"), 1)
        layout_1 = Layout([1], fill_frame=True)
        self.add_layout(layout_1)
        layout_1.add_widget(Divider())
        layout_1.add_widget(self._services_widget)
        layout_1.add_widget(Divider())
        layout_1.add_widget(self._service_widget)
        self.fix()  # Prepare Frame for use
        self._value_width = self._service_widget.width - 16

    def _on_change_services(self):
        global _SERVICE_SELECTED
        row = self._services_widget.value
        if row != self.service_row:
            if self.ec_consumer:
                self.ec_consumer.terminate()
                self.ec_consumer = None
                self.service_cache = {}
                self.service_tags = None

            self.service_row = row
            services_topics = self.services_cache.get_services_topics()
            _SERVICE_SELECTED = None
            if len(services_topics) > 0:
                service_topic_path = services_topics[row]
                services = self.services_cache.get_services()
                _SERVICE_SELECTED = services[service_topic_path]
                self.service_tags = _SERVICE_SELECTED[4]
                if aiko.match_tags(self.service_tags, ["ecproducer=true"]):
                    topic_in = f"{service_topic_path}/control"
                    self.ec_consumer = ECConsumer(self.service_cache, topic_in)

    def _update(self, frame_no):
        if self.adjust_palette_required:
            self._adjust_palette()
        services = self.services_cache.get_services()
        services_formatted = []
        for service in services.values():
            after_slash = service[1].rfind("/") + 1
            protocol = service[1][after_slash:]  # protocol shortened
            tags = str(service[4])               # [tags] stringified
            services_formatted.append(
                (service[0], protocol, service[2], service[3], tags))
        self._services_widget.options = [
            (service_info, row_index)
            for row_index, service_info in enumerate(services_formatted)
        ]

        variables = []
        if self.ec_consumer:
            service_variables = self.service_cache.items()
            for variable_name, variable_value in service_variables:
                if type(variable_value) != dict:
                #   variables.append((variable_name, variable_value))
                    self._update_field(
                        variables, variable_name,
                        variable_value, self._value_width)
                else:
                    variables.append((f"{variable_name} ...", ""))
                    for name, value in variable_value.items():
                        variables.append((f"  {name}", str(value)))
            variables.append(("", ""))

        if self.service_tags:
            for service_tag in self.service_tags:
            #   variables.append(("Tag:", service_tag))
                self._update_field(
                    variables, "Tag:", service_tag, self._value_width)

        self._service_widget.options = [
            (variable, row_index)
            for row_index, variable in enumerate(variables)
        ]

        super(DashboardFrame, self)._update(frame_no)

    def process_event(self, event):
        if isinstance(event, KeyboardEvent):
            if event.key_code in [ord("L")]:
                raise NextScene("Log")
        self._process_event_common(event)
        return super(DashboardFrame, self).process_event(event)

class LogFrame(FrameCommon, Frame):
    def __init__(self, screen):
        super(LogFrame, self).__init__(
            screen, screen.height, screen.width, has_border=False,
            name="AikoServices Log"
        )
        self.ring_buffer = None
        self.topic_log = None

        self._log_widget = MultiColumnListBox(
            Widget.FILL_FRAME,
            ["<0"],
            options=[],
            titles=["Log records"]
        )
        layout_0 = Layout([1, 1])
        self.add_layout(layout_0)
        layout_0.add_widget(Label("AikoServices Dashboard"), 0)
        layout_0.add_widget(Label('Press "?" for help', align=">"), 1)
        layout_1 = Layout([1], fill_frame=True)
        self.add_layout(layout_1)
        layout_1.add_widget(Divider())
        layout_1.add_widget(self._log_widget)
        self.fix()  # Prepare Frame for use
        self._value_width = self._log_widget.width

    def _topic_log_handler(self, _aiko, topic, payload_in):
        self.ring_buffer.append(payload_in)

    def _update(self, frame_no):
        global _SERVICE_SUBSCRIBED

        if self.adjust_palette_required:
            self._adjust_palette()

        if _SERVICE_SELECTED != _SERVICE_SUBSCRIBED:
            _SERVICE_SUBSCRIBED = _SERVICE_SELECTED
            self.ring_buffer = deque(maxlen=_LOG_RING_BUFFER_SIZE)
            self.topic_log = f"{_SERVICE_SELECTED[0]}/log"
            aiko.add_message_handler(self._topic_log_handler, self.topic_log)

        log_records = []
        if self.ring_buffer:
            for log_record in self.ring_buffer:
            #   log_records.append((log_record,))
                self._update_field(
                    log_records, None, log_record, self._value_width)
        self._log_widget.options = [
            (log_record, row_index)
            for row_index, log_record in enumerate(log_records)
        ]

        super(LogFrame, self)._update(frame_no)

    def process_event(self, event):
        global _SERVICE_SUBSCRIBED
        if isinstance(event, KeyboardEvent):
            if event.key_code in [ord("D")]:
                aiko.remove_message_handler(
                    self._topic_log_handler, self.topic_log)
                self.ring_buffer = None
                self.topic_log = None
                _SERVICE_SUBSCRIBED = None
                raise NextScene("Dashboard")
        self._process_event_common(event)
        return super(LogFrame, self).process_event(event)

def dashboard(screen, start_scene):
    scenes = [
        Scene([DashboardFrame(screen)], -1, name="Dashboard"),
        Scene([LogFrame(screen)], -1, name="Log")
    ]
    screen.play(scenes, stop_on_resize=True, start_scene=start_scene)

if __name__ == "__main__":
    scene = None

    while True:
        try:
            Screen.wrapper(
                dashboard, catch_interrupt=True, arguments=[scene]
            )
            break
        except ResizeScreenError as exception:
            scene = exception.scene
