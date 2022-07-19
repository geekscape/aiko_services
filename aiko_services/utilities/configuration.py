# Usage
#
# AIKO_NAMESPACE=test
# AIKO_MQTT_HOST=localhost
# AIKO_MQTT_PORT=1883
# AIKO_MQTT_TRANSPORT=tcp  # websockets
# AIKO_USERNAME=username  # Specifying a username enables TLS (SSL)
# AIKO_PASSWORD=password
#
# mqtt_configuration = get_mqtt_configuration(tls_enabled=True)
#
# Where mqtt_configuration is a tuple ...
#     (mqtt_host, mqtt_port, mqtt_transport, username, password, tls_enabled)
#
# Resources
# ~~~~~~~~~
# https://stackoverflow.com/questions/24196932/how-can-i-get-the-ip-address-of-eth0-in-python
#
# To Do
# ~~~~~
# - Replace hard-coded "_AIKO_MQTT_HOSTS" with environment variable
# - Move discovery and bootstrap functions into "message/discovery.py"
# - Implement discovery for finding the default MQTT hostname
# - Implement discovery for finding the default namespace
#   - Define Namespace class for holding information about a specific namespace

import getpass
import os
import socket
from threading import Thread
import time

__all__ = [
    "get_hostname", "get_mqtt_configuration", "get_mqtt_host", "get_mqtt_port",
    "get_namespace", "get_pid", "get_username"
]

_AIKO_BOOTSTRAP_UDP_PORT = 4149
_AIKO_MQTT_HOSTS = []  # List of host (name, port) to check for MQTT server
_AIKO_MQTT_HOST = "localhost"
_AIKO_MQTT_PORT = 1883        # TCP/IP: 9883, WebSockets: 9884
_AIKO_MQTT_TRANSPORT = "tcp"  # "websockets"
_AIKO_NAMESPACE = "aiko"

def _get_ip_address():
    _socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    _socket.connect(("8.8.8.8", 80))
    return _socket.getsockname()[0]

def _host_service_up(host, port):
    try:
        _socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        _socket.connect((host, port))
        _socket.close()
        result = True
    except socket.error as exception:
        result = False
    return result

def get_hostname():
    hostname = socket.gethostname()
    if hostname.find('.') < 0:
        hostname = socket.gethostbyaddr(hostname)[0]
    return hostname

def get_mqtt_configuration(tls_enabled=None):
    mqtt_host, mqtt_port = get_mqtt_host()
    mqtt_transport = os.environ.get("AIKO_MQTT_TRANSPORT", _AIKO_MQTT_TRANSPORT)
    username = os.environ.get("AIKO_USERNAME", None)
    password = os.environ.get("AIKO_PASSWORD", None)
    if tls_enabled == None:
        tls_enabled = (username is not None) and (len(username) > 0)
    return (mqtt_host, mqtt_port, mqtt_transport, username, password, tls_enabled)

# Try in order ...
# - Environment variables: AIKO_MQTT_HOST and AIKO_MQTT_PORT
# - _AIKO_MQTT_HOSTS list
# - Default: _AIKO_MQTT_HOST and _AIKO_MQTT_PORT

def get_mqtt_host():
    mqtt_hosts = _AIKO_MQTT_HOSTS.copy()
    mqtt_host = os.environ.get("AIKO_MQTT_HOST", None)
    mqtt_port = get_mqtt_port()
    if mqtt_host:
        mqtt_hosts.insert(0, (mqtt_host, mqtt_port))
    mqtt_hosts.append((_AIKO_MQTT_HOST, mqtt_port))

    for host, port in mqtt_hosts:
        if _host_service_up(host, port):
            mqtt_host = host
            mqtt_port = port
            break

    return mqtt_host, mqtt_port

def get_mqtt_port():
    return int(os.environ.get("AIKO_MQTT_PORT", _AIKO_MQTT_PORT))

def get_namespace():
    return os.environ.get("AIKO_NAMESPACE", _AIKO_NAMESPACE)

def get_pid():
    return str(os.getpid())

def get_username():
    return getpass.getuser()

# Bootstrap devices that don't support DNS or mDNS yet.
# Simple UDP broadcast request / unicast reply to find the MQTT server.
# Request  message: "boot? response_ip_address response_ip_port"
# Response message: "boot mqtt_ip_address mqtt_ip_port namespace"

RESPONSE = "boot " +  \
    _get_ip_address() + " " + str(get_mqtt_port()) + " " + get_namespace()

def bootstrap_thread():
    time.sleep(1)  # wait for previous service manager to terminate
    _socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        _socket.bind(("0.0.0.0", _AIKO_BOOTSTRAP_UDP_PORT))
        while True:
            message, address = s.recvfrom(256)
            message = message.decode("utf-8")
            tokens = message.split()
            if len(tokens) == 3  and tokens[0] == "boot?":
                print(f"Bootstrap request: {tokens[1]}:{tokens[2]}")
                _socket.sendto(RESPONSE.encode(), (tokens[1], int(tokens[2])))
    except Exception as exception:
        print(f"Bootstrap thread stopped: {exception}")

def bootstrap_start():
    thread = Thread(target=bootstrap_thread, args=())
    thread.daemon = True
    thread.start()
