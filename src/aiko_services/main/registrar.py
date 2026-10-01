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
# - {topic_path}/probe:      (item_count 0), the primary's reply to a probe
# - {namespace}/+/+/+/state: (absent)
#
# Primary election
# ~~~~~~~~~~~~~~~~
# start --> primary_search --found--> primary_probe --alive--> secondary
#                  |                        |
#                  |                        +--dead--> primary_search
#                  +--timeout or absent--> primary
#
# A retained "(primary found ...)" can outlive its Registrar: when the MQTT
# server and the Registrar stop together (a power cycle), the server keeps
# the retained announcement but never sends the Registrar's will.  So a
# found primary is probed before this Registrar yields: "(history
# {topic_path}/probe 0)" to its topic_in, which costs one reply.  No reply
# in _PRIMARY_PROBE_TIMEOUT seconds: this Registrar publishes the will the
# dead primary never sent, "(primary absent)" retained, and searches again.
# Its own echo of that "absent" then promotes it.
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
# * BUG: "service_remove()" if Process, then remove *all* Process' Services
#
# * BUG: When ECProducer updates "service_count", need to int(services_count) !
#
# * BUG: If there are multiple secondaries, when the primary fails, then all
#        secondaries end up being primaries :(
#
# * FIX: Update public methods to match Category Interface ...
#        Rename service_add() --> add(), service_remove() --> remove()
#        Consider services_share() as a synonym for list() ?
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
# - If no Registrar is started after a system crash, then Aiko Clients still
#   try to use the defunct Registrar that the stale announcement names (a new
#   Registrar replaces it: see "Primary election").  ServicesCache warns
#   when the Registrar doesn't reply
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
#
# Ideas
# ~~~~~
# - Use "Services:self._services = OrderedDict()" as a tree structure ...
#   - Ordered by Service "topic_path" fields: namespace, host, pid, sid
#   - Share portions of the tree via Eventual Consistency like GraphQL

from abc import abstractmethod
import click
from collections import deque
import random
import time

from aiko_services.main import *
from aiko_services.main.utilities import *

__all__ = ["Registrar"]

_LOGGER = aiko.logger(__name__)

_HISTORY_LIMIT_DEFAULT = 16
_HISTORY_RING_BUFFER_SIZE = 4096
_PRIMARY_PROBE_JITTER = 0.5    # seconds, at most: Registrars probe apart
_PRIMARY_PROBE_TIMEOUT = 3.0   # seconds a found primary has to reply
_PRIMARY_SEARCH_TIMEOUT = 2.0  # seconds
_SERVICE_STATE_TOPIC = f"{get_namespace()}/+/+/+/state"
_TIME_STARTED = time.monotonic()

# --------------------------------------------------------------------------- #

class StateMachineModel():
    states = ["start", "primary_search", "primary_probe", "secondary", "primary"]

    transitions = [
        {"source":
          "start", "trigger": "initialize", "dest": "primary_search"},
        {"source":
          "primary_search", "trigger": "primary_found", "dest": "primary_probe"},
        {"source":
          "primary_probe", "trigger": "primary_found", "dest": "primary_probe"},
        {"source":
          "primary_probe", "trigger": "primary_alive", "dest": "secondary"},
        {"source":
          "primary_probe", "trigger": "primary_dead", "dest": "primary_search"},
        {"source":
          "primary_probe", "trigger": "primary_absent", "dest": "primary_search"},
        {"source":
          "primary_search", "trigger": "primary_promotion", "dest": "primary"},
        {"source":
          "primary", "trigger": "primary_failed", "dest": "primary_search"},
        {"source":
          "secondary", "trigger": "primary_failed", "dest": "primary_search"}
    ]

    def __init__(self, service):
        self.service = service
        self.probe_target = None       # the found primary's topic_path
        self._timers = set()           # the timer handlers pending

    def _timer_add(self, handler, period):
        if handler not in self._timers:
            self._timers.add(handler)
            event.add_timer_handler(handler, period)

    def _timer_remove(self, handler):
        # remove_timer_handler() counts down even when nothing is removed
        if handler in self._timers:
            self._timers.discard(handler)
            event.remove_timer_handler(handler)

    def on_enter_primary_search(self, event_data):
        self.service.ec_producer.update("lifecycle", "primary_search")
        _LOGGER.debug("do primary_search add_timer")

