# Usage
# ~~~~~
# pytest [-s] unit/test_mqtt.py
#
# Unit tests for the MQTT client's connection (message/mqtt.py): paho is
# given the address that answered when TLS is off over TCP, the host name
# otherwise, and a failed connection becomes a SystemError.  paho's Client
# and the MQTT configuration are replaced by fakes: no network is used.
#
# With connection_required=False, an unavailable MQTT server is retried in
# the background (connect_async), publish() doesn't wait whilst
# disconnected, a refused CONNACK isn't "connected", a deliberate
# disconnection sends DISCONNECT before the paho loop stops, and a "#"
# subscription is restored after reconnection

import threading
import time

import pytest

import aiko_services.main.message.mqtt as mqtt_module
from aiko_services.main.message import MessageState

class FakeClient:
    instances = []
    fail_with = None

    def __init__(self, transport="tcp"):
        self.transport = transport
        self.calls = []
        self.connected_to = None
        self.connect_async_to = None
        self.published = []
        self.subscribed = []
        self.tls = False
        FakeClient.instances.append(self)

    def will_set(self, topic, payload=None, retain=False):
        pass

    def tls_set(self):
        self.tls = True

    def username_pw_set(self, username, password):
        pass

    def reconnect_delay_set(self, min_delay, max_delay):
        pass

    def connect(self, host, port, keepalive):
        if FakeClient.fail_with:
            raise FakeClient.fail_with
        self.connected_to = (host, port)

    def connect_async(self, host, port, keepalive):
        self.connect_async_to = (host, port)

    def disconnect(self):
        self.calls.append("disconnect")

    def loop_start(self):
        self.calls.append("loop_start")

    def loop_stop(self):
        self.calls.append("loop_stop")

    def publish(self, topic, payload, retain=False):
        self.published.append((topic, payload))

    def subscribe(self, topic):
        self.subscribed.append(topic)

    def unsubscribe(self, topic):
        pass

def make_mqtt(monkeypatch, tls=False, transport="tcp", address="192.168.0.137",
              server_up=True, connection_required=True, state_handler=None):
    configuration = (server_up, "w3029f1.local", 1883, transport, None, None, tls, address)
    monkeypatch.setattr(mqtt_module, "get_mqtt_configuration", lambda: configuration)
    monkeypatch.setattr(mqtt_module.mqtt, "Client", FakeClient)
    FakeClient.instances = []
    return mqtt_module.MQTT(mqtt_state_handler=state_handler,
                            connection_required=connection_required)

@pytest.fixture(autouse=True)
def no_failure():
    FakeClient.fail_with = None
    yield
    FakeClient.fail_with = None

def test_tls_off_connects_to_the_address(monkeypatch):
    make_mqtt(monkeypatch)
    assert FakeClient.instances[-1].connected_to == ("192.168.0.137", 1883)

def test_tls_on_keeps_the_host_name(monkeypatch):
    make_mqtt(monkeypatch, tls=True)
    client = FakeClient.instances[-1]
    assert client.connected_to == ("w3029f1.local", 1883) and client.tls

def test_websockets_keep_the_host_name(monkeypatch):
    make_mqtt(monkeypatch, transport="websockets")
    assert FakeClient.instances[-1].connected_to == ("w3029f1.local", 1883)

def test_no_address_keeps_the_host_name(monkeypatch):
    make_mqtt(monkeypatch, address=None)
    assert FakeClient.instances[-1].connected_to == ("w3029f1.local", 1883)

@pytest.mark.parametrize("error", [TimeoutError("timed out"), OSError(65, "No route to host"),
                                   ConnectionRefusedError(), ConnectionResetError()])
def test_a_failed_connection_is_a_system_error(monkeypatch, error):
    FakeClient.fail_with = error
    with pytest.raises(SystemError, match="Couldn't connect to MQTT server"):
        make_mqtt(monkeypatch)

def test_server_down_and_required_is_a_system_error(monkeypatch):
    with pytest.raises(SystemError, match="Couldn't connect to MQTT server"):
        make_mqtt(monkeypatch, server_up=False, address=None)

def test_server_down_and_not_required_retries_in_background(monkeypatch):
    mqtt = make_mqtt(monkeypatch, server_up=False, address=None,
                     connection_required=False)
    client = FakeClient.instances[-1]
    assert client.connect_async_to == ("w3029f1.local", 1883)
    assert client.calls == ["loop_start"]
    assert mqtt.connected == MessageState.DISCONNECTED

def test_failed_connect_and_not_required_retries_in_background(monkeypatch):
    FakeClient.fail_with = ConnectionRefusedError()
    make_mqtt(monkeypatch, connection_required=False)
    client = FakeClient.instances[-1]
    assert client.connect_async_to == ("192.168.0.137", 1883)
    assert client.calls == ["loop_start"]

def test_publish_whilst_disconnected_does_not_wait(monkeypatch):
    mqtt = make_mqtt(monkeypatch, server_up=False, address=None,
                     connection_required=False)
    time_start = time.monotonic()
    for _ in range(10):
        mqtt.publish("topic", "payload")
    assert time.monotonic() - time_start < 0.1
    assert FakeClient.instances[-1].published == []

def test_publish_waits_for_the_first_connack(monkeypatch):
    mqtt = make_mqtt(monkeypatch)
    client = FakeClient.instances[-1]
    threading.Timer(0.05, mqtt._on_connect, (client, None, {}, 0)).start()
    mqtt.publish("topic", "payload")
    assert client.published == [("topic", "payload")]

def test_refused_connack_is_not_connected(monkeypatch):
    states = []
    mqtt = make_mqtt(monkeypatch, state_handler=states.append)
    client = FakeClient.instances[-1]
    mqtt._on_connect(client, None, {}, 5)  # not authorised
    assert mqtt.connected == MessageState.DISCONNECTED
    assert MessageState.CONNECTED not in states
    mqtt._on_disconnect(client, None, 5)
    assert states == [MessageState.DISCONNECTED]  # only from __init__()

def test_deliberate_disconnect_sends_disconnect_first(monkeypatch):
    states = []
    mqtt = make_mqtt(monkeypatch, state_handler=states.append)
    client = FakeClient.instances[-1]
    mqtt._on_connect(client, None, {}, 0)
    states.clear()
    mqtt._disconnect()
    assert client.calls == ["loop_start", "disconnect", "loop_stop"]
    assert mqtt.connected == MessageState.DISCONNECTED
    assert states == []  # deliberate: mqtt_state_handler isn't told

def test_wildcard_subscription_restored_after_reconnection(monkeypatch):
    mqtt = make_mqtt(monkeypatch)
    client = FakeClient.instances[-1]
    mqtt._on_connect(client, None, {}, 0)
    mqtt.subscribe("#")
    assert client.subscribed.count("#") == 1
    mqtt._on_disconnect(client, None, 1)
    mqtt._on_connect(client, None, {}, 0)
    assert client.subscribed.count("#") == 2
