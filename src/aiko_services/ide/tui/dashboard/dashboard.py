#!/usr/bin/env python3
#
# Usage
# ~~~~~
# export AIKO_DISCOVERY_TIMEOUT=5.0  # seconds for remote WAN hosts (optional)
#
# Set-up ssh X11 forwarding for copy-paste support
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# # Requires Python package "pyperclip-1.8.2"
# xhost +
# ssh -Y username@hostname
# export DISPLAY=localhost:10.0
#
# Notes
# ~~~~~
# - Watch out for "stream.py:Frame()" dataclass and
#   "dashboard.py" use of "asciimatics.widgets.Frame()"
#
# Debugging approach #1
#   aiko.process.message.publish("$AIKO_NAMESPACE/DASHBOARD", f"Debug message")
#
#   mosquitto_sub -h $AIKO_MQTT_HOST -t $AIKO_NAMESPACE/DASHBOARD -v
#
# Debugging approach #2
#   from aiko_services.main.utilities import *
#   print_error("I've got a bad feeling about this !")
#
#   aiko_dashboard 1>/dev/null  # Debug messages only
#   aiko_dashboard 2>/dev/null  # TUI only
#
# Debugging approach #3
#   import logging
#   logging.basicConfig(format='%(message)s')
#   log = logging.getLogger(__name__)
#   log.warning("It's a trap !\r")
#
#   aiko_dashboard 1>/dev/null  # Debug messages only
#   aiko_dashboard 2>/dev/null  # TUI only
#
# Debugging approach #4
#   Write a custom Dashboard plugin for the Service / Actor
#
# To Do Elsewhere !
# ~~~~~~~~~~~~~~~~~
# * Turn Registrar into an ECProducer
# * Integrate into Ray HLActor ... Service, Actor, ECProducer, ECConsumer
#
# To Do
# ~~~~~
# * AI REPL --> LISP/Ollama --> Aiko Services analysis logs and MQTT messages
#
# * Command line option: Set number of rows for each DashboardFrame widget
#
# * BUG: Filter pop-up diaglogue "fc" (Filter Category) on exit,
#        causes main Dashboard to receive "c" keyboard event -->
#        causes superfluous "Copy topic path to clipboard" :(
#
# * BUG: Dashboard doesn't display variables that contain whitespace !
#        Variable doesn't appear at all 😔
#
# * BUG: When Dashboard exits, must clean-up (unshared) the ECConsumer !
#        Also, check that the ECProducer lease(s) expire as required
#
# * BUG: Dashboard isn't terminating ECConsumer lease extend timer 😔
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
# * FIX: Variable update dialogue replace with "maps.py:EnterLocation(Frame)"
#
# * FIX: Enable Service History selected "topic path" to clipboard
# * FIX: Enable Service History selected "topic path" can show LogFrame
# * FIX: Enable Service History multiple Service selection for logging
#
# * Write a file or template (for a script) for every Service / Actor seen
# *** "w" command for on-demand write file
# *** Provide a simple script that extracts the last topic_path and uses it
#
# - Show usage statistics: mosquitto messages, Service messages / uptime
#
# - LogFrame should support LogLevelPopupMenu to update selected Service
# - LogFrame display and allow the Service's "log_level" to be updated
#
# * If Registrar isn't available, then display "Waiting for Registrar"
# - Secondary Registrars should periodically send a non-retained message to
#     the TOPIC_REGISTRAR_BOOT topic ... (secondary found ...) for Dashboard
# - Dashboard should show if ...
#   - TOPIC_REGISTRAR_BOOT indicates that there is no primary Registrar
#   - TOPIC_REGISTRAR_BOOT indicates that there is a primary Registrar,
#       but the primary is not responding to (history ...) or (share ...)
#   - TOPIC_REGISTRAR_BOOT indicates there are secondary Registrar(s)
#       and show their details
#
# * Keyboard "H": Toggles between "Services History" and "Service Log"
#
# * Show Services running: time_add and time running
# * Show Services history: tags, time_add, time_remove and time running
#
# - ArchiveService should record "+/+/+/log" and removed Services ...
#   - Dashboard History section can ECConsumer the removed Services
#
# - Consider how to efficiently provide Service summary lifecycle states
#
# - Selecting (mouse or tab key) Service allows ...
#   - Toggle show/hide Services with specific field values (share * * * *)
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
#
# Ideas
# ~~~~~
# - Dashboard plug-ins: Metrics for all Services/Actors/Agents/Pipelines
#   - LISP REPL: Interactive, composable GUI IDE Graph WorkSpace
#     - Interact with Ollama(Actor), timg (videos, images)
#     - do_discovery(), do_command(), do_request() with Services
#   - mosquitto (MQTT): Metrics (charts), publish, subscribe, DynSec admin
#   - Registrar: Query the Services OrderedDict or as a tree viewer
#   - ProcessManager: LISP REPL using API
#   - HyperSpace: Tree view and LISP REPL using API

