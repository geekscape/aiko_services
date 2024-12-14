#!/usr/bin/env python3
#
# Usage
# ~~~~~
# aiko_registrar
# ./share.py sc_test  # ServicesCache test
#
# ./share.py ec_test  # EventualConsistency test
# ./share.py ec_test PRODUCER_PID [EC_PRODUCER_SID]
#
# NAMESPACE=aiko
# HOST=localhost
# PRODUCER_PID=`ps ax | grep python | grep share.py | xargs | cut -d" " -f1`;  \
#     TOPIC_PATH=$NAMESPACE/$HOST/$PRODUCER_PID/1
#
# mosquitto_sub -t '#' -v
#
# mosquitto_pub -t $TOPIC_PATH/control -m "(invalid)"
# mosquitto_pub -t $TOPIC_PATH/control -m "(share)"
# mosquitto_pub -t $TOPIC_PATH/control -m "(share topic)"
# mosquitto_pub -t $TOPIC_PATH/control -m "(share topic 0)"
# mosquitto_pub -t $TOPIC_PATH/control -m "(share topic a *)"
# mosquitto_pub -t $TOPIC_PATH/control -m "(share topic 0 *)"
# mosquitto_pub -t $TOPIC_PATH/control -m "(share topic 0 lifecycle)"
# mosquitto_pub -t $TOPIC_PATH/control -m "(share topic 0 services)"
# mosquitto_pub -t $TOPIC_PATH/control -m "(share topic 0 x)"
# mosquitto_pub -t $TOPIC_PATH/control -m "(share topic 0 (lifecycle))"
# mosquitto_pub -t $TOPIC_PATH/control -m "(share topic 0 (lifecycle x))"
# mosquitto_pub -t $TOPIC_PATH/control -m "(add count 0)"
# mosquitto_pub -t $TOPIC_PATH/control -m "(update count 1)"
# mosquitto_pub -t $TOPIC_PATH/control -m "(remove count)"
# mosquitto_pub -t $TOPIC_PATH/control -m "(update lifecycle ready)"
# mosquitto_pub -t $TOPIC_PATH/control -m "(add services.test 0)"
# mosquitto_pub -t $TOPIC_PATH/control -m "(remove services)"
#
# To Do
# ~~~~~
# - BUG?: ECProducer remote expired leases
# - BUG?: ECConsumer remote expired leases
#
# - BUG: ServicesCache (and also EC) should handle degradation of
#   network (ConnectionState changes) and/or lease expiring.
#
# - ECProducerCore class provides absolute minimum implementation
#   - Responds to all "(share ...)" requests with "(item_count 0)"
#     Ignores all other requests
#   - ECProducer extends ECProducerCore
#
# - For multiple Actors in same process, when each Actor wants to have a
#   its own unique ECProducer shared amongst different aspects of the Actor,
#   e.g LifeCycleClient and some other functionality, then the ECProducer
#   constructor optionally includes the Service "name" to disambigute
#
# - Provide unit tests !
# - Registrar should migrate use of ServicesCache to ECProducer
# - ECProducer and ECConsumer should handle Registrar not available
# - ECProducer and ECConsumer should handle Registrar stop and restart
# - Allow ECConsumer to change share filter, with or without existing lease
# - Fix ECConsumer to handle _ec_remove_item()/_ec_update_item() exceptions
# - Improve EC share/cache to work recursively beyond just two levels
# - When subscribed to a component of a dictionary, removal of the dictionary
#   does not send a remove message for the component

import click
import os

from aiko_services.main import *
from aiko_services.main.utilities import *

__all__ = [
    "ECConsumer", "PROTOCOL_EC_CONSUMER",
    "ECProducer", "PROTOCOL_EC_PRODUCER",
    "services_cache_create_singleton", "services_cache_delete"
]

_VERSION = 0

