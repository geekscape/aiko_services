#!/usr/bin/env python3
#
# Usage
# ~~~~~
# LOG_LEVEL=DEBUG registrar
# LOG_LEVEL=DEBUG ./share.py
# LOG_LEVEL=DEBUG ./share.py ec_producer_pid
#
# mosquitto_sub -t '#' -v
#
# NAMESPACE=aiko
# HOST=localhost
# PID=`ps ax | grep python | grep share.py | xargs | cut -d" " -f1`;  \
#     TOPIC_PATH=$NAMESPACE/$HOST/$PID
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
# - BUG: Provide filtered Services to "service_change_handler"
# - BUG?: ECProducer remote expired leases
# - BUG?: ECConsumer remote expired leases
#
# - ECProducerBase class provides absolute minimum implementation
#   - Responds to all "(share ...)" requests with "(item_count 0)"
#     Ignores all other requests
#   - ECProducer extends ECProducerBase
#
# - For multiple Actors in same process, when each Actor wants to have a
#   its own unique ECProducer shared amongst different aspects of the Actor,
#   e.g LifeCycleClient and some other functionality, then the ECProducer
#   constructor optionally includes the "actor_name" to disambigute
#
# - Provide unit tests !
# - Registrar should migrate use of ServiceCache to ECProducer
# - ECProducer and ECConsumer should handle Registrar not available
# - ECProducer and ECConsumer should handle Registrar stop and restart
# - Allow ECConsumer to change share filter, with or without existing lease
# - Fix ECConsumer to handle _ec_remove_item()/_ec_update_item() exceptions
# - Improve EC state/cache to work recursively beyond just two levels
# - When subscribed to a component of a dictionary, removal of the dictionary
#   does not send a remove message for the component

import click

from aiko_services import *
from aiko_services.utilities import *

__all__ = [
    "ECConsumer", "PROTOCOL_EC_CONSUMER",
    "ECProducer", "PROTOCOL_EC_PRODUCER",
    "ServiceFilter",
    "filter_services", "filter_services_by_actor_names",
    "filter_services_by_attributes", "filter_services_by_topic_paths",
    "service_cache_create_singleton", "service_cache_delete"
]

PROTOCOL_EC_CONSUMER = f"{AIKO_PROTOCOL_PREFIX}/ec_consumer:0"
PROTOCOL_EC_PRODUCER = f"{AIKO_PROTOCOL_PREFIX}/ec_producer:0"

_LEASE_TIME = 300  # seconds
_LOGGER = aiko.logger(__name__)

# --------------------------------------------------------------------------- #

class ServiceFilter:
    def __init__(self, topic_paths, protocol, transport, owner, tags):
        self.topic_paths = topic_paths
        self.protocol = protocol
        self.transport = transport
        self.owner = owner
        self.tags = tags

def filter_services(services_in, filter):
    services = filter_services_by_topic_paths(services_in, filter.topic_paths)
    services = filter_services_by_attributes(services, filter)
    return services

def filter_services_by_actor_names(services_in, actor_names):
    actors = {}
    for actor_name in actor_names:
        actor_topic = ".".join(actor_name.split(".")[:-1])  # WIP: Actor name
        if actor_topic in services_in.keys():
            service = services_in[actor_topic]
            match_tag = f"actor={actor_name}"
            if aiko.match_tags(service[4], [match_tag]):
                actors[actor_name] = service
    return actors

# TODO: Make this a more general "filter" that is compatible with
#       "aiko_services/share.py:_filter_compare()" and keep them together
# TODO: Note this code is copied from "aiko_services/registrar.py"
#       The registrar should also use general filters

def filter_services_by_attributes(services_in, filter):
    services = {}
    for service_topic, service_details in services_in.items():
        matches = True
        if filter.protocol != "*":
            if filter.protocol != service_details[1]:
                matches = False
        if filter.transport != "*":
            if filter.transport != service_details[2]:
                matches = False
        if filter.owner != "*":
            if filter.owner != service_details[3]:
                matches = False
        if filter.tags != "*":
            if not aiko.match_tags(service_details[4], filter.tags):
                matches = False
        if matches:
            services[service_topic] = service_details
    return services

