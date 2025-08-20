#!/usr/bin/env python3
#
# Starts an Actor called "AlohaHonua".
# This Actor can be discovered via the Aiko Services Registrar.
# The method "aloha(name)" can then be invoked remotely, see "aloha_honua_1.py"
#
# Usage
# ~~~~~
#   Terminal session 1 (when starting)
#   ~~~~~~~~~~~~~~~~~~
#   ../../../../scripts/system_start.sh  # Start mosquitto and Aiko Registrar
#
#   Terminal session 2
#   ~~~~~~~~~~~~~~~~~~
#   ./aloha_honua_0.py         # Start AlohaHonua Actor
#
#   Terminal session 3
#   ~~~~~~~~~~~~~~~~~~
#   ./aloha_honua_1.py [Pele]  # Remote function call to say "hello"
#
# Or, make a function call using an MQTT message ...
#   mosquitto_pub -m "(aloha Pele)" -t ?  # replace with aiko_dashboard publish
#
#   Terminal session 1 (when finished)
#   ~~~~~~~~~~~~~~~~~~
#   ../../../../scripts/system_stop.sh  # Stop mosquitto and Aiko Registrar
#
# To Do
# ~~~~~
# - None, yet !

import aiko_services as aiko

class AlohaHonua(aiko.Actor):
    def __init__(self, context):
        context.call_init(self, "Actor", context)
        print(f"MQTT topic: {self.topic_in}")

    def aloha(self, name):
        self.logger.info(f"Aloha {name} !")

if __name__ == "__main__":
    init_args = aiko.actor_args("aloha_honua")
    aloha_honua = aiko.compose_instance(AlohaHonua, init_args)
    aiko.process.run()