import click
from subprocess import Popen
import pyperclip  # Clipboard support

from asciimatics.event import KeyboardEvent
from asciimatics.exceptions import NextScene, ResizeScreenError
from asciimatics.parsers import AnsiTerminalParser
from asciimatics.scene import Scene
from asciimatics.screen import Screen
from asciimatics.widgets import Frame as asciimatics_Frame  # avoid confusion !
from asciimatics.widgets import (
    Layout, MultiColumnListBox, PopUpDialog, PopupMenu, TextBox, Widget
)

import aiko_services as aiko  # designed to be external to the main framework
from aiko_services.main.utilities import load_module

from aiko_services.ide.tui.dashboard.frames import (
    FrameCommon, LogUI, NICE_COLORS, ServiceFrame,
)

__all__ = [
    "DashboardFrame", "LogFrame", "LogLevelPopupMenu", "main",
    "update_plugins"
]

_HISTORY_LIMIT = 32
_PLUGINS = {}  # updated by update_plugins()

class DashboardFrame(FrameCommon, asciimatics_Frame):
    dashboard_singleton = None  # Instance reference for ServiceFrames plugins

    FILTER_OUT = set(["category", "pipeline_element"])

    @classmethod
    def get_singleton(cls):
        return DashboardFrame.dashboard_singleton

    def __init__(self, screen, _):
        if not DashboardFrame.dashboard_singleton:
            DashboardFrame.dashboard_singleton = self

        super(DashboardFrame, self).__init__(
            screen, screen.height, screen.width, has_border=False,
            name="dashboard_frame"
        )

        self.ec_consumer = None
        self._ec_consumer_reset()
        self.filter_out = DashboardFrame.FILTER_OUT.copy()
        self.services_row = -1
        self.selected_service = None
        self.selected_services = {}  # TODO: Make this a set() ?
        self.subscribed_service = None

        self.services_cache = aiko.services_cache_create_singleton(
            aiko.process, True, history_limit=_HISTORY_LIMIT)
    #   filter = aiko.ServiceFilter("*", "*", "*", "*", "*", "*")

        self._services_widget = MultiColumnListBox(
            screen.height // 3,
            ["<28", "<14", "<8", "<20", ">0"],  # Transport: <10 columns
            options=[],
            titles=["Active: Topic", "Name", "Owner", "Protocol", "Transport"],
            on_change=self._on_change_services,
            parser=AnsiTerminalParser()
        )
        self._service_widget = MultiColumnListBox(
            screen.height // 2,
            ["<24", "<0"],
            options=[],
            titles=["Shared variable: Name", "Value"],
            on_select=self._on_select_variable
        )
        self._history_widget = MultiColumnListBox(  # Transport: <10 columns
            Widget.FILL_FRAME,
            ["<28", "<14", "<8", "<20", ">0"],
            options=[],
            titles=["History: Topic", "Name", "Owner", "Protocol", "Transport"]
        )
        self._add_title_bar()
        layout_0 = Layout([1], fill_frame=True)
        self.add_layout(layout_0)
        layout_0.add_widget(self._services_widget)
        layout_0.add_widget(self._service_widget)
        layout_0.add_widget(self._history_widget)
        self.fix()  # Prepare asciimatics_Frame for use
        self._value_width = self._service_widget.width - 16

    def _ec_consumer_set(self, topic_path):
        self._ec_consumer_reset()
        services = self.services_cache.get_services()
        self.selected_service = services.get_service(topic_path)
        self.service_tags = self.selected_service[5]
        if aiko.ServiceTags.match_tags(self.service_tags, ["ec=true"]):
            topic_control = f"{topic_path}/control"
            self.ec_consumer = aiko.compose_instance(
                aiko.ECConsumerImpl, aiko.ec_consumer_args(
                    aiko.process, 0, self.service_cache, topic_control))

    def _ec_consumer_reset(self):
        if self.ec_consumer:
            self.ec_consumer.terminate()
        self.ec_consumer = None
        self.service_cache = {}
        self.service_tags = None

    def _filter(self, parent, service, topic_path, protocol):
        protocol = protocol.split(":")[0]
        if topic_path.service_id == "1":
            parent = (topic_path, protocol)

        show = protocol not in self.filter_out
        if topic_path.service_id != "1":
            if "sid>1" in self.filter_out:
                show = False
            if "pipeline_element" in self.filter_out and  \
                parent[1] and parent[1] == "pipeline":
                show = False
        return parent, show

    def _get_service_topic_path_next(self):
        service_topic_path_next = None
        services_row_next = self.services_row + 1
        services = self._services_widget.options
        if len(services) > services_row_next:
            service = services[services_row_next]
            service_topic_path_next = str(service[0][0])  # remove color
        return service_topic_path_next

    def _kill_service(self, service):
        topic_path = service[0]
        transport = service[3]
        kill_signal = "-2" if transport == "ray" else "-9"
        if topic_path.count("/") == 3:
            process_id = aiko.ServiceTopicPath.parse(topic_path).process_id
            if process_id.isnumeric():
                topic_path_next = self._get_service_topic_path_next()
                if topic_path_next:
                    self._ec_consumer_set(topic_path_next)
                command_line = ["kill", kill_signal, process_id]
                Popen(command_line, bufsize=0, shell=False)

    def _on_change_services(self):
        row = self._services_widget.value
        if row is not None and row != self.services_row:
            self.services_row = row
            topic_path_color = self._services_widget.options[row][0][0]
            self._ec_consumer_set(str(topic_path_color))  # remove color

    def _on_select_variable(self):
        text_box = TextBox(1, None, None, False, False)
        variable_name = None

        def _on_close(button_index):
            if button_index == 1:
                self._update_ecproducer_variable(
                    self.selected_service[0], variable_name, text_box.value[0])

        row = self._service_widget.value
        variable = self._service_widget.options[row]
        variable_name = variable[0][0]
        if len(variable_name) > 0:
            if variable_name != "Tag:" and not variable_name.endswith(" ..."):
                variable_value = variable[0][1]
                text_box.value[0] = variable_value
                title = f"Update {variable_name}" + " "*32
            # TODO: Replace with "maps.py:EnterLocation(asciimatics_Frame)"
                popup_dialog = PopUpDialog(
                    self._screen, title, ["Cancel", "OK"],
                    on_close=_on_close, theme="nice")
                layout = Layout([1])
                popup_dialog.add_layout(layout)
                layout.add_widget(text_box)
                popup_dialog.fix()
                self.scene.add_effect(popup_dialog)

    def process_event(self, event):
        if isinstance(event, KeyboardEvent):
            if event.key_code == ord("c") and self.selected_service:
                try:
                    pyperclip.copy(self.selected_service[0])
                except pyperclip.PyperclipException:
                    text = 'Clipboard copy/paste failed\n'          \
                           'Python package "pyperclip" requires\n'  \
                           'Linux package  "xclip"'
                    self.scene.add_effect(
                        PopUpDialog(self._screen, text, ["OK"], theme="nice"))
            if event.key_code == ord("f"):
                self.scene.add_effect(FilterPopupMenu(self._screen,
                    self._services_widget))
            if event.key_code == ord("l") and self.selected_service:
                self.scene.add_effect(LogLevelPopupMenu(self._screen,
                    self._services_widget, self.selected_service[0]))
            if event.key_code == ord("s") and self.selected_service:
                self._service_selection_toggle(self.selected_service)
            if event.key_code == ord("C"):
                self._service_selection_clear()
            if event.key_code == ord("K") and self.selected_service:
                self._kill_service(self.selected_service)
            if event.key_code == ord("L") and self.selected_service:
                raise NextScene("Log")
            if event.key_code == ord("S") and self.selected_service:
                self._raise_next_scene(self.selected_service)
        self._process_event_common(event)
        return super(DashboardFrame, self).process_event(event)

    def _raise_next_scene(self, service):
        service_name = service[1]
        service_protocol = self._short_name(service[2]).split(":")[0]
        names = [service_name, service_protocol]
        scene_name = [name for name in names if name in _PLUGINS]

        if scene_name:
            raise NextScene(scene_name[0])
        else:
            text = f" Service: {service_name} \n Does not have a custom page "
            self.scene.add_effect(
                PopUpDialog(self._screen, text, ["OK"], theme="nice"))

    def _service_selection_clear(self):
        self.selected_services = {}  # TODO: Make this a set() ?

    def _service_selection_color(self, color, topic_path, topic_path_show):
        topic_path_colored = topic_path_show
        if topic_path in self.selected_services:  # TODO: Make this a set() ?
            topic_path_colored = self._color_text(color, topic_path_show)
        return topic_path_colored

    def _service_selection_toggle(self, service):
        topic_path = service[0]
        if topic_path in self.selected_services:  # TODO: Make this a set() ?
            del self.selected_services[topic_path]
        else:
            self.selected_services[topic_path] = service

    def _update(self, frame_no):
        if self.adjust_palette_required:
            self._adjust_palette()

        parent = (None, None)
        services = self.services_cache.get_services().copy()
        services_formatted = []
        for service in services:
            topic_path = aiko.ServiceTopicPath.parse(service[0])
            topic_color = self._service_selection_color(
                self.YELLOW, str(topic_path), topic_path.terse)
            protocol = self._short_name(service[2])
            parent, show = self._filter(parent, service, topic_path, protocol)
            if show:
                services_formatted.append(
                    (topic_color, service[1], service[4], protocol, service[3]))
        self._services_widget.options = [
            (service_info, row_index)
            for row_index, service_info in enumerate(services_formatted)
        ]

        variables = []
        if self.ec_consumer:
            service_variables = list(self.service_cache.items())
            for variable_name, variable_value in service_variables:
                if isinstance(variable_value, dict):
                    variables.append((f"{variable_name} ...", ""))
                    for name, value in variable_value.items():
                        variables.append((f"  {name}", f"{value}"))
                else:
                #   variables.append((variable_name, variable_value))
                    self._update_field(
                        variables, variable_name,
                        variable_value, self._value_width)
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

        parent = (None, None)
        service_history = list(self.services_cache.get_history())
        services_formatted = []
        for service in service_history:
            topic_path = aiko.ServiceTopicPath.parse(service[0])
            topic_terse = topic_path.terse
            protocol = self._short_name(service[2])
            parent, show = self._filter(parent, service, topic_path, protocol)
            if show:
                services_formatted.append(
                    (topic_terse, service[1], service[4], protocol, service[3]))
        self._history_widget.options = [
            (service_info, row_index)
            for row_index, service_info in enumerate(services_formatted)
        ]

        super(DashboardFrame, self)._update(frame_no)

