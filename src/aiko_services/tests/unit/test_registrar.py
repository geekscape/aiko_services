# Usage
# ~~~~~
# pytest [-s] unit/test_registrar.py
#
# Unit tests for the Registrar Interface contract (e_10 §2.2, 2026-07-13):
# the wire commands add/remove/history/share are real Interface methods
# (service_add / service_remove / services_history / services_share — the
# "service(s)_" prefix avoids colliding with universal Service state
# "share" and "history"), with _topic_in_handler() reduced to
# parse-and-delegate.  The primary election's liveness probe (a found
# primary is probed before this Registrar yields) is tested here with a
# recording message stub and the timer handlers called directly, plus one
# run of the real event loop; the election over a real MQTT server is in
# tests/integration/test_registrar_election.py.
#
# To Do
# ~~~~~
# - None, yet !

import pytest

import aiko_services as aiko
from aiko_services.main import aiko as process_data
from aiko_services.main import event
import aiko_services.main.registrar as registrar_module
from aiko_services.main.registrar import Registrar, RegistrarImpl


class _StubMessage:
    def __init__(self):
        self.published = []
        self.retained = []
        self.will = None

    def publish(self, topic, payload=None, retain=False):
        self.published.append((topic, payload))
        if retain:
            self.retained.append((topic, payload))

    def set_last_will_and_testament(self, topic, payload, retain):
        self.will = (topic, payload, retain)

    def subscribe(self, topic):
        pass

    def unsubscribe(self, topic):
        pass


def test_registrar_interface_declares_contract():
    assert {"service_add", "service_remove",
            "services_history", "services_share"
           } <= set(Registrar.__abstractmethods__)

def test_registrar_add_remove_share():
    saved_message = process_data.message
    stub = _StubMessage()
    process_data.message = stub
    try:
        registrar = aiko.compose_instance(
            RegistrarImpl, aiko.service_args("t_registrar"))

        registrar.service_add(
            "aiko/host/9999/9", "t_svc", "t_proto:0", "mqtt", "o", ["x=1"])
        assert registrar.services.count == 1
        assert registrar.share["service_count"] == 1
        topic, payload = stub.published[-1]
        assert topic == registrar.topic_out
        assert payload == "(add aiko/host/9999/9 t_svc t_proto:0 mqtt o (x=1))"

        registrar.services_share(
            "t/response", "t_svc", "*", "*", "*", "*")
        payloads = [payload for _, payload in stub.published]
        assert "(item_count 1)" in payloads
        assert payloads[-1] == "(sync t/response)"
        assert any(payload.startswith("(add aiko/host/9999/9 t_svc")
            for payload in payloads)

        registrar.service_remove("aiko/host/9999/9")
        assert registrar.services.count == 0
        assert len(registrar.history) == 1
        assert stub.published[-1][1] == "(remove aiko/host/9999/9)"

        registrar.services_history("t/response", 16)
        assert any(payload and "time_add" not in payload
            and payload.startswith("(add aiko/host/9999/9")
            for _, payload in stub.published[-2:])

        # The wire handler is parse-and-delegate onto the same methods
        registrar._topic_in_handler(None, registrar.topic_in,
            "(add aiko/host/8888/8 t_svc2 p:0 mqtt o (y=2))")
        assert registrar.services.count == 1
    finally:
        model = registrar.state_machine.model
        for handler in list(model._timers):              # the search timer
            model._timer_remove(handler)
        process_data.message = saved_message


# --------------------------------------------------------------------------- #
# The primary election's liveness probe

BOOT = process_data.TOPIC_REGISTRAR_BOOT
DEAD = "aiko/deadhost/4242/1"

@pytest.fixture
def election(monkeypatch):
    """A Registrar in primary_search with a recording message stub; every
    timer it leaves pending is removed afterwards"""

    stub = _StubMessage()
    monkeypatch.setattr(process_data, "message", stub)   # the class: undone cleanly
    registrar = aiko.compose_instance(RegistrarImpl, aiko.service_args("t_election"))
    model = registrar.state_machine.model
    yield registrar, model, stub
    for handler in list(model._timers):
        model._timer_remove(handler)

def state(registrar):
    return registrar.state_machine.get_state()

def found(registrar, topic_path=DEAD):
    registrar._registrar_handler("found", {"topic_path": topic_path,
                                           "version": "2", "timestamp": "0"})

