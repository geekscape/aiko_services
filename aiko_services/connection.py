# Notes
# ~~~~~
# This is a low-level mechanism, used by the AikoServices framework
# and should not have any static dependencies on that framework
#
# To Do
# ~~~~~
# - Add support for ConnectionState.TRANSPORT (MQTT) connection state updates

__all__ = ["ConnectionState", "Connection"]

class ConnectionState:
    NONE = "NONE"
    NETWORK = "NETWORK"      # Wi-Fi or Ethernet available
    BOOTSTRAP = "BOOTSTRAP"  # MQTT configuration found
    TRANSPORT = "TRANSPORT"  # MQTT, Ray, ROS2, etc
    REGISTRAR = "REGISTRAR"  # Registrar available for use

    states = [NONE, NETWORK, TRANSPORT, REGISTRAR]  # order matters

    @classmethod
    def index(cls, connection_state):  # throws ValueError
        return cls.states.index(connection_state)

class Connection:
    def __init__(self):
        self.connection_state = ConnectionState.NONE
        self.connection_state_handlers = []

    def add_handler(self, connection_state_handler):
        connection_state_handler(self, self.connection_state)
        if not connection_state_handler in self.connection_state_handlers:
            self.connection_state_handlers.append(connection_state_handler)

    def is_connected(self, connection_state):  # throws ValueError
        current_state_index = ConnectionState.index(self.connection_state)
        return current_state_index >= ConnectionState.index(connection_state)

    def remove_handler(self, connection_state_handler):
        if connection_state_handler in self.connection_state_handlers:
           self.connection_state_handlers.remove(connection_state_handler)

    def update_state(self, connection_state):
        self.connection_state = connection_state
        for connection_state_handler in self.connection_state_handlers:
            connection_state_handler(self, connection_state)
