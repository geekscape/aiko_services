#!/usr/bin/env python3
#
# Usage
# ~~~~~
# ./lifecycle.py manager [client_count]
#
# ./lifecycle.py client client_id lifecycle_manager_topic
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
#   - Every LifeCycleClient is using ActorDiscovery/ServicesCache and
#     receiving notification on every other LifeCycleClient on the
#     Registrar topic "/out" ?!?
#
# - PERFORMANCE: Why does LifeCycleClient creation on AikoDashboard appear
#   so delayed / chunky ?  Where are the bottlenecks ?
#
# - BUG: LifeCycleManager and LifeCycleClient should handle degradation of
#   network (ConnectionState changes) and/or lease expiring.  Should LCM
#   recreate LCCs or terminate ?  Should LCC terminate ?
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

from abc import abstractmethod
import click
import os
import time
from typing import Dict, List

from aiko_services.main import *
from aiko_services.main.transport import *
from aiko_services.main.utilities import *

CLIENT_SHELL_COMMAND = "./lifecycle.py"

_VERSION = 0

ACTOR_TYPE_LIFECYCLE_MANAGER = "lifecycle_manager"
PROTOCOL_LIFECYCLE_MANAGER =  \
    f"{SERVICE_PROTOCOL_AIKO}/{ACTOR_TYPE_LIFECYCLE_MANAGER}:{_VERSION}"

ACTOR_TYPE_LIFECYCLE_CLIENT = "lifecycle_client"
PROTOCOL_LIFECYCLE_CLIENT =  \
    f"{SERVICE_PROTOCOL_AIKO}/{ACTOR_TYPE_LIFECYCLE_CLIENT}:{_VERSION}"

_DELETION_LEASE_TIME_DEFAULT = 30  # seconds
_HANDSHAKE_LEASE_TIME_DEFAULT = 30  # seconds

_AIKO_LOG_LEVEL_LIFECYCLE = os.environ.get("AIKO_LOG_LEVEL_LIFECYCLE", "INFO")
_LOGGER = aiko.logger(__name__, log_level=_AIKO_LOG_LEVEL_LIFECYCLE)

# ---------------------------------------------------------------------------- #
# Over time, intend to utilise the Handshake concept more broadly
#
#class HandshakeLease(Lease):
#    def __init__(
#        self, lease_time, handshake_id, handler, lease_expired_handler):
#
#        super().__init__(
#            lease_time, handshake_id,
#            lease_expired_handler=lease_expired_handler)
#        self.handler = handler

class LifeCycleClientDetails:
    def __init__(self, client_id, topic_path, ec_consumer=None):
        self.client_id = client_id
        self.ec_consumer = ec_consumer
        self.topic_path = topic_path

class LifeCycleManager(ServiceProtocolInterface):
    Interface.default("LifeCycleManager",
        "aiko_services.main.lifecycle.LifeCycleManagerImpl")

    @abstractmethod
    def lcm_create_client(self, parameters=None):
        """Public method for creating clients

        Handles bookkeeping of clients, calling self._lcm_create_client
        for the creation step
        """

    @abstractmethod
    def lcm_delete_client(self, client_id):
        """Public method for deleting clients

        Handles bookkeeping of clients, calling self._lcm_delete_client
        for the deletion step.
        """

class LifeCycleManagerPrivate(Interface):
    Interface.default("LifeCycleManagerPrivate",
        "aiko_services.main.lifecycle.LifeCycleManagerImpl")

    @abstractmethod
    def _lcm_create_client(
        self, client_id, lifecycle_manager_topic, parameters):
        """Creation of a new client"""

    @abstractmethod
    def _lcm_delete_client(self, client_id, force=False):
        """Deletion of a client"""

    @abstractmethod
    def _lcm_get_clients(self) -> Dict[str, str]:
        """Getter for clients"""

    @abstractmethod
    def _lcm_get_handshaking_clients(self) -> List[int]:
        """Return IDs of clients that have been created,
           but that have not yet added themselves"""

    @abstractmethod
    def _lcm_lookup_client_state(self, client_id, client_state_key):
        """Lookup value from state of client"""

