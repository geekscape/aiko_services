#!/usr/bin/env python3
#
# Description
# ~~~~~~~~~~~
# Maintain list of available Services and stream (filtered) updates.
#
# Usage
# ~~~~~
# registrar [--primary]
#
#   TODO: --primary: Force take over of the primary registrar role
#
# NAMESPACE=aiko
# HOST=localhost
# PID=`ps ax | grep python | grep registrar | cut -d" " -f1`
# SID=0
# TAGS="(key1=value1 key2=value2)"
# TOPIC_PATH=$NAMESPACE/$HOST/$PID/$SID
#
# mosquitto_pub -t $TOPIC_PATH/in -m  \
#     "(add topic_prefix name protocol transport owner $TAGS)"
# mosquitto_pub -t $TOPIC_PATH/in -m  \
#     "(remove topic_prefix)"
# mosquitto_pub -t $TOPIC_PATH/in -m  \
#     "(share response * * * * $TAGS)"
#
# Notes
# ~~~~~
# Registrar subscribes to ...
# - TOPIC_REGISTRAR_BOOT:    (primary found ...), (primary absent)
# - {topic_path}/in:         (add ...), (history ...), (remove ...), (share ...)
# - {namespace}/+/+/+/state: (absent)
#
# Protocol
# ~~~~~~~~
# V2: 2023-02-21: Registrar supports "(history ...)" message
# V1: 2023-01-12: Registrar bootstrap message includes version number
#                 Renamed request message "query" to "share"
#                 Added Service name field
# V0: 2020-08-18: Initial version
#
# To Do
# ~~~~~
# * Define public API (available function calls) in the Registrar Interface
#
# * BUG: When ECProducer updates "service_count", need to int(services_count) !
#
# * BUG: Registrar won't become primary when there isn't another Registrar
#        and retained topic "aiko.TOPIC_REGISTRAR_BOOT" incorrectly indicates
#        that a primary Registrar is running and should say "(primary absent)"
#
# * BUG: If there are multiple secondaries, when the primary fails, then all
#        secondaries end up being primaries :(
#
# * Consider whether the Registrar should be an Actor instead of a Service ?
#
# * Secondary Registrar subscribe to primary Registrar and update "self.history"
#
# * Reimplement ServicesCache using ECProducer / ECConsumer
#
# - Allow Services to update ServiceDetails, e.g change tags on-the-fly
#
# * Create "Service" class, use everywhere and include "__str__()"
#   - Includes topic_path, protocol, transport, owner and tags
# - Implement Registrar as a sub-class of Category
#
# - Secondary Registrars should acquire Primary Registrar history
# - Secondary Registrars should periodically send a non-retained message to
#     the TOPIC_REGISTRAR_BOOT topic ... (secondary found ...) for Dashboard
# - Dashboard should show if ...
#   - TOPIC_REGISTRAR_BOOT indicates that there is no primary Registrar
#   - TOPIC_REGISTRAR_BOOT indicates that there is a primary Registrar,
#       but the primary is not responding to (history ...) or (share ...)
#   - TOPIC_REGISTRAR_BOOT indicates there are secondary Registrar(s)
#       and show their details
#
# - CLI: show [registrar_filter] ... show running Registrar state
# - CLI: kill service_filter ... terminate running Services
# - CLI: --primary ... Force take over of the primary registrar role
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
# - Consider the ability to add, change or remove a Service's details, e.g tags
# - When Service fails with LWT, publish timestamp on "topic_path/state"
#   - Maybe ProcessController should do this, rather than Registrar ?
# - Every Service persisted in MeemStore should have "uuid" Service tag
# - Document state and protocol
#   - Service state inspired by Meem life-cycle
# - Create registrar/protocol.py
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
#     - Find all other registars via "share"

import click
from collections import deque
import time

from aiko_services.main import *
from aiko_services.main.utilities import *

_LOGGER = aiko.logger(__name__)

_HISTORY_LIMIT_DEFAULT = 16
_HISTORY_RING_BUFFER_SIZE = 4096
_PRIMARY_SEARCH_TIMEOUT = 2.0  # seconds
_SERVICE_STATE_TOPIC = f"{get_namespace()}/+/+/+/state"
_TIME_STARTED = time.monotonic()

# --------------------------------------------------------------------------- #

