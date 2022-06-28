#!/usr/bin/env python3
#
# Aiko Service: Aloha Honua
# ~~~~~~~~~~~~~~~~~~~~~~~~~
#
# Usage
# ~~~~~
# LOG_LEVEL=INFO  # DEBUG
# mosquitto_sub -t '#' -v
# REGISTRAR=0   LOG_MQTT=$LOG_LEVEL registrar &
# ALOHA_HONUA=0 LOG_MQTT=$LOG_LEVEL ./aloha_honua.py [test_value] &
#
# NAMESPACE=aiko
# HOST=localhost
# PID=`ps ax | grep python | grep aloha_honua.py | cut -d" " -f1`
# TOPIC_PATH=$NAMESPACE/$HOST/$PID  # or copy from dashboard
#
# ALOHA_HONUA=0 LOG_LEVEL=DEBUG ./aloha_honua.py 0 & PID=`echo $!`; TOPIC_PATH=$NAMESPACE/`hostname`/$PID; echo ALOHA_HONUA: $TOPIC_PATH
#
# mosquitto_pub -t $TOPIC_PATH/contol -m '(update log_lebel DEBUG)'
# mosquitto_pub -t $TOPIC_PATH/contol -m '(update test_value 0)'
# mosquitto_pub -t $TOPIC_PATH/in -m '(test hello)'
#
# count=0
# while true; do
#   mosquitto_pub -t $TOPIC_PATH/control -m "(update test_value $count)"
#   count=$((count+1))
#   sleep 0.001
# done
#
# To Do
# ~~~~~
# - None, yet !

from abc import abstractmethod
import click

from aiko_services import *
from aiko_services.utilities import *

ACTOR_TYPE = "AlohaHonua"
PROTOCOL = f"{AIKO_PROTOCOL_PREFIX}/aloha_honua:0"

_LOGGER = aiko.logger(__name__)

# --------------------------------------------------------------------------- #

class AlohaHonua(Actor):
    Interface.implementations["AlohaHonua"] = "__main__.AlohaHonuaImpl"

    @abstractmethod
    def test(self, value):
        pass

class AlohaHonuaImpl(AlohaHonua):
    def __init__(self, implementations, actor_name, test_value=0):
        implementations["Actor"].__init__(self, implementations, actor_name)
        aiko.set_protocol(PROTOCOL)  # TODO: Move into service.py

        self.state = {
            "lifecycle": "initialize",
            "log_level": get_log_level_name(_LOGGER),
            "test_value": test_value,
            "test_dict": {"item_1": ["value_a"], "item_2": ["value_b"]}
        }
        self.ec_producer = ECProducer(self.state)
        self.ec_producer.add_handler(self._ec_producer_change_handler)

    #   aiko.add_message_handler(self.topic_all_handler, "#")  # for testing
        aiko.add_topic_in_handler(self.topic_in_handler)

    def _ec_producer_change_handler(self, command, item_name, item_value):
        _LOGGER.debug(f"ECProducer: {command} {item_name} {item_value}")
        if item_name == "log_level":
            _LOGGER.setLevel(str(item_value).upper())

    def test(self, value):
        _LOGGER.debug(f"{self.actor_name}: test({value})")
        payload_out = f"(test {value})"
        aiko.public.message.publish(aiko.public.topic_out, payload_out)

    def topic_all_handler(self, _aiko, topic, payload_in):
        command, parameters = parse(payload_in)
        _LOGGER.debug(
            f"topic_all_handler(): topic: {topic}, {command}:{parameters}")

    def topic_in_handler(self, _aiko, topic, payload_in):
        command, parameters = parse(payload_in)
        _LOGGER.debug(
            f"{self.actor_name}: topic_in_handler(): {command}:{parameters}"
        )
# TODO: Apply proxy automatically for ActorMQTT and not manually here
        self._post_message(actor.Topic.IN, command, parameters)

# --------------------------------------------------------------------------- #

@click.command("main", help="Hello World Actor")
@click.argument("test_value", nargs=1, default=0, required=False)
def main(test_value):
    actor_name = f"{aiko.public.topic_path}.{ACTOR_TYPE}"  # WIP: Actor name
    aiko.add_tags([
        f"actor={actor_name}",               # WIP: Actor name
    #   f"class={AlohaHonuaActor.__name__}"  # TODO: Use full class pathname ?
    ])
    init_args = {"actor_name": actor_name, "test_value": 1}
    aloha_honua = compose_instance(AlohaHonuaImpl, init_args)
    aloha_honua.run()

if __name__ == "__main__":
    main()

# --------------------------------------------------------------------------- #
