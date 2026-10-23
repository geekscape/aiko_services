#!/usr/bin/env python3
#
# Aiko Services: the Registrar's Dashboard page
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# The Services the Registrar knows about, and its log.  It reads the
# ServicesCache, which the Dashboard already keeps, rather than asking the
# Registrar itself.
#
# Registered through "plugins.py", the Dashboard's default "--plugin"
# module, so this page needs no flag.  The key is the protocol type.
#
# To Do
# ~~~~~
# - Show the Service history, which the ServicesCache also holds
# - Filter the list, as the Dashboard's own page does

from asciimatics.widgets import Layout, MultiColumnListBox

import aiko_services as aiko  # designed to be external to the main framework

__all__ = ["RegistrarFrame", "plugins"]

class RegistrarFrame(aiko.ServiceFrame):
    def __init__(self, screen, dashboard):
        super(RegistrarFrame, self).__init__(
            screen, dashboard, name="registrar_frame")

        self.services_cache = aiko.services_cache_create_singleton(
            aiko.process, True, history_limit=screen.height)

        self._registrar_widget = MultiColumnListBox(
            screen.height * 1 // 2, ["<0"], options=[],
            titles=["Registrar: Discovered Services topic paths"]
        )
        layout_0 = Layout([1])
        self.add_layout(layout_0)
        layout_0.add_widget(self._registrar_widget)
        self.log_ui = aiko.LogUI(self)
        self.fix()  # Prepare asciimatics_Frame for use

    def _service_frame_start(self, service, service_ec_consumer):
        self.log_ui._service_frame_start(service, service_ec_consumer)

    def _service_frame_stop(self, service):
        self.log_ui._service_frame_stop(service)

    def _update(self, frame_no):
        super(RegistrarFrame, self)._update(frame_no)

        services = self.services_cache.get_services().copy()
        services_formatted = []
        for service in services:
            topic_path = str(aiko.ServiceTopicPath.parse(service[0]))
            protocol = service[2]  # self._short_name(service[2])
            services_formatted.append(
                (topic_path, service[1], service[4], protocol, service[3]))
        self._registrar_widget.options = [
            (service_info, row_index)
            for row_index, service_info in enumerate(services_formatted)
        ]

        self.log_ui._update(frame_no)

# plugin key: the protocol type of registrar:2
plugins = {"registrar": RegistrarFrame}

# --------------------------------------------------------------------------- #
