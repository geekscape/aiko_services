#!/usr/bin/env python3
#
# Combines "aloha_honua_0.py" and "aloha_honua_1.py" into a single file.
# Also, adds the method "hoomaka()", which stops the AlohaHonua Actor.
#
# Usage
# ~~~~~
#   Terminal session 1
#   ~~~~~~~~~~~~~~~~~~
#   ../../../../scripts/system_start.sh  # Start mosquitto and Aiko Registrar
#
#   Terminal session 2
#   ~~~~~~~~~~~~~~~~~~
#   ./aloha_honua_2.py start         # Start AlohaHonua Actor
#
#   Terminal session 3
#   ~~~~~~~~~~~~~~~~~~
#   ./aloha_honua_2.py aloha [Pele]  # Remote function call to say "hello"
#   ./aloha_honua_2.py hoomaka       # Remote function call to stop AlohaHonua
#
#   Terminal session 1 (when finished)
#   ~~~~~~~~~~~~~~~~~~
#   ../../../../scripts/system_stop.sh  # Stop mosquitto and Aiko Registrar
#
# To Do
# ~~~~~
# - None, yet !

import click

import aiko_services as aiko

# --------------------------------------------------------------------------- #

class AlohaHonua(aiko.Actor):
    def __init__(self, context):
        context.get_implementation("Actor").__init__(self, context)
        print(f"MQTT topic: {self.topic_in}")

    def aloha(self, name):
        self.logger.info(f"Aloha {name} !")

    def hoomaka(self):
        self.logger.info(f"Aloha 👋")
        raise SystemExit()

# --------------------------------------------------------------------------- #

@click.group

def main():
    pass

@main.command(help="Start AlohaHonua Actor")

def start():
    init_args = aiko.actor_args("aloha_honua")
    aloha_honua = aiko.compose_instance(AlohaHonua, init_args)
    aiko.process.run()

@main.command(help='Remote call AlohaHonua Actor to say "hello"')
@click.argument("name", default="hoaloha", required=False)

def aloha(name):
    aiko.do_command(
        AlohaHonua,
        aiko.ServiceFilter("*", "aloha_honua", "*", "*", "*", "*"),
        lambda aloha_honua: aloha_honua.aloha(name),
        terminate=True)
    aiko.process.run()

@main.command(help="Remote call AlohaHonua to stop the Actor")

def hoomaka():
    aiko.do_command(
        AlohaHonua,
        aiko.ServiceFilter("*", "aloha_honua", "*", "*", "*", "*"),
        lambda aloha_honua: aloha_honua.hoomaka(),
        terminate=True)
    aiko.process.run()

if __name__ == "__main__":
    main()

# --------------------------------------------------------------------------- #