def filter_services_by_topic_paths(services_in, topic_paths):
    services = {}
    if topic_paths == "*":
        services = services_in
    else:
        for topic_path in topic_paths:
            if topic_path in services_in.keys():
                services[topic_path] = services_in[topic_path]
    return services

def _update_handlers(handlers, command, service_details=None):
    topic_path = service_details[0] if service_details else None
    for handler, filter in handlers:
        if topic_path:
            services = filter_services({topic_path: service_details}, filter)
            service = services.get(service_details[0])
        else:
            service = True
        if service:
            handler(command, service_details)

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
       raise ValueError(f'EC "state" dictionary depth maximum is 2: {name}')
   return item_path

def _ec_remove_item(state, item_path):
    def remove_item(items, item_key):
        if item_key in items:
            del items[item_key]
    _ec_modify_item(state, item_path, remove_item)

def _ec_update_item(state, item_path, item_value):
    def update_item(items, item_key):
        items[item_key] = item_value
    _ec_modify_item(state, item_path, update_item, create_path=True)

def _flatten_dictionary(dictionary):
    result = []
    for item_name, item in dictionary.items():
        if type(item) != dict:
            result.append((item_name, item))
        else:
            for subitem_name, subitem in item.items():
                name = f"{item_name}.{subitem_name}"
                result.append((name, subitem))
    return result

# --------------------------------------------------------------------------- #

class ECLease(Lease):
    def __init__(
        self, lease_time, topic, filter=None, lease_expired_handler=None):

        super().__init__(
            lease_time, topic, lease_expired_handler=lease_expired_handler)
        self.filter = filter

class ECProducer:
    def __init__(
        self,
        state,
        topic_in=aiko.public.topic_control,  # aiko.public.topic_in
        topic_out=aiko.public.topic_state,   # aiko.public.topic_out
        actor_name=None):                    # optional for specific Actor

        self.state = state
        self.topic_in = topic_in
        self.topic_out = topic_out
        self.handlers = set()
        self.leases = {}
        aiko.add_message_handler(self._producer_handler, topic_in)
        aiko.add_tags(["ecproducer=true"])

    def add_handler(self, handler):  # TODO: Implement remove_handler()
        for item_name, item_value in _flatten_dictionary(self.state):
            handler("add", item_name, item_value)
        self.handlers.add(handler)

    def get(self, item_name):
        success = True
        item_path = _ec_parse_item_path(item_name)
        item = self.state
        for key in item_path:
            if type(item) == dict and key in item:
                item = item.get(key)
            else:
                success = False
        if not success:
            raise ValueError(f"Item not found: {item_name}")
        return item

    def update(self, item_name, item_value):
        item_path = _ec_parse_item_path(item_name)
        success = False
        try:
            _ec_update_item(self.state, item_path, item_value)
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
            _ec_remove_item(self.state, item_path)
            success = True
        except ValueError as value_error:
            diagnostic = f'remove {item_name}: {value_error}'
            _LOGGER.error(f"remove(): {diagnostic}")
        if success:
            self._update_consumers("remove", item_name, None)

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
            if type(lease_time) == int:
                filter = parameters[2]
                if filter != "*" and type(filter) != list:
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
                _ec_update_item(self.state, item_path, item_value)
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
                _ec_remove_item(self.state, item_path)
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
        state = {}
        for item_name, item in dictionary.items():
            item_path = path + [str(item_name)]
            if type(item) != dict:
                item_path_str = ".".join(item_path)
                if self._filter_compare(filter, item_path_str):
                    state[item_name] = item
            else:
                filtered_item = self._filter_dictionary(item, filter, item_path)
                if filtered_item != {}:
                    state[item_name] = filtered_item
        return state

    def _filter_state(self, filter):
        return self._filter_dictionary(self.state, filter, [])

    def _synchronize(self, response_topic, filter):
        filtered_state = self._filter_state(filter)
        commands = self._dictionary_to_commands("add", filtered_state)

        command_count = len(commands)
        payload_out = f"(item_count {command_count})"
        aiko.public.message.publish(response_topic, payload=payload_out)
        for payload_out in commands:
            aiko.public.message.publish(response_topic, payload=payload_out)

        payload_out = f"(sync {response_topic})"
        aiko.public.message.publish(self.topic_out, payload_out)

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
                aiko.public.message.publish(response_topic, payload_out)

