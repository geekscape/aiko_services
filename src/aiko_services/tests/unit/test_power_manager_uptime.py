# Usage
# ~~~~~
# pytest [-s] unit/test_power_manager_uptime.py
#
# Unit tests for who still needs this host
# (actors/power_manager/uptime.py, and the wire function in
# power_manager.py).
#
# The register is a plain value store with the clock as an argument, so time
# is walked rather than waited for.
#
# Two things are worth reading first.  A client is its own topic, so a
# client that asks twice extends one claim rather than making two.  And the
# topic a client names is checked before anything is published to it:
# without that check an unknown client makes this Actor publish wherever it
# likes.

import itertools

import pytest

import aiko_services as aiko
from aiko_services.actors.power_manager import (
    MockPowerManagerImpl, THRESHOLDS, power_manager_args,
)
from aiko_services.actors.power_manager.uptime import (
    BRIDGE_TOPIC, UPTIME_MAXIMUM_S, UPTIME_REQUESTS_MAXIMUM, UptimeLease,
    UptimeRegister,
)

_counter = itertools.count()
TOPIC = "aikotest/host/900/1/in"
OTHER = "aikotest/host/901/1/in"

# The register ------------------------------------------------------------- #

def test_a_request_is_granted_with_the_seconds_it_asked_for():
    register = UptimeRegister()
    assert register.request(TOPIC, 300, "upload", 1000.0)  \
        == ("granted", "300")
    assert register.held(1000.0) == 1

def test_a_claim_runs_out_at_its_time():
    register = UptimeRegister()
    register.request(TOPIC, 300, "upload", 1000.0)
    assert register.held(1299.0) == 1
    assert register.held(1300.0) == 0

def test_a_client_that_asks_again_extends_one_claim():
    """The key is the client, so a client in a loop cannot fill the
    register with copies of itself"""

    register = UptimeRegister()
    register.request(TOPIC, 300, "upload", 1000.0)
    register.request(TOPIC, 300, "upload", 1200.0)
    assert register.held(1200.0) == 1
    assert register.held(1450.0) == 1            # The second one moved it

def test_two_clients_are_two_claims():
    register = UptimeRegister()
    register.request(TOPIC, 60, "upload", 1000.0)
    register.request(OTHER, 60, "recording", 1000.0)
    assert register.held(1000.0) == 2

def test_zero_seconds_releases():
    """A client that has finished says so, rather than waiting to expire"""

    register = UptimeRegister()
    register.request(TOPIC, 300, "upload", 1000.0)
    assert register.request(TOPIC, 0, "-", 1010.0) == ("released", "0")
    assert register.held(1010.0) == 0

def test_releasing_what_was_never_held_is_not_an_error():
    assert UptimeRegister().request(TOPIC, 0, "-", 1000.0)[0] == "released"

def test_more_than_the_maximum_is_refused_with_the_maximum():
    register = UptimeRegister(maximum_seconds=600)
    outcome, detail = register.request(TOPIC, 9999, "upload", 1000.0)
    assert outcome == "refused"
    assert detail == "maximum_seconds 600"
    assert register.held(1000.0) == 0

def test_the_maximum_itself_is_granted():
    register = UptimeRegister(maximum_seconds=600)
    assert register.request(TOPIC, 600, "upload", 1000.0)[0] == "granted"

def test_too_many_claims_are_refused():
    register = UptimeRegister(maximum_requests=2)
    register.request("a/b/1/1/in", 60, "one", 1000.0)
    register.request("a/b/2/1/in", 60, "two", 1000.0)
    outcome, detail = register.request("a/b/3/1/in", 60, "three", 1000.0)
    assert outcome == "refused"
    assert detail == "no_resource requests"

def test_a_client_that_already_holds_one_is_not_refused_when_full():
    """Otherwise a full register would stop every holder from extending"""

    register = UptimeRegister(maximum_requests=1)
    register.request(TOPIC, 60, "upload", 1000.0)
    assert register.request(TOPIC, 60, "upload", 1030.0)[0] == "granted"