SERVICE_TYPE_EC_CONSUMER = "ec_consumer_test"
PROTOCOL_EC_CONSUMER =  \
    f"{SERVICE_PROTOCOL_AIKO}/{SERVICE_TYPE_EC_CONSUMER}:{_VERSION}"

SERVICE_TYPE_EC_PRODUCER = "ec_producer_test"
PROTOCOL_EC_PRODUCER =  \
    f"{SERVICE_PROTOCOL_AIKO}/{SERVICE_TYPE_EC_PRODUCER}:{_VERSION}"

_LEASE_TIME = 300  # seconds

_AIKO_LOG_LEVEL_SHARE = os.environ.get("AIKO_LOG_LEVEL_SHARE", "INFO")
_LOGGER = aiko.logger(__name__, log_level=_AIKO_LOG_LEVEL_SHARE)

# --------------------------------------------------------------------------- #

def _ec_modify_item(items, item_path, modify_operation, create_path=False):
    if not isinstance(items, dict):
        item_type = type(items).__name__
        raise ValueError(f'"items" must be a dictionary, not {item_type}')
    if not isinstance(item_path, list):
        item_path_type = type(item_path).__name__
        raise ValueError(f'"item_path" must be a list, not {item_path_type}')
    if len(item_path) == 0:
        raise ValueError('"item_path" must be non-empty')

    item_key, *item_path_tail = item_path
    if len(item_path_tail) == 0:
        modify_operation(items, item_key)
    else:
        if item_key in items:
            nested_items = items[item_key]
            _ec_modify_item(nested_items, item_path_tail, modify_operation)
        elif create_path:
            nested_items = {}
            items[item_key] = nested_items
            _ec_modify_item(nested_items, item_path_tail, modify_operation)

def _ec_parse_item_path(name):
   item_path = name.split(".")
   if len(item_path) > 2:
       raise ValueError(f'EC "share" dictionary depth maximum is 2: {name}')
   return item_path

def _ec_remove_item(share, item_path):
    def remove_item(items, item_key):
        if item_key in items:
            del items[item_key]
    _ec_modify_item(share, item_path, remove_item)

def _ec_update_item(share, item_path, item_value):
    def update_item(items, item_key):
        items[item_key] = item_value
    _ec_modify_item(share, item_path, update_item, create_path=True)

def _flatten_dictionary(dictionary):
    result = []
    for item_name, item in dictionary.items():
        if isinstance(item, dict):
            for subitem_name, subitem in item.items():
                name = f"{item_name}.{subitem_name}"
                result.append((name, subitem))
        else:
            result.append((item_name, item))
    return result

# --------------------------------------------------------------------------- #

class ECLease(Lease):
    def __init__(
        self, lease_time, topic, filter=None, lease_expired_handler=None):

        super().__init__(
            lease_time, topic, lease_expired_handler=lease_expired_handler)
        self.filter = filter