# --------------------------------------------------------------------------- #

class ECConsumer:
    def __init__(self, ec_consumer_id, cache, ec_producer_topic_control, filter="*"):
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
            f"{aiko.public.topic_path}/{self.ec_producer_topic_control}/{ec_consumer_id}/in"
        aiko.add_message_handler(self._consumer_handler, self.topic_share_in)
        aiko.public.connection.add_handler(self._connection_state_handler)

    def add_handler(self, handler):  # TODO: Implement remove_handler()
        for item_name, item_value in _flatten_dictionary(self.cache):
            handler(self.ec_consumer_id, "add", item_name, item_value)
        self.handlers.add(handler)

    def _consumer_handler(self, aiko, topic, payload_in):
        command, parameters = parse(payload_in)

        if command == "item_count" and len(parameters) == 1:
            self.item_count = int(parameters[0])
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

    def _share_request(self, lease_time=_LEASE_TIME, lease_uuid=None):
        aiko.public.message.publish(
            self.ec_producer_topic_control,
            f"(share {self.topic_share_in} {lease_time} {self.filter})"
        )

    def _update_handlers(self, command, item_name, item_value):
        for handler in self.handlers:
            handler(self.ec_consumer_id, command, item_name, item_value)

    def terminate(self):
        aiko.remove_message_handler(self._consumer_handler,self.topic_share_in)
        aiko.public.connection.remove_handler(self._connection_state_handler)
        self.cache = {}
        self.cache_state = "empty"

        if self.lease:
            self.lease.terminate()
            self.lease = None
            self._share_request(lease_time=0)  # cancel share request

# --------------------------------------------------------------------------- #
# Service cache states
# ~~~~~~~~~~~~~~~~~~~~
# - empty:  Unpopulated and waiting for Service Registrar
# - loaded: Populated and waiting for Service Registrar "sync" message
# - live:  Ready for use and continuously updating
#
# To Do
# ~~~~~
# - service_cache_delete() should be a class method delete()
# - aiko_services.registrar should have identical code to the cache code !

from threading import Thread
import time

_REGISTRAR_TOPIC_QUERY = aiko.public.topic_path + "/registrar_query"

