# Usage
# ~~~~~
# pytest [-s] unit/test_discovery.py
#
# Tests for do_command() and do_request() timeouts, without an MQTT server.
# A fake do_discovery() replaces the ServicesCache and Registrar
#
# To Do
# ~~~~~
# - None, yet !

import threading

import pytest

import aiko_services as aiko
from aiko_services.main import discovery
from aiko_services.main import event

_WATCHDOG_TIME = 10.0  # seconds

class _FakeServiceDiscovery:
    def __init__(self):
        self.removed = []

    def remove_handler(self, handler, service_filter):
        self.removed.append((handler, service_filter))

class _FakeDiscovery:
    def __init__(self):
        self.add_handler = None
        self.service_discovery = _FakeServiceDiscovery()

    def __call__(self, service_interface, service_filter,
                 discovery_add_handler=None, discovery_remove_handler=None):
        self.add_handler = discovery_add_handler
        return self.service_discovery, discovery_add_handler

@pytest.fixture
def fakes(monkeypatch):
    saved_mailboxes = event.mailboxes.copy()
    saved_head = event.event_list.head
    saved_handler_count = event._handler_count
    event.mailboxes.clear()
    event.event_list.head = None
    event._handler_count = 0

    fake_discovery = _FakeDiscovery()
    monkeypatch.setattr(discovery, "do_discovery", fake_discovery)
    exit_status = []
    def fake_terminate(status=0):
        exit_status.append(status)
        event.terminate()
    monkeypatch.setattr(aiko.process, "terminate", fake_terminate)
    message_handlers = {}
    def fake_add_message_handler(handler, topic, binary=False):
        message_handlers[topic] = handler
    monkeypatch.setattr(
        aiko.process, "add_message_handler", fake_add_message_handler)
    monkeypatch.delenv("AIKO_DISCOVERY_TIMEOUT", raising=False)

    watchdog = threading.Timer(_WATCHDOG_TIME, event.terminate)
    watchdog.daemon = True
    watchdog.start()
    yield fake_discovery, exit_status, message_handlers
    watchdog.cancel()

    event.mailboxes.clear()
    event.mailboxes.update(saved_mailboxes)
    event.event_list.head = saved_head
    event._handler_count = saved_handler_count

def _service_filter():
    return aiko.ServiceFilter("*", "test_service", "*", "*", "*", "*")

def test_get_timeout(monkeypatch):
    monkeypatch.delenv("AIKO_DISCOVERY_TIMEOUT", raising=False)
    assert discovery._get_timeout(None) is None
    assert discovery._get_timeout(0) is None
    assert discovery._get_timeout(2.5) == 2.5
    monkeypatch.setenv("AIKO_DISCOVERY_TIMEOUT", "1.5")
    assert discovery._get_timeout(None) == 1.5
    assert discovery._get_timeout(0) is None  # explicit 0: no timeout
    monkeypatch.setenv("AIKO_DISCOVERY_TIMEOUT", "not_a_number")
    assert discovery._get_timeout(None) is None

def test_do_command_timeout(fakes):
    fake_discovery, exit_status, _ = fakes
    commands = []
    discovery.do_command(None, _service_filter(),
        lambda service: commands.append(service),
        terminate=True, timeout=0.2)

    event.loop()

    assert commands == []
    assert exit_status == [1]
    assert len(fake_discovery.service_discovery.removed) == 1

def test_do_command_timeout_handler(fakes):
    fake_discovery, exit_status, _ = fakes
    timeouts = []
    def timeout_handler():
        timeouts.append(True)
        event.terminate()
    discovery.do_command(None, _service_filter(), lambda service: None,
        timeout=0.2, timeout_handler=timeout_handler)

    event.loop()

    assert timeouts == [True]
    assert exit_status == []  # terminate=False

def test_do_command_discovered_before_timeout(fakes):
    fake_discovery, exit_status, _ = fakes
    commands = []
    discovery.do_command(None, _service_filter(),
        lambda service: commands.append(service),
        terminate=True, timeout=0.5)
    def discover():
        event.remove_timer_handler(discover)
        fake_discovery.add_handler(("topic", "test_service"), "service")
    event.add_timer_handler(discover, 0.05)

    event.loop()

    assert commands == ["service"]
    assert exit_status == [0]
    assert fake_discovery.service_discovery.removed == []

def test_do_request_response_timeout(fakes):
    fake_discovery, exit_status, _ = fakes
    responses = []
    discovery.do_request(None, _service_filter(),
        lambda service: None, lambda response: responses.append(response),
        "response/topic", terminate=True, timeout=0.3)
    def discover():  # Service found, but it never responds
        event.remove_timer_handler(discover)
        fake_discovery.add_handler(("topic", "test_service"), "service")
    event.add_timer_handler(discover, 0.05)

    event.loop()

    assert responses == []
    assert exit_status == [1]

def test_do_request_response_before_timeout(fakes):
    fake_discovery, exit_status, message_handlers = fakes
    responses = []
    def request_handler(service):
        handler = message_handlers["response/topic"]
        handler(None, "response/topic", "(item_count 1)")
        handler(None, "response/topic", "(response a b)")
    discovery.do_request(None, _service_filter(),
        request_handler, lambda response: responses.append(response),
        "response/topic", terminate=True, timeout=0.5)
    def discover():
        event.remove_timer_handler(discover)
        fake_discovery.add_handler(("topic", "test_service"), "service")
    event.add_timer_handler(discover, 0.05)

    event.loop()

    assert responses == [[["a", "b"]]]
    assert exit_status == [0]