class ECProducer:
    def __init__(self, service, share, topic_in=None, topic_out=None):
        self.share = share
        self.topic_in = topic_in if topic_in else service.topic_control
        self.topic_out = topic_out if topic_out else service.topic_state
        self.handlers = set()
        self.leases = {}
        service.add_message_handler(self._producer_handler, self.topic_in)
        service.add_tags(["ec=true"])

    def add_handler(self, handler):
        for item_name, item_value in _flatten_dictionary(self.share):
            handler("add", item_name, item_value)
        self.handlers.add(handler)

    def get(self, item_name):
        success = True
        item_path = _ec_parse_item_path(item_name)
        item = self.share
        for key in item_path:
            if isinstance(item, dict) and key in item:
                item = item.get(key)
            else:
                success = False
        if not success:
            item = None
        return item

    def update(self, item_name, item_value):
        item_path = _ec_parse_item_path(item_name)
        success = False
        try:
            _ec_update_item(self.share, item_path, item_value)
            success = True
        except ValueError as value_error:
            diagnostic = f'update {item_name}: {value_error}'
            _LOGGER.error(f"update(): {diagnostic}")
        if success:
            self._update_consumers("update", item_name, item_value)

    def remove(self, item_name):
        item_path = _ec_parse_item_path(item_name)
        success = False
        try:
            _ec_remove_item(self.share, item_path)
            success = True
        except ValueError as value_error:
            diagnostic = f'remove {item_name}: {value_error}'
            _LOGGER.error(f"remove(): {diagnostic}")
        if success:
            self._update_consumers("remove", item_name, None)

    def remove_handler(self, handler):
        if handler in self.handlers:
            self.handlers.remove(handler)

    def _dictionary_to_commands(self, command, dictionary):
        payloads = []
        for name, subitem in _flatten_dictionary(dictionary):
            payloads.append(generate(command, [name, subitem]))
        return payloads

    def _ec_parse_share(self, command, parameters):
        response_topic = None
        lease_time = None
        filter = []

        if command == "share" and len(parameters) == 3:
            try:
                lease_time = int(parameters[1])
            except Exception:
                pass
            if isinstance(lease_time, int):
                filter = parameters[2]
                if filter != "*" and not isinstance(filter, list):
                    filter = [filter]
                response_topic = parameters[0]  # Deliberately do this last

        return response_topic, lease_time, filter

    def _filter_compare(self, filter, item_name):
        match = False
        if filter == "*":
            match = True
        else:
            for filter_item in filter:
                if item_name == filter_item or \
                   item_name.startswith(f"{filter_item}."):
                    match = True
        return match

    def _lease_expired_handler(self, topic):
        if topic in self.leases:
            del self.leases[topic]

    def _producer_handler(self, aiko, topic, payload_in):
        command, parameters = parse(payload_in)
        payload_out = payload_in

        if (command == "add" or command == "update") and len(parameters) == 2:
            item_name = parameters[0]
            item_value = parameters[1]
            item_path = _ec_parse_item_path(item_name)

            success = False
            try:
                _ec_update_item(self.share, item_path, item_value)
                success = True
            except ValueError as value_error:
                diagnostic = f'command "{command}", {parameters}: {value_error}'
                _LOGGER.error(f"_producer_hander(): {diagnostic}")
            if success:
                aiko.message.publish(self.topic_out, payload_out)
                self._update_consumers(command, item_name, item_value)

        if command == "remove" and len(parameters) == 1:
            item_name = parameters[0]
            item_path = _ec_parse_item_path(item_name)

            success = False
            try:
                _ec_remove_item(self.share, item_path)
                success = True
            except ValueError as value_error:
                diagnostic = f'command "{command}", {parameters}: {value_error}'
                _LOGGER.error(f"_producer_hander(): {diagnostic}")
            if success:
                aiko.message.publish(self.topic_out, payload_out)
                self._update_consumers(command, item_name, None)

        if command == "share":
            response_topic, lease_time, filter = self._ec_parse_share(
                command, parameters)
            if response_topic:
                if lease_time == 0:
                    if response_topic in self.leases:
                        self.leases[response_topic].terminate()
                        del self.leases[response_topic]
                    else:
                        self._synchronize(response_topic, filter)
                elif lease_time > 0:
                    if response_topic in self.leases:
                        self.leases[response_topic].extend(lease_time)
                    else:
                        lease = ECLease(
                            lease_time,
                            response_topic,
                            filter=filter,
                            lease_expired_handler=self._lease_expired_handler)
                        self.leases[response_topic] = lease
                        self._synchronize(response_topic, filter)

    def _filter_dictionary(self, dictionary, filter, path):
        share = {}
        for item_name, item in dictionary.items():
            item_path = path + [str(item_name)]
            if isinstance(item, dict):
                filtered_item = self._filter_dictionary(item, filter, item_path)
                if filtered_item != {}:
                    share[item_name] = filtered_item
            else:
                item_path_str = ".".join(item_path)
                if self._filter_compare(filter, item_path_str):
                    share[item_name] = item
        return share

    def _filter_share(self, filter):
        return self._filter_dictionary(self.share, filter, [])

    def _synchronize(self, response_topic, filter):
        filtered_share = self._filter_share(filter)
        commands = self._dictionary_to_commands("add", filtered_share)

        command_count = len(commands)
        payload_out = f"(item_count {command_count})"
        aiko.message.publish(response_topic, payload_out)
        for payload_out in commands:
            aiko.message.publish(response_topic, payload_out)

        payload_out = f"(sync {response_topic})"
        aiko.message.publish(self.topic_out, payload_out)

    def _update_consumers(self, command, item_name, item_value):
        for handler in self.handlers:
            handler(command, item_name, item_value)
        if command == "remove":
            payload_out = f"({command} {item_name})"
        else:
            # TODO: Use "generate()" on item_value
            payload_out = f"({command} {item_name} {item_value})"
        for lease in self.leases.values():
            if self._filter_compare(lease.filter, item_name):
                response_topic = lease.lease_uuid
                aiko.message.publish(response_topic, payload_out)

