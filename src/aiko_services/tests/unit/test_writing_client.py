# Usage
# ~~~~~
# pytest [-s] unit/test_writing_client.py
#
# Unit tests for whether this host wants to be written to
# (main/writing_client.py).
#
# One property matters more than every other here: **it is True until
# something says otherwise.**  A host with no power manager, a power manager
# not yet found, and a value not yet received all answer True.  So adding
# this client changes nothing anywhere until a power manager is running and
# says to stop.  The alternative loses recordings on every host that has no
# battery pack, which is most of them.
#
# This is a subscription and not a request (P3), so there is no message to
# assert.  The tests drive the item changes that an ECConsumer would
# deliver, which is the seam that matters.

from aiko_services.main.powered_up_client import POWERED_UP_PROTOCOL
from aiko_services.main.writing_client import POWER_MANAGER_PROTOCOL, WRITING_ITEM, WritingClient

MANAGER = "aikotest/host/9/1"
OWN = "aikotest/host/5/1"


class FakeService:
    topic_path = OWN


def make_client(**parameters):
    return WritingClient(FakeService(), **parameters)


def change(client, value, command="update", item=WRITING_ITEM):
    """One item change, as an ECConsumer would deliver it"""

    client._item_change(0, command, item, value)


# The safe default --------------------------------------------------------- #


def test_writing_is_okay_before_anything_is_known():
    """A host with no power manager must write exactly as it did before
    this client existed"""

    assert make_client().writing_ok() is True


def test_writing_is_okay_while_no_power_manager_is_found():
    client = make_client()
    assert client.found() is False
    assert client.writing_ok() is True


def test_a_power_manager_that_goes_away_allows_writing_again():
    """A host whose power manager died must not stop recording for ever"""

    client = make_client()
    client._manager = MANAGER
    change(client, "false")
    assert client.writing_ok() is False
    client._service_change("remove", [MANAGER])
    assert client.writing_ok() is True


def test_closing_allows_writing_again():
    """A writer that closed this must not be left believing a stale no"""

    client = make_client()
    change(client, "false")
    assert client.writing_ok() is False
    client.close()
    assert client.writing_ok() is True


def test_a_value_that_cannot_be_read_allows_writing():
    """A writer must not stop because a value could not be parsed"""

    client = make_client()
    for value in ("", "maybe", None, "yes please"):
        change(client, "false")
        change(client, value)
        assert client.writing_ok() is True, value


def test_an_item_removed_allows_writing():
    client = make_client()
    change(client, "false")
    change(client, "false", command="remove")
    assert client.writing_ok() is True


# Reading the one item ----------------------------------------------------- #


def test_false_stops_the_writing():
    client = make_client()
    change(client, "false")
    assert client.writing_ok() is False


def test_the_spellings_of_no_are_all_read():
    for value in ("false", "False", "FALSE", "0", "no", "off", False):
        client = make_client()
        change(client, value)
        assert client.writing_ok() is False, value


def test_the_spellings_of_yes_are_all_read():
    for value in ("true", "True", "1", "yes", "on", True):
        client = make_client()
        change(client, "false")
        change(client, value)
        assert client.writing_ok() is True, value


def test_another_item_is_ignored():
    """The filter asks for one item, and a producer that sends more must
    not change the answer"""

    client = make_client()
    change(client, "false", item="mode")
    assert client.writing_ok() is True


# Telling the caller -------------------------------------------------------- #


def test_the_handler_is_told_on_a_change():
    told = []
    client = make_client(handler=told.append)
    change(client, "false")
    assert told == [False]
    change(client, "true")
    assert told == [False, True]


def test_the_handler_is_not_told_twice_for_one_value():
    """A producer replays its cache, so the same value arrives again"""

    told = []
    client = make_client(handler=told.append)
    change(client, "false")
    change(client, "false")
    change(client, "false")
    assert told == [False]
    assert client.changes == 1


def test_a_handler_that_raises_does_not_reach_the_power_manager():
    """A broken writer must not become an exception in the path of the
    Actor that told it"""

    def fail(writing_ok):
        raise ValueError("the writer is confused")

    client = make_client(handler=fail)
    change(client, "false")
    assert client.writing_ok() is False


def test_changes_are_counted_for_the_caller():
    client = make_client()
    change(client, "false")
    change(client, "true")
    assert client.changes == 2


# What it looks for -------------------------------------------------------- #


def test_the_protocol_is_the_power_manager_own():
    assert POWER_MANAGER_PROTOCOL == POWERED_UP_PROTOCOL
    assert POWER_MANAGER_PROTOCOL.endswith("/power_manager:0")


def test_the_filter_looks_for_that_protocol():
    assert make_client()._filter().protocol == POWER_MANAGER_PROTOCOL


def test_one_item_is_replicated_and_not_the_whole_state():
    """A writer needs one boolean, so it asks for one boolean"""

    assert WRITING_ITEM == "writing_ok"


def test_the_first_power_manager_found_is_the_one_used(monkeypatch):
    client = make_client()
    monkeypatch.setattr(client, "_attach", lambda: None)
    client._service_change("add", [MANAGER])
    assert client.found() is True
    client._service_change("add", ["aikotest/host/99/1"])
    assert client._manager == MANAGER


def test_another_service_going_away_changes_nothing(monkeypatch):
    client = make_client()
    monkeypatch.setattr(client, "_attach", lambda: None)
    client._service_change("add", [MANAGER])
    client._service_change("remove", ["aikotest/host/99/1"])
    assert client.found() is True


# Which thread does what --------------------------------------------------- #
#
# Found by reviewing Goal 3 on 2026-11-05.  The first version attached the
# subscription from the services cache thread.  A subscription takes a
# Lease, a Lease takes a timer, and the event list that the loop walks has
# no lock on it (event.py), so that was an unsynchronized mutation of a
# list the loop was reading.  PoweredUpClient had never done it, and this
# client now follows the same discipline.


def test_the_discovery_thread_only_records():
    """Nothing that takes a timer may happen there"""

    client = make_client()
    client._service_change("add", [MANAGER])
    assert client.found() is True
    assert client._consumer is None  # Nothing attached yet


def test_asking_is_what_attaches():
    """writing_ok() runs on the thread of whoever asks, which is where a
    Lease may be taken"""

    attached = []
    client = make_client()
    client._attach = lambda: attached.append(True)
    client._service_change("add", [MANAGER])
    assert attached == []
    client.writing_ok()
    assert attached == [True]


def test_asking_without_a_power_manager_attaches_nothing():
    attached = []
    client = make_client()
    client._attach = lambda: attached.append(True)
    client.writing_ok()
    assert attached == []


def test_the_answer_is_still_true_while_it_attaches():
    client = make_client()
    client._attach = lambda: None
    client._service_change("add", [MANAGER])
    assert client.writing_ok() is True


def test_every_client_shares_one_finder():
    """Three clients ask three different things of one Actor, and all
    three find it the same way.  One copy, not three"""

    from aiko_services.main.power_manager_client import PowerManagerClient
    from aiko_services.main.powered_up_client import PoweredUpClient
    from aiko_services.main.working_client import WorkingClient

    for client in (PoweredUpClient, WorkingClient, WritingClient):
        assert issubclass(client, PowerManagerClient), client.__name__
