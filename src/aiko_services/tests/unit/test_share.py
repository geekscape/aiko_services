# Usage
# ~~~~~
# pytest [-s] unit/test_share.py
#
# Unit tests for the share.py Interface / Implementation conversion
# (e_10 §2.1, 2026-07-13): composed ECProducer / ECConsumer construction,
# the deprecated one-release positional-construction shim, and the ECCache
# local replica.  Wire behaviour (leases, share requests, sync) needs a
# broker and belongs to the e_06 integration / golden-trace work — these
# tests cover construction, local reads and handler bookkeeping only.
#
# To Do
# ~~~~~
# - None, yet !

import aiko_services as aiko
from aiko_services.main.context import Context


def _make_actor(name):
    class TShareActor(aiko.Actor):  # synthesized __init__ (ADR-021)
        pass
    TShareActor.__name__ = f"TShareActor_{name}"
    return aiko.compose_instance(TShareActor, aiko.actor_args(name))


def test_actor_ec_producer_is_composed():
    actor = _make_actor("t_share_actor")
    assert isinstance(actor.ec_producer, aiko.ECProducer)
    assert isinstance(actor.ec_producer, aiko.ECProducerImpl)
    actor.ec_producer.update("lifecycle", "testing")
    assert actor.ec_producer.get("lifecycle") == "testing"
    assert actor.share["lifecycle"] == "testing"

def test_ec_producer_deprecated_positional_shim():
    # One-release shim: "ECProducer(service, share)" still works, returning
    # the composed Implementation
    actor = _make_actor("t_share_shim")
    share = {"key_1": "value_1"}
    producer = aiko.ECProducer(actor, share)
    assert isinstance(producer, aiko.ECProducerImpl)
    assert producer.get("key_1") == "value_1"
    producer.update("key_2.nested", "value_2")
    assert producer.get("key_2.nested") == "value_2"
    producer.remove("key_1")
    assert producer.get("key_1") is None

def test_ec_consumer_deprecated_positional_shim():
    actor = _make_actor("t_share_consumer")
    cache = {}
    consumer = aiko.ECConsumer(
        actor, 0, cache, f"{actor.topic_path}/control")
    assert isinstance(consumer, aiko.ECConsumerImpl)
    events = []
    consumer.add_handler(
        lambda consumer_id, command, name, value:
            events.append((command, name, value)))
    consumer.terminate()
    assert consumer.cache_state == "empty"

def test_ec_cache_local_get_and_handlers():
    actor = _make_actor("t_share_cache")
    cache = aiko.compose_instance(aiko.ECCacheImpl, aiko.ec_cache_args(
        actor, aiko.ServiceFilter("*", "t_producer", "*", "*", "*", "*")))
    assert cache.get("anything", default="fallback") == "fallback"

    # A producer appears (simulated discovery event, no broker required)
    topic_path = "aiko/host/1234/1"
    cache._service_change_handler("add",
        [topic_path, "t_producer", "*", "*", "*", []])
    assert topic_path in cache.consumers
    assert isinstance(cache.consumers[topic_path], aiko.ECConsumerImpl)

    # Local, non-blocking reads from the replica
    cache.caches[topic_path]["battery"] = {"percent": "82"}
    assert cache.get("battery.percent") == "82"           # sole producer
    assert cache.get("battery.percent", topic_path=topic_path) == "82"
    assert cache.get("absent", default=0) == 0

    # Filtered update call-backs (local callable — P12: mobile predicates
    # are refused until the sandboxed predicate language ships)
    seen = []
    cache.add_handler(
        lambda tp, command, name, value: seen.append((tp, name, value)),
        filter=lambda name, value: name.startswith("battery"))
    assert seen == [(topic_path, "battery.percent", "82")]  # replay
    relay = cache._make_consumer_relay_handler(topic_path)
    relay(1, "update", "battery.percent", "81")
    relay(1, "update", "screen.detail", "off")              # filtered out
    assert seen[-1] == (topic_path, "battery.percent", "81")
    assert len(seen) == 2

    # Producer disappears; replica and consumer are cleaned up
    cache._service_change_handler("remove",
        [topic_path, "t_producer", "*", "*", "*", []])
    assert cache.consumers == {}
    assert cache.get("battery.percent", default=None) is None
    cache.terminate()


# --------------------------------------------------------------------------- #
# ServicesCache: a bounded warning when the Registrar never replies

class _StubService:
    topic_path = "aiko/t_host/1/1"

    def add_message_handler(self, handler, topic, binary=False):
        pass

    def remove_message_handler(self, handler, topic):
        pass


class _Connected:
    def __init__(self, connected):
        self.connected = connected

    def is_connected(self, state):
        return self.connected


def test_services_cache_warns_once_when_the_registrar_is_silent(monkeypatch):
    import aiko_services.main.share as share_module
    from aiko_services.main import aiko as process_data

    published, warnings = [], []
    stub = type("Message", (), {"publish": lambda self, topic, payload:
                                published.append((topic, payload))})()
    monkeypatch.setattr(process_data, "message", stub)
    monkeypatch.setattr(process_data, "registrar", {"topic_path": "aiko/dead/9/1"})
    monkeypatch.setattr(share_module._LOGGER, "warning", warnings.append)
    cache = share_module.ServicesCache(_StubService())
    try:
        cache._connection_state_handler(_Connected(True), None)
        assert published[-1][0] == "aiko/dead/9/1/in" and cache._reply_timer_pending
        cache._reply_timer()                             # no (item_count ...)
        assert len(warnings) == 1 and "aiko/dead/9/1" in warnings[0]
        assert "mosquitto_pub" in warnings[0] and not cache._reply_timer_pending

        cache._connection_state_handler(_Connected(False), None)   # reset
        cache._connection_state_handler(_Connected(True), None)
        assert cache._reply_timer_pending
        cache.registrar_share_handler(None, "t", "(item_count 0)")   # a reply
        assert not cache._reply_timer_pending

        cache._connection_state_handler(_Connected(False), None)
        cache._connection_state_handler(_Connected(True), None)
        cache._connection_state_handler(_Connected(False), None)   # lost: cancelled
        assert not cache._reply_timer_pending and len(warnings) == 1
    finally:
        process_data.connection.remove_handler(cache._connection_state_handler)
        cache._reply_timer_cancel()