# --------------------------------------------------------------------------- #
# Note: For non-Service use, can substitute "aiko.process" for "service"

class ECConsumer:
    def __init__(self,
        service, ec_consumer_id, cache, ec_producer_topic_control, filter="*"):

        self.service = service
        self.ec_consumer_id = ec_consumer_id
        self.cache = cache
        self.ec_producer_topic_control = ec_producer_topic_control
        self.filter = filter

        self.cache_state = "empty"
        self.handlers = set()
        self.item_count = 0
        self.items_received = 0
        self.lease = None

        self.topic_share_in = \
            f"{self.service.topic_path}/{self.ec_producer_topic_control}/{self.ec_consumer_id}/in"
        self.service.add_message_handler(self._consumer_handler, self.topic_share_in)
        aiko.connection.add_handler(self._connection_state_handler)

    def add_handler(self, handler):
        for item_name, item_value in _flatten_dictionary(self.cache):
            handler(self.ec_consumer_id, "add", item_name, item_value)
        self.handlers.add(handler)

    def _consumer_handler(self, aiko, topic, payload_in):
        command, parameters = parse(payload_in)

        if command == "item_count" and len(parameters) == 1:
            self.item_count = parse_int(parameters[0])
            self.items_received = 0

        elif command == "add" and len(parameters) == 2:
            item_name = parameters[0]
            item_path = _ec_parse_item_path(item_name)
            item_value = parameters[1]
# TODO: Catch ValueError and provide better console log (see ECProducer)
            _ec_update_item(self.cache, item_path, item_value)
            self.items_received += 1
            if self.items_received == self.item_count:
                self.cache_state = "ready"
            self._update_handlers(command, item_name, item_value)

        elif command == "remove" and len(parameters) == 1:
            item_name = parameters[0]
            item_path = _ec_parse_item_path(item_name)
# TODO: Catch ValueError and provide better console log (see ECProducer)
            _ec_remove_item(self.cache, item_path)
            self._update_handlers(command, item_name, None)

        elif command == "update" and len(parameters) == 2:
            item_name = parameters[0]
            item_path = _ec_parse_item_path(item_name)
            item_value = parameters[1]
