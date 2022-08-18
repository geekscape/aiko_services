#!/usr/bin/env python3
#
# Usage
# ~~~~~
# ./test_mqtt.py
#
# TODO: ./test_mqtt.py create
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

ACTOR_TYPE = "TestMQTT"
PROTOCOL = f"{AIKO_PROTOCOL_PREFIX}/test_mqtt:0"

_LOGGER = aiko.logger(__name__)
_VERSION = 0

#---------------------------------------------------------------------------- #

class TestMQTT(TransportMQTT):
    Interface.implementations["TestMQTT"] = "__main__.TestMQTTImpl"

    @abstractmethod
    def test(self, message):
        pass

class TestMQTTImpl(TestMQTT):
    def __init__(self, implementations, actor_name):
        implementations["TransportMQTT"].__init__(
            self, implementations, actor_name)
        aiko.set_protocol(PROTOCOL)  # TODO: Move into service.py

        self.actor_discovery = ActorDiscovery()
        self.state = {
            "lifecycle": "ready",
            "log_level": get_log_level_name(_LOGGER),
            "message": None,
            "source_file": f"v{_VERSION}⇒{__file__}"
        }
        self.ec_producer = ECProducer(self.state)
        self.ec_producer.add_handler(self._ec_producer_change_handler)

        tags = "*"  # ["class=AlohaHonuaActor"]  # TODO: CLI parameter
        self.filter = ServiceFilter("*", "*", "*", "*", tags)
        self.actor_discovery.add_handler(
            self._actor_change_handler, self.filter)

    def _actor_change_handler(self, command, service_details):
        if command == "sync":
            _LOGGER.debug("sync")
        #   actors = self.actor_discovery.query_actor_mqtt(self.filter)

        #   actor_name = "aiko/zeus/3704321.AlohaHonua"
        #   actor = self.actor_discovery.get_actor_mqtt(actor_name)
        #   actor_topic = ".".join(actor_name.split(".")[:-1])
        else:
            _LOGGER.debug(f"{command}: {service_details}")

    def _ec_producer_change_handler(self, command, item_name, item_value):
        if item_name == "log_level":
            _LOGGER.setLevel(str(item_value).upper())

    def test(self, message):
        print(f"test({message})")
        self.ec_producer.update("message", message)

@click.command("main", help="Transport MQTT Test Actor")
def main():
    actor_name = f"{aiko.public.topic_path}.{ACTOR_TYPE}"  # WIP: Actor name
    init_args = {"actor_name": actor_name}
    test_mqtt = compose_instance(TestMQTTImpl, init_args)
    aiko.process()

if __name__ == "__main__":
    main()

#---------------------------------------------------------------------------- #

@click.group()
def main():
    pass

@main.command(help="Transport MQTT Test Actor")
def create():
    actor_name = f"{aiko.public.topic_path}.{ACTOR_TYPE}"  # WIP: Actor name
    init_args = {"actor_name": actor_name}
    test_mqtt = compose_instance(TestMQTTImpl, init_args)
    aiko.process()

@main.command()
@click.argument("topic")
@click.argument("message")
def send_message(topic, message):
    actor_proxy = get_actor_mqtt(topic, TestMQTT)
    aiko.initialize()
    if actor_proxy:
        actor_proxy.test(message)
    else:
        print(f"Actor {topic} not found")