class LifeCycleManagerImpl(LifeCycleManager, LifeCycleManagerPrivate):
    def __init__(
            self,
            lifecycle_client_change_handler=None,
            ec_producer=None,
            client_state_consumer_filter="(lifecycle)",
            handshake_lease_time=_HANDSHAKE_LEASE_TIME_DEFAULT,
            deletion_lease_time=_DELETION_LEASE_TIME_DEFAULT):

        self.lcm_lifecycle_client_change_handler =  \
            lifecycle_client_change_handler
        self.lcm_client_count = 0
        self.lcm_ec_producer = ec_producer
        self.lcm_client_state_consumer_filter = client_state_consumer_filter
        self.lcm_deletion_lease_time = deletion_lease_time
        self.lcm_deletion_leases = {}
        self.lcm_handshake_lease_time = handshake_lease_time
        self.lcm_handshakes = {}
        self.lcm_lifecycle_clients = {}
        self.add_message_handler(
            self._lcm_topic_control_handler, self.topic_control)
        self.lcm_ec_producer.update("lifecycle_manager", {})  # TODO: Remove !

        if self.lcm_ec_producer is not None:
            self.lcm_ec_producer.update("lifecycle_manager_clients_active", 0)

    def lcm_create_client(self, parameters=None):
        if parameters == None:
            parameters = {}
        client_id = self.lcm_client_count
        self.lcm_client_count += 1
        self._lcm_create_client(client_id, self.topic_path, parameters)
        handshake = Lease(
            self.lcm_handshake_lease_time, client_id,
            lease_expired_handler=self._lcm_handshake_lease_expired_handler)
        self.lcm_handshakes[client_id] = handshake

    def lcm_delete_client(self, client_id):
        if client_id not in self.lcm_deletion_leases:
            self._lcm_delete_client(client_id)
            deletion_lease = Lease(
                self.lcm_deletion_lease_time, client_id,
                lease_expired_handler=self._lcm_deletion_lease_expired_handler)
            self.lcm_deletion_leases[client_id] = deletion_lease

    def _lcm_topic_control_handler(self, _aiko, topic, payload_in):
        command, parameters = parse(payload_in)

        if command == "add_client":
            lifecycle_client_topic_path = parameters[0]
            client_id = int(parameters[1])
            if client_id not in self.lcm_handshakes:
                _LOGGER.debug(f"LifeCycleClient {client_id} unknown")
            else:
                self.lcm_handshakes[client_id].terminate()
                del self.lcm_handshakes[client_id]
                _LOGGER.debug(f"LifeCycleClient {client_id} responded")

                class NullClass():
                    def null(self): pass

                do_discovery(NullClass,
                    ServiceFilter([lifecycle_client_topic_path],
                        "*", "*", "*", "*", "*"),
                    None, self._lcm_service_remove_handler)

                ec_consumer = ECConsumer(
                    self,
                    client_id, {},
                    f"{lifecycle_client_topic_path}/control",
                    self.lcm_client_state_consumer_filter)
                if self.lcm_lifecycle_client_change_handler:
                    ec_consumer.add_handler(self.lcm_lifecycle_client_change_handler)
                lifecycle_client_details = LifeCycleClientDetails(
                    client_id, lifecycle_client_topic_path, ec_consumer)
                self.lcm_lifecycle_clients[client_id] = lifecycle_client_details
                if self.lcm_ec_producer is not None:
                    self.lcm_ec_producer.update(
                        "lifecycle_manager_clients_active",
                        len(self.lcm_lifecycle_clients))
