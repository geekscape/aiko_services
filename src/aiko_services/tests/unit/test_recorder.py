#!/usr/bin/env python3
#
# Aiko Services tests: the Recorder
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# The Recorder had no tests at all.  These are the first, and they need no
# message broker: the handler takes a topic and a payload, and publishes
# through an ECProducer, so a double records what it published.
#
# What they hold, which is what the Recorder got wrong:
#
# - an evicted topic must lose its shared state, or a consumer keeps that
#   topic's last log record for ever
# - both sizes are a client's to change, and a bad value must leave the
#   one in force alone and say so
# - the counters are the Recorder's own, because a share item is writable
#   from the "control" topic and arithmetic on one then fails
#
# To Do
# ~~~~~
# - The whole ring buffer in the shared state, once that is settled

from collections import deque

import pytest

import aiko_services as aiko
from aiko_services.main.recorder import (
    LRU_CACHE_SIZE, RING_BUFFER_SIZE, RecorderImpl, SERVICE_TYPE,
)
from aiko_services.main.utilities import LRUCache, generate, parse

TOPIC = "aiko/host/1234/1/log"
OTHER = "aiko/host/5678/1/log"

class FakeECProducer:
    """Records what the Recorder published, instead of a broker"""

    def __init__(self, share):
        self.share = share
        self.updates, self.removes = [], []

    def add_handler(self, handler):
        self.handler = handler

    def update(self, item_name, item_value):
        self.updates.append((item_name, item_value))
        path = item_name.split(".")
        target = self.share
        for key in path[:-1]:
            target = target.setdefault(key, {})
        target[path[-1]] = item_value

    def remove(self, item_name):
        self.removes.append(item_name)
        path = item_name.split(".")
        target = self.share
        for key in path[:-1]:
            target = target.get(key, {})
        target.pop(path[-1], None)

@pytest.fixture
def recorder():
    """A composed Recorder whose publications are collected.  The Service
    registers, which needs no broker, and nothing subscribes"""

    def make(lru_cache_size=4, ring_buffer_size=3):
        actor = aiko.compose_instance(RecorderImpl, {
            **aiko.service_args(SERVICE_TYPE, protocol="r:0"),
            "topic_path_filter": f"{TOPIC}",
            "lru_cache_size": lru_cache_size,
            "ring_buffer_size": ring_buffer_size})
        actor.ec_producer = FakeECProducer(actor.share)
        return actor
    return make

def record(actor, topic, text):
    actor.recorder_handler(None, topic, text)

# A log record is stored as it arrived ----------------------------------- #
#
# It used to have its parentheses turned into braces, and a replace() that
# was meant to remove a non-breaking space but had an ordinary space on
# both sides, so it did nothing.  Neither is necessary, and the first made
# the Recorder report a log record that nobody wrote.  These tests hold
# the parser contract that makes the substitutions unnecessary.

AWKWARD = [
    "INFO call (a b) done", "(unbalanced", "unbalanced)", "(",
    "a (b (c) d) e", 'say "hello"', "line one\nline two", "a\tb", "",
    "12:30:45 INFO", "a\u00a0b", "\u00a0",
]

@pytest.mark.parametrize("record_text", AWKWARD,
    ids=[repr(text) for text in AWKWARD])
def test_the_parser_carries_an_awkward_log_record(record_text):
    """generate() gives a value with a space, a parenthesis, a quote, a
    newline or a non-breaking space a length prefix, and parse() returns
    it exactly.  So the Recorder needs no substitution of its own"""

    payload = generate("update", ["lru_cache.t", record_text])

    assert parse(payload)[1][1] == record_text

@pytest.mark.parametrize("record_text", AWKWARD,
    ids=[repr(text) for text in AWKWARD])
def test_an_awkward_record_is_stored_as_it_arrived(recorder, record_text):
    actor = recorder()
    record(actor, TOPIC, record_text)

    assert actor.get_records(TOPIC) == [record_text]
    assert actor.share["lru_cache"][TOPIC] == record_text

# The ring buffer --------------------------------------------------------- #

def test_the_newest_record_reaches_the_shared_state(recorder):
    actor = recorder()
    record(actor, TOPIC, "first")

    assert actor.share["lru_cache"][TOPIC] == "first"
    assert actor.get_records(TOPIC) == ["first"]

def test_the_ring_buffer_keeps_the_newest_records(recorder):
    actor = recorder(ring_buffer_size=3)
    for text in ("one", "two", "three", "four"):
        record(actor, TOPIC, text)

    assert actor.get_records(TOPIC) == ["two", "three", "four"]
    assert actor.share["lru_cache"][TOPIC] == "four"

def test_each_topic_has_its_own_ring_buffer(recorder):
    actor = recorder()
    record(actor, TOPIC, "mine")
    record(actor, OTHER, "theirs")

    assert actor.get_records(TOPIC) == ["mine"]
    assert actor.get_records(OTHER) == ["theirs"]

def test_a_topic_never_recorded_has_no_records(recorder):
    assert recorder().get_records("aiko/absent/1/1/log") == []

# The eviction leak, which is what this Epic set out to close ------------- #

def test_an_evicted_topic_loses_its_shared_state(recorder):
    """The leak: nothing called ECProducer.remove(), so a consumer kept
    the evicted topic's last log record for ever"""

    actor = recorder(lru_cache_size=2)
    record(actor, "a/1/1/1/log", "first")
    record(actor, "b/1/1/1/log", "second")
    record(actor, "c/1/1/1/log", "third")        # evicts a/1/1/1/log

    assert "lru_cache.a/1/1/1/log" in actor.ec_producer.removes
    assert "a/1/1/1/log" not in actor.share["lru_cache"]
    assert sorted(actor.share["lru_cache"]) == ["b/1/1/1/log", "c/1/1/1/log"]

