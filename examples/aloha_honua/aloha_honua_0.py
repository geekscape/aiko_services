#!/usr/bin/env python3
#
# Usage
# ~~~~~
#   Terminal session 1 (replace with shell script [start|stop])
#   ~~~~~~~~~~~~~~~~~~
#   mosquitto >/dev/null 2>&1 &
#   aiko_registrar &
#   aiko_dashboard
#
#   Terminal session 2
#   ~~~~~~~~~~~~~~~~~~
#   ./aloha_honua.py &
#   mosquitto_pub -t ? -m "(aloha Pele)"  # replace with aiko_dasboard publish
#
# To Do
# ~~~~~
# - Shell script to start and stop
# - Dashboard "publish" command (1) topic suffic and (2) payload
# - CLI for Service list, publish, subscribe, linking together
#   - Service list filtered via list of ServiceFIlters
#   - Publish and/or subscribe to multiple Services via list of ServiceFilters
#   - Subscribe message filter, e.g regex for logging payload
#   - Monitor via "watch" command ?

from aiko_services import *

_LOGGER = aiko.logger(__name__)

class AlohaHonua(Actor):
    def __init__(self, implementations, name, protocol, tags, transport):
        implementations["Actor"].__init__(self,
            implementations, name, protocol, tags, transport)

    def get_logger(self):
        return _LOGGER

    def aloha(self, name):
        _LOGGER.info(f"Aloha honua {name} !")

if __name__ == "__main__":
    init_args = actor_args("aloha_honua", "*")
    aloha_honua = compose_instance(AlohaHonua, init_args)
    aiko.process.run()
