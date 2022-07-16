#!/usr/bin/env python3
#
# Notes
# ~~~~~
# Debugging: aiko.public.message.publish("DASHBOARD", f"Debug message")
#
# Set-up ssh X11 forwarding for copy-paste support
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# # Requires Python package "xerox-0.4.1"
# xhost +
# ssh -Y username@hostname
# export DISPLAY=localhost:10.0
#
# To Do Elsewhere !
# ~~~~~~~~~~~~~~~~~
# * Turn Registrar into an ECProducer
# * Integrate into Ray HLActor ... Service, Actor, ECProducer, ECConsumer
#
# To Do
# ~~~~~
# * BUG: When Dashboard exits, must clean-up (unshared) the ECConsumer !
#        Also, check that the ECProducer lease(s) expire as required
#
# * BUG: Dashboard isn't terminating ECConsumer lease extend timer :(
#
# - BUG: If currently selected Service terminates, then Dashboard doesn't
#        update selected Service's veriables section
#
# - BUG: Dashboard "Kill Service" command assumes running on same system
#        as the Service.  Should send "terminate" MQTT message to the
#        Service.  Or find a ProcessManager running on the correct host ?
#
# * FIX: Whenever DashboardFrame or LogFrame is destroyed and recreated
#        due to ResizeScreenError, all handlers need to be removed.
#        Provide DashboardFrame.cleanup() and LogFrame.cleanup(),
#        which are invoked by ResizeScreenError
#
# - ArchiveService should record "+/+/+/log" and removed Services ...
#   - Dashboard History section can ECConsumer the removed Services
#
# - Consider how to efficiently provide Service summary lifecycle states
#
# - Selecting (mouse or tab key) Service allows ...
#   - Toggle show/hide Services with specific field values (query * * * *)
#   - Subscribe to MQTT messages ("s" key) from topic (/#, /out, /state)
#   - Publish MQTT message ("p" key) to topic (/#, /in, /control, ...)
#
# - Service variable details should sort variable names alphabetically
# - Toggle show/hide of Service variables "services.*" visually redundant
# - Toggle show/hide Service variables with specific names (regex)
# - Allow Service variables to be added and removed
#
# - Dashboard Web browser (JavaScript) implementation using MQTT / WebSockets
#   - Service / ECProducer / ECConsumer JavaScript implementation
#   - Integrate Dashboard into HighLighter Web !
#
# Service variables that Services should have ...
# - lifecycle state: ...
# - log level: info, debug, ...
# - statistics: busy/idle time, mailbox queue size, message count, uptime
#
# Actors that should have interesting variables ...
# - MQTT: statistics / variables ?
# - Host / Containers (root ProcessManager)
# - Registrar(s), LifeCycleManager(s), StorageManager(s), HyperSpace
# - Pipeline(s) / PipelineElement(s)
# - Ray node(s)

import click
from collections import defaultdict, deque
from subprocess import Popen
import xerox  # Clipboard support

from asciimatics.event import KeyboardEvent
from asciimatics.exceptions import (
    NextScene, ResizeScreenError, StopApplication
)
from asciimatics.scene import Scene
from asciimatics.screen import Screen
from asciimatics.widgets import (
    Frame, Label, Layout, MultiColumnListBox,
    PopUpDialog, PopupMenu, TextBox, Widget
)
from asciimatics.widgets.utilities import THEMES

from aiko_services import *
from aiko_services.utilities import *

_HISTORY_RING_BUFFER_SIZE = 32
_LOG_RING_BUFFER_SIZE = 128

_SERVICE_SELECTED = None    # written by Dashboard._on_change_services()
_SERVICE_SUBSCRIBED = None  # written by LogFrame._update() and process_event()

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

mqtt_configuration = get_mqtt_configuration()
mqtt_host = mqtt_configuration[0]
mqtt_port = mqtt_configuration[1]

