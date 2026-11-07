# Usage
# ~~~~~
# pytest [-s] unit/test_power_manager_powered_up.py
#
# Unit tests for who still needs this host
# (actors/power_manager/powered_up.py, and the wire function in
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
    THRESHOLDS,
    MockPowerManagerImpl,
    power_manager_args,
)
from aiko_services.actors.power_manager.powered_up import (
    BRIDGE_TOPIC,
    CONSTRAINTS,
    POWERED_UP_MAXIMUM_S,
    POWERED_UP_REQUESTS_MAXIMUM,
    LeaseConstraint,
    PoweredUpLease,
    PoweredUpRegister,
)
from aiko_services.main import event
from aiko_services.main.lease import Lease

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

    assert issubclass(PoweredUpLease, Lease)


def test_a_request_is_granted_with_the_seconds_it_asked_for():
    register = PoweredUpRegister()
    assert register.request(TOPIC, 300, "upload") == ("granted", "300")
    assert register.held() == 1
    register.terminate()


def test_a_lease_carries_a_timer_of_its_own():
    """Which is the whole reason for using the framework's Lease: the
    expiry happens at the time that was agreed"""

    register = PoweredUpRegister()
    before = timer_count()
    register.request(TOPIC, 300, "upload")
    assert timer_count() > before
    register.terminate()
    assert timer_count() == before


def test_releasing_leaves_no_timer_behind():
    register = PoweredUpRegister()
    before = timer_count()
    register.request(TOPIC, 300, "upload")
    register.request(TOPIC, 0, "-")
    assert timer_count() == before
    assert register.held() == 0


def test_a_client_that_asks_again_extends_one_lease():
    """The key is the client, so a client in a loop cannot fill the
    register with copies of itself"""

    register = PoweredUpRegister()
    register.request(TOPIC, 300, "upload")
    assert register.request(TOPIC, 120, "upload") == ("granted", "120")
    assert register.held() == 1
    assert register.seconds() == 120.0  # The Lease time moved
    register.terminate()


def test_extending_changes_the_reason_too():
    register = PoweredUpRegister()
    register.request(TOPIC, 60, "upload")
    register.request(TOPIC, 60, "recording")
    assert register.reasons() == ("recording",)
    register.terminate()


def test_two_clients_are_two_leases():
    register = PoweredUpRegister()
    register.request(TOPIC, 60, "upload")
    register.request(OTHER, 60, "recording")
    assert register.held() == 2
    register.terminate()


def test_zero_seconds_releases():
    """A client that has finished says so, rather than waiting to expire"""

    register = PoweredUpRegister()
    register.request(TOPIC, 300, "upload")
    assert register.request(TOPIC, 0, "-") == ("released", "0")
    assert register.held() == 0


def test_releasing_what_was_never_held_is_not_an_error():
    assert PoweredUpRegister().request(TOPIC, 0, "-")[0] == "released"


def test_more_than_the_maximum_is_refused_with_the_maximum():
    register = PoweredUpRegister(maximum_seconds=600)
    outcome, detail = register.request(TOPIC, 9999, "upload")
    assert outcome == "refused"
    assert detail == "maximum_seconds 600"
    assert register.held() == 0


def test_the_maximum_itself_is_granted():
    register = PoweredUpRegister(maximum_seconds=600)
    assert register.request(TOPIC, 600, "upload")[0] == "granted"
    register.terminate()


def test_too_many_leases_are_refused():
    register = PoweredUpRegister(maximum_requests=2)
    register.request("a/b/1/1/in", 60, "one")
    register.request("a/b/2/1/in", 60, "two")
    assert register.request("a/b/3/1/in", 60, "three") == ("refused", "no_resource requests")
    register.terminate()


def test_a_client_that_already_holds_one_is_not_refused_when_full():
    """Otherwise a full register would stop every holder from extending"""

    register = PoweredUpRegister(maximum_requests=1)
    register.request(TOPIC, 60, "upload")
    assert register.request(TOPIC, 60, "upload")[0] == "granted"
    register.terminate()


