#!/usr/bin/env python3
#
# Builds on "aloha_honua_2.py".
# Replaces "do_command()" with "do_request()", which provides a response.
#
# A "request" is a function call that returns a response on the provided topic.
#
# Usage
# ~~~~~
#   Terminal session 1
#   ~~~~~~~~~~~~~~~~~~
#   ../../../../scripts/system_start.sh  # Start mosquitto and Aiko Registrar
#
#   Terminal session 2
#   ~~~~~~~~~~~~~~~~~~
#   ./aloha_honua_3.py start         # Start AlohaHonua Actor
#
#   Terminal session 3
#   ~~~~~~~~~~~~~~~~~~
#   ./aloha_honua_3.py aloha [Pele]  # Remote function call to say "hello"
#   ./aloha_honua_3.py hoomaka       # Remote function call to stop AlohaHonua
#
#   Terminal session 1 (when finished)
#   ~~~~~~~~~~~~~~~~~~
#   ../../../../scripts/system_stop.sh  # Stop mosquitto and Aiko Registrar
#
# To Do
# ~~~~~
# - None, yet !

from abc import abstractmethod
import click

import aiko_services as aiko

_RESPONSE_TOPIC = aiko.aiko.topic_in

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

    def request(self, topic_path_response, request):
        service = aiko.get_service_proxy(
            topic_path_response, AlohaHonuaResponse)
        service.item_count(1)
        service.response(f"Aloha {request} 👋")

class AlohaHonuaResponse(aiko.Actor):
    @abstractmethod
    def item_count(self, count):
        pass

    @abstractmethod
    def response(self, payload):
        pass

# --------------------------------------------------------------------------- #

@click.group

def main():
    pass

@main.command(help="Start AlohaHonua Actor")

def start():
    init_args = aiko.actor_args("aloha_honua")
    aloha_honua = aiko.compose_instance(AlohaHonua, init_args)
    aiko.process.run()

@main.command(help='Remote request AlohaHonua Actor to say "hello"')
@click.argument("name", default="hoaloha", required=False)

def aloha(name):
    def response_handler(response):
        print(f"Response: {response[0][0]}")

    aiko.do_request(
        AlohaHonua,
        aiko.ServiceFilter("*", "aloha_honua", "*", "*", "*", "*"),
        lambda aloha_honua: aloha_honua.request(_RESPONSE_TOPIC, name),
        response_handler, _RESPONSE_TOPIC, terminate=True)

    aiko.process.run(loop_when_no_handlers=True)  # Keep event loop running

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
