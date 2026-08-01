# Usage
# ~~~~~
# pytest [-s] unit/test_registrar.py
#
# Unit tests for the Registrar Interface contract (e_10 §2.2, 2026-07-13):
# the wire commands add/remove/history/share are real Interface methods
# (service_add / service_remove / services_history / services_share — the
# "service(s)_" prefix avoids colliding with universal Service state
# "share" and "history"), with _topic_in_handler() reduced to
# parse-and-delegate.  Wire-level behaviour (election, leases) needs a
# broker and belongs to e_06 integration tests.
#
# To Do
# ~~~~~
# - None, yet !

import aiko_services as aiko
from aiko_services.main import aiko as process_data
from aiko_services.main.registrar import Registrar, RegistrarImpl


class _StubMessage:
    def __init__(self):
        self.published = []

    def publish(self, topic, payload=None):
        self.published.append((topic, payload))

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
        process_data.message = saved_message
