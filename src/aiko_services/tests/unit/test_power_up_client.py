# Usage
# ~~~~~
# pytest [-s] unit/test_power_up_client.py
#
# Unit tests for asking a host to stay powered up
# (main/power_up_client.py).
#
# No broker and no power manager.  The publish is injected, so a test
# asserts the exact request that goes out.
#
# The claim extends itself, through a Lease of the client's own with
# automatic_extend, so a caller does not count seconds.  That symmetry is
# the point: both ends of this agreement are a Lease, and both act at the
# time that was agreed.

import pytest

from aiko_services.main import event
from aiko_services.main.power_up_client import (
    POWER_UP_PROTOCOL, PowerUpClient
)

MANAGER = "aikotest/host/9/1"
OWN = "aikotest/host/5/1"

class FakeService:
    topic_path = OWN

def make_client(**parameters):
    sent = []
    settings = {"seconds": 120, "reason": "upload",
        "publish": lambda topic, payload: sent.append((topic, payload))}
    settings.update(parameters)
    client = PowerUpClient(FakeService(), **settings)
    client._manager = MANAGER                   # Found, without discovery
    return client, sent

def timer_count():
    count, current = 0, event.event_list.head
    while current:
        count += 1
        current = current.next
    return count

# Asking -------------------------------------------------------------------- #

def test_a_claim_asks_the_power_manager_on_its_in_topic():
    client, sent = make_client()
    assert client.claim() is True
    assert sent == [
        (f"{MANAGER}/in", f"(request_power_up {OWN}/in 120 upload)")]
    client.close()

def test_the_claim_names_the_client_own_topic():
    """It is the identity of the claim, and where the answers go"""

    client, sent = make_client()
    client.claim()
    assert f"{OWN}/in" in sent[0][1]
    client.close()

def test_asking_twice_does_not_ask_twice():
    """The claim extends itself, so a caller may call claim() on every
    scan without a message for each one"""

    client, sent = make_client()
    client.claim()
    assert client.claim() is False
    assert len(sent) == 1
    client.close()

def test_the_claim_extends_itself_before_it_lapses():
    client, sent = make_client()
    client.claim()
    client._extend(120, "x")                    # What its own Lease calls
    assert len(sent) == 2
    assert sent[1] == sent[0]
    client.close()

def test_a_release_asks_for_zero():
    client, sent = make_client()
    client.claim()
    assert client.release() is True
    assert sent[-1][1] == f"(request_power_up {OWN}/in 0 upload)"

def test_releasing_what_was_never_claimed_is_not_an_error():
    client, sent = make_client()
    assert client.release() is False
    assert sent == []

def test_the_seconds_and_the_reason_can_be_given_when_claiming():
    client, sent = make_client()
    client.claim(seconds=30, reason="recording")
    assert "30 recording" in sent[0][1]
    client.close()

def test_nothing_is_asked_before_a_power_manager_is_found():
    """A host with no power manager is unaffected: the claim is simply
    never answered"""

    client, sent = make_client()
    client._manager = None
    client.claim()
    assert sent == []
    assert client.found() is False
    client.close()

def test_a_publish_that_fails_does_not_raise():
    def boom(topic, payload):
        raise OSError("the broker went away")

    client, _ = make_client(publish=boom)
    client.claim()                              # Logs, and does not raise
    client.close()

# The client's own Lease ---------------------------------------------------- #

def test_a_claim_carries_a_lease_of_its_own():
    client, _ = make_client()
    before = timer_count()
    client.claim()
    assert timer_count() > before               # Expiry, and the extend
    assert client.holding() is True
    client.close()
    assert timer_count() == before

def test_releasing_leaves_no_timer_behind():
    client, _ = make_client()
    before = timer_count()
    client.claim()
    client.release()
    assert timer_count() == before
    assert client.holding() is False

def test_closing_releases_and_forgets_the_manager():
    client, sent = make_client()
    client.claim()
    client.close()
    assert client.holding() is False
    assert client.found() is False
    assert sent[-1][1].endswith("0 upload)")

def test_the_claims_are_counted_for_the_caller():
    client, _ = make_client()
    client.claim()
    client.release()
    client.claim()
    assert (client.claims, client.releases) == (2, 1)
    client.close()

# Discovery ----------------------------------------------------------------- #

def test_the_filter_names_the_power_manager_protocol():
    client, _ = make_client()
    assert client._filter().protocol == POWER_UP_PROTOCOL
    client.close()

def test_the_protocol_is_the_one_the_actor_registers():
    assert POWER_UP_PROTOCOL.endswith("/power_manager:0")

def test_a_power_manager_that_appears_is_remembered():
    client, _ = make_client()
    client._manager = None
    client._service_change("add", (MANAGER,))
    assert client.found() is True
    client.close()

def test_a_power_manager_that_goes_away_is_forgotten():
    client, _ = make_client()
    client._service_change("remove", (MANAGER,))
    assert client.found() is False
    client.close()

def test_another_service_going_away_is_ignored():
    client, _ = make_client()
    client._service_change("remove", ("aikotest/other/1/1",))
    assert client.found() is True
    client.close()

def test_a_second_power_manager_does_not_replace_the_first():
    client, _ = make_client()
    client._service_change("add", ("aikotest/other/2/1",))
    assert client._manager == MANAGER
    client.close()

# --------------------------------------------------------------------------- #
