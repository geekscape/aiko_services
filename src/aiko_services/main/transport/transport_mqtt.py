# To Do
# ~~~~~
# * Make Service/ActorDiscovery and get_actor_mqtt() more convenient
#   * Integrate with do_command() and do_request()
#   * Also, support a cache or remote Service/Actor proxies, use LRUCache
#
# * Improve get_actor_mqtt() and make_proxy_mqtt() to be re-usable
#   * Can just replace target_service_topic_in or target_topic_in
#     without have to call get_public_methods() on the Interface or Class
#
# * Rename TransportMQTT --> MQTTActor
#   Rename "transport_mqtt.py" --> "mqtt_actor.py"
#
# * Refactor current code into ServiceDiscovery
#   * ServiceDiscovery should handle multiple simultaneous ServiceFilters
#   * Rename get_actor_mqtt() to be get_service_mqtt()
#
# * Design Pattern for creating Actors of different types, e.g MQTT or Ray
#
# - Replace Actor topic with Actor name ... and name can be the topic
#   - Will need to support multiple Actors running in the same process !
#
# * Once Service protocol matching is properly implemented ...
#     Replace Service tag "actor=name" marking Actors with
#     matching via Service protocol "{ServiceProtocol.AIKO}/actor:0"
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
from inspect import getmembers, isfunction

from aiko_services.main import *
from aiko_services.main.utilities.parser import generate

__all__ = [
    "TransportMQTT", "TransportMQTTImpl","ActorDiscovery", "get_actor_mqtt"
]

_LOGGER = aiko.logger(__name__)

class TransportMQTT(Actor):
    Interface.default("TransportMQTT",
        "aiko_services.main.transport.transport_mqtt.TransportMQTTImpl")

class TransportMQTTImpl(TransportMQTT):
    def __init__(self, context):
        context.get_implementation("Actor").__init__(self, context)

    def terminate(self):
        self.stop()

# def _proxy_post_message(
#   proxy_name, actual_object, actual_function,
#   actual_function_name, *args, **kwargs):
#
#   actual_object._post_message.remote(
#       actor.Topic.IN, actual_function_name, args
#   )

class ServiceDiscovery:  # Move to registrar.py or share.py ?
    pass                 # Refactor after ActorDiscovery starts to work properly

class ActorDiscovery(ServiceDiscovery):  # Move to actor.py or share.py ?
    def __init__(self, service):
        self.services_cache = services_cache_create_singleton(service)

    def add_handler(self, service_change_handler, filter):
        self.services_cache.add_handler(service_change_handler, filter)

    def remove_handler(self, service_change_handler, filter):
        self.services_cache.remove_handler(service_change_handler, filter)

# TODO: Update to use ServiceFields.name, rather than "actor=name" tag
    def get_actor_mqtt(self, name):
        actor_topic = ".".join(name.split(".")[:-1])  # WIP: Actor name
        services = self.services_cache.get_services()
        raise Exception("Broken: get_actor_mqtt()")  # REVIEW FIXME
        services = services.filter_by_name(name)
        actor = services.get(name)
        return actor

# TODO: Currently unused
#   def share_actor_mqtt(self, filter):
#       services = self.services_cache.get_services()
#       actors = services.filter_by_attributes(filter)
#       return actors

# -----------------------------------------------------------------------------

def create_actor_mqtt(
        actor_class,
        name,
        actor_init_args={},
        resources=None,
        daemon = True):
    pass

def delete_actor_mqtt(actor):
    actor.terminate()

def get_public_methods(protocol_class):
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

def make_proxy_mqtt(target_topic_in, public_method_names):
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

def get_actor_mqtt(target_service_topic_in, protocol_class):
    public_methods = get_public_methods(protocol_class)
    actor_proxy = make_proxy_mqtt(target_service_topic_in, public_methods)
    return actor_proxy

# -----------------------------------------------------------------------------
