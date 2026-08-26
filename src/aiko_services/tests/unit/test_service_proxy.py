# Usage
# ~~~~~
# pytest [-s] unit/test_service_proxy.py
#
# Covers the remote Service proxy made by get_service_proxy():
# - a proxy publishes to the Service "topic_in" while the Service is present
# - a proxy raises ServiceUnavailable once discovery removes that Service,
#   rather than publishing to a topic with no subscriber and reporting success
# - only the removed Service's proxies are affected
# - a proxy obtained without a Service topic path keeps the old behaviour,
#   because nothing tells it when the Service goes away
# - is_available() reports the same state the proxy acts on

from abc import abstractmethod

import pytest

import aiko_services as aiko
from aiko_services.main import discovery

_TOPIC_A = "aiko/host/1000/1"
_TOPIC_B = "aiko/host/2000/1"


class _Target(aiko.Actor):
    aiko.Interface.default("_Target", None)

    @abstractmethod
    def ping(self, value):
        pass


@pytest.fixture
def published(monkeypatch):
    records = []

    class _Message:
        def publish(self, topic, payload, retain=False):
            records.append((topic, payload))

    monkeypatch.setattr(aiko.aiko, "message", _Message())
    monkeypatch.setattr(discovery, "_service_proxies", {})
    return records


def _proxy(topic_path):
    return aiko.get_service_proxy(
        f"{topic_path}/in", _Target, service_topic_path=topic_path)


def test_proxy_publishes_while_service_is_present(published):
    _proxy(_TOPIC_A).ping(1)
    assert published == [(f"{_TOPIC_A}/in", "(ping 1)")]


def test_proxy_raises_after_its_service_is_removed(published):
    proxy = _proxy(_TOPIC_A)
    proxy.ping(1)
    assert len(published) == 1

    discovery._remove_service_proxies(_TOPIC_A)

    with pytest.raises(aiko.ServiceUnavailable) as error:
        proxy.ping(2)
    assert "ping()" in str(error.value)
    assert _TOPIC_A in str(error.value)

    # The point of the change: nothing reached a topic with no subscriber
    assert len(published) == 1


def test_removing_one_service_leaves_other_proxies_alone(published):
    proxy_a = _proxy(_TOPIC_A)
    proxy_b = _proxy(_TOPIC_B)

    discovery._remove_service_proxies(_TOPIC_A)

    with pytest.raises(aiko.ServiceUnavailable):
        proxy_a.ping(1)
    proxy_b.ping(2)
    assert published == [(f"{_TOPIC_B}/in", "(ping 2)")]


def test_every_proxy_for_one_service_is_removed(published):
    proxy_0 = _proxy(_TOPIC_A)
    proxy_1 = _proxy(_TOPIC_A)

    discovery._remove_service_proxies(_TOPIC_A)

    for proxy in (proxy_0, proxy_1):
        with pytest.raises(aiko.ServiceUnavailable):
            proxy.ping(1)


def test_untracked_proxy_keeps_the_previous_behaviour(published):
    # get_service_proxy() without a Service topic path, as chat_server.py and
    # ExampleImpl.request() use it for a response topic.  Nothing reports when
    # that topic goes away, so the proxy cannot know: it must still publish.
    proxy = aiko.get_service_proxy(f"{_TOPIC_A}/in", _Target)
    discovery._remove_service_proxies(_TOPIC_A)
    proxy.ping(1)
    assert published == [(f"{_TOPIC_A}/in", "(ping 1)")]


def test_is_available_matches_what_the_proxy_does(published):
    proxy = _proxy(_TOPIC_A)
    assert proxy.is_available() is True

    discovery._remove_service_proxies(_TOPIC_A)

    assert proxy.is_available() is False
    with pytest.raises(aiko.ServiceUnavailable):
        proxy.ping(1)