def test_seconds_that_are_not_a_number_are_refused():
    assert PoweredUpRegister().request(TOPIC, "soon", "upload") == ("refused", "parameters")


def test_a_negative_request_releases_rather_than_grants():
    register = PoweredUpRegister()
    register.request(TOPIC, 60, "upload")
    assert register.request(TOPIC, -60, "upload")[0] == "released"
    assert register.held() == 0


def test_an_expiry_tells_whoever_is_watching():
    """The framework's Lease calls this at the agreed time, on the
    event-loop thread.  An expiry is never silent"""

    gone = []
    register = PoweredUpRegister(expired_handler=gone.append)
    register.request(TOPIC, 60, "upload")
    register._lease_expired(TOPIC)
    assert gone == [TOPIC]
    assert register.held() == 0
    assert register.expired == 1


def test_an_expiry_of_a_lease_that_went_already_is_ignored():
    register = PoweredUpRegister(expired_handler=lambda topic: None)
    register._lease_expired(TOPIC)
    assert register.expired == 0


def test_an_expiry_leaves_no_timer_behind():
    register = PoweredUpRegister(expired_handler=lambda topic: None)
    before = timer_count()
    register.request(TOPIC, 60, "upload")
    register._lease_expired(TOPIC)
    assert timer_count() == before


def test_the_reasons_are_each_given_once():
    register = PoweredUpRegister()
    register.request(TOPIC, 60, "upload")
    register.request(OTHER, 60, "upload")
    assert register.reasons() == ("upload",)
    register.terminate()


def test_what_is_published_says_who_and_for_how_long():
    register = PoweredUpRegister()
    register.request(TOPIC, 300, "recording")
    items = register.as_share()
    assert items["powered_up.held"] == "1"
    assert items["powered_up.reasons"] == "recording"
    assert items["powered_up.seconds"] == "300"
    register.terminate()


def test_no_published_token_holds_a_space():
    """They are shared variables, and ServiceFilter splits on a space"""

    register = PoweredUpRegister()
    register.request(TOPIC, 60, "store_forward")
    register.request(OTHER, 60, "recording")
    for value in register.as_share().values():
        assert " " not in value
    register.terminate()


def test_nothing_held_says_so():
    assert PoweredUpRegister().as_share()["powered_up.reasons"] == "-"


def test_a_lease_knows_the_client_that_holds_it():
    lease = PoweredUpLease(60.0, TOPIC, "upload")
    assert lease.topic == TOPIC
    assert lease.reason == "upload"
    lease.terminate()


def test_the_bridge_is_not_a_client_topic():
    """The reserved key is not a topic, and nothing is published to it"""

    register = PoweredUpRegister()
    register.request(BRIDGE_TOPIC, 60, "store_forward")
    assert register.held() == 1
    assert register.topics() == ()
    register.terminate()


def test_the_defaults_are_bounded():
    assert 0 < POWERED_UP_MAXIMUM_S <= 3600
    assert 0 < POWERED_UP_REQUESTS_MAXIMUM <= 1024


def test_the_limits_are_configuration():
    for name in ("powered_up_maximum_s", "powered_up_requests_maximum"):
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
        except Exception:  # noqa: BLE001
            pass


def make_actor(**parameters):
    settings = {"log_directory": None, "telemetry": False, "timer": False, "worker": False}
    settings.update(parameters)
    init_args = power_manager_args(
        f"power_up_test_{next(_counter)}", "mock", declared=MockPowerManagerImpl.DECLARED_PROPERTIES, **settings
    )
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
    actor.request_powered_up(own_topic(actor), 300, "recording")
    assert actor.share["powered_up"]["held"] == "1"
    assert actor.share["powered_up"]["reasons"] == "recording"