def _get_title(name, context=None):
    title = f"AikoServices {name}: "
    if context:
        title += context
    else:
        mqtt_host_short_name = mqtt_host.partition(".")[0]
        title += f"{mqtt_host_short_name}:{mqtt_port}"
    return title

def _short_name(path):
    after_slash = path.rfind("/") + 1
    return path[after_slash:]

def _update_ecproducer_variable(topic_path, name, value):
    topic_path_control = topic_path + "/control"
    payload_out = f"(update {name} {value})"
    aiko.public.message.publish(topic_path_control, payload_out)

class FrameCommon:
    def __init__(self, screen, height, width, has_border, name):
        super(FrameCommon, self).__init__(
            screen, height, width, has_border=has_border, name=name)
        self.adjust_palette_required = True

    def _adjust_palette(self):
        self.palette = NICE_COLORS
        self.adjust_palette_required = False

    @property
    def frame_update_count(self):
        return 4  # assuming 20 FPS, then refresh screen at 5 Hz

# TODO: Replace _process_event_common() with the following ...
# https://asciimatics.readthedocs.io/en/stable/widgets.html#global-key-handling
    def _process_event_common(self, event):
        if isinstance(event, KeyboardEvent):
            if event.key_code in [ord("?")]:
                message =" Help\n ----\n"  \
                         " Enter: Update variable value \n"  \
                         " Tab:   Move to next section \n"  \
                         " c:     Copy topic path to clipboard \n"  \
                         " l:     Log level change\n"  \
                         " D:     Show Dashboard page \n"  \
                         " K:     Kill Service \n"  \
                         " L:     Show Log page \n"  \
                         " x:     Exit"
                self.scene.add_effect(
                    PopUpDialog(self._screen, message, ["OK"], theme="nice"))
            if event.key_code in [ord("x"), ord("X"), Screen.ctrl("c")]:
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
            name="dashboard_frame"
        )

        self.ec_consumer = None
        self._ec_consumer_reset()
        self.service_history = deque(maxlen=_HISTORY_RING_BUFFER_SIZE)
        self.services_row = -1

        self.services_cache = service_cache_create_singleton(True)
        filter = ServiceFilter("*", "*", "*", "*", "*")
        self.services_cache.add_handler(self._service_change_handler, filter)

        self._services_widget = MultiColumnListBox(
            screen.height * 1 // 3,
            ["<24", "<20", "<12", "<8", "<0"],
            options=[],
            titles=["Service", "Protocol", "Transport", "Owner", "Tags"],
            on_change=self._on_change_services
        )
        self._service_widget = MultiColumnListBox(
            screen.height * 1 // 2,
            ["<24", "<0"],
            options=[],
            titles=["Variable name", "Value"],
            on_select=self._on_select_variable
        )
        self._history_widget = MultiColumnListBox(
            Widget.FILL_FRAME,
            ["<24", "<16", "<12", "<8", "<0"],
            options=[],
            titles=["Service history", "Protocol", "Transport", "Owner", "Tags"]
        )
        layout_0 = Layout([1, 1])
        self.add_layout(layout_0)
        label_name = _get_title("Dashboard")
        layout_0.add_widget(Label(label_name), 0)
        layout_0.add_widget(Label('Press "?" for help', align=">"), 1)
        layout_1 = Layout([1], fill_frame=True)
        self.add_layout(layout_1)
        layout_1.add_widget(self._services_widget)
        layout_1.add_widget(self._service_widget)
        layout_1.add_widget(self._history_widget)
        self.fix()  # Prepare Frame for use
        self._value_width = self._service_widget.width - 16

    def _ec_consumer_set(self, index):
        global _SERVICE_SELECTED
        self._ec_consumer_reset()
        self.services_row = -1
        _SERVICE_SELECTED = None

        services_topics = self.services_cache.get_services_topics()
        if len(services_topics) > index:
            self.services_row = index
            service_topic_path = services_topics[index]
            services = self.services_cache.get_services()
            _SERVICE_SELECTED = services[service_topic_path]
            self.service_tags = _SERVICE_SELECTED[4]
            if aiko.match_tags(self.service_tags, ["ecproducer=true"]):
                topic_control = f"{service_topic_path}/control"
                self.ec_consumer = ECConsumer(
                    0, self.service_cache, topic_control)

    def _ec_consumer_reset(self):
        if self.ec_consumer:
            self.ec_consumer.terminate()
        self.ec_consumer = None
        self.service_cache = {}
        self.service_tags = None

    def _kill_service(self, service_topic_path):
        global _SERVICE_SELECTED
        if service_topic_path.count("/") == 2:
            pid = _short_name(service_topic_path)
            if pid.isnumeric():
                command_line = ["kill", "-9", pid]
                Popen(command_line, bufsize=0, shell=False)
                self._ec_consumer_set(self.services_row + 1)

    def _on_change_services(self):
        row = self._services_widget.value
        if row is not None and row != self.services_row:
            self._ec_consumer_set(row)

    def _on_select_variable(self):
        text_box = TextBox(1, None, None, False, False)
        variable_name = None

        def _on_close(button_index):
            if button_index == 1:
                _update_ecproducer_variable(
                    _SERVICE_SELECTED[0], variable_name, text_box.value[0])

        row = self._service_widget.value
        variable = self._service_widget.options[row]
        variable_name = variable[0][0]
        if len(variable_name) > 0:
            if variable_name != "Tag:" and not variable_name.endswith(" ..."):
                variable_value = variable[0][1]
                text_box.value[0] = variable_value
                title = f"Update {variable_name}" + " "*32
                popup_dialog = PopUpDialog(
                    self._screen, title, ["Cancel", "OK"],
                    on_close=_on_close, theme="nice")
                layout = Layout([1])
                popup_dialog.add_layout(layout)
                layout.add_widget(text_box)
                popup_dialog.fix()
                self.scene.add_effect(popup_dialog)

    def _service_change_handler(self, command, service_details):
        if command == "remove":
            self.service_history.appendleft(service_details)

    def _update(self, frame_no):
        if self.adjust_palette_required:
            self._adjust_palette()

        services = self.services_cache.get_services().copy()
        services_formatted = []
        for service in services.values():
            protocol = _short_name(service[1])
            tags = str(service[4])               # [tags] stringified
            services_formatted.append(
                (service[0], protocol, service[2], service[3], tags))
        self._services_widget.options = [
            (service_info, row_index)
            for row_index, service_info in enumerate(services_formatted)
        ]

        variables = []
        if self.ec_consumer:
            service_variables = list(self.service_cache.items())
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

        services_formatted = []
        service_history = list(self.service_history)
        for service in service_history:
            protocol = _short_name(service[1])
            tags = str(service[4])               # [tags] stringified
            services_formatted.append(
                (service[0], protocol, service[2], service[3], tags))
        self._history_widget.options = [
            (service_info, row_index)
            for row_index, service_info in enumerate(services_formatted)
        ]

        super(DashboardFrame, self)._update(frame_no)

    def process_event(self, event):
        if isinstance(event, KeyboardEvent):
            if event.key_code in [ord("c")] and _SERVICE_SELECTED:
                xerox.copy(_SERVICE_SELECTED[0])
            if event.key_code in [ord("l")] and _SERVICE_SELECTED:
                self.scene.add_effect(LogLevelPopupMenu(
                    self._screen, self._services_widget, _SERVICE_SELECTED[0]))
            if event.key_code in [ord("K")] and _SERVICE_SELECTED:
                self._kill_service(_SERVICE_SELECTED[0])
            if event.key_code in [ord("L")] and _SERVICE_SELECTED:
                raise NextScene("Log")
        self._process_event_common(event)
        return super(DashboardFrame, self).process_event(event)