class StateMachineModel():
    states = ["start", "primary_search", "secondary", "primary"]

    transitions = [
        {"source":
          "start", "trigger": "initialize", "dest": "primary_search"},
        {"source":
          "primary_search", "trigger": "primary_found", "dest": "secondary"},
        {"source":
          "primary_search", "trigger": "primary_promotion", "dest": "primary"},
        {"source":
          "primary", "trigger": "primary_failed", "dest": "primary_search"},
        {"source":
          "secondary", "trigger": "primary_failed", "dest": "primary_search"}
    ]

    def __init__(self, service):
        self.service = service

    def on_enter_primary_search(self, event_data):
#       parameters = event_data.kwargs.get("parameters", {})
        self.service.ec_producer.update("lifecycle", "primary_search")
        _LOGGER.debug("do primary_search add_timer")

# TODO: If oldest known secondary, then immediately become the primary
# TODO: Choose timer period as _PRIMARY_SEARCH_TIMEOUT +/- delta to avoid collisions
        event.add_timer_handler(
            self.primary_search_timer, _PRIMARY_SEARCH_TIMEOUT)

    def primary_search_timer(self):
        timer_valid = self.service.state_machine.get_state() == "primary_search"
        _LOGGER.debug(f"timer primary_search {timer_valid}")
        event.remove_timer_handler(self.primary_search_timer)
        if timer_valid:
            self.service.state_machine.transition("primary_promotion", None)

    def on_enter_secondary(self, event_data):
        self.service.ec_producer.update("lifecycle", "secondary")
        _LOGGER.debug("do enter_secondary")

    def on_enter_primary(self, event_data):
        self.service.ec_producer.update("lifecycle", "primary")
        _LOGGER.debug("do enter_primary")
        # Clear LWT, so this registrar doesn't receive another LWT on reconnect
        aiko.message.publish(aiko.TOPIC_REGISTRAR_BOOT, "", retain=True)
        payload_lwt = "(primary absent)"
        try:
            aiko.process.set_last_will_and_testament(  # May raise SystemError
                aiko.TOPIC_REGISTRAR_BOOT, payload_lwt, True)
            topic_path = self.service.topic_path
            time_started = self.service.time_started
            version = REGISTRAR_VERSION
            payload_out =  \
                f"(primary found {topic_path} {version} {time_started})"
            aiko.message.publish(
                aiko.TOPIC_REGISTRAR_BOOT, payload_out, retain=True)
        except SystemError as system_error:  # Probably MQTT server not running
            self.service.state_machine.transition("primary_failed", None)

# --------------------------------------------------------------------------- #

class Registrar(Service):
    Interface.default("Registrar", "aiko_services.main.registrar.RegistrarImpl")