def test_a_request_is_counted():
    actor = make_actor()
    actor.request_powered_up(own_topic(actor), 300, "recording")
    assert actor.share["metrics"]["powered_up_granted"] == 1


def test_a_request_holds_the_host_up():
    actor = make_actor(
        properties=("readings", "hold", "signal", "button", "dock"), script=[{"battery_volts": 12.0, "docked": False}]
    )
    actor.request_powered_up(own_topic(actor), 300, "recording")
    actor._evaluate(actor.reading(), now=1000.0)
    actor._evaluate(actor.reading(), now=1011.0)  # Past the dock dwell
    assert actor.share["policy_reason"] == "powered_up_held"


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


def payloads_for(message, topic):
    """What was published to one topic.

    The patch is on ProcessData, the class, so every live Actor in the
    process publishes into the same fake.  A test that read the first entry
    would pass alone and fail in a full run, where an Actor that an earlier
    test left behind publishes first"""

    return [payload for published_topic, payload in message.published if published_topic == topic]


def test_the_client_is_told_what_became_of_its_request(monkeypatch):
    """The answer is a published message, so a test must assert the publish
    itself.  Without this the publish failed silently on the hardware,
    because "aiko.message" is the module of that name and not the process's
    message layer"""

    actor = make_actor()
    message = fake_message(monkeypatch)
    topic = own_topic(actor)
    actor.request_powered_up(topic, 300, "recording")
    mine = payloads_for(message, topic)
    assert mine == ["(powered_up_granted 300)"]


def test_a_refusal_is_published_too(monkeypatch):
    actor = make_actor()
    message = fake_message(monkeypatch)
    topic = own_topic(actor)
    actor.request_powered_up(topic, 99999, "greedy")
    payload = payloads_for(message, topic)[0]
    assert "powered_up_refused" in payload
    assert "maximum_seconds" in payload


def test_a_refusal_carries_separate_arguments(monkeypatch):
    """Otherwise the wire encoding makes one length-prefixed string of
    "maximum_seconds 600", which a client has to take apart again"""

    actor = make_actor()
    message = fake_message(monkeypatch)
    topic = own_topic(actor)
    actor.request_powered_up(topic, 99999, "greedy")
    assert payloads_for(message, topic) == ["(powered_up_refused maximum_seconds 600)"]


def test_a_release_is_published_too(monkeypatch):
    actor = make_actor()
    message = fake_message(monkeypatch)
    topic = own_topic(actor)
    actor.request_powered_up(topic, 0, "done")
    assert "powered_up_released" in payloads_for(message, topic)[0]


def test_a_holder_hears_a_change_of_mode(monkeypatch):
    """So a client can stop writing without watching the shared state"""

    actor = make_actor(
        properties=("readings", "hold", "signal", "button", "dock"), script=[{"battery_volts": 9.0, "docked": False}]
    )
    actor.request_powered_up(own_topic(actor), 300, "recording")
    message = fake_message(monkeypatch)
    actor._evaluate(actor.reading(), now=1000.0)
    assert any("power_mode" in payload for payload in payloads_for(message, own_topic(actor)))


def test_an_expiry_is_never_silent(monkeypatch):
    """The register's own handler is what the Lease timer calls at the
    agreed time, so a test calls it rather than waiting"""

    actor = make_actor(
        properties=("readings", "hold", "signal", "button", "dock"), script=[{"battery_volts": 12.0, "docked": True}]
    )
    topic = own_topic(actor)
    actor.request_powered_up(topic, 10, "recording")
    message = fake_message(monkeypatch)
    actor._powered_up._lease_expired(topic)
    assert any("powered_up_expired" in payload for payload in payloads_for(message, topic))
    assert actor.share["powered_up"]["held"] == "0"


