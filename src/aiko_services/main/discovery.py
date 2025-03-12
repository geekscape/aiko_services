#!/usr/bin/env python3
#
# Usage
# ~~~~~
# AIKO_LOG_LEVEL=DEBUG ./discovery.py start &
#
# AIKO_LOG_LEVEL=DEBUG ./discovery.py test_discovery
#   DiscoveryTest add:    name: topic_path
#   DiscoveryTest remove: name: topic_path
#
# AIKO_LOG_LEVEL=DEBUG ./discovery.py test_command [argument_0]
#   DiscoveryTest command: test_command(argument_0)
#
# AIKO_LOG_LEVEL=DEBUG ./discovery.py test_request [request_0]
#   DiscoveryTest response: [("request_0", [])]
#
# To Do
# ~~~~~
# * Improve DiscoveryImpl.test_request() by implementing DiscoveryRequest
# * Improve DiscoveryImpl.test_request() to handle multiple response items
#
# - Consolidate "proxy.py" (used by "actor.py") and "get_service_proxy()"
#   - See "_proxy_post_message()" below
#
# - Design and implement Dependency
# - Refactor ServiceDiscovery into an Interface and Implementation ?
#
# * Make Service/ActorDiscovery and get_actor_mqtt() more convenient
#   * Integrate with do_discovery(), do_command() and do_request()
#   * Also, support a cache or remote Service/Actor proxies, use LRUCache
#
# * Improve get_actor_mqtt() and make_proxy_mqtt() to be re-usable
#   * Can just replace target_service_topic_in or target_topic_in
#     without have to call get_public_methods() on the Interface or Class
#
# * Refactor current code into ServiceDiscovery
#   * ServiceDiscovery should handle multiple simultaneous ServiceFilters
#
# * Design Pattern for creating Actors of different types, e.g MQTT, ROS2 or Ray
#
# - Replace Actor topic with Actor name ... and name can be the topic
#   - Will need to support multiple Actors running in the same process !
#
# * Once Service protocol matching is properly implemented ...
#     Replace Service tag "actor=name" marking Actors with
#     matching via Service protocol "{SERVICE_PROTOCOL_AIKO}/actor:0"
#
#------------------------------------------------------------------------------
# def create_actor(actor_class, actor_type, actor_uuid,
#     actor_check = True, actor_init_args = {}, daemon = False,
#     max_concurrency = _MAX_CONCURRENCY, resources = None):
#
# delete_actor(name, wait = False, force = False):
#
# get_actor(name,
#     exit_not_found = False, fail_not_found = True, wait_time = None):

from abc import abstractmethod
import click
from inspect import getmembers, isfunction

from aiko_services.main import *
from aiko_services.main.utilities import *

__all__ = [
    "ServiceDiscovery", "ActorDiscovery",
    "PipelineElementDiscovery", "PipelineDiscovery",
    "do_command", "do_discovery", "do_request", "get_service_proxy"
]

_VERSION = 0

ACTOR_TYPE = "discovery"
PROTOCOL = f"{SERVICE_PROTOCOL_AIKO}/{ACTOR_TYPE}:{_VERSION}"

_RESPONSE_TOPIC = f"{aiko.topic_in}"

# --------------------------------------------------------------------------- #

class ServiceDiscovery:
    def __init__(self, service):
        self.services_cache = services_cache_create_singleton(service)

    def add_handler(self, service_change_handler, filter):
        self.services_cache.add_handler(service_change_handler, filter)

    def remove_handler(self, service_change_handler, filter):
        self.services_cache.remove_handler(service_change_handler, filter)

#   def terminate(self):
#       self.stop()

# TODO: Update to use ServiceFields.name, rather than "actor=name" tag
#   def get_actor_mqtt(self, name):
#       actor_topic = ".".join(name.split(".")[:-1])  # WIP: Actor name
#       services = self.services_cache.get_services()
#       raise Exception("Broken: get_actor_mqtt()")  # REVIEW FIXME
#       services = services.filter_by_name(name)
#       actor = services.get(name)
#       return actor

# TODO: Currently unused
#   def share_actor_mqtt(self, filter):
#       services = self.services_cache.get_services()
#       actors = services.filter_by_attributes(filter)
#       return actors

class ActorDiscovery(ServiceDiscovery):
    pass

class PipelineElementDiscovery(ActorDiscovery):
    pass

class PipelineDiscovery(PipelineElementDiscovery):
    pass

# def _proxy_post_message(
#   proxy_name, actual_object, actual_function,
#   actual_function_name, *args, **kwargs):
#
#   actual_object._post_message.remote(
#       actor.Topic.IN, actual_function_name, args
#   )

# --------------------------------------------------------------------------- #

# def create_actor_mqtt(
#   actor_class, name, actor_init_args={}, resources=None, daemon = True):
#   pass

# def delete_actor_mqtt(actor):
#   actor.terminate()

def _get_public_method_names(protocol_class):
    if isinstance(protocol_class, str):
        raise ValueError(
            f"{protocol_class} is a String, should be a Class reference ?")
    public_method_names = [
        method_name
        for method_name, method in getmembers(protocol_class, isfunction)
        if not method_name.startswith("_")
    ]
    if len(public_method_names) == 0:
        raise ValueError(f"Class {protocol_class} has no public methods")
    return public_method_names

