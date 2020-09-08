#!/usr/bin/env python3
#
# Aiko Service: Service Registrar
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#
# Usage
# ~~~~~
# registrar [--primary]
#
#   --primary: Force take over of the primary service_registrar role
#
# To Do
# ~~~~~
# - Make this a sub-command of Aiko CLI
# - Rename to registrar
#
# - Handle MQTT restart
# - Handle MQTT stop and start on a different host
# - Handle if system crashes, then mosquitto doesn't get to send a LWT messages for
#   the Service Manager, leaving a stale reference to a Service Manager that
#   now longer exists.  If a new Service Manager isn't started when the system
#   restarts, then Aiko Clients try to use the defunct Service Manager !
#
# - Implement as a sub-class of Category ?
# - When Service fails with LWT, publish timestamp on "topic_path/state"
#   - Maybe ProcessController should do this, rather than ServiceRegistrar ?
# - Every Service persisted in MeemStore should have "uuid" Service tag
# - Document state and protocol
#   - Service state inspired by Meem life-cycle
# - Create service_registrar/protocol.py
# - Rename "framework.py" to "service.py" and create a Service class ?
# - Implement protocol.py and state_machine.py !
# - Primary and secondaries Service Registrars
# - Primary Service Registrar supports discovery protocol
# - Implement protocol matching similar to programming language interfaces with inheritance

import click
import time

import aiko_services.event as event
import aiko_services.framework as aiko
from aiko_services.state import StateMachine
from aiko_services.utilities import get_logger

_LOGGER = get_logger(__name__)
_PRIMARY_SEARCH_TIMEOUT = 2.0  # seconds

time_started = time.time()

# --------------------------------------------------------------------------- #

class StateMachineModel(object):
    states = [
        "start",
        "primary_search",
        "secondary",
        "primary"
    ]

    transitions = [
        {"source": "start", "trigger": "initialize", "dest": "primary_search"},
        {"source": "primary_search", "trigger": "primary_found", "dest": "secondary"},
        {"source": "primary_search", "trigger": "primary_promotion", "dest": "primary"},
        {"source": "secondary", "trigger": "primary_failed", "dest": "primary_search"}
    ]

    def on_enter_primary_search(self, event_data):
#       parameters = event_data.kwargs.get("parameters", {})
        _LOGGER.debug("do primary_search add_timer")

# TODO: If oldest known secondary, then immediately become the primary
# TODO: Choose timer period as _PRIMARY_SEARCH_TIMEOUT +/- delta to avoid collisions
        event.add_timer_handler(self.primary_search_timer, _PRIMARY_SEARCH_TIMEOUT)

    def primary_search_timer(self):
        timer_valid = state_machine.get_state() == "primary_search"
        _LOGGER.debug(f"timer primary_search {timer_valid}")
        event.remove_timer_handler(self.primary_search_timer)
        if timer_valid:
            state_machine.transition("primary_promotion", None)

    def on_enter_secondary(self, event_data):
        _LOGGER.debug("do enter_secondary")

    def on_enter_primary(self, event_data):
        _LOGGER.debug("do enter_primary")
        aiko.set_last_will_and_testament(aiko.SERVICE_REGISTRAR_TOPIC, True)
        payload_out = f"(primary {aiko.public.topic_in} {time_started})"
        aiko.public.message.publish(aiko.SERVICE_REGISTRAR_TOPIC, payload_out, retain=True)

state_machine = StateMachine(StateMachineModel())

# --------------------------------------------------------------------------- #

parameter_1 = None

def on_service_registrar(_aiko, event_type, topic_path, timestamp):
    _LOGGER.debug(f"event: {event_type}, topic_path={topic_path}, timestamp={timestamp}")
    if event_type == "add":
        if state_machine.get_state() == "primary_search":
            state_machine.transition("primary_found", None)

    if event_type == "remove":
        if state_machine.get_state() == "primary_search":
            state_machine.transition("primary_promotion", None)
        else:
            if state_machine.get_state() == "secondary":
                state_machine.transition("primary_failed", None)

# --------------------------------------------------------------------------- #

@click.command()
def main():
# V2: namespace/service/registrar (primary namespace/host/pid timestamp)

# TODO: Add message handler for listening for other Service Registars ?
#       This means that the Aiko V2 framework should do the subscription automagically
#       - Find the primary service registrar (if it exists ?)
#       - Query to find all other service registars

# TODO: Add on_message_broker() handler to track MQTT connection status
#       - Events: "add", "remove", "timeout" (waiting for connection)

# TODO: Add discovery protocol handler to keep a list of Service Registrars

    aiko.set_protocol(aiko.SERVICE_REGISTRAR_PROTOCOL)
    aiko.add_service_registrar_handler(on_service_registrar)
    state_machine.transition("initialize", None)
    aiko.process(True)

if __name__ == "__main__":
    main()

# --------------------------------------------------------------------------- #