class RegistrarImpl(Registrar):
    def __init__(self, context):
        context.get_implementation("Service").__init__(self, context)

        state_machine_model = StateMachineModel(self)
        self.state_machine = StateMachineOld(state_machine_model)

        self.history = deque(maxlen=_HISTORY_RING_BUFFER_SIZE)
        self.services = Services()

        self.share = {
            "lifecycle": "start",
            "log_level": get_log_level_name(_LOGGER),
            "source_file": f"v{REGISTRAR_VERSION}⇒ {__file__}",
            "service_count": 0
        }
        self.ec_producer = ECProducer(self, self.share)
        self.ec_producer.add_handler(self._ec_producer_change_handler)

        self.add_message_handler(
            self._service_state_handler, _SERVICE_STATE_TOPIC)
        self.add_message_handler(self._topic_in_handler, self.topic_in)
        self.set_registrar_handler(self._registrar_handler)

        self.state_machine.transition("initialize", None)

    def _ec_producer_change_handler(self, command, item_name, item_value):
        if item_name == "log_level":
            _LOGGER.setLevel(str(item_value).upper())

    def _registrar_handler(self, action, registrar):
        if action == "found":
            if self.state_machine.get_state() == "primary_search":
                self.state_machine.transition("primary_found", None)

        if action == "absent":
            if self.state_machine.get_state() == "primary_search":
                self.state_machine.transition("primary_promotion", None)
            else:
                self.services = Services()
                self.state_machine.transition("primary_failed", None)

    def _service_state_handler(self, _, topic, payload_in):
        command, parameters = parse(payload_in)
        if command == "absent" and topic.endswith("/state"):
            topic_path = topic[:-len("/state")]
            self._service_remove(topic_path)

    def _topic_in_handler(self, _, topic, payload_in):
        command, parameters = parse(payload_in)
        _LOGGER.debug(f"topic_in_handler(): {command}: {parameters}")

        if len(parameters) > 0:
            topic_path = parameters[0]
            if len(parameters) == 6:
                name = parameters[1]
                protocol = parameters[2]
                transport = parameters[3]
                owner = parameters[4]
                tags = parameters[5]

        if command == "add" and len(parameters) == 6:
            self._service_add(
                topic_path, name, protocol, transport, owner, tags, payload_in)

        if command == "remove" and len(parameters) == 1:
            self._service_remove(topic_path)

        if command == "history" and len(parameters) == 2:
            if parameters[1] == "*":
                count = _HISTORY_LIMIT_DEFAULT
            else:
                count = parse_int(parameters[1])
            if len(self.history) < count:
                count = len(self.history)

            payload_out = f"(item_count {count})"
            aiko.message.publish(topic_path, payload=payload_out)

            for service_details in self.history:
                if count < 1:
                    break
                service_tags = " ".join(service_details["tags"])
                payload_out =  "(add"                                \
                              f" {service_details['topic_path']}"    \
                              f" {service_details['name']}"          \
                              f" {service_details['protocol']}"      \
                              f" {service_details['transport']}"     \
                              f" {service_details['owner']}"         \
                              f" ({service_tags})"                   \
                              f" {service_details['time_add']}"      \
                              f" {service_details['time_remove']})"
                aiko.message.publish(topic_path, payload_out)
                count -= 1

        if command == "share" and len(parameters) == 6:
            filter = ServiceFilter("*", name, protocol, transport, owner, tags)
            services_out = self.services.filter_by_attributes(filter)

            payload_out = f"(item_count {services_out.count})"
            aiko.message.publish(topic_path, payload=payload_out)

            for service_details in services_out:
                service_tags = " ".join(service_details["tags"])
                payload_out =  "(add"                              \
                              f" {service_details['topic_path']}"  \
                              f" {service_details['name']}"        \
                              f" {service_details['protocol']}"    \
                              f" {service_details['transport']}"   \
                              f" {service_details['owner']}"       \
                              f" ({service_tags}))"
                aiko.message.publish(topic_path, payload_out)

            payload_out = f"(sync {topic_path})"
            aiko.message.publish(self.topic_out, payload_out)

    def _service_add(self,
        topic_path, name, protocol, transport, owner, tags, payload_out):

        if not self.services.get_service(topic_path):
            _LOGGER.debug(f"Service add: {topic_path}")

            service_details = {
                "topic_path": topic_path,
                "name": name,
                "protocol": protocol,
                "transport": transport,
                "owner": owner,
                "tags": tags,
                "time_add": time.monotonic(),
                "time_remove": 0
            }

            self.services.add_service(topic_path, service_details)
            self.ec_producer.update("service_count", self.services.count)

            aiko.message.publish(self.topic_out, payload_out)

    def _service_remove(self, topic_path):
        service_topic_path = ServiceTopicPath.parse(topic_path)
        if service_topic_path:
            if service_topic_path.service_id == "0":  # Process terminated
                process_topic_path, _ = ServiceTopicPath.topic_paths(topic_path)
                topic_paths =  \
                    self.services.get_process_services(process_topic_path)
            else:
                topic_paths = topic_path

            for topic_path in list(topic_paths):
                service_details = self.services.get_service(topic_path)
                if service_details:
                    _LOGGER.debug(f"Service remove: {topic_path}")

                    service_details["time_remove"] = time.monotonic()
                    self.history.appendleft(service_details)

                    self.services.remove_service(topic_path)
                    self.ec_producer.update(
                        "service_count", self.services.count)

                    payload_out = f"(remove {topic_path})"
                    aiko.message.publish(self.topic_out, payload_out)

# --------------------------------------------------------------------------- #

@click.command("main", help="Registrar Service")

def main():
    tags = ["ec=true"]  # TODO: Add ECProducer tag before add to Registrar
    init_args = service_args(
        REGISTRAR_SERVICE_TYPE, None, None, REGISTRAR_PROTOCOL, tags)
    registrar = compose_instance(RegistrarImpl, init_args)
    aiko.process.run(True)

if __name__ == "__main__":
    main()

# --------------------------------------------------------------------------- #
