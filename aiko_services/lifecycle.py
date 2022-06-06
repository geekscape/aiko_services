#!/usr/bin/env python3
#
# Usage
# ~~~~~
# LOG_LEVEL=DEBUG ./lifecycle.py manager [client_count]
#
# LOG_LEVEL=DEBUG ./lifecycle.py client client_id lifecycle_manager_topic
#
# To Do: LifeCycleManager
# ~~~~~~~~~~~~~~~~~~~~~~~
# - Implement "lifecycle_manager.delete(lifecycle_client_id)"
#
# - BUG: Fix "aiko_services/event.py" ...
#        With multiple timer handlers using the same handler function,
#        then remove_timer_handler() make remove the wrong one.
#        Need an identifier to specific exactly which handler instance
#
# - CRITICAL: *** Check all MQTT messages for excessive quantity ***
#   - Every LifeCycleClient is using ActorDiscovery/ServiceCache and
#     receiving notification on every other LifeCycleClient on the
#     Registrar topic "/out" ?!?
#
# - PERFORMANCE: Why does LifeCycleClient creation on AikoDashboard appear
#   so delayed / chunky ?  Where are the bottlenecks ?
#
# - PRIORITY: Optionally replace ProcessManager with Ray to create Actor
#
# - Should be able to create LifeCycleClients as either separate processes
#   or within the same process.  When the LifeCycleClients are all running
#   in the same process ... that could the same or a different to the
#   LifeCycleManager.
#
# - The LifeCycleManager / LifeCycleClient can be generalized to be
#   one manager Actor creates other client Actor(s) and then uses
#   ECProducer / ECConsumer to listen to specified variable(s),
#   not just the "lifecycle" state
#
# - Use ProcessManager to monitor state of LifeCycleClient process
#   - Use "process_exit_handler" to manage unexpected process termination
#
# - Refactor Handshake out as more generally useful concept,
#   e.g as part of ServiceDiscovery or ActorDiscovery
#
# To Do: LifeCycleClient
# ~~~~~~~~~~~~~~~~~~~~~~
# - LifeCycleClient exits when its manager exits

import click
import time

from aiko_services import *
from aiko_services.transport import *
from aiko_services.utilities import *

CLIENT_SHELL_COMMAND = "./lifecycle.py"

ACTOR_TYPE_LIFECYCLE_MANAGER = "LifeCycleManager"
PROTOCOL_LIFECYCLE_MANAGER = f"{AIKO_PROTOCOL_PREFIX}/lifecyclemanager:0"

ACTOR_TYPE_LIFECYCLE_CLIENT = "LifeCycleClient"
PROTOCOL_LIFECYCLE_CLIENT = f"{AIKO_PROTOCOL_PREFIX}/lifecycleclient:0"

_HANDSHAKE_LEASE_TIME = 10  # seconds or 120 seconds for lots of clients
_LOGGER = aiko.logger(__name__)

#---------------------------------------------------------------------------- #

class HandshakeLease(Lease):
    def __init__(
        self, lease_time, handshake_id, handler, lease_expired_handler):

        super().__init__(
            lease_time, handshake_id,
            lease_expired_handler=lease_expired_handler)
        self.handler = handler

class LifeCycleClientDetails:
    def __init__(self, client_id, topic_path, ec_consumer=None):
        self.client_id = client_id
        self.ec_consumer = ec_consumer
        self.topic_path = topic_path

class LifeCycleManager:
    def __init__(self, lifecycle_client_change_handler, ec_producer=None):
        self.lifecycle_client_change_handler = lifecycle_client_change_handler
        self.actor_discovery = None
        self.client_count = 0
        self.ec_producer = ec_producer
        self.handshakes = {}
        self.lifecycle_clients = {}
        self.process_manager = ProcessManager()
        aiko.add_message_handler(
            self._topic_control_handler, aiko.public.topic_control)

        if self.ec_producer is not None:
            self.ec_producer.update("lifecycle_manager.clients_active", 0)

    def create(self, command, arguments):
        client_id = f"client_{self.client_count}"
        self.client_count += 1
        arguments = ["client", client_id] + arguments
        self.process_manager.create(client_id, command, arguments)
        handshake = Lease(
            _HANDSHAKE_LEASE_TIME, client_id,
            lease_expired_handler=self._lease_expired_handler)
        self.handshakes[client_id] = handshake
        return client_id

    def _topic_control_handler(self, _aiko, topic, payload_in):
        command, parameters = parse(payload_in)

        if command == "add_client":
            lifecycle_client_topic_path = parameters[0]
            client_id = parameters[1]
            if client_id not in self.handshakes:
                _LOGGER.debug(f"LifeCycleClient {client_id} unknown")
            else:
                self.handshakes[client_id].terminate()
                del self.handshakes[client_id]
                _LOGGER.debug(f"LifeCycleClient {client_id} responded")

                topic_paths = [lifecycle_client_topic_path]
                self.filter = ServiceFilter(topic_paths, "*", "*", "*", "*")
                self.actor_discovery = ActorDiscovery() # TODO: Use ServiceDiscovery
                self.actor_discovery.add_handler(
                    self._service_change_handler, self.filter)

                ec_consumer = ECConsumer(
                    client_id, {},
                    f"{lifecycle_client_topic_path}/control", "(lifecycle)")
                ec_consumer.add_handler(self.lifecycle_client_change_handler)
                lifecycle_client_details = LifeCycleClientDetails(
                    client_id, lifecycle_client_topic_path, ec_consumer)
                self.lifecycle_clients[client_id] = lifecycle_client_details
                if self.ec_producer is not None:
                    self.ec_producer.update(
                        "lifecycle_manager.clients_active",
                        len(self.lifecycle_clients))
                #   self.ec_producer.update(
                #       f"lifecycle_manager.{client_id}",
                #       lifecycle_client_topic_path)

    def _service_change_handler(self, command, service_details):
        if command == "remove":
            lifecycle_client_topic_path = service_details[0]
            lifecycle_clients = list(self.lifecycle_clients.values())
            for lifecycle_client in lifecycle_clients:
                if lifecycle_client.topic_path == lifecycle_client_topic_path:
                    if lifecycle_client.ec_consumer:
                        lifecycle_client.ec_consumer.terminate()
                        lifecycle_client.ec_consumer = None
                    client_id = lifecycle_client.client_id
                    del self.lifecycle_clients[client_id]
                    if self.ec_producer is not None:
                        self.ec_producer.update(
                            "lifecycle_manager.clients_active",
                            len(self.lifecycle_clients))
                    #   self.ec_producer.remove(
                    #       f"lifecycle_manager.{client_id}")

    def _lease_expired_handler(self, client_id):
        if client_id in self.handshakes:
            del self.handshakes[client_id]
        self.process_manager.delete(client_id, kill=True)
        _LOGGER.debug(f"LifeCycleClient {client_id} handshake failed")