# TODO: Catch ValueError and provide better console log (see ECProducer)
            _ec_update_item(self.cache, item_path, item_value)
            self._update_handlers(command, item_name, item_value)
        elif command == "sync":
            #pass  # ECConsumer doesn't use the share "(sync ...)" command
            self._update_handlers(command, None, None)
        else:
            diagnostic = f"Unknown command: {command}, {parameters}"
            _LOGGER.debug(f"_consumer_handler(): {diagnostic}")

     #   for item_name, item in self.cache.items():
     #       _LOGGER.debug(f"ECConsumer cache {item_name}: {item}")
     #   _LOGGER.debug("----------------------------")

    def _connection_state_handler(self, connection, connection_state):
        if connection.is_connected(ConnectionState.REGISTRAR):
            if not self.lease:
                self.lease = Lease(
                    _LEASE_TIME, None, automatic_extend=True,
                    lease_extend_handler=self._share_request)
                self._share_request()

    def remove_handler(self, handler):
        if handler in self.handlers:
            self.handlers.remove(handler)

    def _share_request(self, lease_time=_LEASE_TIME, lease_uuid=None):
        aiko.message.publish(
            self.ec_producer_topic_control,
            f"(share {self.topic_share_in} {lease_time} {self.filter})"
        )

    def _update_handlers(self, command, item_name, item_value):
        for handler in self.handlers:
            handler(self.ec_consumer_id, command, item_name, item_value)

    def terminate(self):
        self.service.remove_message_handler(
            self._consumer_handler, self.topic_share_in)
        aiko.connection.remove_handler(self._connection_state_handler)
        self.cache = {}
        self.cache_state = "empty"

        if self.lease:
            self.lease.terminate()
            self.lease = None
            self._share_request(lease_time=0)  # cancel share request

# --------------------------------------------------------------------------- #
# Note: For use by non-Service, can substitute "aiko.process" for "service"
#
# Service cache states
# ~~~~~~~~~~~~~~~~~~~~
# - empty:   No history or running Services and waiting for Service Registrar
# - history: Waiting for Services history to be shared
# - share:   Waiting for Services running to be shared
# - loaded:  Services populated and waiting for Service Registrar "sync" message
# - ready:   Ready for use and continuously updating
#
# To Do
# ~~~~~
# - Reimplement ServicesCache using ECProducer / ECConsumer
# - aiko_services.registrar should have identical code to the cache code !
# - services_cache_delete() should be a class method delete()

from collections import deque
from threading import Thread
import time

_HISTORY_RING_BUFFER_SIZE = 4096