def test_seconds_that_are_not_a_number_are_refused():
    assert UptimeRegister().request(TOPIC, "soon", "upload", 1000.0)  \
        == ("refused", "parameters")

def test_a_negative_request_releases_rather_than_grants():
    register = UptimeRegister()
    register.request(TOPIC, 60, "upload", 1000.0)
    assert register.request(TOPIC, -60, "upload", 1000.0)[0] == "released"
    assert register.held(1000.0) == 0

def test_expiry_returns_the_topics_so_the_clients_can_be_told():
    """An expiry is never silent"""

    register = UptimeRegister()
    register.request(TOPIC, 60, "upload", 1000.0)
    register.request(OTHER, 600, "recording", 1000.0)
    assert register.expire(1100.0) == [TOPIC]
    assert register.held(1100.0) == 1

def test_expiry_counts_what_it_dropped():
    register = UptimeRegister()
    register.request(TOPIC, 60, "upload", 1000.0)
    register.expire(1100.0)
    assert register.expired == 1

def test_the_reasons_are_each_given_once():
    register = UptimeRegister()
    register.request(TOPIC, 60, "upload", 1000.0)
    register.request(OTHER, 60, "upload", 1000.0)
    assert register.reasons(1000.0) == ("upload",)

def test_what_is_published_says_who_and_for_how_long():
    register = UptimeRegister()
    register.request(TOPIC, 300, "recording", 1000.0)
    items = register.as_share(1100.0)
    assert items["uptime.held"] == "1"
    assert items["uptime.reasons"] == "recording"
    assert items["uptime.longest_s"] == "200"

def test_no_published_token_holds_a_space():
    """They are shared variables, and ServiceFilter splits on a space"""

    register = UptimeRegister()
    register.request(TOPIC, 60, "store_forward", 1000.0)
    register.request(OTHER, 60, "recording", 1000.0)
    for value in register.as_share(1000.0).values():
        assert " " not in value

def test_nothing_held_says_so():
    assert UptimeRegister().as_share(1000.0)["uptime.reasons"] == "-"

def test_a_lease_reports_what_is_left_and_never_less_than_nothing():
    lease = UptimeLease(TOPIC, 60.0, "upload", 1060.0)
    assert lease.left(1030.0) == 30.0
    assert lease.left(9999.0) == 0.0

def test_the_bridge_is_not_a_client_topic():
    """The power manager holds one claim for a client that cannot yet ask
    for itself, and nothing is ever published to it"""

    register = UptimeRegister()
    register.request(BRIDGE_TOPIC, 60, "store_forward", 1000.0)
    assert register.held(1000.0) == 1
    assert register.topics(1000.0) == ()

def test_the_defaults_are_bounded():
    assert 0 < UPTIME_MAXIMUM_S <= 3600
    assert 0 < UPTIME_REQUESTS_MAXIMUM <= 1024

def test_the_limits_are_configuration():
    for name in ("uptime_maximum_s", "uptime_requests_maximum"):
        assert name in THRESHOLDS

# The wire function -------------------------------------------------------- #

def make_actor(**parameters):
    settings = {"log_directory": None, "telemetry": False, "timer": False,
        "worker": False}
    settings.update(parameters)
    init_args = power_manager_args(
        f"power_uptime_test_{next(_counter)}", "mock",
        declared=MockPowerManagerImpl.DECLARED_PROPERTIES, **settings)
    return aiko.compose_instance(MockPowerManagerImpl, init_args)

def own_topic(actor, pid="900", sid="1", suffix="in"):
    """A topic in this Actor's own namespace, which the guard allows"""

    namespace = str(actor.topic_path).split("/")[0]
    host = str(actor.topic_path).split("/")[1]
    return f"{namespace}/{host}/{pid}/{sid}/{suffix}"

def test_a_request_from_a_proper_topic_is_held():
    actor = make_actor()
    actor.request_uptime(own_topic(actor), 300, "recording")
    assert actor.share["uptime"]["held"] == "1"
    assert actor.share["uptime"]["reasons"] == "recording"