class TestLifeCycleManager(Actor):
    def __init__(self, actor_name, actor_count):
        super().__init__(actor_name)
        self.actor_count = actor_count
        aiko.set_protocol(PROTOCOL_LIFECYCLE_MANAGER) # TODO: Move into actor.py

        self.state = {"lifecycle": "initialize", "log_level": "info"}
        self.ec_producer = ECProducer(self.state)

        self.lifecycle_manager = LifeCycleManager(
            self._lifecycle_client_change_handler, self.ec_producer)

        aiko.public.connection.add_handler(self._connection_state_handler)

    def _connection_state_handler(self, connection, connection_state):
        if connection.is_connected(ConnectionState.REGISTRAR):
            for count in range(self.actor_count):
                lifecycle_client_id = self.lifecycle_manager.create(
                    CLIENT_SHELL_COMMAND, [aiko.public.topic_path])
                time.sleep(0.01)

    def _lifecycle_client_change_handler(
        self, client_id, command, item_name, item_value):

        _LOGGER.debug(f"LifeCycleClient: {client_id}: {command} {item_name} {item_value}")

#---------------------------------------------------------------------------- #

class LifeCycleClient:
    def __init__(
        self, actor_name, client_id, lifecycle_manager_topic, ec_producer):

        self.actor_name = actor_name
        self.client_id = client_id
        self.ec_producer = ec_producer
        self.ec_producer.update(
            "lifecycle_client.lifecycle_manager_topic", lifecycle_manager_topic)
        aiko.public.connection.add_handler(self._connection_handler)

    def _connection_handler(self, connection, connection_state):
        lifecycle_manager_topic = self.ec_producer.get(
            "lifecycle_client.lifecycle_manager_topic")
        if connection.is_connected(ConnectionState.REGISTRAR):
            topic = f"{lifecycle_manager_topic}/control"
            payload_out = "(add_client "                \
                          f"{aiko.public.topic_path} "  \
                          f"{self.client_id})"
            aiko.public.message.publish(topic, payload_out)

class TestLifeCycleClient(Actor):
    def __init__(self, actor_name, client_id, lifecycle_manager_topic):
        super().__init__(actor_name)
        aiko.set_protocol(PROTOCOL_LIFECYCLE_CLIENT)  # TODO: Move into actor.py

        self.state = {"lifecycle": "initialize", "log_level": "info"}
        self.ec_producer = ECProducer(self.state)

        self.lifecycle_client = LifeCycleClient(
            actor_name, client_id, lifecycle_manager_topic, self.ec_producer)

# TODO: When scaling up to lots of LifeCycleClient, every LifeCycleClient
# receiving the ServiceDetails for every other LifeCycleClient is too much.
# - Registrar should provide a filter that limits to the requested topic path
#   Use below to be notified only when that Service is added or removed
# - Could also filter on the LifeCycleManager protocol to limit results
#
#       filter = ServiceFilter([lifecycle_manager_topic], "*", "*", "*", "*")
#       self.actor_discovery = ActorDiscovery()
#       self.actor_discovery.add_handler(
#           self._lifecycle_manager_change_handler, filter)
#
#   def _lifecycle_manager_change_handler(self, command, service_details):
#       if command == "remove":
#           self.delete()

#---------------------------------------------------------------------------- #

@click.group()
def main():
    pass

@main.command(help=("LifeCycleManager Actor"))
@click.argument("count", default=1)
def manager(count):
    actor_name = f"{aiko.public.topic_path}.{ACTOR_TYPE_LIFECYCLE_MANAGER}"
    aiko.add_tags([f"actor={actor_name}"])  # WIP: Actor name
    lifecycle_manager = TestLifeCycleManager(actor_name, count)
    lifecycle_manager.run()

@main.command(help=("LifeCycleClient Actor"))
@click.argument("client_id", default=None)
@click.argument("lifecycle_manager_topic", default=None)
def client(client_id, lifecycle_manager_topic):
    actor_name = f"{aiko.public.topic_path}.{ACTOR_TYPE_LIFECYCLE_CLIENT}"
    aiko.add_tags([f"actor={actor_name}"])  # WIP: Actor name
    life_cycle_client = TestLifeCycleClient(
        actor_name, client_id, lifecycle_manager_topic)
    life_cycle_client.run()

if __name__ == "__main__":
    main()

#---------------------------------------------------------------------------- #