class ServicesCache():
    def __init__(self, service, event_loop_start=False, history_limit=0):
        self._service = service
        self._event_loop_start = event_loop_start
        self._event_loop_owner = False
        self._history_limit = history_limit

        self._cache_reset()
        self._handlers = set()
        self._history = deque(maxlen=_HISTORY_RING_BUFFER_SIZE)
        self._registrar_topic_share = f"{service.topic_path}/registrar_share"
        aiko.connection.add_handler(self._connection_state_handler)

    def _cache_reset(self):
        self._begin_registration = False
        self._item_count = None
        self._registrar_service = None
        self._registrar_topic_in = None
        self._registrar_topic_out = None
        self._services = Services()
        self._state = "empty"

    def add_handler(self, service_change_handler, service_filter):
        if self._state in ["loaded", "ready"]:
        # TODO: Provide filtered Services to "service_change_handler"
            service_change_handler("sync", None)
        self._handlers.add((service_change_handler, service_filter))

    def remove_handler(self, service_change_handler, service_filter):
        if (service_change_handler, service_filter) in self._handlers:
            self._handlers.remove((service_change_handler, service_filter))

    def _connection_state_handler(self, connection, connection_state):
        if connection.is_connected(ConnectionState.REGISTRAR):
            if not self._begin_registration:
                self._begin_registration = True
                self._registrar_topic_in = f"{aiko.registrar['topic_path']}/in"
                self._registrar_topic_out = f"{aiko.registrar['topic_path']}/out"
                self._service.add_message_handler(
                    self.registrar_out_handler, self._registrar_topic_out
                )
                self._service.add_message_handler(
                    self.registrar_share_handler, self._registrar_topic_share
                )
                if self._history_limit > 0:
                    self._publish_registrar_history()
                    self._state = "history"
                else:
                    self._publish_registrar_share()
                    self._state = "share"
        else:
            if self._registrar_topic_out:
                self._service.remove_message_handler(
                    self.registrar_out_handler, self._registrar_topic_out
                )
                self._service.remove_message_handler(
                    self.registrar_share_handler, self._registrar_topic_share
                )
                if self._registrar_service:
                    self._history.appendleft(self._registrar_service)
                self._cache_reset()

    def _publish_registrar_history(self):
        aiko.message.publish(
            self._registrar_topic_in,
            f"(history {self._registrar_topic_share} {self._history_limit})"
        )

    def _publish_registrar_share(self):
        aiko.message.publish(
            self._registrar_topic_in,
            f"(share {self._registrar_topic_share} * * * * *)"
        )

    def _update_handlers(self, command, service_details=None):
        topic_path = service_details[0] if service_details else None
        for handler, filter in self._handlers:
            if topic_path:
                services = self._services.filter_services(filter)
                service = services.get_service(topic_path)
            else:
                service = True
            if service:
                handler(command, service_details)

    def get_history(self):
        return self._history

    def get_services(self):
        return self._services

    def get_state(self):
        return self._state

    def registrar_share_handler(self, aiko, topic_path, payload_in):
        command, parameters = parse(payload_in)
        if command == "item_count" and len(parameters) == 1:
            self._item_count = int(parameters[0])
        elif command == "add" and len(parameters) >= 6:
            if self._item_count is None:
                _LOGGER.error("Service cache: registrar_share_handler(): "
                    "(item_count N) was incorrect")
                return
            self._item_count -= 1
            service_details = parameters
            if self._state == "history":
                self._history.append(service_details)
            elif self._state == "share":
                service_topic_path = service_details[0]
                self._services.add_service(service_topic_path, service_details)
                if service_topic_path == aiko.registrar["topic_path"]:
                    self._registrar_service = service_details
        else:
            _LOGGER.debug(f"Service cache: registrar_share_handler(): Unhandled message topic: {topic_path}, payload: {payload_in}")

        if self._item_count == 0:
            self._item_count = None
            if self._state == "history":
                self._publish_registrar_share()
                self._state = "share"
            elif self._state == "share":
                self._state = "loaded"
                self._update_handlers("sync")
                for service_details in self._services:
                    self._update_handlers("add", service_details)

    def registrar_out_handler(self, aiko, topic, payload_in):
        command, parameters = parse(payload_in)
        if command == "sync" and len(parameters) == 1:
            sync_topic = parameters[0]
            if sync_topic == self._registrar_topic_share and self._state == "loaded":
                self._state = "ready"
        elif command == "add" and len(parameters) == 6:
            service_details = parameters
            self._services.add_service(service_details[0], service_details)
            self._update_handlers(command, service_details)
        elif command == "remove":
            topic_path = parameters[0]
            service_details = self._services.get_service(topic_path)
            if service_details:
                self._update_handlers(command, service_details)
                self._services.remove_service(topic_path)
                self._history.appendleft(service_details)
        else:
            _LOGGER.debug(f"Service cache: registrar_out_handler(): Unknown command: topic: {topic}, payload: {payload_in}")

    def run(self):
        if self._event_loop_start and not event.event_loop_running:
            self._event_loop_owner = True
            diagnostic = None
            try:
                aiko.process.run()
            except SystemError:
                diagnostic = "Error: MQTT Connection Reset: Incorrect configuration or security credentials ?"
            if diagnostic:
                _LOGGER.error(diagnostic)
                raise ValueError(diagnostic)  # TODO: Provide stack trackback ?

    def terminate(self):
        if self._event_loop_owner:
            aiko.process.terminate()

    def wait_ready(self):
        while self._state != "ready":
            time.sleep(0.1)

services_cache = None

def services_cache_create_singleton(
    service, event_loop_start=False, history_limit=0):

    global services_cache

    if not services_cache:
        services_cache = ServicesCache(service, event_loop_start, history_limit)
        Thread(target=services_cache.run).start()
    return services_cache

def services_cache_delete():
    global services_cache

    if services_cache:
        services_cache.terminate()
        services_cache = None

# --------------------------------------------------------------------------- #