# TODO: If oldest known secondary, then immediately become the primary
# TODO: Choose timer period as _PRIMARY_SEARCH_TIMEOUT +/- delta to avoid collisions
        self._timer_add(self.primary_search_timer, _PRIMARY_SEARCH_TIMEOUT)

    def on_exit_primary_search(self, event_data):
        self._timer_remove(self.primary_search_timer)

    def primary_search_timer(self):
        timer_valid = self.service.state_machine.get_state() == "primary_search"
        _LOGGER.debug(f"timer primary_search {timer_valid}")
        self._timer_remove(self.primary_search_timer)
        if timer_valid:
            self.service.state_machine.transition("primary_promotion", None)

    def on_enter_primary_probe(self, event_data):
        """Ask the found primary for nothing: "(history TOPIC 0)" has
        exactly one reply, "(item_count 0)", on this Registrar's probe topic"""

        parameters = event_data.kwargs.get("parameters") or {}
        self.probe_target = parameters.get("topic_path")
        self.service.ec_producer.update("lifecycle", "primary_probe")
        _LOGGER.debug(f"do primary_probe {self.probe_target}")
        aiko.message.publish(f"{self.probe_target}/in",
            f"(history {self.service.topic_probe} 0)")
        self._timer_add(self.primary_probe_timer, _PRIMARY_PROBE_TIMEOUT +
                        random.uniform(0, _PRIMARY_PROBE_JITTER))

    def on_exit_primary_probe(self, event_data):
        self._timer_remove(self.primary_probe_timer)

    def primary_probe_timer(self):
        self._timer_remove(self.primary_probe_timer)
        if self.service.state_machine.get_state() != "primary_probe":
            return
        _LOGGER.warning(f"Primary Registrar {self.probe_target} didn't reply "
            f"in {_PRIMARY_PROBE_TIMEOUT:g} s: its announcement is stale, "
            f"publishing (primary absent)")
        aiko.message.publish(
            aiko.TOPIC_REGISTRAR_BOOT, "(primary absent)", retain=True)
        self.service.state_machine.transition("primary_dead", None)

    def on_enter_secondary(self, event_data):
        self.service.ec_producer.update("lifecycle", "secondary")
        _LOGGER.debug("do enter_secondary")

    def on_enter_primary(self, event_data):
        self.service.announced = True
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
    """
    The Service discovery hub (concepts/registrar.md): the live directory
    of running Services, their history, and the primary election.  Method
    names carry a "service(s)_" prefix because the bare wire-command names
    collide with universal Service state ("share", "history").  Requests
    reply via messages to "topic_response" (s_02 §2), never return values
    """
    Interface.default("Registrar", "aiko_services.main.registrar.RegistrarImpl")

    @abstractmethod
    def service_add(self, topic_path, name, protocol, transport, owner, tags):
        """Register a Service.  Wire form: "(add topic_path name protocol
        transport owner (tags))" on topic_in.  Projection: command"""

    @abstractmethod
    def service_remove(self, topic_path):
        """Deregister a Service (a process topic_path with service id 0
        removes all of that process's Services).  Wire form:
        "(remove topic_path)".  Projection: command"""

    @abstractmethod
    def services_history(self, topic_response, count):
        """Reply with up to "count" most-recently removed Services:
        "(item_count n)" then one "(add ... time_add time_remove)" per
        Service, to topic_response.  Wire form:
        "(history topic_response count)".  Projection: request"""

    @abstractmethod
    def services_share(self, topic_response,
        name, protocol, transport, owner, tags):
        """Reply with the running Services matching the filter:
        "(item_count n)" then one "(add ...)" per Service to
        topic_response, then "(sync topic_response)" on topic_out.
        Wire form: "(share topic_response name protocol transport owner
        tags)".  Projection: request"""

