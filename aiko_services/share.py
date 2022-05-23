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
# mosquitto_pub -t $TOPIC_PATH/control -m "(stream)"
# mosquitto_pub -t $TOPIC_PATH/control -m "(stream topic)"
# mosquitto_pub -t $TOPIC_PATH/control -m "(stream topic 0)"
# mosquitto_pub -t $TOPIC_PATH/control -m "(stream topic a *)"
# mosquitto_pub -t $TOPIC_PATH/control -m "(stream topic 0 *)"
# mosquitto_pub -t $TOPIC_PATH/control -m "(stream topic 0 lifecycle)"
# mosquitto_pub -t $TOPIC_PATH/control -m "(stream topic 0 services)"
# mosquitto_pub -t $TOPIC_PATH/control -m "(stream topic 0 x)"
# mosquitto_pub -t $TOPIC_PATH/control -m "(stream topic 0 (lifecycle))"
# mosquitto_pub -t $TOPIC_PATH/control -m "(stream topic 0 (lifecycle x))"
# mosquitto_pub -t $TOPIC_PATH/control -m "(add count 0)"
# mosquitto_pub -t $TOPIC_PATH/control -m "(update count 1)"
# mosquitto_pub -t $TOPIC_PATH/control -m "(remove count)"
# mosquitto_pub -t $TOPIC_PATH/control -m "(update lifecycle ready)"
# mosquitto_pub -t $TOPIC_PATH/control -m "(add services.test 0)"
# mosquitto_pub -t $TOPIC_PATH/control -m "(remove services)"
#
# To Do
# ~~~~~
# - ECProducerBase class provides absolute minimum implementation
#   - Responds to all "(stream ...)" requests with "(item_count 0)"
#     Ignores all other requests
#   - ECProducer extends EXProducerBase
#
# - Provide unit tests !
# - Registrar should migrate use of ServiceCache to ECProducer
# - ECProducer and ECConsumer should handle Registrar not available
# - ECProducer and ECConsumer should handle Registrar stop and restart
# - Allow ECConsumer to change stream filter, with or without existing lease
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
    "service_cache_create_singleton", "service_cache_delete"
]

PROTOCOL_EC_CONSUMER = f"{AIKO_PROTOCOL_PREFIX}/ec_consumer:0"
PROTOCOL_EC_PRODUCER = f"{AIKO_PROTOCOL_PREFIX}/ec_producer:0"

_LEASE_TIME = 300  # seconds
_LOGGER = aiko.logger(__name__)

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
        topic_out=aiko.public.topic_state):  # aiko.public.topic_out

        self.state = state
        self.topic_in = topic_in
        self.topic_out = topic_out
        self.leases = {}
        aiko.add_message_handler(self._producer_handler, topic_in)
        aiko.add_tags(["ecproducer=true"])

    def _ec_parse_stream(self, command, parameters):
        response_topic = None
        lease_time = None
        filter = []

        if command == "stream" and len(parameters) == 3:
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
            item_path = _ec_parse_item_path(item_name)
            item_value = parameters[1]

            success = False
            try:
                _ec_update_item(self.state, item_path, item_value)
                success = True
            except ValueError as value_error:
                diagnostic = f'command "{command}", {parameters}: {value_error}'
                _LOGGER.error(f"_producer_hander(): {diagnostic}")
            if success:
                aiko.message.publish(self.topic_out, payload_out)
                self._update_consumers(item_name, payload_out)

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
                self._update_consumers(item_name, payload_out)

        if command == "stream":
            response_topic, lease_time, filter = self._ec_parse_stream(
                command, parameters)
            if response_topic:
                if lease_time == 0:
                    if response_topic in self.leases:
                        lease = self.leases[response_topic]
                        lease.terminate()
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

    def _filter_dict(self, dictionary, filter, path):
        filtered_state = {}
        for item_name, item in dictionary.items():
            item_path = path + [str(item_name)]
            if type(item) != dict:
                item_path_str = ".".join(item_path)
                if self._filter_compare(filter, item_path_str):
                    filtered_state[item_name] = item
            else:
                filtered_item = self._filter_dict(item, filter, item_path)
                if filtered_item != {}:
                    filtered_state[item_name] = filtered_item
        return filtered_state

    def _filter_state(self, filter):
        return self._filter_dict(self.state, filter, [])

    def _dict_to_commands(self, dictionary):
        commands = []
        for item_name, item in dictionary.items():
            if type(item) != dict:
                commands.append(f"(add {item_name} {item})")
            else:
                for subitem_name, subitem in item.items():
                    name = f"{item_name}.{subitem_name}"
                    commands.append(generate("add", [name, subitem]))
        return commands

    def _synchronize(self, response_topic, filter):
        filtered_state = self._filter_state(filter)
        items = self._dict_to_commands(filtered_state)

        item_count = len(items)
        payload_out = f"(item_count {item_count})"
        aiko.public.message.publish(response_topic, payload=payload_out)
        for item in items:
            aiko.public.message.publish(response_topic, payload=item)

        payload_out = f"(sync {response_topic})"
        aiko.public.message.publish(self.topic_out, payload_out)

    def _update_consumers(self, item_name, payload_out):
        for lease in self.leases.values():
            if self._filter_compare(lease.filter, item_name):
                response_topic = lease.lease_uuid
                aiko.public.message.publish(response_topic, payload_out)

# --------------------------------------------------------------------------- #

class ECConsumer:
    def __init__(self, cache, topic_in, filter="*"):
        self.cache = cache
        self.topic_in = topic_in
        self.filter = filter

        self.cache_state = "empty"
        self.item_count = 0
        self.items_received = 0
        self.lease = None

        self.topic_stream_in = \
            f"{aiko.public.topic_path}/{self.topic_in}/in"
        aiko.add_message_handler(self._consumer_handler, self.topic_stream_in)
        aiko.public.connection.add_handler(self._connection_state_handler)

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

        elif command == "remove" and len(parameters) == 1:
            item_path = _ec_parse_item_path(parameters[0])
