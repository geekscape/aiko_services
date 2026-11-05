# Usage
# ~~~~~
# pytest [-s] unit/test_power_manager_power_up.py
#
# Unit tests for who still needs this host
# (actors/power_manager/power_up.py, and the wire function in
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
from aiko_services.main import event
from aiko_services.main.lease import Lease
from aiko_services.actors.power_manager import (
    MockPowerManagerImpl, THRESHOLDS, power_manager_args,
)
from aiko_services.actors.power_manager.power_up import (
    BRIDGE_TOPIC, POWER_UP_MAXIMUM_S, POWER_UP_REQUESTS_MAXIMUM,
    PowerUpLease, PowerUpRegister,
)

_counter = itertools.count()
TOPIC = "aikotest/host/900/1/in"
OTHER = "aikotest/host/901/1/in"

# The register ------------------------------------------------------------- #

def timer_count():
    """How many timers the event loop holds.  A Lease carries one, so this
    is how a test sees that a Lease was really taken and really released"""

    count, current = 0, event.event_list.head
    while current:
        count += 1
        current = current.next
    return count

def test_a_power_up_lease_is_a_lease():
    """It extends the framework's Lease, as ECLease does, so an expiry acts
    at the agreed time rather than at the next convenient moment"""

    assert issubclass(PowerUpLease, Lease)

def test_a_request_is_granted_with_the_seconds_it_asked_for():
    register = PowerUpRegister()
    assert register.request(TOPIC, 300, "upload") == ("granted", "300")
    assert register.held() == 1
    register.terminate()

def test_a_lease_carries_a_timer_of_its_own():
    """Which is the whole reason for using the framework's Lease: the
    expiry happens at the time that was agreed"""

    register = PowerUpRegister()
    before = timer_count()
    register.request(TOPIC, 300, "upload")
    assert timer_count() > before
    register.terminate()
    assert timer_count() == before

def test_releasing_leaves_no_timer_behind():
    register = PowerUpRegister()
    before = timer_count()
    register.request(TOPIC, 300, "upload")
    register.request(TOPIC, 0, "-")
    assert timer_count() == before
    assert register.held() == 0

def test_a_client_that_asks_again_extends_one_lease():
    """The key is the client, so a client in a loop cannot fill the
    register with copies of itself"""

    register = PowerUpRegister()
    register.request(TOPIC, 300, "upload")
    assert register.request(TOPIC, 120, "upload") == ("granted", "120")
    assert register.held() == 1
    assert register.seconds() == 120.0           # The Lease time moved
    register.terminate()

def test_extending_changes_the_reason_too():
    register = PowerUpRegister()
    register.request(TOPIC, 60, "upload")
    register.request(TOPIC, 60, "recording")
    assert register.reasons() == ("recording",)
    register.terminate()

def test_two_clients_are_two_leases():
    register = PowerUpRegister()
    register.request(TOPIC, 60, "upload")
    register.request(OTHER, 60, "recording")
    assert register.held() == 2
    register.terminate()

def test_zero_seconds_releases():
    """A client that has finished says so, rather than waiting to expire"""

    register = PowerUpRegister()
    register.request(TOPIC, 300, "upload")
    assert register.request(TOPIC, 0, "-") == ("released", "0")
    assert register.held() == 0

def test_releasing_what_was_never_held_is_not_an_error():
    assert PowerUpRegister().request(TOPIC, 0, "-")[0] == "released"

def test_more_than_the_maximum_is_refused_with_the_maximum():
    register = PowerUpRegister(maximum_seconds=600)
    outcome, detail = register.request(TOPIC, 9999, "upload")
    assert outcome == "refused"
    assert detail == "maximum_seconds 600"
    assert register.held() == 0

def test_the_maximum_itself_is_granted():
    register = PowerUpRegister(maximum_seconds=600)
    assert register.request(TOPIC, 600, "upload")[0] == "granted"
    register.terminate()