def test_recording_a_topic_again_keeps_it(recorder):
    """The LRU order is what decides, so a topic that keeps logging is not
    the one evicted"""

    actor = recorder(lru_cache_size=2)
    record(actor, "a/1/1/1/log", "first")
    record(actor, "b/1/1/1/log", "second")
    record(actor, "a/1/1/1/log", "again")        # a is now the most recent
    record(actor, "c/1/1/1/log", "third")        # so b is evicted

    assert "b/1/1/1/log" not in actor.share["lru_cache"]
    assert "a/1/1/1/log" in actor.share["lru_cache"]

def test_an_eviction_is_counted(recorder):
    actor = recorder(lru_cache_size=1)
    record(actor, "a/1/1/1/log", "first")
    record(actor, "b/1/1/1/log", "second")

    assert actor.share["metrics"]["evicted"] == 1
    assert actor.share["metrics"]["topics"] == 1

# The statistics the module's own To Do asked for ------------------------ #

def test_the_records_and_topics_are_counted(recorder):
    actor = recorder()
    record(actor, TOPIC, "one")
    record(actor, TOPIC, "two")
    record(actor, OTHER, "three")

    assert actor.share["metrics"]["records"] == 3
    assert actor.share["metrics"]["topics"] == 2

def test_a_counter_a_client_falsified_is_corrected(recorder):
    """A share item is writable from the "control" topic.  The count is
    held by the Recorder, so "string + 1" is never evaluated"""

    actor = recorder()
    record(actor, TOPIC, "one")
    actor.ec_producer.update("metrics.records", "0")     # falsified

    record(actor, TOPIC, "two")

    assert actor.share["metrics"]["records"] == 2

# The sizes, which a client may change ----------------------------------- #

def test_the_defaults_are_what_the_source_intends():
    assert LRU_CACHE_SIZE == 128 and RING_BUFFER_SIZE == 128

def test_the_sizes_are_published(recorder):
    actor = recorder(lru_cache_size=7, ring_buffer_size=9)

    assert actor.share["lru_cache_size"] == 7
    assert actor.share["ring_buffer_size"] == 9

def test_a_larger_ring_buffer_takes_effect(recorder):
    actor = recorder(ring_buffer_size=2)
    for text in ("one", "two", "three"):
        record(actor, TOPIC, text)
    assert actor.get_records(TOPIC) == ["two", "three"]

    actor._ec_producer_change_handler("update", "ring_buffer_size", "4")
    for text in ("four", "five"):
        record(actor, TOPIC, text)

    assert actor.get_records(TOPIC) == ["two", "three", "four", "five"]
    assert actor.share["ring_buffer_size"] == 4

def test_a_smaller_ring_buffer_keeps_the_newest(recorder):
    actor = recorder(ring_buffer_size=4)
    for text in ("one", "two", "three", "four"):
        record(actor, TOPIC, text)

    actor._ec_producer_change_handler("update", "ring_buffer_size", "2")

    assert actor.get_records(TOPIC) == ["three", "four"]

def test_a_smaller_lru_cache_evicts_at_once(recorder):
    actor = recorder(lru_cache_size=3)
    for name in "abc":
        record(actor, f"{name}/1/1/1/log", name)

    actor._ec_producer_change_handler("update", "lru_cache_size", "1")

    assert list(actor.share["lru_cache"]) == ["c/1/1/1/log"]
    assert actor.share["metrics"]["evicted"] == 2
    assert actor.share["metrics"]["topics"] == 1

@pytest.mark.parametrize("item_name", ["lru_cache_size", "ring_buffer_size"])
@pytest.mark.parametrize("value", ["0", "-1", "9999", "abc", ""])
def test_a_bad_size_leaves_the_one_in_force(recorder, item_name, value):
    actor = recorder(lru_cache_size=4, ring_buffer_size=3)
    in_force = actor.share[item_name]

    actor._ec_producer_change_handler("update", item_name, value)

    assert actor.share[item_name] == in_force
    assert (item_name, in_force) in actor.ec_producer.updates

def test_the_log_level_is_still_a_shared_variable(recorder, monkeypatch):
    """The handler that was there before this Epic, still working"""

    import aiko_services.main.recorder as module

    levels = []
    monkeypatch.setattr(module._LOGGER, "setLevel", levels.append)
    actor = recorder()

    # ec_producer.add_handler() replays the whole share, so the level in
    # the share is applied once at construction
    assert levels == ["INFO"]

    actor._ec_producer_change_handler("update", "log_level", "debug")
    assert levels == ["INFO", "DEBUG"]

# The LRU cache utility it depends on ------------------------------------ #

def test_the_cache_reports_what_it_evicted():
    cache = LRUCache(2)

    assert cache.put("a", 1) is None
    assert cache.put("b", 2) is None
    assert cache.put("c", 3) == ("a", 1)

def test_refreshing_an_item_evicts_nothing():
    cache = LRUCache(2)
    cache.put("a", 1)
    cache.put("b", 2)

    assert cache.put("a", 9) is None
    assert cache.get("a") == 9

def test_a_resize_reports_each_eviction():
    cache = LRUCache(3)
    for key, value in (("a", 1), ("b", 2), ("c", 3)):
        cache.put(key, value)

    assert cache.resize(1) == [("a", 1), ("b", 2)]
    assert len(cache) == 1

def test_a_resize_that_evicts_nothing():
    cache = LRUCache(2)
    cache.put("a", 1)

    assert cache.resize(8) == []
    assert cache.size == 8

def test_a_cache_size_below_one_is_refused():
    with pytest.raises(ValueError):
        LRUCache(2).resize(0)

# --------------------------------------------------------------------------- #