def test_the_policy_is_asked_again_the_moment_the_last_lease_ends():
    """Prompt action at the agreed timeout is most of what a Lease is for.
    A host that waited for its next sample would be holding a battery pack
    up for nobody"""

    actor = make_actor(
        properties=("readings", "hold", "signal", "button", "dock"), script=[{"battery_volts": 12.0, "docked": False}]
    )
    topic = own_topic(actor)
    actor.request_powered_up(topic, 10, "recording")
    actor._evaluate(actor.reading(), now=1000.0)
    actor._evaluate(actor.reading(), now=1011.0)  # Past the dock dwell
    assert actor.share["policy_reason"] == "powered_up_held"
    actor._powered_up._lease_expired(topic)  # The agreed time
    assert actor.share["policy_reason"] != "powered_up_held"


def test_an_expiry_that_leaves_another_lease_does_not_ask_again():
    """Only the last one to end is the event that lets a host stop"""

    actor = make_actor(
        properties=("readings", "hold", "signal", "button", "dock"), script=[{"battery_volts": 12.0, "docked": False}]
    )
    first, second = own_topic(actor, pid="900"), own_topic(actor, pid="901")
    actor.request_powered_up(first, 10, "recording")
    actor.request_powered_up(second, 300, "upload")
    actor._powered_up._lease_expired(first)
    assert actor.share["powered_up"]["held"] == "1"
    assert actor.share["powered_up"]["reasons"] == "upload"


def test_a_publish_that_fails_does_not_stop_a_reading(monkeypatch):
    from aiko_services.main.process import ProcessData

    class Broken:
        def publish(self, topic, payload):
            raise OSError("the broker went away")

    actor = make_actor(script=[{"battery_volts": 12.0, "docked": True}])
    monkeypatch.setattr(ProcessData, "message", Broken())
    actor.request_powered_up(own_topic(actor), 300, "recording")
    assert actor.share["powered_up"]["held"] == "1"  # Still taken
    assert actor.sample().battery_volts == 12.0  # Still reading


def test_a_wildcard_topic_is_refused_and_counted():
    """Without this check an unknown client makes this Actor publish
    wherever it likes"""

    actor = make_actor()
    actor.request_powered_up("aikotest/+/1/1/in", 300, "recording")
    assert actor.share["powered_up"]["held"] == "0"
    assert actor.share["metrics"]["denied"] == 1


def test_a_topic_in_another_namespace_is_refused():
    actor = make_actor()
    actor.request_powered_up("elsewhere/host/1/1/in", 300, "recording")
    assert actor.share["powered_up"]["held"] == "0"


def test_a_topic_with_a_suffix_a_service_does_not_own_is_refused():
    actor = make_actor()
    actor.request_powered_up(own_topic(actor, suffix="log"), 300, "recording")
    assert actor.share["powered_up"]["held"] == "0"


def test_the_bridge_key_cannot_be_asked_for_from_the_bus():
    """It is not a topic, and a client must not be able to take the claim
    that the power manager holds for another"""

    actor = make_actor()
    actor.request_powered_up(BRIDGE_TOPIC, 300, "store_forward")
    assert actor.share["powered_up"]["held"] == "0"
    assert actor.share["metrics"]["denied"] == 1


def test_a_request_that_is_too_long_is_refused_and_counted():
    actor = make_actor()
    actor.request_powered_up(own_topic(actor), 99999, "recording")
    assert actor.share["powered_up"]["held"] == "0"
    assert actor.share["metrics"]["powered_up_refused"] == 1


def test_zero_seconds_releases_from_the_bus():
    actor = make_actor()
    topic = own_topic(actor)
    actor.request_powered_up(topic, 300, "recording")
    actor.request_powered_up(topic, 0, "-")
    assert actor.share["powered_up"]["held"] == "0"


# The second condition: a constraint ---------------------------------------- #
#
# A Lease has two conditions.  The lease_time is the period for which it is
# valid, and a client extends it.  A constraint is a quantity of a finite
# resource, in the unit that measures it, and the host must still be able
# to meet it.  A Lease whose time is current but whose constraint cannot be
# met is not usable, so it is not a reason to keep the host up.
#
# The case to read first is a unit the host cannot measure.  It is refused,
# and never granted: a client must not plan on a promise that nothing can
# keep.

