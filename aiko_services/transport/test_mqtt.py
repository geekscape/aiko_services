#!/usr/bin/env python3
#
# Usage
# ~~~~~
# LOG_LEVEL=DEBUG ./test_mqtt.py
#
# TODO: ./test_mqtt.py create
# TODO: ./test_mqtt.py delete
# TODO: ./test_mqtt.py list [filter]
#
# To Do
# ~~~~~
# - transport_mqtt.py: Complete create_actor_mqtt() and delete_actor_mqtt()
# - transport_mqtt.py: Wrap in CLI / TUI for handy tools for finding Services

import click

from aiko_services import *
from aiko_services.transport import *

ACTOR_TYPE = "TestMQTT"
PROTOCOL = f"{AIKO_PROTOCOL_PREFIX}/test_mqtt:0"

_LOGGER = aiko.logger(__name__)

#---------------------------------------------------------------------------- #

class TestMQTT(TransportMQTTActor):
    def __init__(self, actor_name):
        super().__init__(actor_name)
        self.actor_discovery = ActorDiscovery()
        self.state = { "lifecycle": "initialize", "log_level": "info" }
        ECProducer(self.state)

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

@click.command("main", help=("Transport MQTT Test Actor"))
def main():
    actor_name = f"{aiko.public.topic_path}.{ACTOR_TYPE}"  # WIP: Actor name
    aiko.add_tags([f"actor={actor_name}"])  # WIP: Actor name
    test_mqtt = TestMQTT(actor_name)
    aiko.set_protocol(PROTOCOL)
    aiko.process()

if __name__ == "__main__":
    main()

#---------------------------------------------------------------------------- #