# ServiceFrame subclass __init__() must include "self.fix()"

class LogFrame(ServiceFrame):
    def __init__(self, screen, dashboard):
        super(LogFrame, self).__init__(screen, dashboard, name="log_frame")
        self.log_ui = LogUI(self)
        self.fix()  # Prepare asciimatics_Frame for use

    def process_event(self, event):
        self.log_ui.process_event(event)
        return super(LogFrame, self).process_event(event)

    def _service_frame_start(self, service, service_ec_consumer):
        self.log_ui._service_frame_start(service, service_ec_consumer)

    def _service_frame_stop(self, service):
        self.log_ui._service_frame_stop(service)

    def _update(self, frame_no):
        super(LogFrame, self)._update(frame_no)
        self.log_ui._update(frame_no)

class FilterPopupMenu(PopupMenu):
    def __init__(self, screen, parent_widget):
        self._dashboard = DashboardFrame.get_singleton()
        self._screen = screen
        self._parent_widget = parent_widget

        menu_items = [
            ("   Cancel",          self._parent_widget.focus),
            ("1: Service id > 1",  self._button_handler),
            ("c: Category",        self._button_handler),
            ("e: PipelineElement", self._button_handler),
            ("R: Reset",           self._button_handler)]
        x = screen.width // 2 - 4
        y = screen.height // 3

        super().__init__(self._screen, menu_items, x, y)
        self.palette = NICE_COLORS

    def _button_handler(self):
        log_level = self.focussed_widget.text.upper()
    #   self._set_log_level(log_level)

    def _set_log_level(self, log_level):
    #   self._dashboard._update_ecproducer_variable(
    #       self._service_selected, "log_level", log_level)
        self._parent_widget.focus()

    filter_key_map = {
        ord("1"): "sid>1",
        ord("c"): "category",
        ord("e"): "pipeline_element"
    }

    def process_event(self, event):
        if isinstance(event, KeyboardEvent):
            if event.key_code == ord("R"):
                self._dashboard.filter_out = DashboardFrame.FILTER_OUT.copy()
                self._destroy()
            if event.key_code in FilterPopupMenu.filter_key_map:
                filter = FilterPopupMenu.filter_key_map[event.key_code]
                if filter in self._dashboard.filter_out:
                    self._dashboard.filter_out.discard(filter)
                else:
                    self._dashboard.filter_out.add(filter)
                self._destroy()
        return super(FilterPopupMenu, self).process_event(event)