# TODO: This is a significant performance problem for large numbers of clients
                    self.lcm_ec_producer.update(
                        f"lifecycle_manager.{client_id}",
                        lifecycle_client_topic_path)

    def _lcm_service_remove_handler(self, service_details):
        lifecycle_client_topic_path = service_details[0]
        lifecycle_clients = list(self.lcm_lifecycle_clients.values())
        for lifecycle_client in lifecycle_clients:
            if lifecycle_client.topic_path == lifecycle_client_topic_path:
                if lifecycle_client.ec_consumer:
                    lifecycle_client.ec_consumer.terminate()
                    lifecycle_client.ec_consumer = None
                client_id = lifecycle_client.client_id

                if client_id in self.lcm_deletion_leases:
                    self.lcm_deletion_leases[client_id].terminate()
                    del self.lcm_deletion_leases[client_id]
                    _LOGGER.debug(f"LifeCycleClient {client_id} removed")

                del self.lcm_lifecycle_clients[client_id]
                if self.lcm_ec_producer is not None:
                    self.lcm_ec_producer.update(
                        "lifecycle_manager_clients_active",
                        len(self.lcm_lifecycle_clients))
                    self.lcm_ec_producer.remove(
                        f"lifecycle_manager.{client_id}")

            # When Service is removed from the Registrar, notify LCM Impl
                if self.lcm_lifecycle_client_change_handler:
                    self.lcm_lifecycle_client_change_handler(
                        client_id, "update", "lifecycle", "absent"
                    )

    def _lcm_deletion_lease_expired_handler(self, client_id):
        _LOGGER.debug(f"LifeCycleClient {client_id} deletion lease expired, force-deleting client")
        if client_id in self.lcm_deletion_leases:
            del self.lcm_deletion_leases[client_id]
        self._lcm_delete_client(client_id, force=True)

    def _lcm_handshake_lease_expired_handler(self, client_id):
        if client_id in self.lcm_handshakes:
            del self.lcm_handshakes[client_id]
        self._lcm_delete_client(client_id)
        _LOGGER.debug(f"LifeCycleClient {client_id} handshake failed")

    def _lcm_get_clients(self):
        clients = self.lcm_ec_producer.get("lifecycle_manager")
        if clients:
            clients = clients.copy()
            clients = { int(k): v for k, v in clients.items() }
        return clients

    def _lcm_get_handshaking_clients(self):
        return list(self.lcm_handshakes.keys())

    def _lcm_lookup_client_state(self, client_id, client_state_key):
        client_state_value = None
        client_details = self.lcm_lifecycle_clients.get(client_id)
        if client_details:
            if client_details.ec_consumer:
                client_state_value =  \
                    client_details.ec_consumer.cache.get(client_state_key)
        return client_state_value

# --------------------------------------------------------------------------- #

class LifeCycleManagerTest(Actor, LifeCycleManager):
    Interface.default("LifeCycleManagerTest",
        "aiko_services.main.lifecycle.LifeCycleManagerTestImpl")

class LifeCycleManagerTestImpl(LifeCycleManagerTest):
    def __init__(self, context, client_count):
        context.get_implementation("Actor").__init__(self, context)

        self.share = {
            "lifecycle": "ready",
            "log_level": get_log_level_name(_LOGGER),
            "source_file": f"v{_VERSION}⇒ {__file__}",
            "client_count": client_count
        }
        self.ec_producer = ECProducer(self, self.share)
        self.process_manager = ProcessManager()

        context.get_implementation("LifeCycleManager").__init__(self,
            self._lifecycle_client_change_handler, self.ec_producer)

        aiko.connection.add_handler(self._connection_state_handler)

    def _lcm_create_client(
        self, client_id, lifecycle_manager_topic, parameters):

        command = parameters
        arguments = ["client", str(client_id), lifecycle_manager_topic]
        self.process_manager.create(client_id, command, arguments)

    def _lcm_delete_client(self, client_id, force=False):
        self.process_manager.delete(client_id, kill=True)

    def _connection_state_handler(self, connection, connection_state):
        if connection.is_connected(ConnectionState.REGISTRAR):
            for client_count in range(self.share["client_count"]):
                lifecycle_client_id =  \
                    self.lcm_create_client(CLIENT_SHELL_COMMAND)
                time.sleep(0.01)

    def _lifecycle_client_change_handler(
        self, client_id, command, item_name, item_value):

        _LOGGER.debug(
            f"LifeCycleClient: {client_id}: {command} {item_name} {item_value}")

# ---------------------------------------------------------------------------- #

class LifeCycleClient(ServiceProtocolInterface):
    Interface.default("LifeCycleClient",
        "aiko_services.main.lifecycle.LifeCycleClientImpl")

class LifeCycleClientPrivate(Interface):
    Interface.default("LifeCycleClientPrivate",
        "aiko_services.main.lifecycle.LifeCycleClientImpl")

    @abstractmethod
    def _lcc_get_lifecycle_manager_topic(self):
        pass

    @abstractmethod
    def _lcc_lifecycle_manager_change_handler(self, service_details):
        pass