# TODO: Catch ValueError and provide better console log (see ECProducer)
            _ec_remove_item(self.cache, item_path)

        elif command == "update" and len(parameters) == 2:
            item_path = _ec_parse_item_path(parameters[0])
            item_value = parameters[1]
# TODO: Catch ValueError and provide better console log (see ECProducer)
            _ec_update_item(self.cache, item_path, item_value)
        elif command == "sync":
            pass  # ECConsumer doesn't use the stream "(sync ...)" command
        else:
            diagnostic = f"Unknown command: {command}, {parameters}"
            _LOGGER.debug(f"_consumer_handler(): {diagnostic}")

        for item_name, item in self.cache.items():
            _LOGGER.debug(f"ECConsumer cache {item_name}: {item}")
        _LOGGER.debug("----------------------------")

    def _connection_state_handler(self, connection, connection_state):
        if connection.is_connected(ConnectionState.REGISTRAR):
            if not self.lease:
                self.lease = Lease(
                    _LEASE_TIME, None,
                    lease_extend_handler=self._stream_request,
                    automatic_extend=True
                )
                self._stream_request()

    def _stream_request(self, lease_time=_LEASE_TIME, lease_uuid=None):
        aiko.public.message.publish(
            self.topic_in,
            f"(stream {self.topic_stream_in} {lease_time} {self.filter})"
        )

    def terminate(self):
        aiko.remove_message_handler(self._consumer_handler,self.topic_stream_in)
        aiko.public.connection.remove_handler(self._connection_state_handler)
        self.cache = {}
        self.cache_state = "empty"

        if self.lease:
            self.lease.terminate()
            self.lease = None
            self._stream_request(lease_time=0)  # cancel stream request

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
    def __init__(self):
        self.cache_reset()
        self.event_loop_owner = False
        aiko.set_registrar_handler(self.registrar_handler)

    def cache_reset(self):
        self.query_items_expected = 0
        self.query_items_received = 0
        self.registrar_topic_out = None
        self.services = {}
        self.state = "empty"
    #   _LOGGER.debug(f"Service cache state: {self.state}")

    def get_services(self):
        return self.services

    def get_services_topics(self):
        return list(self.services.keys())

    def get_state(self):
        return self.state

    def registrar_handler(self, public, action, registrar):
        if action == "started":
            self.registrar_topic_out = registrar["topic_path"] + "/out"
            aiko.add_message_handler(
                self.registrar_out_handler, self.registrar_topic_out
            )
            aiko.add_message_handler(
                self.registrar_query_handler, _REGISTRAR_TOPIC_QUERY,
            )
            aiko.public.message.publish(
                registrar["topic_path"] + "/in",
                f"(query {_REGISTRAR_TOPIC_QUERY} * * * *)",
            )

        if action == "stopped":
            if self.registrar_topic_out:
                aiko.remove_message_handler(
                    self.registrar_out_handler, self.registrar_topic_out
                )
                aiko.remove_message_handler(
                    self.registrar_query_handler, _REGISTRAR_TOPIC_QUERY,
                )
                self.cache_reset()

    def registrar_query_handler(self, aiko, topic, payload_in):
        command, parameters = parse(payload_in)
        if command == "item_count" and len(parameters) == 1:
            self.query_items_expected = int(parameters[0])
        elif command == "add" and len(parameters) == 5:
            service_details = parameters
            self.services[service_details[0]] = service_details
            self.query_items_received += 1
            if self.query_items_received == self.query_items_expected:
                self.state = "loaded"
            #   _LOGGER.debug(f"Service cache state: {self.state}")
        else:
            _LOGGER.debug(f"Service cache: registrar_query_handler(): Unhandled message topic: {topic}, payload: {payload_in}")

    def registrar_out_handler(self, aiko, topic, payload_in):
        command, parameters = parse(payload_in)
        if command == "sync" and len(parameters) == 1:
            sync_topic = parameters[0]
            if sync_topic == _REGISTRAR_TOPIC_QUERY and self.state == "loaded":
                self.state = "live"
            #   _LOGGER.debug(f"Service cache state: {self.state}")
        elif command == "add" and len(parameters) == 5:
            service_details = parameters
        #   _LOGGER.debug(f"registry delta: {command} {service_details}")
            self.services[service_details[0]] = service_details
        elif command == "remove":
            topic = parameters[0]
            if topic in self.services:
                del self.services[topic]
        else:
            _LOGGER.debug(f"Service cache: registrar_out_handler(): Unknown command: topic: {topic}, payload: {payload_in}")

    #   _LOGGER.debug(f"Service cache contents ...")
    #   for service in self.services.values():
    #       after_slash = service[1].rfind("/") + 1
    #       if after_slash >= 0:
    #           protocol = service[1][after_slash:]
    #       _LOGGER.debug(f"    {service[0]} {protocol}")

    def run(self):
        if not event.event_loop_running:
            self.event_loop_owner = True
            aiko.process()

    def terminate(self):
        if self.event_loop_owner:
            event.terminate()

    def wait_live(self):
    #   _LOGGER.debug(f"Service cache: wait until live")
        while self.state != "live":
            time.sleep(1)

service_cache = None

def service_cache_create_singleton():
    global service_cache

    if not service_cache:
        service_cache = ServiceCache()
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
    topic_in = f"{get_namespace()}/{get_hostname()}/{ec_producer_pid}/control"

    aiko.set_protocol(PROTOCOL_EC_CONSUMER)
    ec_consumer = ECConsumer(state, topic_in, filter)

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
