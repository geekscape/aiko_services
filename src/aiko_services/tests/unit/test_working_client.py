# Usage
# ~~~~~
# pytest [-s] unit/test_working_client.py
#
# Unit tests for reporting that a Service is doing its work
# (main/working_client.py).
#
# No broker and no power manager.  The publish is injected, so a test
# asserts the exact message that goes out.
#
# A report holds nothing: it is one message, and it leaves no Lease and no
# timer.  So these tests are about what is sent, and about the client being
# quiet when there is no power manager to tell.

from aiko_services.main import event
from aiko_services.main.powered_up_client import POWERED_UP_PROTOCOL
from aiko_services.main.working_client import (
    POWER_MANAGER_PROTOCOL, WorkingClient
)

MANAGER = "aikotest/host/9/1"
OWN = "aikotest/host/5/1"

class FakeService:
    topic_path = OWN

def make_client(found=True, **parameters):
    sent = []
    settings = {"detail": "frames",
        "publish": lambda topic, payload: sent.append((topic, payload))}
    settings.update(parameters)
    client = WorkingClient(FakeService(), **settings)
    if found:
        client._manager = MANAGER               # Found, without discovery
    return client, sent

def timer_count():
    count, current = 0, event.event_list.head
    while current:
        count += 1
        current = current.next
    return count

# Reporting ---------------------------------------------------------------- #

def test_a_report_goes_to_the_power_manager_on_its_in_topic():
    client, sent = make_client()
    assert client.report() is True
    assert sent == [(f"{MANAGER}/in", f"(report_working {OWN}/in frames)")]

def test_the_report_names_the_reporter_own_topic():
    """It is the identity of the reporter, which the dwell is kept against"""

    client, sent = make_client()
    client.report()
    assert f"{OWN}/in" in sent[0][1]

def test_the_detail_can_be_given_at_the_report():
    client, sent = make_client()
    client.report("capturing")
    assert sent[0][1] == f"(report_working {OWN}/in capturing)"
    assert client.detail == "capturing"

def test_a_report_with_no_detail_is_still_well_formed():
    client, sent = make_client(detail=None)
    client.report()
    assert sent[0][1] == f"(report_working {OWN}/in -)"

def test_reports_are_counted_for_the_caller():
    client, _ = make_client()
    client.report()
    client.report()
    assert client.reports == 2

def test_repeated_reports_are_all_sent():
    """The rate is the power manager's business, not the client's.  A
    client that hid reports would make the dwell untestable from outside,
    and two places would decide one rule"""

    client, sent = make_client()
    for _ in range(5):
        client.report()
    assert len(sent) == 5

# When there is no power manager -------------------------------------------- #

def test_a_report_with_no_power_manager_sends_nothing_and_says_so():
    """A host with no power manager is the usual case, and a Service that
    reports must work there unchanged"""

    client, sent = make_client(found=False)
    assert client.found() is False
    assert client.report() is False
    assert sent == []

def test_a_publish_that_fails_is_reported_and_never_raised():
    """A Service is doing its work.  A buzzer that cannot be reached must
    not become an exception in that Service's path"""

    def fail(topic, payload):
        raise OSError("the broker went away")

    client, _ = make_client(publish=fail)
    assert client.report() is False
    assert client.reports == 0

# What it holds ------------------------------------------------------------- #

def test_a_report_leaves_no_timer_behind():
    """Unlike the up-time claim, a report holds no Lease.  So a client that
    is never closed leaks nothing into the event loop"""

    before = timer_count()
    client, _ = make_client()
    client.report()
    assert timer_count() == before

def test_close_forgets_the_power_manager():
    client, _ = make_client()
    client.close()
    assert client.found() is False
    assert client.report() is False

def test_the_protocol_is_the_power_manager_own():
    """One Actor answers both this and the up-time request, so there is one
    protocol string and not two that can drift apart"""

    assert POWER_MANAGER_PROTOCOL == POWERED_UP_PROTOCOL
    assert POWER_MANAGER_PROTOCOL.endswith("/power_manager:0")

def test_the_filter_looks_for_that_protocol():
    client, _ = make_client()
    assert client._filter().protocol == POWER_MANAGER_PROTOCOL

# Discovery ----------------------------------------------------------------- #

def test_the_first_power_manager_found_is_the_one_used():
    client, _ = make_client(found=False)
    client._service_change("add", [MANAGER])
    assert client.found() is True
    client._service_change("add", ["aikotest/host/99/1"])
    assert client._manager == MANAGER

def test_a_power_manager_that_goes_away_is_forgotten():
    client, _ = make_client()
    client._service_change("remove", [MANAGER])
    assert client.found() is False

def test_another_service_going_away_changes_nothing():
    client, _ = make_client()
    client._service_change("remove", ["aikotest/host/99/1"])
    assert client.found() is True
