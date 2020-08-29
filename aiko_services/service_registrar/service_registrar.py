#!/usr/bin/env python3
#
# Aiko Service: Service Registrar
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#
# Usage
# ~~~~~
# service_registrar [--primary]
#
#   --primary: Force take over of the primary service_registrar role
#
# To Do
# ~~~~~
# - Implement as a sub-class of Category ?
# - When Service fails with LWT, publish timestamp on "topic_path/state"
#   - Maybe ProcessController should do this, rather than ServiceRegistrar ?
# - Every Service persisted in MeemStore should have "uuid" Service tag
# - Document state and protocol
#   - Service state inspired by Meem life-cycle
# - Create service_registrar/protocol.py
# - Rename "framework.py" to "service.py" and create a Service class ?
# - Implement protocol.py and state_machine.py !
# - Primary and secondaries Service Registrars
# - Primary Service Registrar supports discovery protocol
# - Implement protocol matching similar to programming language interfaces with inheritance

import click

import aiko_services.framework as aiko

# --------------------------------------------------------------------------- #

parameter_1 = None

# TODO: Events: "add", "remove", "timeout" (waiting for Service Registrar)
#       Remove and timeout triggers this Service Registrar becoming the "primary"

def on_service_registrar(aiko_, event_type, topic_path, timestamp):
    print(f"service_registrar: {event_type}, topic_path: {topic_path}, timestamp: {timestamp}")
    if event_type == "add":
        pass
    if event_type == "remove" or event_type == "timeout":
        payload_out = f"(primary {aiko_.topic_in} 0)"
        aiko_.message.publish(aiko.SERVICE_REGISTRAR_TOPIC, payload_out)
# TODO: publish with retain = True !

# --------------------------------------------------------------------------- #

@click.command()
def main():
    aiko.set_protocol(aiko.SERVICE_REGISTRAR_PROTOCOL)

# TODO: Start with SERVICE_REGISTRAR_PROTOCOL_SECONDARY
# TODO: When promoting from secondary to primary ...
#         Change to SERVICE_REGISTRAR_PROTOCOL_PRIMARY
#         MQTT disconnect and wait for automatic reconnection

# TODO: Add on_message_broker() handler to track MQTT connection status
#       - Events: "add", "remove", "timeout" (waiting for connection)

# V2: namespace/service/registrar (primary namespace/host/pid timestamp)

# TODO: Add message handler for listening for other Service Registars ?
#       This means that the Aiko V2 framework should do the subscription automagically
#       - Find the primary service registrar (if it exists ?)
#       - Query to find all other service registars

# TODO: Add discovery protocol handler

    aiko.add_service_registrar_handler(on_service_registrar)
    aiko.process()

if __name__ == "__main__":
    main()

# --------------------------------------------------------------------------- #