class LogFrame(FrameCommon, Frame):
    def __init__(self, screen):
        super(LogFrame, self).__init__(
            screen, screen.height, screen.width, has_border=False,
            name="log_frame"
        )
        self.log_buffer = None
        self.topic_log = None

        self._log_widget = MultiColumnListBox(
            Widget.FILL_FRAME,
            ["<0"],
            options=[],
            titles=["Log records"]
        )
        layout_0 = Layout([1, 1])
        self.add_layout(layout_0)
        layout_0.add_widget(Label(_get_title("Log")), 0)
        layout_0.add_widget(Label('Press "?" for help', align=">"), 1)
        layout_1 = Layout([1], fill_frame=True)
        self.add_layout(layout_1)
        layout_1.add_widget(self._log_widget)
        self.fix()  # Prepare Frame for use
        self._value_width = self._log_widget.width

    def _topic_log_handler(self, _aiko, topic, payload_in):
        self.log_buffer.append(payload_in)

    def _update(self, frame_no):
        global _SERVICE_SUBSCRIBED

        if self.adjust_palette_required:
            self._adjust_palette()

        if _SERVICE_SELECTED != _SERVICE_SUBSCRIBED:
            _SERVICE_SUBSCRIBED = _SERVICE_SELECTED
            service_topic_path = _SERVICE_SELECTED[0]
            protocol = _short_name(_SERVICE_SELECTED[1])
            title = f"Log records: {service_topic_path}: {protocol}"
            self._log_widget._titles = [title]
            self.log_buffer = deque(maxlen=_LOG_RING_BUFFER_SIZE)
            self.topic_log = f"{_SERVICE_SELECTED[0]}/log"
            aiko.add_message_handler(self._topic_log_handler, self.topic_log)

        log_records = []
        if self.log_buffer:
            for log_record in self.log_buffer:
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
                self.log_buffer = None
                self.topic_log = None
                _SERVICE_SUBSCRIBED = None
                raise NextScene("Dashboard")
        self._process_event_common(event)
        return super(LogFrame, self).process_event(event)