class ServiceCache():
    def __init__(self, event_loop_start=False):
        self._event_loop_start = event_loop_start
        self._event_loop_owner = False
        self._cache_reset()
        self._handlers = set()
        self._registrar_topic_out = None
        aiko.public.connection.add_handler(self._connection_state_handler)

    def add_handler(self, service_change_handler, service_filter):
        if self._state in ["loaded", "live"]:
        # TODO: Provide filtered Services to "service_change_handler"
            service_change_handler("sync", None)
        self._handlers.add((service_change_handler, service_filter))

    def remove_handler(self, service_change_handler, service_filter):
        self._handlers.remove((service_change_handler, service_filter))

    def _cache_reset(self):
        self._query_items_expected = 0
        self._query_items_received = 0
        self._registrar_topic_out = None
        self._services = {}
        self._state = "empty"

    def _connection_state_handler(self, connection, connection_state):
        if connection.is_connected(ConnectionState.REGISTRAR):
            self._registrar_topic_out =  \
                aiko.public.topic_path_registrar + "/out"
            aiko.add_message_handler(
                self.registrar_out_handler, self._registrar_topic_out
            )
            aiko.add_message_handler(
                self.registrar_query_handler, _REGISTRAR_TOPIC_QUERY
            )
            aiko.public.message.publish(
                aiko.public.topic_path_registrar + "/in",
                f"(query {_REGISTRAR_TOPIC_QUERY} * * * *)"
            )
        else:
            if self._registrar_topic_out:
                aiko.remove_message_handler(
                    self.registrar_out_handler, self._registrar_topic_out
                )
                aiko.remove_message_handler(
                    self.registrar_query_handler, _REGISTRAR_TOPIC_QUERY
                )
                self._cache_reset()

    def get_services(self):
        return self._services

    def get_services_topics(self):
        return list(self._services.keys())

    def get_state(self):
        return self._state

    def registrar_query_handler(self, aiko, topic, payload_in):
        command, parameters = parse(payload_in)
        if command == "item_count" and len(parameters) == 1:
            self._query_items_expected = int(parameters[0])
        elif command == "add" and len(parameters) == 5:
            service_details = parameters
            self._services[service_details[0]] = service_details
            self._query_items_received += 1
            if self._query_items_received == self._query_items_expected:
                self._state = "loaded"
                _update_handlers(self._handlers, "sync")
                for service_details in self._services.values():
                    _update_handlers(self._handlers, "add", service_details)
        else:
            _LOGGER.debug(f"Service cache: registrar_query_handler(): Unhandled message topic: {topic}, payload: {payload_in}")

    def registrar_out_handler(self, aiko, topic, payload_in):
        command, parameters = parse(payload_in)
        if command == "sync" and len(parameters) == 1:
            sync_topic = parameters[0]
            if sync_topic == _REGISTRAR_TOPIC_QUERY and self._state == "loaded":
                self._state = "live"
        elif command == "add" and len(parameters) == 5:
            service_details = parameters
            self._services[service_details[0]] = service_details
            _update_handlers(self._handlers, command, service_details)
        elif command == "remove":
            topic = parameters[0]
            if topic in self._services:
                service_details = self._services[topic]
                _update_handlers(self._handlers, command, service_details)
                del self._services[topic]
        else:
            _LOGGER.debug(f"Service cache: registrar_out_handler(): Unknown command: topic: {topic}, payload: {payload_in}")

    def run(self):
        if self._event_loop_start and not event.event_loop_running:
            self._event_loop_owner = True
            aiko.process()

    def terminate(self):
        if self._event_loop_owner:
            event.terminate()

    def wait_live(self):
        while self._state != "live":
            time.sleep(1)

service_cache = None

def service_cache_create_singleton(event_loop_start=False):
    global service_cache

    if not service_cache:
        service_cache = ServiceCache(event_loop_start)
        Thread(target=service_cache.run).start()
    return service_cache

def service_cache_delete():
    global service_cache

    if service_cache:
        service_cache.terminate()
        service_cache = None

# if __name__ == "__main__":
#     service_cache = service_cache_create_singleton()
#     service_cache.wait_live()

# --------------------------------------------------------------------------- #

def _create_ec_consumer(ec_producer_pid, filter="*"):
    state = {}
    ec_producer_topic_control = f"{get_namespace()}/{get_hostname()}/{ec_producer_pid}/control"

    aiko.set_protocol(PROTOCOL_EC_CONSUMER)
    ec_consumer = ECConsumer(state, ec_producer_topic_control, filter)

def _create_ec_producer():
    state = {
        "lifecycle": "initialize",
        "services": {
            "topic_1": ["topic_1", "protocol_1", "transport", "owner_1", []],
            "topic_2": ["topic_2", "protocol_2", "transport", "owner_2", []]
        }
    }

    aiko.set_protocol(PROTOCOL_EC_PRODUCER)
    ec_producer = ECProducer(state)

@click.command("main", help=(
    "Demonstrate Eventual Consistency ECProducer and ECConsumer"))
@click.argument("ec_producer_pid", nargs=1, required=False)
@click.argument("filter", nargs=1, default="*", required=False)
def main(ec_producer_pid, filter):
    if ec_producer_pid:
        _create_ec_consumer(ec_producer_pid, filter)
    else:
        _create_ec_producer()

    aiko.process(True)

if __name__ == "__main__":
    main()

# --------------------------------------------------------------------------- #
