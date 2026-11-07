# Usage
# ~~~~~
# pytest [-s] unit/test_power_manager_working.py
#
# Unit tests for the report that an application is doing its work
# (report_working in actors/power_manager/power_manager.py).
#
# The division of knowledge is what these tests are about.  The reporter
# decides what working means, because only it knows.  This Actor decides
# what the report sounds like, and how often, because the buzzer is its
# property and a sound that plays too often means nothing.
#
# The dwell is walked rather than waited for: the clock is an attribute of
# the Actor, so a test moves it.  It is deliberately not a parameter of
# report_working, because a parameter would let a client on the bus pass
# its own time and defeat the dwell.

import itertools

import aiko_services as aiko
from aiko_services.actors.power_manager import (
    MockPowerManagerImpl,
    power_manager_args,
)
from aiko_services.actors.power_manager.power_manager import (
    WORKING_DWELL_S,
    WORKING_PATTERN,
    WORKING_REPORTERS_MAXIMUM,
)

_counter = itertools.count()
_made = []

import pytest


@pytest.fixture(autouse=True)
def close_actors():
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
        f"working_test_{next(_counter)}", "mock", declared=MockPowerManagerImpl.DECLARED_PROPERTIES, **settings
    )
    actor = aiko.compose_instance(MockPowerManagerImpl, init_args)
    actor._clock = lambda: actor._now
    actor._now = 1000.0
    _made.append(actor)
    return actor


def own_topic(actor, pid="900", sid="1"):
    """A topic in this Actor's own namespace, which the guard allows"""

    namespace, host = str(actor.topic_path).split("/")[:2]
    return f"{namespace}/{host}/{pid}/{sid}/in"


# The sound ---------------------------------------------------------------- #


def test_a_report_sounds_the_pattern():
    actor = make_actor()
    assert actor.report_working(own_topic(actor), "frames") is True
    assert actor.signals == [WORKING_PATTERN]


def test_the_pattern_is_the_cheerful_one():
    """The lead asked for a happy sound for an application that runs, and
    the table's name for it is "pipeline" """

    assert WORKING_PATTERN == "pipeline"


def test_a_report_is_counted():
    actor = make_actor()
    actor.report_working(own_topic(actor), "frames")
    assert actor.share["metrics"]["working_reports"] == 1


def test_the_detail_reaches_the_shared_state():
    """An operator with the Dashboard sees what was reported, and not only
    that something was"""

    actor = make_actor()
    actor.report_working(own_topic(actor), "frames")
    assert actor.share["working"]["last"] == "frames"
    assert actor.share["working"]["reporters"] == 1


def test_a_long_detail_is_cut_rather_than_published_whole():
    actor = make_actor()
    actor.report_working(own_topic(actor), "x" * 200)
    assert len(actor.share["working"]["last"]) <= 24


# The dwell ---------------------------------------------------------------- #


def test_a_second_report_inside_the_dwell_is_silent():
    """A Service in a loop must not be a siren.  The report is still
    counted, because it happened"""

    actor = make_actor()
    topic = own_topic(actor)
    assert actor.report_working(topic, "frames") is True
    actor._now += WORKING_DWELL_S - 1
    assert actor.report_working(topic, "frames") is False
    assert actor.signals == [WORKING_PATTERN]
    assert actor.share["metrics"]["working_reports"] == 2


def test_a_report_after_the_dwell_sounds_again():
    actor = make_actor()
    topic = own_topic(actor)
    actor.report_working(topic, "frames")
    actor._now += WORKING_DWELL_S + 1
    assert actor.report_working(topic, "frames") is True
    assert actor.signals == [WORKING_PATTERN, WORKING_PATTERN]


def test_the_dwell_is_not_restarted_by_a_report_inside_it():
    """Otherwise a Service that reports every second is never heard again:
    each report would push the next sound away"""

    actor = make_actor()
    topic = own_topic(actor)
    actor.report_working(topic, "frames")
    for _ in range(10):
        actor._now += WORKING_DWELL_S / 10
        actor.report_working(topic, "frames")
    assert actor.signals == [WORKING_PATTERN, WORKING_PATTERN]


def test_each_reporter_has_its_own_dwell():
    """Two applications that both start working are both heard"""

    actor = make_actor()
    assert actor.report_working(own_topic(actor, "900"), "frames") is True
    assert actor.report_working(own_topic(actor, "901"), "upload") is True
    assert actor.signals == [WORKING_PATTERN, WORKING_PATTERN]
    assert actor.share["working"]["reporters"] == 2


def test_the_dwell_comes_from_the_thresholds():
    actor = make_actor(thresholds={"working_dwell_s": 10.0})
    topic = own_topic(actor)
    actor.report_working(topic, "frames")
    actor._now += 11
    assert actor.report_working(topic, "frames") is True


# What is refused ---------------------------------------------------------- #


def test_a_topic_this_service_may_not_publish_to_is_refused():
    """The same guard as the up-time request.  A report names a topic, and
    an unchecked topic is a way to make this Actor publish where it likes"""

    actor = make_actor()
    assert actor.report_working("../elsewhere/in", "frames") is False
    assert actor.signals == []
    assert actor.share["metrics"]["denied"] == 1


def test_the_bridge_topic_is_refused():
    actor = make_actor()
    assert actor.report_working("-", "frames") is False
    assert actor.signals == []


def test_the_reporters_are_capped():
    """A cap, so that a stream of distinct topics cannot grow this Actor's
    memory without bound"""

    actor = make_actor(thresholds={"working_reporters_maximum": 3})
    for index in range(3):
        assert actor.report_working(own_topic(actor, f"90{index}"), "x") is True
    assert actor.report_working(own_topic(actor, "999"), "x") is False
    assert actor.share["metrics"]["denied"] == 1
    assert actor.share["working"]["reporters"] == 3


def test_a_reporter_already_known_is_not_refused_by_the_cap():
    """The cap is on how many are kept, and not on how often one reports"""

    actor = make_actor(thresholds={"working_reporters_maximum": 1, "working_dwell_s": 1.0})
    topic = own_topic(actor)
    assert actor.report_working(topic, "x") is True
    actor._now += 2
    assert actor.report_working(topic, "x") is True
    assert actor.share["metrics"]["denied"] == 0


def test_the_cap_default_matches_the_powered_up_cap():
    """Both bound a request surface that any client can reach, so they are
    the same number until a measurement says otherwise"""

    from aiko_services.actors.power_manager.powered_up import POWERED_UP_REQUESTS_MAXIMUM

    assert WORKING_REPORTERS_MAXIMUM == POWERED_UP_REQUESTS_MAXIMUM


# What this Actor does not know -------------------------------------------- #


def test_no_application_is_named_anywhere_in_the_report_path():
    """The rule the lead set when the StoreForward bridge was removed.  A
    reporter is a topic and a token, and this Actor knows nothing else"""

    import inspect

    from aiko_services.actors.power_manager import power_manager

    source = inspect.getsource(power_manager.PowerManagerCommon.report_working)
    for word in ("pipeline", "camera", "store_forward", "upload"):
        assert word not in source.lower(), word