class LogLevelPopupMenu(PopupMenu):
    def __init__(self, screen, parent_widget, service_selected):
        self._screen = screen
        self._parent_widget = parent_widget
        self._service_selected = service_selected

        menu_items = [
            ("Cancel", self._parent_widget.focus),
            ("Debug", self._button_handler),
            ("Error", self._button_handler),
            ("Info", self._button_handler),
            ("Warning", self._button_handler)]
        x = screen.width // 2 - 4
        y = screen.height // 3

        super().__init__(self._screen, menu_items, x, y)
        self.palette = NICE_COLORS

    def _button_handler(self):
        log_level = self.focussed_widget.text.upper()
        self._set_log_level(log_level)

    def _set_log_level(self, log_level):
        _update_ecproducer_variable(
            self._service_selected, "log_level", log_level)
        self._parent_widget.focus()

    def process_event(self, event):
        if isinstance(event, KeyboardEvent):
            if event.key_code in [ord("c")]:
                self._destroy()
            if _SERVICE_SELECTED:
                if event.key_code in [ord("d")]:
                    self._set_log_level("DEBUG")
                    self._destroy()
                elif event.key_code in [ord("e")]:
                    self._set_log_level("ERROR")
                    self._destroy()
                elif event.key_code in [ord("i")]:
                    self._set_log_level("INFO")
                    self._destroy()
                elif event.key_code in [ord("w")]:
                    self._set_log_level("WARNING")
                    self._destroy()
        return super(LogLevelPopupMenu, self).process_event(event)

def dashboard(screen, start_scene):
    scenes = [
        Scene([DashboardFrame(screen)], -1, name="Dashboard"),
        Scene([LogFrame(screen)], -1, name="Log")
    ]
    screen.play(scenes, stop_on_resize=True, start_scene=start_scene)

@click.command()
def main():
    scene = None

    while True:
        try:
            Screen.wrapper(
                dashboard, catch_interrupt=True, arguments=[scene]
            )
            break
        except ResizeScreenError as exception:
            scene = exception.scene

if __name__ == "__main__":
    main()
