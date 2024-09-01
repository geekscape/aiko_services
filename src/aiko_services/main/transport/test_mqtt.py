#!/usr/bin/env python3
#
# Usage
# ~~~~~
# AIKO_LOG_LEVEL=DEBUG ./transport/test_mqtt.py create
#
# AIKO_LOG_LEVEL=DEBUG ./transport/test_mqtt.py  \
#                      send_message aiko/nomad.local/45812/1/in hello
#
# TODO: ./test_mqtt.py delete
# TODO: ./test_mqtt.py list [filter]
#
# To Do
# ~~~~~
# * Rename MQTTTest --> MQTTActorTest
#   Rename "test_mqtt.py" --> "mqtt_actor_test.py"
#
# - transport_mqtt.py: Complete create_actor_mqtt() and delete_actor_mqtt()
# - transport_mqtt.py: Wrap in CLI / TUI for handy tools for finding Services

from abc import abstractmethod
import click

from aiko_services.main import *
from aiko_services.main.transport import *

_VERSION = 0

ACTOR_TYPE = "mqtt_test"
PROTOCOL = f"{ServiceProtocol.AIKO}/{ACTOR_TYPE}:{_VERSION}"

_LOGGER = aiko.logger(__name__)

# --------------------------------------------------------------------------- #

class MQTTTest(TransportMQTT):
    Interface.default("MQTTTest",
        "aiko_services.main.transport.test_mqtt.MQTTTestImpl")

    @abstractmethod
    def test(self, message):
        pass

class MQTTTestImpl(MQTTTest):
    def __init__(self, context):
        context.get_implementation("TransportMQTT").__init__(self, context)

        self.share["source_file"] = f"v{_VERSION}⇒ {__file__}"
        self.share["message"] = None

        self.actor_discovery = ActorDiscovery(self)
        tags = "*"  # ["class=AlohaHonuaActor"]  # TODO: CLI parameter
        filter = ServiceFilter("*", "*", "*", "*", "*", tags)
        self.actor_discovery.add_handler(self._actor_change_handler, filter)

    def _actor_change_handler(self, command, service_details):
        if command == "sync":
            _LOGGER.debug("sync")
        #   actors = self.actor_discovery.share_actor_mqtt(self.filter)

        #   name = "aiko/zeus/3704321.AlohaHonua"
        #   actor = self.actor_discovery.get_actor_mqtt(name)
        #   actor_topic = ".".join(name.split(".")[:-1])
        else:
            _LOGGER.debug(f"{command}: {service_details}")

    def test(self, message):
        _LOGGER.info(f"{self.name}: test({message})")
        self.ec_producer.update("message", message)
        payload_out = f"(test {message})"
        aiko.message.publish(self.topic_out, payload_out)

# --------------------------------------------------------------------------- #

@click.group()

def main():
    pass

@main.command(help="Transport MQTT Test Actor")

def create():
    init_args = actor_args(ACTOR_TYPE, protocol=PROTOCOL)
    mqtt_test = compose_instance(MQTTTestImpl, init_args)
    aiko.process.run()

@main.command(name="send_message",
    help="Make function call (send message) to Transport MQTT Actor")
@click.argument("topic", default=None, required=True)
@click.argument("message", default=None, required=True)

def send_message(topic, message):
    actor_remote_proxy = get_actor_mqtt(topic, MQTTTest)
    aiko.process.initialize()
    if actor_remote_proxy:
        actor_remote_proxy.test(message)
        aiko.message.wait_published()
    else:
        print(f"Actor {topic} not found")

if __name__ == "__main__":
    main()

# --------------------------------------------------------------------------- #
