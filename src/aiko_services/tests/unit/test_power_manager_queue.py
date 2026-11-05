# Usage
# ~~~~~
# pytest [-s] unit/test_power_manager_queue.py
#
# Unit tests for what still waits to be transferred
# (actors/power_manager/queue.py).
#
# No broker and no peer.  The one distinction that every test here is about
# is "unknown" against "empty": a source that could not ask must not report
# zero, because the policy would then stop a host with work left to do.
#
# StoreForwardQueueSource is tested through its handler rather than through
# discovery.  Discovery starts a thread that outlives a test, and what is
# worth asserting is the mapping from the peer's published state to a
# QueueState, not the framework's own cache.

import pytest

from aiko_services.actors.power_manager import (
    FakeQueueSource, NoQueueSource, QueueState, STORE_FORWARD_PROTOCOL,
    StoreForwardQueueSource, choose_queue_source,
)

# Unknown is not empty ----------------------------------------------------- #

def test_a_queue_that_was_never_heard_from_is_unknown():
    state = NoQueueSource().state()
    assert state.known is False
    assert state.busy is False

def test_unknown_and_empty_are_different_states():
    """The policy reads "known" before it reads "depth" for this reason"""

    unknown = QueueState(known=False, depth=0)
    empty = QueueState(known=True, depth=0)
    assert unknown.busy is empty.busy is False
    assert unknown.known is False and empty.known is True

def test_a_known_queue_with_work_is_busy():
    assert QueueState(known=True, depth=1).busy is True

def test_a_queue_is_not_busy_while_it_is_unknown():
    """Even with a depth, because the depth came from nowhere"""

    assert QueueState(known=False, depth=9).busy is False

# What is published -------------------------------------------------------- #

def test_the_state_is_published_as_tokens():
    items = QueueState(known=True, depth=7, oldest_s=42.4, link="up",
        peer="ns/host/1/1").as_share()
    assert items["queue.known"] == "yes"
    assert items["queue.depth"] == "7"
    assert items["queue.oldest_s"] == "42"
    assert items["queue.link"] == "up"

def test_no_token_holds_a_space():
    """They are shared variables, and ServiceFilter splits on a space"""

    for value in QueueState(known=True, peer="a/b/1/1").as_share().values():
        assert " " not in value

def test_an_unknown_queue_says_so_in_its_tokens():
    assert QueueState().as_share()["queue.known"] == "no"

# The fake ----------------------------------------------------------------- #

def test_the_fake_starts_unknown():
    assert choose_queue_source("fake").state().known is False

def test_the_fake_is_set_by_hand():
    source = FakeQueueSource()
    source.set_state(known=True, depth=3, link="up")
    assert source.state().depth == 3
    assert source.state().busy is True

def test_the_fake_keeps_what_was_not_changed():
    source = FakeQueueSource()
    source.set_state(known=True, depth=3)
    source.set_state(depth=0)
    assert source.state().known is True and source.state().busy is False

# The real source's mapping ------------------------------------------------ #

def test_a_peer_that_has_published_nothing_is_still_unknown():
    """Present is not the same as heard from"""

    source = StoreForwardQueueSource()
    assert source.state().known is False

def test_the_peer_s_published_queue_becomes_a_queue_state():
    source = StoreForwardQueueSource()
    source._cache = {
        "queue": {"depth": "4", "oldest_s": "12", "bytes": "1024"},
        "link": "up@2026-11-05T00:00:00Z"}
    state = source.state()
    assert state.known is True
    assert state.depth == 4 and state.oldest_s == 12.0
    assert state.busy is True
    assert state.link.startswith("up")

def test_a_published_queue_with_no_depth_is_unknown():
    source = StoreForwardQueueSource()
    source._cache = {"queue": {"oldest_s": "0"}}
    assert source.state().known is False

def test_a_published_depth_that_is_nonsense_reads_as_zero():
    """A token that cannot be a number must not stop a host"""

    source = StoreForwardQueueSource()
    source._cache = {"queue": {"depth": "many"}}
    assert source.state().known is True
    assert source.state().depth == 0

def test_a_peer_that_goes_away_takes_its_queue_with_it():
    source = StoreForwardQueueSource()
    source._peer = "ns/host/1/1"
    source._cache = {"queue": {"depth": "4"}}
    source._service_change("remove", ("ns/host/1/1",))
    assert source.state().known is False

def test_another_peer_going_away_leaves_the_queue_alone():
    source = StoreForwardQueueSource()
    source._peer = "ns/host/1/1"
    source._cache = {"queue": {"depth": "4"}}
    source._service_change("remove", ("ns/other/2/1",))
    assert source.state().known is True

def test_the_filter_names_the_store_forward_protocol():
    assert StoreForwardQueueSource()._filter().protocol  \
        == STORE_FORWARD_PROTOCOL

def test_the_filter_can_name_one_host():
    assert StoreForwardQueueSource(name="w3029f1")._filter().name  \
        == "w3029f1"

def test_closing_forgets_everything():
    source = StoreForwardQueueSource()
    source._cache = {"queue": {"depth": "4"}}
    source.close()
    assert source.state().known is False

# Composition -------------------------------------------------------------- #

def test_none_is_the_default_choice():
    """A host that forwards nothing must not wait for a peer that will
    never answer"""

    assert choose_queue_source().device == "none"

def test_each_source_is_chosen_by_name():
    assert choose_queue_source("store_forward").device == "store_forward"
    assert choose_queue_source("fake").device == "fake"
    assert choose_queue_source("none").device == "none"

def test_an_unknown_source_raises_rather_than_guessing():
    with pytest.raises(ValueError, match="unknown queue source"):
        choose_queue_source("outbox")

# --------------------------------------------------------------------------- #