def test_found_primary_is_probed(election):
    registrar, model, stub = election
    assert state(registrar) == "primary_search"
    assert model.primary_search_timer in model._timers
    found(registrar)
    assert state(registrar) == "primary_probe"
    assert registrar.share["lifecycle"] == "primary_probe"
    assert stub.published[-1] == (f"{DEAD}/in", f"(history {registrar.topic_probe} 0)")
    assert model._timers == {model.primary_probe_timer}  # the search timer cancelled

def test_probe_reply_makes_a_secondary(election):
    registrar, model, stub = election
    found(registrar)
    registrar._probe_handler(None, registrar.topic_probe, "(item_count 0)")
    assert state(registrar) == "secondary" and model._timers == set()
    assert stub.retained == []                           # nothing published

def test_probe_timeout_publishes_absent_then_the_echo_promotes(election):
    registrar, model, stub = election
    found(registrar)
    model.primary_probe_timer()                          # no reply
    assert stub.retained == [(BOOT, "(primary absent)")]
    assert state(registrar) == "primary_search"
    registrar._registrar_handler("absent", None)         # the echo
    assert state(registrar) == "primary"
    assert stub.will == (BOOT, "(primary absent)", True)
    assert stub.retained[-1][1].startswith(f"(primary found {registrar.topic_path} ")
    assert model._timers == set()

def test_probe_timeout_without_echo_the_search_timer_promotes(election):
    registrar, model, stub = election
    found(registrar)
    model.primary_probe_timer()
    assert model._timers == {model.primary_search_timer}
    model.primary_search_timer()                         # the echo was lost
    assert state(registrar) == "primary" and model._timers == set()

def test_own_topic_path_never_announced_is_stale(election):
    registrar, model, stub = election
    found(registrar, registrar.topic_path)               # a reused PID
    assert state(registrar) == "primary_search"
    assert stub.retained == [(BOOT, "(primary absent)")]
    assert not any(payload.startswith("(history") for _, payload in stub.published)

def test_own_topic_path_once_announced_is_this_registrar(election):
    registrar, model, stub = election
    registrar.announced = True
    found(registrar, registrar.topic_path)
    assert state(registrar) == "primary"

def test_absent_while_probing_searches_without_publishing(election):
    registrar, model, stub = election
    found(registrar)
    registrar._registrar_handler("absent", None)
    assert state(registrar) == "primary_search"
    assert stub.retained == [] and model._timers == {model.primary_search_timer}

def test_newer_primary_is_probed_again(election):
    registrar, model, stub = election
    found(registrar)
    found(registrar, "aiko/newhost/77/1")
    assert state(registrar) == "primary_probe" and model.probe_target == "aiko/newhost/77/1"
    assert stub.published[-1][0] == "aiko/newhost/77/1/in"
    probes = len(stub.published)
    found(registrar, "aiko/newhost/77/1")                # the same one: no new probe
    assert len(stub.published) == probes
    assert model._timers == {model.primary_probe_timer}

def test_late_reply_or_timer_is_ignored(election):
    registrar, model, stub = election
    registrar._probe_handler(None, registrar.topic_probe, "(item_count 0)")
    assert state(registrar) == "primary_search"          # not probing: ignored
    model.primary_probe_timer()
    assert stub.retained == []

def test_history_zero_costs_one_message(election):
    registrar, model, stub = election
    registrar.service_add("aiko/h/1/1", "s", "p:0", "mqtt", "o", [])
    registrar.service_remove("aiko/h/1/1")
    before = len(stub.published)
    registrar.services_history("t/probe", 0)
    assert stub.published[before:] == [("t/probe", "(item_count 0)")]

def test_probe_timeout_on_the_real_event_loop(election, monkeypatch):
    registrar, model, stub = election
    monkeypatch.setattr(registrar_module, "_PRIMARY_PROBE_TIMEOUT", 0.05)
    monkeypatch.setattr(registrar_module, "_PRIMARY_PROBE_JITTER", 0.0)
    monkeypatch.setattr(registrar_module, "_PRIMARY_SEARCH_TIMEOUT", 0.05)
    model._timer_remove(model.primary_search_timer)      # armed at 2 s: re-arm
    registrar.state_machine.transition("primary_found", {"topic_path": DEAD})

    def stop():
        event.remove_timer_handler(stop)
        event.terminate()

    event.add_timer_handler(stop, 0.5)
    event.loop()
    assert stub.retained[0] == (BOOT, "(primary absent)")
    assert state(registrar) == "primary"                 # the search timer promoted
    assert model._timers == set()