class LogLevelPopupMenu(PopupMenu):
    def __init__(self, screen, parent_widget, service_selected):
        self._dashboard = DashboardFrame.get_singleton()
        self._screen = screen
        self._parent_widget = parent_widget
        self._service_selected = service_selected

        menu_items = [
            ("   Cancel",      self._parent_widget.focus),
            ("d: Debug",       self._button_handler),
            ("e: Error",       self._button_handler),
            ("i: Info",        self._button_handler),
            ("w: Warning",     self._button_handler),
            ("D: Debug   all", self._button_handler),
            ("E: Error   all", self._button_handler),
            ("I: Info    all", self._button_handler),
            ("W: Warning all", self._button_handler)]
        x = screen.width // 2 - 4
        y = screen.height // 3

        super().__init__(self._screen, menu_items, x, y)
        self.palette = NICE_COLORS

    def _button_handler(self):
        log_level = self.focussed_widget.text.upper()
        self._set_log_level(log_level)

    def _set_log_level(self, log_level):
        self._dashboard._update_ecproducer_variable(
            self._service_selected, "log_level", log_level)
        self._parent_widget.focus()

    log_level_key_map = {
        ord("d"): "DEBUG",
        ord("e"): "ERROR",
        ord("i"): "INFO",
        ord("w"): "WARNING",
        ord("D"): "DEBUG_ALL",
        ord("E"): "ERROR_ALL",
        ord("I"): "INFO_ALL",
        ord("W"): "WARNING_ALL"
    }

    def process_event(self, event):
        if isinstance(event, KeyboardEvent):
            if self._dashboard.selected_service:
                if event.key_code in LogLevelPopupMenu.log_level_key_map:
                    level = LogLevelPopupMenu.log_level_key_map[event.key_code]
                    self._set_log_level(level)
                    self._destroy()
        return super(LogLevelPopupMenu, self).process_event(event)