class RegistrarImpl(Registrar):
    def __init__(self, context):
        context.call_init(self, "Service", context)

        state_machine_model = StateMachineModel(self)
        self.state_machine = StateMachineOld(state_machine_model)

        self.announced = False           # has been the primary
        self.history = deque(maxlen=_HISTORY_RING_BUFFER_SIZE)
        self.services = Services()
        self.topic_probe = f"{self.topic_path}/probe"

        self.share = {
            "aiko_id": aiko.id,
            "lifecycle": "start",
            "log_level": get_log_level_name(_LOGGER),
            "source_file": f"v{REGISTRAR_VERSION}⇒ {__file__}",
            "service_count": 0
        }
        self.ec_producer = compose_instance(
            ECProducerImpl, ec_producer_args(self, self.share))
        self.ec_producer.add_handler(self._ec_producer_change_handler)

        self.add_message_handler(
            self._service_state_handler, _SERVICE_STATE_TOPIC)
        self.add_message_handler(self._topic_in_handler, self.topic_in)
        self.add_message_handler(self._probe_handler, self.topic_probe)
        self.set_registrar_handler(self._registrar_handler)

        self.state_machine.transition("initialize", None)

    def _ec_producer_change_handler(self, command, item_name, item_value):
        if item_name == "log_level":
            _LOGGER.setLevel(str(item_value).upper())

    def _registrar_handler(self, action, registrar):
        state = self.state_machine.get_state()
        if action == "found":
            target = registrar.get("topic_path") if registrar else None
            if state == "primary_search":
                if target == self.topic_path:
                    if self.announced:           # this Registrar, still primary
                        self.state_machine.transition("primary_promotion", None)
                    else:                        # a reused PID: stale
                        _LOGGER.warning(f"Primary Registrar {target} is this "
                            "Registrar's own topic path, never announced: "
                            "stale, publishing (primary absent)")
                        aiko.message.publish(aiko.TOPIC_REGISTRAR_BOOT,
                            "(primary absent)", retain=True)
                else:
                    self.state_machine.transition(
                        "primary_found", {"topic_path": target})
            elif state == "primary_probe" and target != self.state_machine.model.probe_target:
                self.state_machine.transition(       # a newer primary: probe it
                    "primary_found", {"topic_path": target})

        if action == "absent":
            if state == "primary_search":
                self.state_machine.transition("primary_promotion", None)
            elif state == "primary_probe":
                self.state_machine.transition("primary_absent", None)
            elif state in ("primary", "secondary"):
                self.services = Services()
                self.state_machine.transition("primary_failed", None)

    def _probe_handler(self, _, topic, payload_in):
        command, _ = parse(payload_in)
        if command == "item_count" and  \
                self.state_machine.get_state() == "primary_probe":
            self.state_machine.transition("primary_alive", None)

    def _service_state_handler(self, _, topic, payload_in):
        command, parameters = parse(payload_in)
        if command == "absent" and topic.endswith("/state"):
            topic_path = topic[:-len("/state")]
            self.service_remove(topic_path)

    def _topic_in_handler(self, _, topic, payload_in):
        command, parameters = parse(payload_in)
        _LOGGER.debug(f"topic_in_handler(): {command}: {parameters}")

        if command == "add" and len(parameters) == 6:
            self.service_add(*parameters)
        elif command == "remove" and len(parameters) == 1:
            self.service_remove(parameters[0])
        elif command == "history" and len(parameters) == 2:
            if parameters[1] == "*":
                count = _HISTORY_LIMIT_DEFAULT
            else:
                count = parse_int(parameters[1])
            self.services_history(parameters[0], count)
        elif command == "share" and len(parameters) == 6:
            self.services_share(*parameters)

    def services_history(self, topic_response, count):
        if len(self.history) < count:
            count = len(self.history)

        payload_out = f"(item_count {count})"
        aiko.message.publish(topic_response, payload=payload_out)

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
            aiko.message.publish(topic_response, payload_out)
            count -= 1

    def services_share(self, topic_response,
        name, protocol, transport, owner, tags):

        filter = ServiceFilter("*", name, protocol, transport, owner, tags)
        services_out = self.services.filter_by_attributes(filter)

        payload_out = f"(item_count {services_out.count})"
        aiko.message.publish(topic_response, payload=payload_out)

        for service_details in services_out:
            service_tags = " ".join(service_details["tags"])
            payload_out =  "(add"                              \
                          f" {service_details['topic_path']}"  \
                          f" {service_details['name']}"        \
                          f" {service_details['protocol']}"    \
                          f" {service_details['transport']}"   \
                          f" {service_details['owner']}"       \
                          f" ({service_tags}))"
            aiko.message.publish(topic_response, payload_out)

        payload_out = f"(sync {topic_response})"
        aiko.message.publish(self.topic_out, payload_out)

    def service_add(self,
        topic_path, name, protocol, transport, owner, tags):

        payload_out = generate(
            "add", [topic_path, name, protocol, transport, owner, tags])
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

    def service_remove(self, topic_path):
        service_topic_path = ServiceTopicPath.parse(topic_path)
        if service_topic_path:
        # TODO: For this Process, remove *all* Services
            if service_topic_path.service_id == "0":  # Process terminated
                process_topic_path, _ = ServiceTopicPath.topic_paths(topic_path)
                topic_paths =  \
                    self.services.get_process_services(process_topic_path)
            else:
                topic_paths = [topic_path]

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
