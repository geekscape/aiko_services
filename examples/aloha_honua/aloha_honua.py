#!/usr/bin/env python3
#
# Aiko Service: Aloha Honua
# ~~~~~~~~~~~~~~~~~~~~~~~~~
#
# Usage
# ~~~~~
# mosquitto_sub -t '#' -v
# REGISTRAR=0 LOG_LEVEL=DEBUG registrar &
# ALOHA_HONUA=0 LOG_LEVEL=DEBUG ./aloha_honua.py [test_value] &
#
# NAMESPACE=aiko
# HOST=localhost
# PID=`ps ax | grep python | grep aloha_honua.py | cut -d" " -f1`
# TOPIC_PATH=$NAMESPACE/$HOST/$PID
#
# ALOHA_HONUA=0 LOG_LEVEL=DEBUG ./aloha_honua.py 0 & PID=`echo $!`; TOPIC_PATH=$NAMESPACE/`hostname`/$PID; echo ALOHA_HONUA: $TOPIC_PATH
#
# mosquitto_pub -t $TOPIC_PATH/in -m '(test hello)'
# mosquitto_pub -t $TOPIC_PATH/contol -m '(update test_value 0)'
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

import click

from aiko_services import *
from aiko_services.utilities import *

ACTOR_TYPE = "AlohaHonua"
PROTOCOL = f"{AIKO_PROTOCOL_PREFIX}/aloha_honua:0"

_LOGGER = aiko.logger(__name__)

# --------------------------------------------------------------------------- #

class AlohaHonuaActor(actor.Actor):
    def __init__(self, actor_name, test_value=0):
        super().__init__(actor_name)
        self.state = {
            "lifecycle": "initialize",
            "log_level": "info",
            "test_value": test_value,
            "test_dict": {
                "item_1": ["value_a"],
                "item_2": ["value_b"]
            },
        }
        ECProducer(self.state)

    def test(self, value):
        _LOGGER.debug(f"{self.actor_name}: test({value})")
        payload_out = f"(test {value})"
        aiko.public.message.publish(aiko.public.topic_out, payload_out)

    def topic_all_handler(self, _aiko, topic, payload_in):
        command, parameters = parse(payload_in)
        _LOGGER.debug(
            f"topic_all_handler(): topic: {topic}, {command}:{parameters}"
        )

    def topic_in_handler(self, _aiko, topic, payload_in):
        command, parameters = parse(payload_in)
        _LOGGER.debug(
            f"{self.actor_name}: topic_in_handler(): {command}:{parameters}"
        )
# TODO: Apply proxy automatically for ActorMQTT and not manually here
        self._post_message(actor.Topic.IN, command, parameters)

# --------------------------------------------------------------------------- #

@click.command("main", help=("Hello World Actor"))
@click.argument("test_value", nargs=1, default=0, required=False)
def main(test_value):
    actor_name = f"{aiko.public.topic_path}.{ACTOR_TYPE}"  # WIP: Actor name
    aloha_honua = AlohaHonuaActor(actor_name, test_value)

    aiko.set_protocol(PROTOCOL)
    aiko.add_tags([
        f"actor={actor_name}",               # WIP: Actor name
        f"class={AlohaHonuaActor.__name__}"  # TODO: Use full class pathname ?
    ])
#   aiko.add_message_handler(aloha_honua.topic_all_handler, "#")  # For testing
    aiko.add_topic_in_handler(aloha_honua.topic_in_handler)
    aiko.process()

if __name__ == "__main__":
    main()

# --------------------------------------------------------------------------- #
