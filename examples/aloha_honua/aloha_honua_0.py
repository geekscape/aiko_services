#!/usr/bin/env python3
#
# Usage
# ~~~~~
#   Terminal session 1
#   ~~~~~~~~~~~~~~~~~~
#   ../../scripts/system_start.sh
#
#   Terminal session 2
#   ~~~~~~~~~~~~~~~~~~
#   ./aloha_honua_0.py &
#   mosquitto_pub -m "(aloha Pele)" -t ?  # replace with aiko_dashboard publish
#
# To Do
# ~~~~~
# - None, yet !

from aiko_services import *

_LOGGER = aiko.logger(__name__)

class AlohaHonua(Actor):
    def __init__(self, implementations, name, protocol, tags, transport):
        implementations["Actor"].__init__(self,
            implementations, name, protocol, tags, transport)
        print(f"MQTT topic: {self.topic_in}")

    def get_logger(self):
        return _LOGGER

    def aloha(self, name):
        _LOGGER.info(f"Aloha honua {name} !")

if __name__ == "__main__":
    init_args = actor_args("aloha_honua", "*")
    aloha_honua = compose_instance(AlohaHonua, init_args)
    aiko.process.run()
