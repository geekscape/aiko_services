#!/usr/bin/env python3
#
# Usage
# ~~~~~
# AIKO_LOG_LEVEL=DEBUG AIKO_LOG_MQTT=false ./transport/test_mqtt.py create
#
# AIKO_LOG_LEVEL=DEBUG AIKO_LOG_MQTT=false ./transport/test_mqtt.py  send_message aiko/nomad.local/45812/1/in hello
#
# TODO: ./test_mqtt.py delete
# TODO: ./test_mqtt.py list [filter]
#
# To Do
# ~~~~~
# - transport_mqtt.py: Complete create_actor_mqtt() and delete_actor_mqtt()
# - transport_mqtt.py: Wrap in CLI / TUI for handy tools for finding Services

from abc import abstractmethod
import click

from aiko_services import *
from aiko_services.transport import *

ACTOR_TYPE = "MQTTTest"
PROTOCOL = f"{ServiceProtocol.AIKO}/test_mqtt:0"

_LOGGER = aiko.logger(__name__)
_VERSION = 0

# --------------------------------------------------------------------------- #

class MQTTTest(TransportMQTT):
    Interface.implementations["MQTTTest"] = "__main__.MQTTTestImpl"

    @abstractmethod
    def test(self, message):
        pass

class MQTTTestImpl(MQTTTest):
    def __init__(self,
        implementations, name, protocol, tags, transport):

        implementations["TransportMQTT"].__init__(self,
            implementations, name, protocol, tags, transport)

        self.state = {
            "lifecycle": "ready",
            "log_level": get_log_level_name(_LOGGER),
            "message": None,
            "source_file": f"v{_VERSION}⇒{__file__}"
        }
        self.ec_producer = ECProducer(self, self.state)
        self.ec_producer.add_handler(self._ec_producer_change_handler)

        self.actor_discovery = ActorDiscovery(self)
        tags = "*"  # ["class=AlohaHonuaActor"]  # TODO: CLI parameter
        filter = ServiceFilter("*", "*", "*", "*", tags)
        self.actor_discovery.add_handler(self._actor_change_handler, filter)

    def _actor_change_handler(self, command, service_details):
        if command == "sync":
            _LOGGER.debug("sync")
        #   actors = self.actor_discovery.query_actor_mqtt(self.filter)

        #   name = "aiko/zeus/3704321.AlohaHonua"
        #   actor = self.actor_discovery.get_actor_mqtt(name)
        #   actor_topic = ".".join(name.split(".")[:-1])
        else:
            _LOGGER.debug(f"{command}: {service_details}")

    def _ec_producer_change_handler(self, command, item_name, item_value):
        if item_name == "log_level":
            _LOGGER.setLevel(str(item_value).upper())

    def _topic_in_handler(self, _aiko, topic, payload_in):
        command, parameters = parse(payload_in)
# TODO: Apply proxy automatically for Actor and not manually here
        self._post_message(actor.Topic.IN, command, parameters)

    def test(self, message):
        _LOGGER.info(f"{self.name}: test({value})")
        self.ec_producer.update("message", message)
        payload_out = f"(test {value})"
        aiko.message.publish(self.topic_out, payload_out)

# --------------------------------------------------------------------------- #

@click.group()
def main():
    pass

@main.command(help="Transport MQTT Test Actor")
def create():
    init_args = actor_args(ACTOR_TYPE, PROTOCOL)
    mqtt_test = compose_instance(MQTTTestImpl, init_args)
    aiko.process.run()

@main.command(name="send_message",
    help="Make function call (send message) to Transport MQTT Actor")
@click.argument("topic", default=None, required=True)
@click.argument("message", default=None, required=True)
def send_message(topic, message):
    actor_proxy = get_actor_mqtt(topic, MQTTTest)
    aiko.process.initialize()
    if actor_proxy:
        actor_proxy.test(message)
        aiko.message.wait_published()
    else:
        print(f"Actor {topic} not found")

if __name__ == "__main__":
    main()

# --------------------------------------------------------------------------- #
