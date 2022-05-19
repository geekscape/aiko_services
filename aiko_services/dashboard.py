#!/usr/bin/env python3
#
# To Do
# ~~~~~
# * Move Service tags into Service variables section, where there is more room
#
# * BUG: Dashboard isn't terminating ECConsumer lease extend timer :(
#
# * Turn Registrar into an ECProducer
# * Integrate into Ray HLActor ... Service, Actor, ECProducer, ECConsumer
#
# * Automatically change Service summary rows to be 1/3 of screen height
#
# * Provide Historical Service add / remove section
# - Consider how to efficiently provide Service summary lifecycle states
#
# - Selecting (mouse or tab key) Service allows ...
#   * Toggle show/hide Services with specific field values (query * * * *)
#   - Service to be terminated / killed ("k" key)
#   * Subscribe to MQTT messages ("s" key) from topic (/#, /out, /state, /log)
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
# Useful Service variables ...
# - lifecycle state: ...
# - log level: none, debug
# - statistics: busy/idle time, mailbox queue size, message count, uptime
#
# Useful Actors ...
# - MQTT: statistics / variables ?
# - Host / Containers (root ProcessManager)
# - Registrar(s), LifeCycleManager(s), StorageManager(s), HyperSpace
# - Pipeline(s) / PipelineElement(s)
# - Ray node(s)

from collections import defaultdict

from asciimatics.event import KeyboardEvent
from asciimatics.exceptions import ResizeScreenError, StopApplication
from asciimatics.scene import Scene
from asciimatics.screen import Screen
from asciimatics.widgets import (
    Divider, Frame, Label, Layout, MultiColumnListBox, Widget
)

from aiko_services import *

class DashboardFrame(Frame):
    def __init__(self, screen):
        self.ec_consumer = None
        self.service_cache = {}
        self.service_row = -1
        self.service_tags = None
        self.services_cache = service_cache_create_singleton()

        super(DashboardFrame, self).__init__(
            screen,
            screen.height,
            screen.width,
            has_border=True,
            name="AikoServices Dashboard"
        )

        box_rows = 16
        self._services_widget = MultiColumnListBox(
            box_rows,
            ["<24", "<16", "<12", "<8", "0"],
            [],
            titles=["Service", "Protocol", "Transport", "Owner", "Tags"],
            on_change=self._on_change_service,
        )

        self._service_widget = MultiColumnListBox(
            Widget.FILL_FRAME,
            ["<16", "<0"],
            [],
            titles=["Variable", "Value"],
        )

        layout = Layout([1], fill_frame=True)
        self.add_layout(layout)
        layout.add_widget(Label("AikoServices Dashboard (press 'q' to quit)"))
        layout.add_widget(Divider())
        layout.add_widget(self._services_widget)
        layout.add_widget(Divider())
        layout.add_widget(self._service_widget)

        self.palette = defaultdict(
            lambda: (Screen.COLOUR_WHITE, Screen.A_NORMAL, Screen.COLOUR_BLACK)
        )
        self.palette["selected_focus_field"] =  \
           (Screen.COLOUR_GREEN, Screen.A_BOLD, Screen.COLOUR_BLACK)
        self.palette["title"] =  \
           (Screen.COLOUR_BLACK, Screen.A_BOLD, Screen.COLOUR_WHITE)
        self.fix()  # Prepare Frame for use

    def _on_change_service(self):
        row = self._services_widget.value
        if row != self.service_row:
            if self.ec_consumer:
                self.ec_consumer.terminate()
                self.ec_consumer = None
                self.service_cache = {}
                self.service_tags = None

            self.service_row = row
            services_topics = self.services_cache.get_services_topics()
            if len(services_topics) > 0:
                service_topic_path = services_topics[row]
                services = self.services_cache.get_services()
                service = services[service_topic_path]
                self.service_tags = service[4]
                if aiko.match_tags(self.service_tags, ["ecproducer=true"]):
                    topic_in = f"{service_topic_path}/control"
                    self.ec_consumer = ECConsumer(self.service_cache, topic_in)

    def _update(self, frame_no):
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
        if self.service_tags:
            for service_tag in self.service_tags:
                variables.append(("tag:", service_tag))
            variables.append(("", ""))

        if self.ec_consumer:
            service_variables = self.service_cache.items()
            for variable in service_variables:
                if type(variable[1]) != dict:
                    variables.append(variable)
                else:
                    variables.append((f"{variable[0]} ...", ""))
                    for name, value in variable[1].items():
                        variables.append((f"  {name}", str(value)))

        self._service_widget.options = [
            (variable, row_index)
            for row_index, variable in enumerate(variables)
        ]

        super(DashboardFrame, self)._update(frame_no)

    @property
    def frame_update_count(self):
        return 4  # assuming 20 FPS, then refresh screen at 5 Hz

    def process_event(self, event):
        if isinstance(event, KeyboardEvent):
            if event.key_code in [ord('q'), ord('Q'), Screen.ctrl("c")]:
                self.services_cache = None
                service_cache_delete()
                raise StopApplication("User quit request")
        return super(DashboardFrame, self).process_event(event)

def dashboard(screen, start_scene):
    screen.play(
        [Scene([DashboardFrame(screen)], -1)],
        stop_on_resize=True,
        start_scene=start_scene
    )

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
