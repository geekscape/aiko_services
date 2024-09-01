#!/usr/bin/env python3
#
# Usage
# ~~~~~
# export AIKO_LOG_LEVEL=DEBUG
# ./storage.py start
#
# ./storage.py test_command
#   Command: test_command(hello)
# ./storage.py test_request request_0
#   Response: [("request_0", [])]
#
# To Do
# ~~~~~
# - Compare "do_command()" and "do_request()" with HL AM / HL SSM
#   - Refactor into "service.py" ?
#
# - Consider GraphQL over MQTT !

from abc import abstractmethod
import click
import sqlite3

from aiko_services.main import *
from aiko_services.main.transport import *
from aiko_services.main.utilities import *

_VERSION = 0

ACTOR_TYPE = "storage"
PROTOCOL = f"{ServiceProtocol.AIKO}/{ACTOR_TYPE}:{_VERSION}"

_LOGGER = aiko.logger(__name__)
_TOPIC_RESPONSE = f"{aiko.topic_out}/storage_response"

# --------------------------------------------------------------------------- #

class Storage(Actor):
    Interface.default("Storage", "aiko_services.main.storage.StorageImpl")

    @abstractmethod
    def test_command(self, parameter):
        pass

    @abstractmethod
    def test_request(self, topic_path_response, request):
        pass

class StorageImpl(Storage):
    def __init__(self, context, database_pathname):
        context.get_implementation("Actor").__init__(self, context)

        self.connection = sqlite3.connect(database_pathname)

        self.share["database_pathname"] = database_pathname
        self.share["source_file"] = f"v{_VERSION}⇒ {__file__}"

    def test_command(self, parameter):
        print(f"Command: test_command({parameter})")

    def test_request(self, topic_path_response, request):
        aiko.message.publish(topic_path_response, "(item_count 1)")
        aiko.message.publish(topic_path_response, f"({request})")

# --------------------------------------------------------------------------- #

def do_command(actor_interface, command_handler, terminate=True):  # Refactor
    def actor_discovery_handler(command, service_details):
        if command == "add":
            event.remove_timer_handler(waiting_timer)
            topic_path = f"{service_details[0]}/in"
            actor = get_actor_mqtt(topic_path, actor_interface)
            command_handler(actor)
            if terminate:
                aiko.process.terminate()

    actor_discovery = ActorDiscovery(aiko.process)
    service_filter = ServiceFilter("*", "*", PROTOCOL, "*", "*", "*")
    actor_discovery.add_handler(actor_discovery_handler, service_filter)
    event.add_timer_handler(waiting_timer, 0.5)
    aiko.process.run()

item_count = 0
items_received = 0
response = []

def do_request(actor_interface, request_handler, response_handler):  # Refactor
    def topic_response_handler(_aiko, topic, payload_in):
        global item_count, items_received, response

        command, parameters = parse(payload_in)
        if command == "item_count" and len(parameters) == 1:
            item_count = int(parameters[0])
            items_received = 0
            response = []
        elif items_received < item_count:
            response.append((command, parameters))
            items_received += 1
            if items_received == item_count:
                response_handler(response)

    aiko.process.add_message_handler(topic_response_handler, _TOPIC_RESPONSE)
    do_command(actor_interface, request_handler, terminate=False)

def waiting_timer():
    event.remove_timer_handler(waiting_timer)
    print(f"Waiting for {ACTOR_TYPE}")

@click.group()

def main():
    pass

@main.command(help="Start Storage")
@click.argument("database_pathname", default="aiko_storage.db")

def start(database_pathname):
    tags = ["ec=true"]
    init_args = actor_args(ACTOR_TYPE, protocol=PROTOCOL, tags=tags)
    init_args["database_pathname"] = database_pathname
    storage = compose_instance(StorageImpl, init_args)
    storage.run()

@main.command(name="test_command")

def test_command():
    do_command(Storage, lambda storage: storage.test_command("hello"))

@main.command(name="test_request")
@click.argument("request")

def test_request(request):
    def response_handler(response):
        print(f"Response: {response}")
        import time; time.sleep(1)

    do_request(Storage,
        lambda storage: storage.test_request(_TOPIC_RESPONSE, request),
        response_handler
    )

if __name__ == "__main__":
    main()

# --------------------------------------------------------------------------- #