WATT_HOURS = {"watt_hours": 30.0}


def watt_hours(quantity):
    return LeaseConstraint.of("watt_hours", quantity)


def test_a_constraint_is_a_unit_and_a_quantity():
    constraint = watt_hours(12.5)
    assert (constraint.name, constraint.value) == ("watt_hours", 12.5)


def test_no_constraint_means_time_alone():
    assert LeaseConstraint.of(None, 0) is None
    assert LeaseConstraint.of("-", 0) is None


def test_an_undeclared_unit_is_refused_at_the_boundary():
    with pytest.raises(ValueError, match="unknown constraint"):
        LeaseConstraint.of("joules", 1)


def test_a_quantity_that_is_not_a_number_is_refused():
    with pytest.raises(ValueError, match="needs a number"):
        LeaseConstraint.of("watt_hours", "lots")


def test_a_quantity_of_nothing_is_refused():
    for quantity in (0, -1):
        with pytest.raises(ValueError, match="more than zero"):
            LeaseConstraint.of("watt_hours", quantity)


def test_seconds_are_not_a_constraint():
    """The lease_time is already the time condition"""

    assert "seconds" not in CONSTRAINTS


# Agreeing one ------------------------------------------------------------- #


def test_a_unit_the_host_cannot_measure_is_refused():
    """Granting what cannot be checked is worse than refusing it"""

    register = PoweredUpRegister()
    assert register.request(TOPIC, 60, "x", watt_hours(10), available={}) == ("refused", "no_measurement watt_hours")
    assert register.held() == 0


def test_more_than_there_is_is_refused_with_what_there_is():
    register = PoweredUpRegister()
    outcome, detail = register.request(TOPIC, 60, "x", watt_hours(50), available=WATT_HOURS)
    assert (outcome, detail) == ("refused", "no_resource watt_hours 30")


def test_a_constraint_that_fits_is_granted():
    register = PoweredUpRegister()
    assert register.request(TOPIC, 60, "x", watt_hours(20), available=WATT_HOURS)[0] == "granted"
    register.terminate()


def test_one_finite_resource_is_shared_between_the_leases():
    """Two clients that each ask for 20 Wh of 30 Wh are each satisfiable
    and together are not"""

    register = PoweredUpRegister()
    register.request(TOPIC, 60, "x", watt_hours(20), available=WATT_HOURS)
    outcome, detail = register.request(OTHER, 60, "y", watt_hours(20), available=WATT_HOURS)
    assert outcome == "refused"
    assert detail == "no_resource watt_hours 10"  # What is left
    register.terminate()


def test_a_second_claim_that_fits_what_is_left_is_granted():
    register = PoweredUpRegister()
    register.request(TOPIC, 60, "x", watt_hours(20), available=WATT_HOURS)
    assert register.request(OTHER, 60, "y", watt_hours(10), available=WATT_HOURS)[0] == "granted"
    register.terminate()


def test_extending_does_not_count_the_claim_against_itself():
    """Otherwise a holder of 20 Wh of 30 Wh could never extend"""

    register = PoweredUpRegister()
    register.request(TOPIC, 60, "x", watt_hours(20), available=WATT_HOURS)
    assert register.request(TOPIC, 60, "x", watt_hours(20), available=WATT_HOURS)[0] == "granted"
    register.terminate()


def test_extending_can_change_the_constraint():
    register = PoweredUpRegister()
    register.request(TOPIC, 60, "x", watt_hours(20), available=WATT_HOURS)
    register.request(TOPIC, 60, "x", watt_hours(5), available=WATT_HOURS)
    assert register.demand() == {"watt_hours": 5.0}
    register.terminate()