def test_too_many_leases_are_refused():
    register = PowerUpRegister(maximum_requests=2)
    register.request("a/b/1/1/in", 60, "one")
    register.request("a/b/2/1/in", 60, "two")
    assert register.request("a/b/3/1/in", 60, "three")  \
        == ("refused", "no_resource requests")
    register.terminate()

def test_a_client_that_already_holds_one_is_not_refused_when_full():
    """Otherwise a full register would stop every holder from extending"""

    register = PowerUpRegister(maximum_requests=1)
    register.request(TOPIC, 60, "upload")
    assert register.request(TOPIC, 60, "upload")[0] == "granted"
    register.terminate()

def test_seconds_that_are_not_a_number_are_refused():
    assert PowerUpRegister().request(TOPIC, "soon", "upload")  \
        == ("refused", "parameters")

def test_a_negative_request_releases_rather_than_grants():
    register = PowerUpRegister()
    register.request(TOPIC, 60, "upload")
    assert register.request(TOPIC, -60, "upload")[0] == "released"
    assert register.held() == 0

def test_an_expiry_tells_whoever_is_watching():
    """The framework's Lease calls this at the agreed time, on the
    event-loop thread.  An expiry is never silent"""

    gone = []
    register = PowerUpRegister(expired_handler=gone.append)
    register.request(TOPIC, 60, "upload")
    register._lease_expired(TOPIC)
    assert gone == [TOPIC]
    assert register.held() == 0
    assert register.expired == 1

def test_an_expiry_of_a_lease_that_went_already_is_ignored():
    register = PowerUpRegister(expired_handler=lambda topic: None)
    register._lease_expired(TOPIC)
    assert register.expired == 0

def test_an_expiry_leaves_no_timer_behind():
    register = PowerUpRegister(expired_handler=lambda topic: None)
    before = timer_count()
    register.request(TOPIC, 60, "upload")
    register._lease_expired(TOPIC)
    assert timer_count() == before

def test_the_reasons_are_each_given_once():
    register = PowerUpRegister()
    register.request(TOPIC, 60, "upload")
    register.request(OTHER, 60, "upload")
    assert register.reasons() == ("upload",)
    register.terminate()

def test_what_is_published_says_who_and_for_how_long():
    register = PowerUpRegister()
    register.request(TOPIC, 300, "recording")
    items = register.as_share()
    assert items["power_up.held"] == "1"
    assert items["power_up.reasons"] == "recording"
    assert items["power_up.seconds"] == "300"
    register.terminate()

def test_no_published_token_holds_a_space():
    """They are shared variables, and ServiceFilter splits on a space"""

    register = PowerUpRegister()
    register.request(TOPIC, 60, "store_forward")
    register.request(OTHER, 60, "recording")
    for value in register.as_share().values():
        assert " " not in value
    register.terminate()

def test_nothing_held_says_so():
    assert PowerUpRegister().as_share()["power_up.reasons"] == "-"

def test_a_lease_knows_the_client_that_holds_it():
    lease = PowerUpLease(60.0, TOPIC, "upload")
    assert lease.topic == TOPIC
    assert lease.reason == "upload"
    lease.terminate()

def test_the_bridge_is_not_a_client_topic():
    """The reserved key is not a topic, and nothing is published to it"""

    register = PowerUpRegister()
    register.request(BRIDGE_TOPIC, 60, "store_forward")
    assert register.held() == 1
    assert register.topics() == ()
    register.terminate()

def test_the_defaults_are_bounded():
    assert 0 < POWER_UP_MAXIMUM_S <= 3600
    assert 0 < POWER_UP_REQUESTS_MAXIMUM <= 1024

def test_the_limits_are_configuration():
    for name in ("power_up_maximum_s", "power_up_requests_maximum"):
        assert name in THRESHOLDS

# The wire function -------------------------------------------------------- #

_made = []

