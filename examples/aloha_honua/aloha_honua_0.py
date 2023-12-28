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

ACTOR_NAME = "aloha_honua"
_LOGGER = aiko.logger(ACTOR_NAME)

class AlohaHonua(Actor):
    def __init__(self, context):
        context.get_implementation("Actor").__init__(self, context)
        print(f"MQTT topic: {self.topic_in}")

    def get_logger(self):
        return _LOGGER

    def aloha(self, name):
        _LOGGER.info(f"Aloha {name} !")

if __name__ == "__main__":
    init_args = actor_args(ACTOR_NAME)
    aloha_honua = compose_instance(AlohaHonua, init_args)
    aiko.process.run()
