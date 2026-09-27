# Usage
# ~~~~~
# pytest [-s] unit/test_configuration.py
#
# Unit tests for finding the MQTT server (utilities/configuration.py):
# the host name is resolved once, IPv4 addresses are tried before IPv6,
# each connection attempt is bounded, and the address that answered is
# returned.  socket.getaddrinfo() and socket.socket() are replaced by
# fakes: no network is used.

import socket

import pytest

import aiko_services.main.utilities.configuration as configuration

IPV4, IPV6 = "192.168.0.137", "fd50::1"

class FakeSocket:
    """Records each connection attempt; OUTCOMES maps an address to None
    (it answers) or the exception its connect() raises"""

    attempts = []
    outcomes = {}

    def __init__(self, family, kind):
        self.family, self.kind, self.timeout = family, kind, None

    def settimeout(self, timeout):
        self.timeout = timeout

    def connect(self, sockaddr):
        FakeSocket.attempts.append((self.family, sockaddr[0], self.timeout))
        outcome = FakeSocket.outcomes.get(sockaddr[0], ConnectionRefusedError())
        if outcome is not None:
            raise outcome

    def close(self):
        pass

def info(family, address, port=1883):
    sockaddr = (address, port) if family == socket.AF_INET else (address, port, 0, 0)
    return (family, socket.SOCK_STREAM, 6, "", sockaddr)

@pytest.fixture
def network(monkeypatch):
    resolved = {}

    def getaddrinfo(host, port, type=0, **_):
        if host not in resolved:
            raise socket.gaierror(8, "nodename nor servname provided, or not known")
        return resolved[host]

    FakeSocket.attempts, FakeSocket.outcomes = [], {}
    monkeypatch.setattr(configuration.socket, "getaddrinfo", getaddrinfo)
    monkeypatch.setattr(configuration.socket, "socket", FakeSocket)
    monkeypatch.delenv("AIKO_MQTT_HOST", raising=False)
    monkeypatch.delenv("AIKO_MQTT_PORT", raising=False)
    return resolved

def test_ipv4_is_tried_first_even_when_the_resolver_lists_ipv6_first(network):
    network["w3029f1.local"] = [info(socket.AF_INET6, IPV6), info(socket.AF_INET, IPV4)]
    FakeSocket.outcomes = {IPV4: None, IPV6: TimeoutError()}
    assert configuration._resolve_mqtt_host("w3029f1.local", 1883) == IPV4
    assert FakeSocket.attempts == [(socket.AF_INET, IPV4, configuration._MQTT_PROBE_TIMEOUT)]

def test_ipv4_refused_falls_back_to_ipv6(network):
    network["dual"] = [info(socket.AF_INET, IPV4), info(socket.AF_INET6, IPV6)]
    FakeSocket.outcomes = {IPV4: ConnectionRefusedError(), IPV6: None}
    assert configuration._resolve_mqtt_host("dual", 1883) == IPV6
    assert [family for family, _, _ in FakeSocket.attempts] == [socket.AF_INET, socket.AF_INET6]
    assert all(timeout == configuration._MQTT_PROBE_TIMEOUT
               for _, _, timeout in FakeSocket.attempts)   # every attempt bounded

def test_duplicate_addresses_are_tried_once(network):
    network["twice"] = [info(socket.AF_INET, IPV4)] * 3
    assert configuration._resolve_mqtt_host("twice", 1883) is None
    assert len(FakeSocket.attempts) == 1

def test_unknown_name_warns_and_reports_the_server_down(network, monkeypatch):
    warnings = []
    monkeypatch.setattr(configuration._LOGGER, "warning", warnings.append)
    monkeypatch.setenv("AIKO_MQTT_HOST", "no_such_host.invalid")
    up, host, port, address = configuration.get_mqtt_host_address()
    assert (up, address) == (False, None)
    assert any("no_such_host.invalid" in warning and "resolve" in warning
               for warning in warnings)

def test_a_literal_address_passes_through(network, monkeypatch):
    network[IPV4] = [info(socket.AF_INET, IPV4)]
    FakeSocket.outcomes = {IPV4: None}
    monkeypatch.setenv("AIKO_MQTT_HOST", IPV4)
    assert configuration.get_mqtt_host_address() == (True, IPV4, 1883, IPV4)
    assert configuration.get_mqtt_host() == (True, IPV4, 1883)   # unchanged: 3 values

def test_the_configuration_carries_the_address_as_element_7(network, monkeypatch):
    network["broker"] = [info(socket.AF_INET, IPV4)]
    FakeSocket.outcomes = {IPV4: None}
    monkeypatch.setenv("AIKO_MQTT_HOST", "broker")
    monkeypatch.setenv("AIKO_MQTT_PORT", "1884")
    configuration_tuple = configuration.get_mqtt_configuration(tls_enabled=False)
    assert len(configuration_tuple) == 8
    assert configuration_tuple[:3] == (True, "broker", 1884)
    assert configuration_tuple[6] is False and configuration_tuple[7] == IPV4

def test_falls_back_to_localhost(network, monkeypatch):
    network["down"] = [info(socket.AF_INET, "10.0.0.9")]
    network["localhost"] = [info(socket.AF_INET, "127.0.0.1")]
    FakeSocket.outcomes = {"10.0.0.9": TimeoutError(), "127.0.0.1": None}
    monkeypatch.setenv("AIKO_MQTT_HOST", "down")
    assert configuration.get_mqtt_host_address() == (True, "localhost", 1883, "127.0.0.1")
