# Usage
# ~~~~~
# connection = Connection(id)
# try:
#     connection.lock_acquire("function_name()")
#     ## Critial code ##
# finally:
#     connection.lock_release()
#
# Notes
# ~~~~~
# This is a low-level mechanism, used by the AikoServices framework
# and should not have any static dependencies on that framework
#
# Must use a Lock for "self.connection_state" updates via concurrent Threads.
# See "process.py", where both the main thread and the MQTT thread may
# independently perform simultaneous ConnectionState updates as the
# MQTT server and Registrar are both discovered and lost over time.
#
# To Do
# ~~~~~
# - Ensure all updates occur via "events" (handlers, messages and timers)
#   managed by the event loop and executed solely by the event loop thread

from aiko_services.main.utilities.lock import Lock

__all__ = ["ConnectionState", "Connection"]

class ConnectionState:
    NONE = "NONE"
    NETWORK = "NETWORK"      # Wi-Fi or Ethernet available
    BOOTSTRAP = "BOOTSTRAP"  # MQTT configuration found
    TRANSPORT = "TRANSPORT"  # MQTT, Ray, ROS2, ZeroMQ, etc
    REGISTRAR = "REGISTRAR"  # Registrar available for use

    states = [NONE, NETWORK, TRANSPORT, REGISTRAR]  # order matters

    @classmethod
    def index(cls, connection_state):  # throws ValueError
        return cls.states.index(connection_state)

class Connection:
    def __init__(self, id):
        self.id = id
        self.lock = Lock(f"connection.{id}")
        self.connection_state = ConnectionState.NONE
        self.connection_state_handlers = []

    def add_handler(self, connection_state_handler):
        connection_state_handler(self, self.connection_state)
        if not connection_state_handler in self.connection_state_handlers:
            self.connection_state_handlers.append(connection_state_handler)

    def get_state(self):
        return self.connection_state

    def is_connected(self, connection_state):  # throws ValueError
        current_state_index = ConnectionState.index(self.connection_state)
        return current_state_index >= ConnectionState.index(connection_state)

    def lock_acquire(self, location):
        self.lock.acquire(location)

    def lock_release(self):
        self.lock.release()

    def remove_handler(self, connection_state_handler):
        if connection_state_handler in self.connection_state_handlers:
           self.connection_state_handlers.remove(connection_state_handler)

    def update_state(self, connection_state, logger=None):
        if logger:
            if not self.lock.in_use():
                diagnostic = "update_state() invoked, whilst not locked"
                logger.error(f'Connection "{self.id}": {diagnostic}')

            state_change = f"{self.connection_state} --> {connection_state}"
            logger.debug(f"Connection state: {state_change}")

        self.connection_state = connection_state

        for connection_state_handler in self.connection_state_handlers:
            connection_state_handler(self, connection_state)