def test_the_demand_is_the_total_of_the_live_claims():
    register = PoweredUpRegister()
    register.request(TOPIC, 60, "x", watt_hours(20), available=WATT_HOURS)
    register.request(OTHER, 60, "y", watt_hours(10), available=WATT_HOURS)
    assert register.demand() == {"watt_hours": 30.0}
    register.terminate()


def test_an_unconstrained_claim_adds_nothing_to_the_demand():
    register = PoweredUpRegister()
    register.request(TOPIC, 60, "x")
    assert register.demand() == {}
    register.terminate()


def test_the_demand_is_published():
    register = PoweredUpRegister()
    register.request(TOPIC, 60, "x", watt_hours(12.5), available=WATT_HOURS)
    assert register.as_share()["powered_up.demand"] == "watt_hours:12.5"
    register.terminate()


def test_no_demand_says_so():
    assert PoweredUpRegister().as_share()["powered_up.demand"] == "-"


# Meeting one, and failing to ---------------------------------------------- #


def test_a_claim_with_no_constraint_is_always_met():
    """Its only condition is its time"""

    register = PoweredUpRegister()
    register.request(TOPIC, 60, "x")
    assert register.satisfied({}) == ((TOPIC,), ())
    assert register.held({}) == 1
    register.terminate()


def test_a_claim_is_met_while_the_resource_covers_it():
    register = PoweredUpRegister()
    register.request(TOPIC, 60, "x", watt_hours(20), available=WATT_HOURS)
    assert register.held(WATT_HOURS) == 1
    register.terminate()


def test_a_claim_stops_being_met_when_the_resource_falls():
    """Its time is current and it is not usable, so the policy must not
    count it as a reason to keep the host up"""

    register = PoweredUpRegister()
    register.request(TOPIC, 60, "x", watt_hours(20), available=WATT_HOURS)
    assert register.held({"watt_hours": 10.0}) == 0
    assert register.satisfied({"watt_hours": 10.0}) == ((), (TOPIC,))
    register.terminate()


def test_first_granted_is_first_served():
    """An arbitrary rule, in the way any fair rule is, and one a person can
    predict"""

    register = PoweredUpRegister()
    register.request(TOPIC, 60, "x", watt_hours(20), available=WATT_HOURS)
    register.request(OTHER, 60, "y", watt_hours(10), available=WATT_HOURS)
    met, unmet = register.satisfied({"watt_hours": 25.0})
    assert met == (TOPIC,) and unmet == (OTHER,)
    register.terminate()


def test_a_resource_that_cannot_be_measured_meets_nothing():
    register = PoweredUpRegister()
    register.request(TOPIC, 60, "x", watt_hours(20), available=WATT_HOURS)
    assert register.held({}) == 0
    register.terminate()


def test_only_the_time_is_counted_when_nothing_is_measured():
    """held() with no argument is the count of Leases whose time is
    current, which is what the register knows by itself"""

    register = PoweredUpRegister()
    register.request(TOPIC, 60, "x", watt_hours(20), available=WATT_HOURS)
    assert register.held() == 1
    register.terminate()


def test_a_lease_says_how_much_of_a_unit_it_asks_for():
    lease = PoweredUpLease(60.0, TOPIC, "x", watt_hours(20))
    assert lease.asks("watt_hours") == 20.0
    assert lease.asks("something_else") == 0.0
    lease.terminate()


def test_a_lease_with_no_constraint_asks_for_nothing():
    lease = PoweredUpLease(60.0, TOPIC, "x")
    assert lease.asks("watt_hours") == 0.0
    lease.terminate()


# Through the Actor -------------------------------------------------------- #


def test_the_actor_measures_nothing_yet():
    """Watt-hours arrive with the characterization of phase 6, so a
    constraint in them is refused today rather than granted"""

    assert make_actor().available() == {}


def test_a_constrained_request_is_refused_while_nothing_is_measured():
    actor = make_actor()
    actor.request_powered_up(own_topic(actor), 300, "upload", "watt_hours", 10)
    assert actor.share["powered_up"]["held"] == "0"
    assert actor.share["metrics"]["powered_up_refused"] == 1