def test_a_request_is_counted():
    actor = make_actor()
    actor.request_uptime(own_topic(actor), 300, "recording")
    assert actor.share["metrics"]["uptime_granted"] == 1

def test_a_request_holds_the_host_up():
    actor = make_actor(
        properties=("readings", "hold", "signal", "button", "dock"),
        script=[{"battery_volts": 12.0, "docked": False}])
    actor.request_uptime(own_topic(actor), 300, "recording")
    actor._evaluate(actor.reading(), now=1000.0)
    actor._evaluate(actor.reading(), now=1011.0)       # Past the dock dwell
    assert actor.share["policy_reason"] == "uptime_held"

class FakeMessage:
    """A message layer that records what was published.

    Patched onto ProcessData, the class, and never onto aiko.process: an
    attribute set on the instance hides the class attribute for every later
    test, which g_03_AgentContext records as a sharp edge"""

    def __init__(self):
        self.published = []

    def publish(self, topic, payload):
        self.published.append((topic, payload))

def fake_message(monkeypatch):
    from aiko_services.main.process import ProcessData

    message = FakeMessage()
    monkeypatch.setattr(ProcessData, "message", message)
    return message

def test_the_client_is_told_what_became_of_its_request(monkeypatch):
    """The answer is a published message, so a test must assert the publish
    itself.  Without this the publish failed silently on the hardware,
    because "aiko.message" is the module of that name and not the process's
    message layer"""

    actor = make_actor()
    message = fake_message(monkeypatch)
    topic = own_topic(actor)
    actor.request_uptime(topic, 300, "recording")
    assert message.published and message.published[0][0] == topic
    assert "uptime_granted" in message.published[0][1]
    assert "300" in message.published[0][1]

def test_a_refusal_is_published_too(monkeypatch):
    actor = make_actor()
    message = fake_message(monkeypatch)
    actor.request_uptime(own_topic(actor), 99999, "greedy")
    payload = message.published[0][1]
    assert "uptime_refused" in payload
    assert "maximum_seconds" in payload

def test_a_refusal_carries_separate_arguments(monkeypatch):
    """Otherwise the wire encoding makes one length-prefixed string of
    "maximum_seconds 600", which a client has to take apart again"""

    actor = make_actor()
    message = fake_message(monkeypatch)
    actor.request_uptime(own_topic(actor), 99999, "greedy")
    assert message.published[0][1] == "(uptime_refused maximum_seconds 600)"

def test_a_release_is_published_too(monkeypatch):
    actor = make_actor()
    message = fake_message(monkeypatch)
    actor.request_uptime(own_topic(actor), 0, "done")
    assert "uptime_released" in message.published[0][1]

def test_a_holder_hears_a_change_of_mode(monkeypatch):
    """So a client can stop writing without watching the shared state"""

    actor = make_actor(
        properties=("readings", "hold", "signal", "button", "dock"),
        script=[{"battery_volts": 9.0, "docked": False}])
    actor.request_uptime(own_topic(actor), 300, "recording")
    message = fake_message(monkeypatch)
    actor._evaluate(actor.reading(), now=1000.0)
    assert any("power_mode" in payload
        for _, payload in message.published)

def test_an_expiry_is_never_silent(monkeypatch):
    actor = make_actor(
        properties=("readings", "hold", "signal", "button", "dock"),
        script=[{"battery_volts": 12.0, "docked": True}])
    actor.request_uptime(own_topic(actor), 10, "recording")
    message = fake_message(monkeypatch)
    actor._evaluate(actor.reading(), now=actor._now() + 100.0)
    assert any("uptime_expired" in payload
        for _, payload in message.published)

