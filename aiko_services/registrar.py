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
# NAMESPACE=aiko
# HOST=localhost
# PID=`ps ax | grep python | grep registrar | cut -d" " -f1`
# TOPIC_PATH=$NAMESPACE/$HOST/$PID
#
# TAGS="(key1=value1 key2=value2)"
# mosquitto_pub -t $TOPIC_PATH/in -m "(add topic_prefix protocol transport owner $TAGS)"
# mosquitto_pub -t $TOPIC_PATH/in -m "(remove topic_prefix)"
# mosquitto_pub -t $TOPIC_PATH/in -m "(query response * * * $TAGS)"
#
# Notes
# ~~~~~
# Registrar subscribes to ...
# - REGISTRAR_TOPIC: "(primary started ...)" and "(primary stopped)"
# - {topic_path}/in: "(add ...)", "(query ...)", "(remove ...)"
# - {namespace}/+/+/state: "(stopped)"
#
# To Do
# ~~~~~
# * Create "Service" class, use everywhere and include "__str__()"
#   - Includes topic_path, protocol, transport, owner and tags
# * Use ServiceField everywhere to elimate service[?] literal integers !
# * Registrar should ECProducer when it is has subsumed ServiceCache
#
# - Primary Registrar supports discovery protocol for finding MQTT server, etc
# - Make this a sub-command of Aiko CLI
#
# - Handle MQTT restart
# - Handle MQTT stop and start on a different host
# - Handle if system crashes, then mosquitto doesn't get to send a LWT messages
#   for the Registrar leaving a stale reference to a Registrar now longer exists
#   If a new Registrar isn't started when the system restarts, then Aiko Clients
#   try to use the defunct Registrar
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
#   - https://en.wikipedia.org/wiki/Raft_(algorithm)
#   - https://en.wikipedia.org/wiki/Conflict-free_replicated_data_type
#   - Eventual consistency and optimistic replication
# - Implement protocol matching similar to programming language interfaces
#     with inheritance
# - Add on_message_broker() handler to track MQTT connection status
#   - Events: "add", "remove", "timeout" (waiting for connection)
# - Add message handler for listening for other Registars ?
#     Add discovery protocol handler to keep a list of Registrars
#     This means the Aiko V2 framework should do the subscription automagically
#     - Find the primary registrar (if it exists ?)
#     - Query to find all other registars


import click
import time

from aiko_services import *
from aiko_services.utilities import *

__all__ = []

_LOGGER = aiko.logger(__name__)
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
        {"source": "primary", "trigger": "primary_failed", "dest": "primary_search"},
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
        # Clear LWT, so this registrar doesn't receive another LWT on reconnect
        aiko.public.message.publish(aiko.REGISTRAR_TOPIC, "", retain=True)
        lwt_payload = "(primary stopped)"
        aiko.set_last_will_and_testament(aiko.REGISTRAR_TOPIC, lwt_payload, True)
        payload_out = f"(primary started {aiko.public.topic_path} {time_started})"
        aiko.public.message.publish(aiko.REGISTRAR_TOPIC, payload_out, retain=True)

state_machine = StateMachine(StateMachineModel())

# --------------------------------------------------------------------------- #

def registrar_handler(aiko, action, registrar):
    if action == "started":
        if state_machine.get_state() == "primary_search":
            state_machine.transition("primary_found", None)

    if action == "stopped":
        if state_machine.get_state() == "primary_search":
            state_machine.transition("primary_promotion", None)
        else:
            services = {}
            state_machine.transition("primary_failed", None)

    return False

def service_state_handler(aiko, topic, payload_in):
    command, parameters = parse(payload_in)
    if command == "stopped" and topic.endswith("/state"):
        topic_path = topic[:-len("/state")]
        service_remove(topic_path)
        payload_out = f"(remove {topic_path})"
        aiko.message.publish(aiko.topic_out, payload_out)

def topic_in_handler(aiko, topic, payload_in):
    command, parameters = parse(payload_in)
#   _LOGGER.debug(f"topic_in_handler(): {command}: {parameters}")

    if len(parameters) > 0:
        topic_path = parameters[0]
        if len(parameters) == 5:
            protocol = parameters[1]
            transport = parameters[2]
            owner = parameters[3]
            tags = parameters[4]

    if command == "add" and len(parameters) == 5:
        service_add(topic_path, protocol, transport, owner, tags)
        payload_out = payload_in
        aiko.message.publish(aiko.topic_out, payload_out)

    if command == "remove" and len(parameters) == 1:
        service_remove(topic_path)
        payload_out = payload_in
        aiko.message.publish(aiko.topic_out, payload_out)

    if command == "query" and len(parameters) == 5:
        filter = ServiceFilter("*", protocol, transport, owner, tags)
        services_out = filter_services_by_attributes(services, filter)

        payload_out = f"(item_count {len(services_out)})"
        aiko.message.publish(topic_path, payload=payload_out)

        for service_topic, service_details in services_out.items():
            service_tags = " ".join(service_details["tags"])
            payload_out =  "(add"                             \
                          f" {service_topic}"                 \
                          f" {service_details['protocol']}"   \
                          f" {service_details['transport']}"  \
                          f" {service_details['owner']}"      \
                          f" ({service_tags}))"
            aiko.message.publish(topic_path, payload_out)

        payload_out = "(sync " + topic_path + ")"
        aiko.message.publish(aiko.topic_out, payload_out)

def service_add(service_topic, protocol, transport, owner, tags):
    if service_topic not in services:
        _LOGGER.debug(f"Service add: {service_topic}")
        service_details = {
            "protocol": protocol,
            "transport": transport,
            "owner": owner,
            "tags": tags
        }
        services[service_topic] = service_details

def service_remove(service_topic):
    if service_topic in services:
        _LOGGER.debug(f"Service remove: {service_topic}")
        del services[service_topic]

# --------------------------------------------------------------------------- #

@click.command()
def main():
    aiko.set_protocol(aiko.REGISTRAR_PROTOCOL)  # TODO: Move into service.py
    aiko.add_message_handler(service_state_handler, aiko.SERVICE_STATE_TOPIC)
    aiko.set_registrar_handler(registrar_handler)
    aiko.add_topic_in_handler(topic_in_handler)
    state_machine.transition("initialize", None)
    aiko.process(True)

if __name__ == "__main__":
    main()

# --------------------------------------------------------------------------- #