@pytest.fixture(autouse=True)
def close_what_was_made():
    """Every Lease carries an event-loop timer, so an Actor that took one
    is closed when its test ends.  The conftest fixture would reclaim the
    timer anyway, and a test should still release what it registers"""

    yield
    while _made:
        try:
            _made.pop().close()
        except Exception:                                # noqa: BLE001
            pass

def make_actor(**parameters):
    settings = {"log_directory": None, "telemetry": False, "timer": False,
        "worker": False}
    settings.update(parameters)
    init_args = power_manager_args(
        f"power_up_test_{next(_counter)}", "mock",
        declared=MockPowerManagerImpl.DECLARED_PROPERTIES, **settings)
    actor = aiko.compose_instance(MockPowerManagerImpl, init_args)
    _made.append(actor)
    return actor

def own_topic(actor, pid="900", sid="1", suffix="in"):
    """A topic in this Actor's own namespace, which the guard allows"""

    namespace = str(actor.topic_path).split("/")[0]
    host = str(actor.topic_path).split("/")[1]
    return f"{namespace}/{host}/{pid}/{sid}/{suffix}"

def test_a_request_from_a_proper_topic_is_held():
    actor = make_actor()
    actor.request_power_up(own_topic(actor), 300, "recording")
    assert actor.share["power_up"]["held"] == "1"
    assert actor.share["power_up"]["reasons"] == "recording"

def test_a_request_is_counted():
    actor = make_actor()
    actor.request_power_up(own_topic(actor), 300, "recording")
    assert actor.share["metrics"]["power_up_granted"] == 1

def test_a_request_holds_the_host_up():
    actor = make_actor(
        properties=("readings", "hold", "signal", "button", "dock"),
        script=[{"battery_volts": 12.0, "docked": False}])
    actor.request_power_up(own_topic(actor), 300, "recording")
    actor._evaluate(actor.reading(), now=1000.0)
    actor._evaluate(actor.reading(), now=1011.0)       # Past the dock dwell
    assert actor.share["policy_reason"] == "power_up_held"

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
    actor.request_power_up(topic, 300, "recording")
    assert message.published and message.published[0][0] == topic
    assert "power_up_granted" in message.published[0][1]
    assert "300" in message.published[0][1]

def test_a_refusal_is_published_too(monkeypatch):
    actor = make_actor()
    message = fake_message(monkeypatch)
    actor.request_power_up(own_topic(actor), 99999, "greedy")
    payload = message.published[0][1]
    assert "power_up_refused" in payload
    assert "maximum_seconds" in payload

def test_a_refusal_carries_separate_arguments(monkeypatch):
    """Otherwise the wire encoding makes one length-prefixed string of
    "maximum_seconds 600", which a client has to take apart again"""

    actor = make_actor()
    message = fake_message(monkeypatch)
    actor.request_power_up(own_topic(actor), 99999, "greedy")
    assert message.published[0][1] == "(power_up_refused maximum_seconds 600)"

def test_a_release_is_published_too(monkeypatch):
    actor = make_actor()
    message = fake_message(monkeypatch)
    actor.request_power_up(own_topic(actor), 0, "done")
    assert "power_up_released" in message.published[0][1]

def test_a_holder_hears_a_change_of_mode(monkeypatch):
    """So a client can stop writing without watching the shared state"""

    actor = make_actor(
        properties=("readings", "hold", "signal", "button", "dock"),
        script=[{"battery_volts": 9.0, "docked": False}])
    actor.request_power_up(own_topic(actor), 300, "recording")
    message = fake_message(monkeypatch)
    actor._evaluate(actor.reading(), now=1000.0)
    assert any("power_mode" in payload
        for _, payload in message.published)

def test_an_expiry_is_never_silent(monkeypatch):
    """The register's own handler is what the Lease timer calls at the
    agreed time, so a test calls it rather than waiting"""

    actor = make_actor(
        properties=("readings", "hold", "signal", "button", "dock"),
        script=[{"battery_volts": 12.0, "docked": True}])
    topic = own_topic(actor)
    actor.request_power_up(topic, 10, "recording")
    message = fake_message(monkeypatch)
    actor._power_up._lease_expired(topic)
    assert any("power_up_expired" in payload
        for _, payload in message.published)
    assert actor.share["power_up"]["held"] == "0"

