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
# - None, yet !

import click

from aiko_services import *
from aiko_services.utilities import *

__all__ = [ "ECConsumer", "ECProducer" ]

_LOGGER = get_logger(__name__)
_PROTOCOL_CONSUMER = "github.com/geekscape/aiko_services/protocol/ec_consumer:0"
_PROTOCOL_PRODUCER = "github.com/geekscape/aiko_services/protocol/ec_producer:0"
_STREAM_LEASE_TIME = 60  # seconds
_TOPIC_PRODUCER_IN = aiko.public.topic_control  # aiko.public.topic_in
_TOPIC_PRODUCER_OUT = aiko.public.topic_state   # aiko.public.topic_out

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
        self, lease_time, topic, item_names=None, lease_expired_handler=None):

        super().__init__(
            lease_time, topic, lease_expired_handler=lease_expired_handler)
        self.item_names = item_names

class ECProducer:
    def __init__(self, state, topic_in, topic_out):
        self.state = state
        self.topic_in = topic_in
        self.topic_out = topic_out
        self.leases = {}
        aiko.add_message_handler(self._producer_handler, topic_in)

    def _ec_parse_stream(self, command, parameters):
        response_topic = None
        lease_time = None
        item_names = []

        if command == "stream" and len(parameters) == 3:
            try:
                lease_time = int(parameters[1])
            except Exception:
                pass
            if type(lease_time) == int:
                if parameters[2] == "*":
                    item_names = self.state.keys()
                else:
                    item_names = parameters[2]
                    if type(item_names) != list:
                        item_names = [item_names]
                response_topic = parameters[0]  # Deliberately do this last

        return response_topic, lease_time, item_names

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
            _ec_update_item(self.state, item_path, item_value)
            aiko.message.publish(self.topic_out, payload_out)

            for lease in self.leases.values():
                if item_name in lease.item_names:
                    response_topic = lease.lease_uuid
                    aiko.message.publish(response_topic, payload_out)

        if command == "remove" and len(parameters) == 1:
            item_path = _ec_parse_item_path(parameters[0])
            _ec_remove_item(self.state, item_path)
            aiko.message.publish(self.topic_out, payload_out)

        if command == "stream":
            response_topic, lease_time, item_names = self._ec_parse_stream(
                command, parameters)
            if response_topic:
                if lease_time > 0:
                    if not response_topic in self.leases:
                        lease = ECLease(
                            lease_time,
                            response_topic,
                            item_names=item_names,
                            lease_expired_handler=self._lease_expired_handler)
                        self.leases[response_topic] = lease
                        self._synchronize(response_topic, item_names)
                    else:
                        self.leases[response_topic].extend(lease_time)

    def _synchronize(self, response_topic, item_names):
        items = []
        for item_name in item_names:
            if item_name in self.state:
                item = self.state[item_name]
                if type(item) != dict:
                    items.append(f"(add {item_name} {item})")
                else:
                    for subitem_name in item.keys():
                        name = f"{item_name}.{subitem_name}"
                        subitem = self.state[item_name][subitem_name]
                        items.append(f"(add {name} {subitem})")

        item_count = len(items)
        payload_out = f"(item_count {item_count})"
        aiko.public.message.publish(response_topic, payload=payload_out)
        for item in items:
            aiko.public.message.publish(response_topic, payload=item)

        payload_out = f"(sync {response_topic})"
        aiko.public.message.publish(self.topic_out, payload_out)

# --------------------------------------------------------------------------- #

class ECConsumer:
    def __init__(self, cache, topic_in):
        self.cache = cache
        self.topic_in = topic_in

        self.cache_state = "empty"
        self.item_count = 0
        self.items_received = 0

        self.topic_stream_in = \
            f"{aiko.public.topic_path}/{self.topic_in}/in"
        aiko.add_message_handler(self._consumer_handler, self.topic_stream_in)
        aiko.add_connection_state_handler(self._connection_state_handler)

    def _connection_state_handler(self, connection_state):
        if connection_state == ConnectionState.REGISTRAR:
            self.lease = Lease(
                _STREAM_LEASE_TIME, None,
                lease_extend_handler=self._stream_request,
                automatic_extend=True
            )
            self._stream_request()

    def _stream_request(self, lease_uuid=None):  # stream lease extend
        aiko.public.message.publish(
            self.topic_in,
            f"(stream {self.topic_stream_in} {_STREAM_LEASE_TIME} *)"
        )

    def _consumer_handler(self, aiko, topic, payload_in):
        command, parameters = parse(payload_in)

        if command == "item_count" and len(parameters) == 1:
            self.item_count = int(parameters[0])
            self.items_received = 0

        elif command == "add" and len(parameters) == 2:
            item_name = parameters[0]
            item_path = _ec_parse_item_path(item_name)
            item_value = parameters[1]
            _ec_update_item(self.cache, item_path, item_value)
            self.items_received += 1
            if self.items_received == self.item_count:
                self.cache_state = "ready"

        elif command == "remove" and len(parameters) == 1:
            item_path = _ec_parse_item_path(parameters[0])
            _ec_remove_item(self.cache, item_path)

        elif command == "update" and len(parameters) == 2:
            item_path = _ec_parse_item_path(parameters[0])
            item_value = parameters[1]
            _ec_update_item(self.cache, item_path, item_value)
        elif command == "sync":
            pass  # ECConsumer doesn't use the stream "(sync ...)" command
        else:
            diagnostic = f"Unknown command: {command}, {parameters}"
            _LOGGER.debug(f"_consumer_handler(): {diagnostic}")

        for item_name, item in self.cache.items():
            _LOGGER.debug(f"ECConsumer cache {item_name}: {item}")

# --------------------------------------------------------------------------- #

def _create_ec_consumer(ec_producer_pid):
    state = {}
    topic_in = f"{get_namespace()}/{get_hostname()}/{ec_producer_pid}/control"

    aiko.set_protocol(_PROTOCOL_CONSUMER)
    ec_consumer = ECConsumer(state, topic_in)

def _create_ec_producer():
    state = {
        "lifecycle": "initialize",
        "services": {
            "topic_1": ["topic_1", "protocol_1", "transport", "owner_1", []],
            "topic_2": ["topic_2", "protocol_2", "transport", "owner_2", []]
        }
    }

    aiko.set_protocol(_PROTOCOL_PRODUCER)
    ec_producer = ECProducer(state, _TOPIC_PRODUCER_IN, _TOPIC_PRODUCER_OUT)

@click.command("main", help=(
    "Demonstrate Eventual Consistency ECProducer and ECConsumer"))
@click.argument("ec_producer_pid", nargs=1, required=False)
def main(ec_producer_pid):
    if ec_producer_pid:
        _create_ec_consumer(ec_producer_pid)
    else:
        _create_ec_producer()

    aiko.process(True)

if __name__ == "__main__":
    main()

# --------------------------------------------------------------------------- #
