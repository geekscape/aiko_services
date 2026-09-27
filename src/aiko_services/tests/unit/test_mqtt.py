# Usage
# ~~~~~
# pytest [-s] unit/test_mqtt.py
#
# Unit tests for the MQTT client's connection (message/mqtt.py): paho is
# given the address that answered when TLS is off over TCP, the host name
# otherwise, and a failed connection becomes a SystemError.  paho's Client
# and the MQTT configuration are replaced by fakes: no network is used.

import pytest

import aiko_services.main.message.mqtt as mqtt_module

class FakeClient:
    instances = []
    fail_with = None

    def __init__(self, transport="tcp"):
        self.transport = transport
        self.connected_to = None
        self.tls = False
        FakeClient.instances.append(self)

    def will_set(self, topic, payload=None, retain=False):
        pass

    def tls_set(self):
        self.tls = True

    def username_pw_set(self, username, password):
        pass

    def connect(self, host, port, keepalive):
        if FakeClient.fail_with:
            raise FakeClient.fail_with
        self.connected_to = (host, port)

    def loop_start(self):
        pass

def make_mqtt(monkeypatch, tls=False, transport="tcp", address="192.168.0.137"):
    configuration = (True, "w3029f1.local", 1883, transport, None, None, tls, address)
    monkeypatch.setattr(mqtt_module, "get_mqtt_configuration", lambda: configuration)
    monkeypatch.setattr(mqtt_module.mqtt, "Client", FakeClient)
    FakeClient.instances = []
    return mqtt_module.MQTT()

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
