# Usage
# ~~~~~
# pytest [-s] unit/test_powered_up_client.py
#
# Unit tests for asking a host to stay powered up
# (main/powered_up_client.py).
#
# No broker and no power manager.  The publish is injected, so a test
# asserts the exact request that goes out.
#
# The claim extends itself, through a Lease of the client's own with
# automatic_extend, so a caller does not count seconds.  That symmetry is
# the point: both ends of this agreement are a Lease, and both act at the
# time that was agreed.


from aiko_services.main import event
from aiko_services.main.powered_up_client import POWERED_UP_PROTOCOL, PoweredUpClient

MANAGER = "aikotest/host/9/1"
OWN = "aikotest/host/5/1"


class FakeService:
    topic_path = OWN


def make_client(**parameters):
    sent = []
    settings = {"seconds": 120, "reason": "upload", "publish": lambda topic, payload: sent.append((topic, payload))}
    settings.update(parameters)
    client = PoweredUpClient(FakeService(), **settings)
    client._manager = MANAGER  # Found, without discovery
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
    assert sent == [(f"{MANAGER}/in", f"(request_powered_up {OWN}/in 120 upload)")]
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
    client._extend(120, "x")  # What its own Lease calls
    assert len(sent) == 2
    assert sent[1] == sent[0]
    client.close()


def test_a_release_asks_for_zero():
    client, sent = make_client()
    client.claim()
    assert client.release() is True
    assert sent[-1][1] == f"(request_powered_up {OWN}/in 0 upload)"


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
    client.claim()  # Logs, and does not raise
    client.close()


# The client's own Lease ---------------------------------------------------- #


def test_a_claim_carries_a_lease_of_its_own():
    client, _ = make_client()
    before = timer_count()
    client.claim()
    assert timer_count() > before  # Expiry, and the extend
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
    assert client._filter().protocol == POWERED_UP_PROTOCOL
    client.close()


def test_the_protocol_is_the_one_the_actor_registers():
    assert POWERED_UP_PROTOCOL.endswith("/power_manager:0")


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

# Reading the answers ------------------------------------------------------ #
#
# Found in production on 2026-11-05.  An Actor dispatches an incoming
# message to a method of that name, so a Service with no such method logged
# an error for every answer: "powered_up_granted('300'): Function not found
# in: SegmentStoreForwardImpl", and the same for every change of mode.  A
# client that asks must also answer.


def test_the_answers_are_put_on_the_service():
    """Otherwise every grant and every change of mode is an error in the
    Service's log, and a real fault is lost in the noise.

    open() installs them; it is called here directly, because open() also
    starts the discovery that needs the transport"""

    client, _ = make_client()
    client._install_handlers()
    for name in ("powered_up_granted", "powered_up_refused", "powered_up_released", "power_mode"):
        assert callable(getattr(client.service, name)), name
    client._remove_handlers()


def test_removing_them_takes_only_what_was_added():
    client, _ = make_client()
    client._install_handlers()
    client._remove_handlers()
    for name in ("powered_up_granted", "power_mode"):
        assert not hasattr(client.service, name), name


def test_a_name_the_service_already_has_is_left_alone():
    """Its own is better than this one, and overwriting it would break the
    Service that defined it"""

    class Service:
        topic_path = OWN

        def power_mode(self, mode, reason="-"):
            self.told = (mode, reason)

    service = Service()
    client = PoweredUpClient(service, publish=lambda *a: None)
    client._install_handlers()
    service.power_mode("quiesce", "battery")
    assert service.told == ("quiesce", "battery")
    client._remove_handlers()
    assert hasattr(service, "power_mode")  # Not taken away


def test_a_grant_is_recorded_as_a_number():
    client, _ = make_client()
    client._install_handlers()
    client.service.powered_up_granted("300")
    assert client.granted == 300.0
    client._remove_handlers()


def test_a_grant_that_cannot_be_read_is_none_and_not_a_raise():
    """A client reports; it does not decide"""

    client, _ = make_client()
    client._install_handlers()
    client.service.powered_up_granted("soon")
    assert client.granted is None
    client._remove_handlers()


def test_a_refusal_is_recorded_with_its_reason():
    """A Service that reads this can do less work, rather than plan on
    time it does not have"""

    client, _ = make_client()
    client._install_handlers()
    client.service.powered_up_refused("maximum_seconds", "600")
    assert client.refused == "maximum_seconds"
    client._remove_handlers()


def test_a_refusal_with_no_detail_is_accepted():
    client, _ = make_client()
    client._install_handlers()
    client.service.powered_up_refused("no_resource")
    assert client.refused == "no_resource"
    client._remove_handlers()


def test_a_release_answer_is_accepted_whatever_it_carries():
    client, _ = make_client()
    client._install_handlers()
    client.service.powered_up_released()
    client.service.powered_up_released("extra")
    client._remove_handlers()


def test_the_mode_reaches_the_caller_handler():
    """The answer that matters.  An application that writes files stops
    when the power will end"""

    told = []
    client, _ = make_client(mode_handler=lambda mode, why: told.append((mode, why)))
    client._install_handlers()
    client.service.power_mode("quiesce", "battery")
    assert client.mode == "quiesce"
    assert told == [("quiesce", "battery")]
    client._remove_handlers()


def test_a_mode_handler_that_raises_does_not_reach_the_power_manager():
    """A broken application must not become an exception in the message
    path of the Actor that told it"""

    def fail(mode, why):
        raise ValueError("the application is confused")

    client, _ = make_client(mode_handler=fail)
    client._install_handlers()
    client.service.power_mode("quiesce", "battery")
    assert client.mode == "quiesce"
    client._remove_handlers()


def test_a_mode_with_no_reason_is_accepted():
    client, _ = make_client()
    client._install_handlers()
    client.service.power_mode("normal")
    assert client.mode == "normal"
    client._remove_handlers()


def test_nothing_is_recorded_before_an_answer_arrives():
    client, _ = make_client()
    assert (client.granted, client.refused, client.mode) == (None, None, None)


def test_open_is_what_installs_them(monkeypatch):
    """The wiring, with the discovery stubbed out.  Without this test a
    change that stopped open() from installing the handlers would pass,
    because every test above installs them itself"""

    class FakeDiscovery:
        def __init__(self, service):
            self.service = service

        def add_handler(self, handler, filter_):
            pass

    monkeypatch.setattr("aiko_services.main.transport.ActorDiscovery", FakeDiscovery)
    client, _ = make_client()
    client.open()
    assert callable(client.service.power_mode)
    client.close()
    assert not hasattr(client.service, "power_mode")