def test_the_refusal_says_the_unit_it_cannot_measure(monkeypatch):
    actor = make_actor()
    message = fake_message(monkeypatch)
    topic = own_topic(actor)
    actor.request_powered_up(topic, 300, "upload", "watt_hours", 10)
    assert payloads_for(message, topic) == ["(powered_up_refused no_measurement watt_hours)"]


def test_an_undeclared_unit_is_refused_by_the_actor(monkeypatch):
    actor = make_actor()
    message = fake_message(monkeypatch)
    topic = own_topic(actor)
    actor.request_powered_up(topic, 300, "upload", "joules", 10)
    assert payloads_for(message, topic) == ["(powered_up_refused parameters)"]


def test_a_quantity_that_is_not_a_number_is_refused_by_the_actor():
    actor = make_actor()
    actor.request_powered_up(own_topic(actor), 300, "upload", "watt_hours", "x")
    assert actor.share["metrics"]["powered_up_refused"] == 1


def test_a_host_that_measures_the_unit_grants_it(monkeypatch):
    actor = make_actor()
    monkeypatch.setattr(type(actor), "available", lambda self: WATT_HOURS)
    actor.request_powered_up(own_topic(actor), 300, "upload", "watt_hours", 10)
    assert actor.share["powered_up"]["held"] == "1"
    assert actor.share["powered_up"]["demand"] == "watt_hours:10"


def test_a_claim_that_cannot_be_met_stops_holding_the_host_up(monkeypatch):
    """The whole point of the second condition"""

    actor = make_actor(
        properties=("readings", "hold", "signal", "button", "dock"), script=[{"battery_volts": 12.0, "docked": False}]
    )
    monkeypatch.setattr(type(actor), "available", lambda self: WATT_HOURS)
    actor.request_powered_up(own_topic(actor), 300, "upload", "watt_hours", 20)
    actor._evaluate(actor.reading(), now=1000.0)
    actor._evaluate(actor.reading(), now=1011.0)  # Past the dock dwell
    assert actor.share["policy_reason"] == "powered_up_held"
    monkeypatch.setattr(type(actor), "available", lambda self: {"watt_hours": 1.0})
    actor._evaluate(actor.reading(), now=1012.0)
    assert actor.share["policy_reason"] != "powered_up_held"


def test_a_holder_is_told_when_its_constraint_cannot_be_met(monkeypatch):
    actor = make_actor(
        properties=("readings", "hold", "signal", "button", "dock"), script=[{"battery_volts": 12.0, "docked": False}]
    )
    monkeypatch.setattr(type(actor), "available", lambda self: WATT_HOURS)
    actor.request_powered_up(own_topic(actor), 300, "upload", "watt_hours", 20)
    monkeypatch.setattr(type(actor), "available", lambda self: {"watt_hours": 1.0})
    message = fake_message(monkeypatch)
    actor._evaluate(actor.reading(), now=1000.0)
    assert any("powered_up_unmet" in payload for payload in payloads_for(message, own_topic(actor)))


def test_a_holder_is_told_once_and_not_on_every_sample(monkeypatch):
    actor = make_actor(
        properties=("readings", "hold", "signal", "button", "dock"), script=[{"battery_volts": 12.0, "docked": False}]
    )
    monkeypatch.setattr(type(actor), "available", lambda self: WATT_HOURS)
    actor.request_powered_up(own_topic(actor), 300, "upload", "watt_hours", 20)
    monkeypatch.setattr(type(actor), "available", lambda self: {"watt_hours": 1.0})
    message = fake_message(monkeypatch)
    for tick in range(3):
        actor._evaluate(actor.reading(), now=1000.0 + tick)
    told = [payload for payload in payloads_for(message, own_topic(actor)) if "powered_up_unmet" in payload]
    assert len(told) == 1


# --------------------------------------------------------------------------- #