def run_dashboard(screen, start_scene):
    scenes = []
    dashboard = None
    for scene_name, scene_class in _PLUGINS.items():
        scene = Scene([scene_class(screen, dashboard)], -1, name=scene_name)
        if scene_name == "Dashboard":
            dashboard = DashboardFrame.get_singleton()
        scenes.append(scene)
    screen.play(scenes, stop_on_resize=True, start_scene=start_scene)

def update_plugins(plugins):
    if not _PLUGINS:
        _PLUGINS["Dashboard"] = DashboardFrame
        _PLUGINS["Log"] = LogFrame
    _PLUGINS.update(plugins)

@click.command()
@click.option("--history_limit", "-hl", type=click.INT, default=32,
    help="History length requested from Registrar")
@click.option("--plugin", "-p", multiple=True, required=False,
    default=["aiko_services.ide.tui.dashboard.plugins"])

def main(plugin, history_limit):
    """Aiko Services Dashboard

    \b
    export AIKO_DISCOVERY_TIMEOUT=5.0  # seconds for remote WAN hosts (optional)
    """

    global _HISTORY_LIMIT
    _HISTORY_LIMIT = history_limit

    for plugin_name in plugin:
        try:
            module = load_module(plugin_name) if plugin_name else None
        except ModuleNotFoundError:
            module = None
        update_plugins(module.plugins if module else {})

    scene = None
    while True:
        try:
            Screen.wrapper(
                run_dashboard, catch_interrupt=True, arguments=[scene]
            )
            break
        except ResizeScreenError as exception:
            scene = exception.scene

if __name__ == "__main__":
    main()
