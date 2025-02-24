#!/usr/bin/env python3
#
# Usage
# ~~~~~
# AIKO_LOG_LEVEL=DEBUG ./storage.py start &
#
# AIKO_LOG_LEVEL=DEBUG ./storage.py test_command [argument_0]
#   Storage command: test_command(argument_0)
#
# AIKO_LOG_LEVEL=DEBUG ./storage.py test_request [request_0]
#   Storage response: [("request_0", [])]
#
# To Do
# ~~~~~
# - Consider GraphQL over MQTT !

from abc import abstractmethod
import click
import sqlite3

from aiko_services.main import *

_VERSION = 0

ACTOR_TYPE = "storage"
PROTOCOL = f"{SERVICE_PROTOCOL_AIKO}/{ACTOR_TYPE}:{_VERSION}"

_LOGGER = aiko.logger(__name__)
_RESPONSE_TOPIC = f"{aiko.topic_in}"

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
        print(f"Storage command: test_command({parameter})")

    def test_request(self, topic_path_response, request):
        aiko.message.publish(topic_path_response, "(item_count 1)")
        aiko.message.publish(topic_path_response, f"({request})")

# --------------------------------------------------------------------------- #

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

@main.command(name="test_command", help="Test Storage invoke command")
@click.argument("argument", default="argument_0", required=False)

def test_command(argument):
    do_command(Storage, ServiceFilter("*", "*", PROTOCOL, "*", "*", "*"),
        lambda storage: storage.test_command(argument), terminate=True)
    aiko.process.run()

@main.command(name="test_request", help="Test Storage invoke request")
@click.argument("request", default="request_0", required=False)

def test_request(request):
    def response_handler(response):
        print(f"Storage response: {response}")

    do_request(Storage, ServiceFilter("*", "*", PROTOCOL, "*", "*", "*"),
        lambda storage: storage.test_request(_RESPONSE_TOPIC, request),
        response_handler, _RESPONSE_TOPIC, terminate=True)
    aiko.process.run()

if __name__ == "__main__":
    main()

# --------------------------------------------------------------------------- #
