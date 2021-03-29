#!/usr/bin/env python3
#
# Aiko Service: Registrar
# ~~~~~~~~~~~~~~~~~~~~~~~
#
# Usage
# ~~~~~
# registrar [--primary]
#
#   --primary: Force take over of the primary registrar role
#
# mosquitto_pub -t registrar_topic_prefix/in -m "(add topic_prefix protocol owner (tags))"
#
# mosquitto_pub -t registrar_topic_prefix/in -m "(remove topic_prefix)"
#
# Notes
# ~~~~~
# Registrar listens for ...
#
# - REGISTRAR_TOPIC: "(primary started ...)" and "(primary stopped)" messages
#
# - {topic_path}/in: "(add ...)", "(query ...)", "(remove ...)" messages
#
# - {namespace}/+/+/state: "(stopped)" from register Aiko Services
#   - Will need a change to framework.py:on_message() regarding "for match_topic ..."
#   - Need to handle endsWith("/state")
#
# To Do
# ~~~~~
# - Make this a sub-command of Aiko CLI
#
# - Handle MQTT restart
# - Handle MQTT stop and start on a different host
# - Handle if system crashes, then mosquitto doesn't get to send a LWT messages for
#   the Registrar leaving a stale reference to a Registrar now longer exists.
#   If a new Registrar't started when the system restarts, then Aiko Clients try
#   to use the defunct Registrar
#
# - Consider the ability to add, change or remove a Service's tag
# - Implement as a sub-class of Category ?
# - When Service fails with LWT, publish timestamp on "topic_path/state"
#   - Maybe ProcessController should do this, rather than Registrar ?
# - Every Service persisted in MeemStore should have "uuid" Service tag
# - Document state and protocol
#   - Service state inspired by Meem life-cycle
# - Create registrar/protocol.py
# - Rename "framework.py" to "service.py" and create a Service class ?
# - Implement protocol.py and state_machine.py !
# - Primary and secondaries Registrars
#   - https://en.wikipedia.org/wiki/Conflict-free_replicated_data_type
#   - Eventual consistency and optimistic replication
# - Primary Registrar supports discovery protocol
# - Implement protocol matching similar to programming language interfaces with inheritance

import click
import time

import aiko_services.event as event
import aiko_services.framework as aiko
from aiko_services.state import StateMachine
from aiko_services.utilities import get_logger
from aiko_services.utilities.parser import parse

_LOGGER = get_logger(__name__)
_PRIMARY_SEARCH_TIMEOUT = 2.0  # seconds

services = {}
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
        lwt_payload = "(primary stopped)"
        aiko.set_last_will_and_testament(aiko.REGISTRAR_TOPIC, lwt_payload, True)
        payload_out = f"(primary started {aiko.public.topic_path} {time_started})"
        aiko.public.message.publish(aiko.REGISTRAR_TOPIC, payload_out, retain=True)

state_machine = StateMachine(StateMachineModel())

# --------------------------------------------------------------------------- #

def registrar_handler(_aiko, action, registrar):
    if action == "started":
        if state_machine.get_state() == "primary_search":
            state_machine.transition("primary_found", None)

    if action == "stopped":
        if state_machine.get_state() == "primary_search":
            state_machine.transition("primary_promotion", None)
        else:
            if state_machine.get_state() == "secondary":
                state_machine.transition("primary_failed", None)

    return False  # Registrar message handling not finished

def topic_in_handler(aiko, topic, payload_in):
    command, parameters = parse(payload_in)         # TODO: FIX TO HANDLE TAGS
#   _LOGGER.debug(f"topic_in_handler(): {command}: {parameters}")

    if command == "add" and len(parameters) == 4:
        service_topic = parameters[0]
        protocol = parameters[1]
        owner = parameters[2]
        tags = parameters[3]

        service_add(service_topic, protocol, owner, tags)
        payload_out = payload_in
        aiko.message.publish(aiko.topic_out, payload_out)

    if command == "remove" and len(parameters) == 1:
        service_topic = parameters[0]
        service_remove(service_topic)
        payload_out = payload_in
        aiko.message.publish(aiko.topic_out, payload_out)

    if command == "query" and len(parameters) == 4:
        response_topic  = parameters[0]
        match_protocol  = parameters[1]
        match_owner     = parameters[2]
        match_tags      = parameters[3]

        services_out = {}

        for service_topic, service_details in services.items():
            matches = 0

            if match_protocol == "*":
                matches += 1
            else:
                if match_protocol == service_details["protocol"]:
                    matches += 1

            if match_owner == "*":
                matches += 1
            else:
                if match_owner == service_details["owner"]:
                    matches += 1

            if match_tags == "*":
                matches += 1
            else:
                service_tags = service_details["tags"]
                if all([tag in service_tags for tag in match_tags]):
                    matches += 1

            if matches == 3:
                services_out[service_topic] = service_details

        payload_out = str(len(services_out))
        aiko.message.publish(response_topic, payload=payload_out)

        for service_topic, service_details in services_out.items():
            service_tags = " ".join(service_details["tags"])
            payload_out = f"({service_topic}"                \
                          f" {service_details['protocol']}"  \
                          f" {service_details['owner']}"     \
                          f" ({service_tags}))"
            aiko.message.publish(response_topic, payload_out)
            _LOGGER.debug(f"QUERY: {payload_out}")

        payload_out = "(sync " + response_topic + ")"
        aiko.message.publish(aiko.topic_out, payload_out)
        _LOGGER.debug(f"QUERY: {payload_out}")

def service_add(service_topic, protocol, owner, tags):
    _LOGGER.debug(f"Service add: {service_topic}")
    service_details = { "protocol": protocol, "owner": owner, "tags": tags }
    services[service_topic] = service_details

def service_remove(service_topic):
    if service_topic in services:
        _LOGGER.debug(f"Service remove: {service_topic}")
        del services[service_topic]

# --------------------------------------------------------------------------- #

# TODO: Add message handler for listening for other Registars ?
#       Add discovery protocol handler to keep a list of Registrars
#       This means that the Aiko V2 framework should do the subscription automagically
#       - Find the primary registrar (if it exists ?)
#       - Query to find all other registars
#
# TODO: Add on_message_broker() handler to track MQTT connection status
#       - Events: "add", "remove", "timeout" (waiting for connection)

@click.command()
def main():
    aiko.set_protocol(aiko.REGISTRAR_PROTOCOL)
    aiko.set_registrar_handler(registrar_handler)
    aiko.add_topic_in_handler(topic_in_handler)
    state_machine.transition("initialize", None)
    aiko.process(True)

if __name__ == "__main__":
    main()

# --------------------------------------------------------------------------- #
