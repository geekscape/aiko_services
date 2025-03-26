#!/usr/bin/env python3
#
# Discovers the remote AlohaHonua Actor, see "aloha_honua_0.py".
# Will wait until that Actor is found.
# Object reference "aloha_honua" can be used to make remote function calls.
# Then "aloha_honua" is used to make a remote function call, as follows ...
#     aloha_honua.aloha(name)
#
# This functionality is conveniently provided by "aiko.do_command()".
# A "command" is a function call that doesn't return a value.
#
# Usage
# ~~~~~
#   Terminal session 1
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
#   Terminal session 1 (when finished)
#   ~~~~~~~~~~~~~~~~~~
#   ../../../../scripts/system_stop.sh  # Stop mosquitto and Aiko Registrar
#
# To Do
# ~~~~~
# - None, yet !

import click

import aiko_services as aiko
from aloha_honua_0 import AlohaHonua

@click.command("main", help="Remote call AlohaHonua Actor")
@click.argument("name", default="hoaloha", required=False)

def main(name):
    aiko.do_command(
        AlohaHonua,
        aiko.ServiceFilter("*", "aloha_honua", "*", "*", "*", "*"),
        lambda aloha_honua: aloha_honua.aloha(name),
        terminate=True)

    aiko.process.run()

if __name__ == "__main__":
    main()