class LifeCycleClientImpl(LifeCycleClient, LifeCycleClientPrivate):
    def __init__(self,
        context, client_id, lifecycle_manager_topic, ec_producer):

        self.lcc_added_to_lcm = False
        self.lcc_client_id = client_id
        self.lcc_ec_producer = ec_producer
        self.lcc_ec_producer.update(
            "lifecycle_client.lifecycle_manager_topic", lifecycle_manager_topic)
        aiko.connection.add_handler(self._lcc_connection_handler)

    def _lcc_get_lifecycle_manager_topic(self):
        return self.lcc_ec_producer.get("lifecycle_client.lifecycle_manager_topic")

    def _lcc_connection_handler(self, connection, connection_state):
        if connection.is_connected(ConnectionState.REGISTRAR):
            if not self.lcc_added_to_lcm:
                lcm_topic_path = self._lcc_get_lifecycle_manager_topic()
                topic = f"{lcm_topic_path}/control"
                payload_out = "(add_client "                \
                              f"{self.topic_path} "  \
                              f"{self.lcc_client_id})"
                aiko.message.publish(topic, payload_out)
                self.lcc_added_to_lcm = True

                # Add handler for LifeCycleManager removal from registrar
                do_discovery(LifeCycleManagerImpl,
                    ServiceFilter([lcm_topic_path], "*", "*", "*", "*", "*"),
                    None, self._lcc_lifecycle_manager_change_handler)

    def _lcc_lifecycle_manager_change_handler(self, service_details):
        pass

# --------------------------------------------------------------------------- #

class LifeCycleClientTest(Actor, LifeCycleClient):
    Interface.default("LifeCycleClientTest",
        "aiko_services.main.lifecycle.LifeCycleClientTestImpl")

class LifeCycleClientTestImpl(LifeCycleClientTest):
    def __init__(self, context, client_id, lifecycle_manager_topic):
        context.get_implementation("Actor").__init__(self, context)

        self.share = {
            "lifecycle": "ready",
            "log_level": get_log_level_name(_LOGGER),
            "source_file": f"v{_VERSION}⇒ {__file__}",
            "client_id": client_id
        }
        self.ec_producer = ECProducer(self, self.share)

        context.get_implementation("LifeCycleClient").__init__(self,
            context, client_id, lifecycle_manager_topic, self.ec_producer)

# TODO: When scaling up to lots of LifeCycleClient, every LifeCycleClient
# receiving the ServiceDetails for every other LifeCycleClient is too much.
# - Registrar should provide a filter that limits to the requested topic path
#   Use below to be notified only when that Service is added or removed
# - Could also filter on the LifeCycleManager protocol to limit results
#
#       filter = ServiceFilter(
#           [lifecycle_manager_topic], "*", "*", "*", "*", "*")
#       self.actor_discovery = ActorDiscovery(service)
#       self.actor_discovery.add_handler(
#           self._lifecycle_manager_change_handler, filter)
#
#   def _lifecycle_manager_change_handler(self, command, service_details):
#       if command == "remove":
#           self.delete()

# ---------------------------------------------------------------------------- #

@click.group()

def main():
    pass

@main.command(help="LifeCycleManager Actor")
@click.argument("client_count", default=1)

def manager(client_count):
    tags = ["ec=true"]  # TODO: Add ECProducer tag before add to Registrar
    init_args = actor_args(ACTOR_TYPE_LIFECYCLE_MANAGER,
        protocol=PROTOCOL_LIFECYCLE_MANAGER, tags=tags)
    init_args["client_count"] = client_count
    lifecycle_manager = compose_instance(LifeCycleManagerTestImpl, init_args)
    aiko.process.run()

@main.command(help="LifeCycleClient Actor")
@click.argument("client_id", default=None)
@click.argument("lifecycle_manager_topic", default=None)

def client(client_id, lifecycle_manager_topic):
    tags = ["ec=true"]  # TODO: Add ECProducer tag before add to Registrar
    name = f"{ACTOR_TYPE_LIFECYCLE_CLIENT}_{client_id}"
    init_args = actor_args(name, protocol=PROTOCOL_LIFECYCLE_CLIENT, tags=tags)
    init_args["client_id"] = client_id
    init_args["lifecycle_manager_topic"] = lifecycle_manager_topic
    life_cycle_client = compose_instance(LifeCycleClientTestImpl, init_args)
    aiko.process.run()

if __name__ == "__main__":
    main()

# ---------------------------------------------------------------------------- #