def _make_service_proxy(target_topic_in, public_method_names):
    class ServiceRemoteProxy(): pass

    def _proxy_send_message(method_name):
        def closure(*args, **kwargs):
            parameters = args if not kwargs else [args[0], kwargs]
            payload = generate(method_name, parameters)
            aiko.message.publish(target_topic_in, payload)
        return closure

    service_remote_proxy = ServiceRemoteProxy()
    for method_name in public_method_names:
        setattr(service_remote_proxy,
            method_name, _proxy_send_message(method_name))
    return service_remote_proxy

def get_service_proxy(service_topic, protocol_class):
    public_methods = _get_public_method_names(protocol_class)
    service_proxy = _make_service_proxy(service_topic, public_methods)
    return service_proxy

# --------------------------------------------------------------------------- #

def do_discovery(
    service_interface, service_filter,
    discovery_add_handler=None, discovery_remove_handler=None):

    def service_discovery_handler(command, service_details):
        if command == "add":
            topic_path = f"{service_details[0]}/in"
            service = get_service_proxy(topic_path, service_interface)
            if discovery_add_handler:
                discovery_add_handler(service_details, service)
        elif command == "remove":
            if discovery_remove_handler:
                discovery_remove_handler(service_details)

    service_discovery = ServiceDiscovery(aiko.process)
    service_discovery.add_handler(service_discovery_handler, service_filter)
    return service_discovery, service_discovery_handler

def do_command(
    service_interface, service_filter,
    command_handler, terminate=False):

    def discovery_add_handler(service_details, service):
        event.remove_timer_handler(waiting_timer_handler)
        command_handler(service)
        if terminate:
            aiko.process.terminate()

    def waiting_timer_handler():
        event.remove_timer_handler(waiting_timer_handler)
        print(f"Waiting for {service_filter.summary()}")

    event.add_timer_handler(waiting_timer_handler, 0.5)
    do_discovery(service_interface, service_filter, discovery_add_handler)

def do_request(
    service_interface, service_filter,
    request_handler, response_handler, response_topic, terminate=False):

    item_count = 0
    items_received = 0
    response = []

# TODO: The "response_handler" should implement the DiscoveryRequest interface
#       Use remote function calls, rather than message payload parsing !

    def response_handler_internal(_aiko, topic, payload_in):
        nonlocal item_count, items_received, response

        command, parameters = parse(payload_in)
        if command == "item_count" and len(parameters) == 1:
            item_count = int(parameters[0])
            items_received = 0
            response = []
        elif command == "response" and items_received < item_count:
            response.append(parameters)
            items_received += 1
            if items_received == item_count:
                response_handler(response)
                if terminate:
                    aiko.process.terminate()

    aiko.process.add_message_handler(response_handler_internal, response_topic)
    do_command(
        service_interface, service_filter, request_handler, terminate=False)

# --------------------------------------------------------------------------- #

class DiscoveryRequest(Actor):
    Interface.default("DiscoveryRequest", None)

    @abstractmethod
    def item_count(self, count):
        pass

    @abstractmethod
    def response(self, payload):
        pass

class DiscoveryTest(Actor):
    Interface.default(
        "DiscoveryTest", "aiko_services.main.discovery.DiscoveryTestImpl")

    @abstractmethod
    def test_command(self, parameter):
        pass

    @abstractmethod
    def test_request(self, topic_path_response, request):
        pass

class DiscoveryTestImpl(DiscoveryTest):
    def __init__(self, context):
        context.get_implementation("Actor").__init__(self, context)
        self.share["source_file"] = f"v{_VERSION}⇒ {__file__}"

    def test_command(self, parameter):
        print(f"DiscoveryTest command: test_command({parameter})")

    def test_request(self, topic_path_response, request):
        service = get_service_proxy(topic_path_response, DiscoveryRequest)
        service.item_count(1)
        service.response(request)

# --------------------------------------------------------------------------- #

@click.group()

def main():
    pass

@main.command(help="DiscoveryTest start")

def start():
    tags = ["ec=true"]
    init_args = actor_args(ACTOR_TYPE, protocol=PROTOCOL, tags=tags)
    discovery = compose_instance(DiscoveryTestImpl, init_args)
    discovery.run()

@main.command(name="test_discovery", help="DiscoveryTest add / remove Service")

def test_discovery():
    def discovery_add_handler(service_details, service):
        print(
            f"DiscoveryTest add:    {service_details[1]}: {service_details[0]}")

    def discovery_remove_handler(service_details):
        print(
            f"DiscoveryTest remove: {service_details[1]}: {service_details[0]}")

    service_discovery, service_discovery_handler =  \
        do_discovery(
            DiscoveryTest, ServiceFilter("*", "*", "*", "*", "*", "*"),
            discovery_add_handler, discovery_remove_handler)
    aiko.process.run()

@main.command(name="test_command", help="DiscoveryTest invoke command")
@click.argument("argument", default="argument_0", required=False)

def test_command(argument):
    do_command(DiscoveryTest, ServiceFilter("*", "*", PROTOCOL, "*", "*", "*"),
        lambda discovery: discovery.test_command(argument), terminate=True)
    aiko.process.run()

@main.command(name="test_request", help="DiscoveryTest invoke request")
@click.argument("request", default="request_0", required=False)

def test_request(request):
    def response_handler(response):
        print(f"DiscoveryTest response: {response}")

    do_request(DiscoveryTest, ServiceFilter("*", "*", PROTOCOL, "*", "*", "*"),
        lambda discovery: discovery.test_request(_RESPONSE_TOPIC, request),
        response_handler, _RESPONSE_TOPIC, terminate=True)
    aiko.process.run()

if __name__ == "__main__":
    main()

# --------------------------------------------------------------------------- #