def test_a_publish_that_fails_does_not_stop_a_reading(monkeypatch):
    from aiko_services.main.process import ProcessData

    class Broken:
        def publish(self, topic, payload):
            raise OSError("the broker went away")

    actor = make_actor(script=[{"battery_volts": 12.0, "docked": True}])
    monkeypatch.setattr(ProcessData, "message", Broken())
    actor.request_uptime(own_topic(actor), 300, "recording")
    assert actor.share["uptime"]["held"] == "1"       # Still taken
    assert actor.sample().battery_volts == 12.0      # Still reading

def test_a_wildcard_topic_is_refused_and_counted():
    """Without this check an unknown client makes this Actor publish
    wherever it likes"""

    actor = make_actor()
    actor.request_uptime("aikotest/+/1/1/in", 300, "recording")
    assert actor.share["uptime"]["held"] == "0"
    assert actor.share["metrics"]["denied"] == 1

def test_a_topic_in_another_namespace_is_refused():
    actor = make_actor()
    actor.request_uptime("elsewhere/host/1/1/in", 300, "recording")
    assert actor.share["uptime"]["held"] == "0"

def test_a_topic_with_a_suffix_a_service_does_not_own_is_refused():
    actor = make_actor()
    actor.request_uptime(own_topic(actor, suffix="log"), 300, "recording")
    assert actor.share["uptime"]["held"] == "0"

def test_the_bridge_key_cannot_be_asked_for_from_the_bus():
    """It is not a topic, and a client must not be able to take the claim
    that the power manager holds for another"""

    actor = make_actor()
    actor.request_uptime(BRIDGE_TOPIC, 300, "store_forward")
    assert actor.share["uptime"]["held"] == "0"
    assert actor.share["metrics"]["denied"] == 1

def test_a_request_that_is_too_long_is_refused_and_counted():
    actor = make_actor()
    actor.request_uptime(own_topic(actor), 99999, "recording")
    assert actor.share["uptime"]["held"] == "0"
    assert actor.share["metrics"]["uptime_refused"] == 1

def test_zero_seconds_releases_from_the_bus():
    actor = make_actor()
    topic = own_topic(actor)
    actor.request_uptime(topic, 300, "recording")
    actor.request_uptime(topic, 0, "-")
    assert actor.share["uptime"]["held"] == "0"

# The bridge --------------------------------------------------------------- #

def test_the_bridge_holds_a_claim_while_the_queue_has_work():
    """Today's store and forward Actor knows nothing about up-time, so the
    power manager holds a claim for it.  This is meant to go"""

    from aiko_services.actors.power_manager import choose_queue_source

    actor = make_actor(
        properties=("readings", "hold", "signal", "button", "dock"),
        script=[{"battery_volts": 12.0, "docked": False}],
        queue_source=choose_queue_source("fake"))
    actor._queue.set_state(known=True, depth=4)
    actor._evaluate(actor.reading(), now=1000.0)
    assert actor.share["uptime"]["reasons"] == "store_forward"

def test_the_bridge_lets_its_claim_go_when_the_queue_empties():
    from aiko_services.actors.power_manager import choose_queue_source

    actor = make_actor(
        properties=("readings", "hold", "signal", "button", "dock"),
        script=[{"battery_volts": 12.0, "docked": False}],
        queue_source=choose_queue_source("fake"))
    actor._queue.set_state(known=True, depth=4)
    actor._evaluate(actor.reading(), now=1000.0)
    actor._queue.set_state(depth=0)
    actor._evaluate(actor.reading(), now=1001.0)
    assert actor.share["uptime"]["held"] == "0"

def test_a_queue_that_is_unknown_holds_nothing():
    """The unknown case is gone: a bridge that cannot see a queue holds no
    claim, and the grace then decides"""

    from aiko_services.actors.power_manager import choose_queue_source

    actor = make_actor(
        properties=("readings", "hold", "signal", "button", "dock"),
        script=[{"battery_volts": 12.0, "docked": False}],
        queue_source=choose_queue_source("fake"))
    actor._evaluate(actor.reading(), now=1000.0)
    assert actor.share["uptime"]["held"] == "0"

# --------------------------------------------------------------------------- #