class ECProducerTest(Service):
    def __init__(self, context):
        context.get_implementation("Service").__init__(self, context)
        _LOGGER.info(f"ECProducer: topic path: {self.topic_path}")

        self.share = {
            "lifecycle": "ready",
            "log_level": get_log_level_name(_LOGGER),
            "source_file": f"v{_VERSION}⇒ {__file__}",
            "items": {
                "key_1": ["item_1a", "item_1b"],
                "key_2": ["item_2a", "item_2b"]
            }
        }
        self.ec_producer = ECProducer(self, self.share)
        self.ec_producer.add_handler(self._ec_producer_change_handler)

    def _ec_producer_change_handler(self, command, item_name, item_value):
        _LOGGER.info(f"ECProducer: {command} {item_name} {item_value}")
        if item_name == "log_level":
            _LOGGER.setLevel(str(item_value).upper())

# --------------------------------------------------------------------------- #

class ECConsumerTest(Service):
    def __init__(self, context, ec_producer_pid, ec_producer_sid, filter):
        context.get_implementation("Service").__init__(self, context)
        _LOGGER.info(f"ECConsumer: topic path: {self.topic_path}")

        self.share_producer = {
            "lifecycle": "ready",
            "log_level": get_log_level_name(_LOGGER),
            "source_file": f"v{_VERSION}⇒ {__file__}",
            "ec_producer_pid": ec_producer_pid,
            "ec_producer_sid": ec_producer_sid
        }
        self.ec_producer = ECProducer(self, self.share_producer)

        self.share_consumer = {}
        ec_producer_topic_control =  \
            f"{get_namespace()}/{get_hostname()}/{ec_producer_pid}/{ec_producer_sid}/control"
        self.ec_consumer = ECConsumer(
            self, 0, self.share_consumer, ec_producer_topic_control, filter)
        self.ec_consumer.add_handler(self._ec_consumer_change_handler)

    def _ec_consumer_change_handler(
        self, client_id, command, item_name, item_value):
        _LOGGER.info(
            f"ECConsumer: {client_id}: {command} {item_name} {item_value}")

# --------------------------------------------------------------------------- #

@click.group()

def main():
    pass

@main.command("sc_test",
    help=("Test Registrar Services Cache"))

def sc_test():
    services_cache = services_cache_create_singleton(
        aiko.process, True, history_limit=4)

    _LOGGER.info("ServicesCache: Wait ready")
    services_cache.wait_ready()

    _LOGGER.info("ServicesCache: Services running")
    services = services_cache.get_services()
    for service_details in services:
        _LOGGER.info(f"{service_details}")

    _LOGGER.info("ServicesCache: Service history")
    history = services_cache.get_history()
    for service_details in history:
        _LOGGER.info(f"{service_details}")

    aiko.process.terminate()

@main.command("ec_test",
    help=("Test Eventual Consistency Producer and Consumer"))
@click.argument("ec_producer_pid", nargs=1, required=False)
@click.argument("ec_producer_sid", nargs=1, required=False, default="1")
@click.argument("filter", nargs=1, default="*", required=False)

def ec_test(ec_producer_pid, ec_producer_sid, filter):
    tags = ["ec=true"]  # TODO: Add ECProducer tag before add to Registrar

    if ec_producer_pid:
        init_args = service_args(
            SERVICE_TYPE_EC_CONSUMER, None, None, PROTOCOL_EC_CONSUMER, tags)
        init_args["ec_producer_pid"] = ec_producer_pid
        init_args["ec_producer_sid"] = ec_producer_sid
        init_args["filter"] = filter
        ec_consumer_test = compose_instance(ECConsumerTest, init_args)
    else:
        init_args = service_args(
            SERVICE_TYPE_EC_PRODUCER, None, None, PROTOCOL_EC_PRODUCER, tags)
        ec_producer_test = compose_instance(ECProducerTest, init_args)

    aiko.process.run(True)

if __name__ == "__main__":
    main()

# --------------------------------------------------------------------------- #