def test_the_policy_is_asked_again_the_moment_the_last_lease_ends():
    """Prompt action at the agreed timeout is most of what a Lease is for.
    A host that waited for its next sample would be holding a battery pack
    up for nobody"""

    actor = make_actor(
        properties=("readings", "hold", "signal", "button", "dock"),
        script=[{"battery_volts": 12.0, "docked": False}])
    topic = own_topic(actor)
    actor.request_power_up(topic, 10, "recording")
    actor._evaluate(actor.reading(), now=1000.0)
    actor._evaluate(actor.reading(), now=1011.0)       # Past the dock dwell
    assert actor.share["policy_reason"] == "power_up_held"
    actor._power_up._lease_expired(topic)              # The agreed time
    assert actor.share["policy_reason"] != "power_up_held"

def test_an_expiry_that_leaves_another_lease_does_not_ask_again():
    """Only the last one to end is the event that lets a host stop"""

    actor = make_actor(
        properties=("readings", "hold", "signal", "button", "dock"),
        script=[{"battery_volts": 12.0, "docked": False}])
    first, second = own_topic(actor, pid="900"), own_topic(actor, pid="901")
    actor.request_power_up(first, 10, "recording")
    actor.request_power_up(second, 300, "upload")
    actor._power_up._lease_expired(first)
    assert actor.share["power_up"]["held"] == "1"
    assert actor.share["power_up"]["reasons"] == "upload"

def test_a_publish_that_fails_does_not_stop_a_reading(monkeypatch):
    from aiko_services.main.process import ProcessData

    class Broken:
        def publish(self, topic, payload):
            raise OSError("the broker went away")

    actor = make_actor(script=[{"battery_volts": 12.0, "docked": True}])
    monkeypatch.setattr(ProcessData, "message", Broken())
    actor.request_power_up(own_topic(actor), 300, "recording")
    assert actor.share["power_up"]["held"] == "1"       # Still taken
    assert actor.sample().battery_volts == 12.0      # Still reading

def test_a_wildcard_topic_is_refused_and_counted():
    """Without this check an unknown client makes this Actor publish
    wherever it likes"""

    actor = make_actor()
    actor.request_power_up("aikotest/+/1/1/in", 300, "recording")
    assert actor.share["power_up"]["held"] == "0"
    assert actor.share["metrics"]["denied"] == 1

def test_a_topic_in_another_namespace_is_refused():
    actor = make_actor()
    actor.request_power_up("elsewhere/host/1/1/in", 300, "recording")
    assert actor.share["power_up"]["held"] == "0"

def test_a_topic_with_a_suffix_a_service_does_not_own_is_refused():
    actor = make_actor()
    actor.request_power_up(own_topic(actor, suffix="log"), 300, "recording")
    assert actor.share["power_up"]["held"] == "0"

def test_the_bridge_key_cannot_be_asked_for_from_the_bus():
    """It is not a topic, and a client must not be able to take the claim
    that the power manager holds for another"""

    actor = make_actor()
    actor.request_power_up(BRIDGE_TOPIC, 300, "store_forward")
    assert actor.share["power_up"]["held"] == "0"
    assert actor.share["metrics"]["denied"] == 1

def test_a_request_that_is_too_long_is_refused_and_counted():
    actor = make_actor()
    actor.request_power_up(own_topic(actor), 99999, "recording")
    assert actor.share["power_up"]["held"] == "0"
    assert actor.share["metrics"]["power_up_refused"] == 1

def test_zero_seconds_releases_from_the_bus():
    actor = make_actor()
    topic = own_topic(actor)
    actor.request_power_up(topic, 300, "recording")
    actor.request_power_up(topic, 0, "-")
    assert actor.share["power_up"]["held"] == "0"

# --------------------------------------------------------------------------- #
