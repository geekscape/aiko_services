# Description
# ~~~~~~~~~~~
# Provides the AikoServices framework for an application process.
# Supports none, one or many Services within a single Process.
#
# Usage
# ~~~~~
# def time_handler():
#     print("timer_handler()")
#
# from aiko_services.main import *       # Invokes __init__.py
# aiko.process = process_create()        # Invoked from __init__.py
# event.add_timer_handler(handler, 1.0)
# aiko.process.run()                     # Invoked by application code
#
# To Do
# ~~~~~
# * BUG: AikoLogger.logger()" uses a Service Id of 0, not actual Service Id
#
# - A Process with ...
#   - Single Service:    Typically isn't a LifeCycleManager
#   - Multiple Services: First Service is a LifeCycleManager or Pipeline
#     - Use optimized single Process LifeCycleManager (not distributed) ?
#     - Using local or remote functional calls should be very similar ?
#
# - Ensure that add_service() and remove_service() update the Registrar
# - Consider moving all registrar related functions into the Registar
#
# - If a Service event (message, timer) handler raises an Exception,
#   then provide the option to terminate and remove the Service or
#   terminate the entire Process
#
# - Replace global Event functions with a Handler class instance
#
# - Improve AikoLogger (console and MQTT) to accurately provide Service id
#   - Use ContextManager ?
#
# - Automatically attempt reconnection with MQTT server after disconnection
#
# - Implement multiple message server connections
#
# - Review "event.py" message and mailbox queues for latency and bandwidth
#   - Minimal latency from MQTT on_message() handler --> application handler
#   - Minimal latency for priority message handling, whilst handling others
# - Load test 1 Process containing 1,000+ Services
# - Load test 1 Process containing 10,000+ Services (what is the limit ?)
# - Load test 1,000+ Process containing 1,000+ Services
# - Load test 1,000+ Process containing 10,000+ Services (what is the limit ?)
#
# - HL Fleet
#   - HL Serving instances: Provide Ray head and worker node public IP addresses
#   - Registrar History and Recorder --> Dashboard, local and remote storage ?
#   - HostService: monitor CPU, memory, disk, GPU, network, mosquitto, etc
#     - Run on artemis, zeus, AWS EC2 Ray head and worker nodes
#   - Statistics: InfluxDB --> Grafana

import os
import sys
import traceback

from aiko_services.main import *
from aiko_services.main.message import *
from aiko_services.main.utilities import *

__all__ = ["aiko", "process_create"]

_VERSION = 0

# Environment variable names
_AIKO_LOG_LEVEL_MESSAGE = "AIKO_LOG_LEVEL_MESSAGE"
_AIKO_LOG_LEVEL_PROCESS = "AIKO_LOG_LEVEL_PROCESS"

# --------------------------------------------------------------------------- #
# ProcessData is intended as a singleton class data structure only

class ProcessData:
    TOPIC_REGISTRAR_BOOT = f"{get_namespace()}/service/registrar"

    connection = Connection()
#   event = aiko_services.event  # TODO: Replace with Handler() instance
    logger = None
    message = None
    process = None
    registrar = None

    topic_path_process = f"{get_namespace()}/{get_hostname()}/{get_pid()}"
    topic_path = f"{topic_path_process}/0"
    topic_in = f"{topic_path}/in"
    topic_log = f"{topic_path}/log"
    topic_lwt = f"{topic_path}/state"
    topic_out = f"{topic_path}/out"
    payload_lwt = "(absent)"

    @classmethod
    def get_topic_path(cls, service_id):
        return f"{cls.topic_path_process}/{service_id}"

aiko = ProcessData

# --------------------------------------------------------------------------- #
# AikoLogger should be usable even before ProcessImplementation() is created

class AikoLogger:
    @classmethod
    def logger(cls,
        name, log_level=None, logging_handler=None, topic=aiko.topic_log):

        if logging_handler is None:
            option = os.environ.get("AIKO_LOG_MQTT", "all")
            if option in ("all", "true"):
                logging_handler = LoggingHandlerMQTT(aiko, topic, option)
        return get_logger(name, log_level, logging_handler)

aiko.logger = AikoLogger.logger

_LOGGER_MESSAGE = aiko.logger(
    f"{__name__}.message",
    log_level=os.environ.get(_AIKO_LOG_LEVEL_MESSAGE, "INFO")
)

