#!/usr/bin/env python3
#
# Aiko Service: Aloha Honua
# ~~~~~~~~~~~~~~~~~~~~~~~~~
#
# Usage
# ~~~~~
# LOG_LEVEL=DEBUG registrar &
# LOG_LEVEL=DEBUG ./aloha_honua.py
#
# mosquitto_sub -t '#' -v
#
# NAMESPACE=aiko
# HOST=localhost
# PID=`ps ax | grep python | grep aloha_honua | cut -d" " -f1`
# TOPIC_PATH=$NAMESPACE/$HOST/$PID
# mosquitto_pub -t $TOPIC_PATH/in -m '(test hello)'
#
# To Do
# ~~~~~
# - None, yet !

import click

from aiko_services import *
from aiko_services.utilities import *

PROTOCOL = "github.com/geekscape/aiko_services/protocol/aloha_honua:0"

_ACTOR_NAME = "AlohaHonua"
_LOGGER = get_logger(__name__)

# --------------------------------------------------------------------------- #

class AlohaHonuaActor(actor.Actor):
    def __init__(self, actor_name):
        super().__init__(actor_name)

    def test(self, value):
        _LOGGER.debug(f"{_ACTOR_NAME}: test({value})")
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
            f"{_ACTOR_NAME}: topic_in_handler(): {command}:{parameters}"
        )
        self._post_message(actor.Topic.IN, command, parameters)

# --------------------------------------------------------------------------- #

@click.command()
def main():
    actor_name = aiko.public.topic_path
    aloha_honua = AlohaHonuaActor(actor_name)

    aiko.set_protocol(PROTOCOL)
    aiko.add_tags([
        f"class={AlohaHonuaActor.__name__}",  # TODO: Use full class pathname
        f"name={_ACTOR_NAME}"
    ])
# BUG: Causes AlohaHonua Service to be added twice !?!
#   aiko.add_message_handler(aloha_honua.topic_all_handler, "#")
    aiko.add_topic_in_handler(aloha_honua.topic_in_handler)
    aiko.process(True)

if __name__ == "__main__":
    main()

# --------------------------------------------------------------------------- #
