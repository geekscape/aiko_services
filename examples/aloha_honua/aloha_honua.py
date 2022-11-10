#!/usr/bin/env python3
#
# Aiko Service: Aloha Honua
# ~~~~~~~~~~~~~~~~~~~~~~~~~
#
# Usage
# ~~~~~
# LOG_LEVEL=INFO  # DEBUG
# mosquitto_sub -t '#' -v
# REGISTRAR=0   LOG_LEVEL=$LOG_LEVEL registrar &
# ALOHA_HONUA=0 LOG_LEVEL=$LOG_LEVEL ./aloha_honua.py [count] &
#
# NAMESPACE=aiko
# HOST=localhost
# PID=`ps ax | grep python | grep aloha_honua.py | cut -d" " -f1`
# TOPIC_PATH=$NAMESPACE/$HOST/$PID  # or copy from dashboard
#
# ALOHA_HONUA=0 LOG_LEVEL=DEBUG ./aloha_honua.py 0 & PID=`echo $!`; TOPIC_PATH=$NAMESPACE/`hostname`/$PID; echo ALOHA_HONUA: $TOPIC_PATH
#
# mosquitto_pub -t $TOPIC_PATH/contol -m '(update log_level DEBUG)'
# mosquitto_pub -t $TOPIC_PATH/in -m '(test hello)'
#
# id=0
# while true; do
#   mosquitto_pub -t $TOPIC_PATH/control -m "(update actor_id $id)"
#   id=$((id+1))
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
PROTOCOL = f"{ServiceProtocol.AIKO}/aloha_honua:0"

_LOGGER = aiko.logger(__name__)
_VERSION = 0

# --------------------------------------------------------------------------- #

class AlohaHonua(Actor):
    Interface.implementations["AlohaHonua"] = "__main__.AlohaHonuaImpl"

    @abstractmethod
    def test(self, value):
        pass

class AlohaHonuaImpl(AlohaHonua):
    def __init__(self,
        implementations, name, protocol, tags, transport):

        implementations["Actor"].__init__(self,
            implementations, name, protocol, tags, transport)

        aiko.connection.add_handler(self._connection_state_handler)

        self.state = {
            "lifecycle": "ready",
            "log_level": get_log_level_name(_LOGGER),
            "source_file": f"v{_VERSION}⇒{__file__}",
            "test_dict": {"item_1": ["value_a"], "item_2": ["value_b"]}
        }
        self.ec_producer = ECProducer(self, self.state)
        self.ec_producer.add_handler(self._ec_producer_change_handler)

    #   self.add_message_handler(self._topic_all_handler, "#")  # for testing
        self.add_message_handler(self._topic_in_handler, self.topic_in)

    def _connection_state_handler(self, connection, connection_state):
        if connection.is_connected(ConnectionState.REGISTRAR):
            _LOGGER.debug("Aloha honua (after Registrar available)")

    def _ec_producer_change_handler(self, command, item_name, item_value):
        if _LOGGER.isEnabledFor(DEBUG):  # Save time
            _LOGGER.debug(f"ECProducer: {command} {item_name} {item_value}")
        if item_name == "log_level":
            _LOGGER.setLevel(str(item_value).upper())

    def _topic_all_handler(self, _aiko, topic, payload_in):
        command, parameters = parse(payload_in)
        if _LOGGER.isEnabledFor(DEBUG):  # Save time
            _LOGGER.debug(
                f"topic_all_handler(): topic: {topic}, {command}:{parameters}")

    def _topic_in_handler(self, _aiko, topic, payload_in):
        command, parameters = parse(payload_in)
        if _LOGGER.isEnabledFor(DEBUG):  # Save time
            _LOGGER.debug(
                f"{self.name}: topic_in_handler(): {command}:{parameters}"
            )
# TODO: Apply proxy automatically for Actor and not manually here
        self._post_message(actor.Topic.IN, command, parameters)

    def test(self, value):
        _LOGGER.info(f"{self.name}: test({value})")
        payload_out = f"(test {value})"
        aiko.message.publish(self.topic_out, payload_out)

# --------------------------------------------------------------------------- #

actor_count = 0
actor_total = 0

@click.command("main", help="Aloha honua")
@click.argument("count", nargs=1, default=1, required=False)
def main(count):
    global actor_total
    actor_total = count
    _LOGGER.debug("Aloha honua (before Registrar available)")

    event.add_timer_handler(create_actor, 0.01)
    aiko.process.run()

def create_actor():
    global actor_count, actor_total

    tags = ["ec=true"]  # TODO: Add ECProducer tag before add to Registrar
    init_args = actor_args(ACTOR_TYPE, PROTOCOL, tags)

    aloha_honua = compose_instance(AlohaHonuaImpl, init_args)
    actor_count += 1
    if actor_count % 100 == 0:
        _LOGGER.info(f"Actor count: {actor_count}")

    if actor_count == actor_total:
        event.remove_timer_handler(create_actor)

if __name__ == "__main__":
    main()

# --------------------------------------------------------------------------- #