_LOGGER = aiko.logger(
    __name__, log_level=os.environ.get(_AIKO_LOG_LEVEL_PROCESS, "INFO")
)

# --------------------------------------------------------------------------- #
# ProcessImplementation is intended as a singleton class implementation only

class ProcessImplementation(ProcessData):
    def __init__(self):
        self.initialized = False
        self.running = False  # TODO: Replace with StateMachine (see actor.py)
        self.service_count = 0

        self._exit_status = 0
        self._message_handlers = {}
        self._message_handlers_binary_topics = {}
        self._message_handlers_wildcard_topics = []
        self._registrar_absent_terminate = False
        self._services = {}
        self._services_lock = Lock(f"{__name__}._services", _LOGGER)

    def initialize(self, mqtt_connection_required=True):
        if not self.initialized:
            self.initialized = True
            event.add_queue_handler(self.on_message_queue_handler, ["message"])
            self.add_message_handler(
                self.on_registrar, aiko.TOPIC_REGISTRAR_BOOT)

            aiko.message = Castaway()  # standalone and isolated :(
            mqtt_connected = False
            try:
                aiko.message = MQTT(
                    self.on_message, self._message_handlers,
                    aiko.topic_lwt, aiko.payload_lwt, False
                )
                mqtt_connected = True
            except SystemError as system_error:
                if mqtt_connection_required:
                    _LOGGER.error(system_error)
                else:
                    _LOGGER.warning(system_error)
            if mqtt_connection_required and not mqtt_connected:
                raise SystemExit()

            context = ContextManager(aiko, aiko.message)

    def run(self, loop_when_no_handlers=False, mqtt_connection_required=True):
        self.initialize(mqtt_connection_required=mqtt_connection_required)

        if not self.running:
            try:
                self.running = True
                event.loop(loop_when_no_handlers)  ## Blocking call ##
            finally:
                self.running = False

        if self._exit_status:
            sys.exit(self._exit_status)

    def add_message_handler(self, message_handler, topic, binary=False):
        if not topic in self._message_handlers:
            self._message_handlers[topic] = []
            if binary:
                self._message_handlers_binary_topics[topic] = True
            if ("#" in topic) or ("+" in topic):
                self._message_handlers_wildcard_topics.append(topic)
            if aiko.message:
                aiko.message.subscribe(topic)
        self._message_handlers[topic].append(message_handler)

    def remove_message_handler(self, message_handler, topic):
        if topic in self._message_handlers:
            if message_handler in self._message_handlers[topic]:
                self._message_handlers[topic].remove(message_handler)
            if len(self._message_handlers[topic]) == 0:
                del self._message_handlers[topic]
                if topic in self._message_handlers_binary_topics:
                    del self._message_handlers_wildcard_topics[topic]
                if topic in self._message_handlers_wildcard_topics:
                    del self._message_handlers_wildcard_topics[topic]
                if self.message:
                    self.message.unsubscribe(topic)

    def _add_service_to_registrar(self, service):
        if service.protocol:
            try:
                owner = get_username()
            except:
                owner = "????????"
                _LOGGER.warning(
                    "Unable to acquire username to identify the Service owner")
            tags = service.get_tags_string()
            # TODO: For payload_out, use parser.generate() ?
            payload_out = f"(add {service.topic_path} {service.name} "  \
                  f"{service.protocol} {service.transport} {owner} ({tags}))"
            registrar_topic_in = f"{aiko.registrar['topic_path']}/in"
            aiko.message.publish(registrar_topic_in, payload_out)

    def _remove_service_from_registrar(self, service):
        if service.protocol:
            # TODO: For payload_out, use parser.generate() ?
            payload_out = f"(remove {service.topic_path})"
            registrar_topic_in = f"{aiko.registrar['topic_path']}/in"
            aiko.message.publish(registrar_topic_in, payload_out)

    def add_service(self, service):
        try:
            self._services_lock.acquire("add_service()")
            self.service_count += 1
            service.service_id = self.service_count
            service.topic_path = aiko.get_topic_path(service.service_id)
            self._services[service.service_id] = service
        finally:
            self._services_lock.release()

        if self.connection.is_connected(ConnectionState.REGISTRAR):
            self._add_service_to_registrar(service)
        return self.service_count

    def remove_service(self, service_id):
        try:
            self._services_lock.acquire("remove_service")
            if service_id in self._services:
                del self._services[service_id]
                self.service_count -= 1
        finally:
            self._services_lock.release()

        if self.connection.is_connected(ConnectionState.REGISTRAR):
            self._remove_service_from_registrar(service)
        return self.service_count

    def on_message(self, mqtt_client, userdata, message):
        try:
            event.queue_put(message, "message")
        except Exception as exception:
            print(traceback.format_exc())

    def on_message_queue_handler(self, message, _):
        topic = message.topic
        payload_in = message.payload
        if topic not in self._message_handlers_binary_topics:
            payload_in = payload_in.decode("utf-8")
        if _LOGGER_MESSAGE.isEnabledFor(DEBUG):  # Don't expand debug message
            _LOGGER_MESSAGE.debug(f"Message: {topic}: {payload_in}")

        message_handler_list = []
        topics_matched = self.topic_matcher(topic, self._message_handlers)
        for topic_match in topics_matched:
            message_handler_list.extend(self._message_handlers[topic_match])

        if len(message_handler_list) > 0:
            for message_handler in message_handler_list:
                try:
                    if message_handler(aiko, topic, payload_in):
                        return
                except Exception as exception:  # REVIEW
                    payload_out = traceback.format_exc()
                    print(payload_out)
                    aiko.message.publish(aiko.topic_log, payload_out)

    def on_registrar(self, _, topic, payload_in):
        action = None
        parse_okay = False
        registrar = {}
        try:
            command, parameters = parse(payload_in)
            if len(parameters) > 0:
                action = parameters[0]
                if command == "primary":
                    if len(parameters) == 4 and action == "found":
                        registrar["topic_path"] = parameters[1]
                        registrar["version"] = parameters[2]
                        registrar["timestamp"] = parameters[3]
                        parse_okay = True
                    if len(parameters) == 1 and action == "absent":
                        parse_okay = True
            if parse_okay:
                if action == "found":
                    aiko.registrar = registrar
                    aiko.connection.update_state(ConnectionState.REGISTRAR)

                    try:
                        self._services_lock.acquire("on_registrar() #1")
                        for service in self._services.values():
                            self._add_service_to_registrar(service)
                    finally:
                        self._services_lock.release()

                if action == "absent":
                    aiko.registrar = None
                    aiko.connection.update_state(ConnectionState.TRANSPORT)
                    if self._registrar_absent_terminate:
                        self.terminate(1)

                try:
                    self._services_lock.acquire("on_registrar() #2")
                    for service in self._services.values():
                        service.registrar_handler_call(action, aiko.registrar)
                finally:
                    self._services_lock.release()
        except Exception as exception:
            _LOGGER.warning(f"Exception raised when adding to Registrar")
            #   f"Exception raised when adding to Registrar: {exception}\n"
            #   f"{exception.__traceback__.tb_frame} "
            #   f"raised via line {exception.__traceback__.tb_lineno}")
            traceback.print_exception(
                type(exception), exception, exception.__traceback__)

    def set_last_will_and_testament(self,
        topic_lwt, payload_lwt="(absent)", retain_lwt=False):

        aiko.message.set_last_will_and_testament(
            topic_lwt, payload_lwt, retain_lwt)

    def set_registrar_absent_terminate(self):
        self._registrar_absent_terminate = True

    def terminate(self, exit_status=0):
        self._exit_status = exit_status
        event.terminate()

# topic_matcher() matches a ...
# - literal topic without wildcards
# - topic ending with a "#" wildcard, e.g prefix/#
# - topic containing "+" wildcards, e.g prefix/+/+/+/suffix

    def topic_matcher(self, topic, topics):
        if topic in topics:
            topics_matched = [topic]
        else:
            topics_matched = []

        for wildcard_topic in self._message_handlers_wildcard_topics:
            tokens = topic.split("/")
            wildcard_tokens = wildcard_topic.split("/")

            if wildcard_tokens[-1] == "#":
                if tokens[:-1] == wildcard_tokens[:-1]:
                    topics_matched.append(wildcard_topic)
            elif tokens[0] == wildcard_tokens[0] and  \
                 tokens[-1] == wildcard_tokens[-1]:
                    topics_matched.append(wildcard_topic)
        return topics_matched

def process_create():
    if not ProcessData.process:
        ProcessData.process = ProcessImplementation()
    return ProcessData.process

# --------------------------------------------------------------------------- #
