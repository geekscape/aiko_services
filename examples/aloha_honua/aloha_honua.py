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
#   mosquitto_pub -t $TOPIC_PATH/control -m "(update id $id)"
#   id=$((id+1))
#   sleep 0.001
# done
#
# To Do
# ~~~~~
# - Create most basic AlohaHonua and incrementally more feature rich versions

from abc import abstractmethod
import click

from aiko_services import *

ACTOR_TYPE = "aloha_honua"
PROTOCOL = f"{ServiceProtocol.AIKO}/{ACTOR_TYPE}:0"

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
            implementations, name, protocol, tags, transport, id):

        implementations["Actor"].__init__(self,
            implementations, name, protocol, tags, transport)

        self.state["id"] = id
        self.state["source_file"] = f"v{_VERSION}⇒{__file__}"
        self.state["test_dict"] = {"item_1": ["value_a"], "item_2": ["value_b"]}

        aiko.connection.add_handler(self._connection_state_handler)

    # TODO: Improve ".../process.py:ProcessImplementation.topic_matcher()"
        topic_path = f"{get_namespace()}/#"
        self.add_message_handler(self._topic_all_handler, topic_path)

    def _connection_state_handler(self, connection, connection_state):
        if connection.is_connected(ConnectionState.REGISTRAR):
            _LOGGER.debug("Aloha honua (after Registrar available)")

    def _topic_all_handler(self, _aiko, topic, payload_in):
        if _LOGGER.isEnabledFor(DEBUG):  # Don't expand debug message
            _LOGGER.debug(f"topic_all_handler(): topic: {topic}, {payload_in}")

    def get_logger(self):
        return _LOGGER

    def test(self, value):
        _LOGGER.info(f"{self.name}: test({value})")
        payload_out = f"(test {value})"
        aiko.message.publish(self.topic_out, payload_out)

# --------------------------------------------------------------------------- #

actor_count = 0
actor_total = 0

def create_actor(id):
    tags = ["ec=true"]  # TODO: Add ECProducer tag before add to Registrar
    name = f"{ACTOR_TYPE}_{id}"
    init_args = actor_args(name, PROTOCOL, tags)
    init_args["id"] = id
    aloha_honua = compose_instance(AlohaHonuaImpl, init_args)

def create_actors():
    global actor_count, actor_total
    actor_count += 1

    create_actor(actor_count)

    if actor_count % 100 == 0:
        _LOGGER.info(f"Actor count: {actor_count}")

    if actor_count == actor_total:
        event.remove_timer_handler(create_actors)

@click.command("main", help="Aloha honua")
@click.argument("count", nargs=1, default=1, required=False)
def main(count):
    global actor_total
    actor_total = count
    _LOGGER.debug("Aloha honua (before Registrar available)")

    if actor_count == 1:
        create_actor()
    else:
        event.add_timer_handler(create_actors, 0.01)

    aiko.process.run()

if __name__ == "__main__":
    main()

# --------------------------------------------------------------------------- #
