#!/usr/bin/env python3
#
# Aiko Services tests: the Recorder's Dashboard page
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# asciimatics has no screen double, so RecorderPage holds every decision
# and is pure, and the Frame is drawn by the shared pseudo-terminal
# fixture.  No broker, no Recorder, no screen for the pure part.
#
# The one thing worth saying twice: a "lru_cache.<topic>" item is either
# the newest record, as a string, or the whole ring buffer, as a list.
# The Recorder has not settled which, so the page reads both and these
# tests hold both.
#
# To Do
# ~~~~~
# - Key events through the pseudo-terminal, for the two dialogues

import pytest

asciimatics = pytest.importorskip("asciimatics")

from aiko_services.actors.dashboard.recorder_plugin import (  # noqa: E402
    KEYS, RECORD_WIDTH, RecorderPage, plugins,
)
from aiko_services.tests.unit.dashboard_screen import (       # noqa: E402
    draw_frame, pty_available,
)

RECORD = "2026-10-23_19:00:01.123 INFO SERVICE service: a log record"
TOPIC = "aiko/host/1234/1/log"
OTHER = "aiko/host/5678/1/log"

# The newest record only, which is what the Recorder publishes today
NEWEST = {
    "lifecycle": "ready", "log_level": "INFO",
    "filters": ["aiko/+/+/+/log", "aiko/+/+/+/out"],
    "lru_cache_size": 128, "ring_buffer_size": 128,
    "lru_cache": {TOPIC: RECORD, OTHER: "another"},
    "metrics": {"records": 42, "topics": 2, "evicted": 7},
}

# The whole ring buffer, which is what the deferred experiment publishes
RING = {
    **NEWEST,
    "lru_cache": {TOPIC: ["first", "second", RECORD], OTHER: ["only"]},
    "records_period": 2.0,
}

@pytest.fixture
def page():
    return RecorderPage()

needs_pty = pytest.mark.skipif(
    not pty_available(), reason="needs a POSIX pseudo-terminal")

# The plug-in registration ------------------------------------------------ #

def test_the_plugin_key_is_the_protocol_type():
    assert list(plugins) == ["recorder"]

def test_the_default_plugin_module_registers_it():
    from aiko_services.actors.dashboard.plugins import plugins as default

    assert sorted(default) == ["process_manager", "recorder", "registrar"]

def test_the_dashboard_derives_that_key_from_the_protocol():
    from aiko_services.actors.dashboard.dashboard import FrameCommon
    from aiko_services.main.recorder import PROTOCOL

    assert FrameCommon._short_name(None, PROTOCOL).split(":")[0] == "recorder"

# The keys ---------------------------------------------------------------- #

def test_each_key_asks_for_one_thing(page):
    assert page.action(ord("r")) == ("record_start",)
    assert page.action(ord("R")) == ("record_stop",)
    assert page.action(ord("L")) == ("log_level",)
    assert page.action(ord("H")) == ("help",)

def test_the_dashboards_own_keys_are_left_alone(page):
    for reserved in "DxqXS":
        assert page.action(ord(reserved)) is None

def test_a_key_that_is_not_a_character_is_ignored(page):
    for key_code in (-1, -204, 0x110000):
        assert page.action(key_code) is None

def test_the_help_names_every_key_the_page_takes(page):
    text = page.help_text()

    for key in KEYS:
        assert key in text
    assert "record_start" in text and "record_stop" in text

# A share item that is a string, or a list ------------------------------- #

def test_the_newest_record_as_a_string(page):
    assert page.records(NEWEST, TOPIC) == [RECORD]

def test_the_whole_ring_as_a_list(page):
    assert page.records(RING, TOPIC) == ["first", "second", RECORD]

def test_a_topic_that_is_not_recorded(page):
    assert page.records(NEWEST, "aiko/absent/1/1/log") == []

def test_no_shared_state_at_all(page):
    assert page.records({}, TOPIC) == []
    assert page.topic_rows({}) == []
    assert page.state_rows({}) == []

def test_a_cache_whose_item_is_not_a_dictionary(page):
    assert page.records({"lru_cache": "nonsense"}, TOPIC) == []
    assert page.topic_rows({"lru_cache": "nonsense"}) == []

# The tables -------------------------------------------------------------- #

def test_the_topic_table_counts_what_each_topic_holds(page):
    rows = page.topic_rows(NEWEST)

    assert [(topic, held) for topic, held, _ in rows] ==  \
        [(TOPIC, "1"), (OTHER, "1")]               # by topic

def test_the_topic_table_counts_a_whole_ring(page):
    rows = {topic: held for topic, held, _ in page.topic_rows(RING)}

    assert rows == {TOPIC: "3", OTHER: "1"}

def test_the_topic_table_shows_the_newest_record(page):
    newest = {topic: record for topic, _, record in page.topic_rows(RING)}

    assert newest[TOPIC] == RECORD             # the last of the ring

def test_a_long_record_is_cut_to_the_width(page):
    cache = {"lru_cache": {TOPIC: "x" * 400}}

    _, _, record = page.topic_rows(cache)[0]
    assert len(record) == RECORD_WIDTH

def test_the_filters_are_read_as_a_list(page):
    assert page.filters(NEWEST) == ["aiko/+/+/+/log", "aiko/+/+/+/out"]

def test_one_filter_that_arrived_as_a_string(page):
    assert page.filters({"filters": "aiko/+/+/+/log"}) == ["aiko/+/+/+/log"]

def test_no_filters_yet(page):
    assert page.filters({}) == []
    assert page.filters({"filters": []}) == []

def test_the_state_table_names_what_the_recorder_is(page):
    names = [name for name, _ in page.state_rows(NEWEST)]

    assert names == [
        "filters", "lru_cache_size", "ring_buffer_size", "lifecycle",
        "log_level", "metrics.evicted", "metrics.records", "metrics.topics"]

def test_the_state_table_shows_a_list_as_words(page):
    values = dict(page.state_rows(NEWEST))

    assert values["filters"] == "aiko/+/+/+/log aiko/+/+/+/out"

def test_the_state_table_shows_the_period_when_there_is_one(page):
    """The deferred experiment publishes "records_period"; a Recorder
    without it must not show an empty row"""

    assert "records_period" in dict(page.state_rows(RING))
    assert "records_period" not in dict(page.state_rows(NEWEST))

def test_the_title_says_how_much_it_holds_and_let_go(page):
    assert page.title(NEWEST) == "topics: 2   records: 42   evicted: 7"

def test_the_title_of_a_recorder_that_has_recorded_nothing(page):
    assert page.title({}) == "topics: 0   records: 0   evicted: 0"

# The frame, on a real terminal ------------------------------------------ #

@needs_pty
@pytest.mark.parametrize("cache,label", [(NEWEST, "newest"), (RING, "ring")],
    ids=["a record for each topic", "a whole ring for each topic"])
def test_the_page_is_built_and_drawn(cache, label, tmp_path):
    drawn = draw_frame("aiko_services.actors.dashboard.recorder_plugin",
        "RecorderFrame", cache, tmp_path)

    assert drawn["ok"], drawn.get("traceback") or drawn.get("error")
    text = "\n".join(drawn["lines"])
    assert "topics: 2" in text and "evicted: 7" in text
    assert TOPIC in text
    assert "record_start" in text              # the legend

@needs_pty
@pytest.mark.parametrize("size", [(80, 24), (132, 48)],
    ids=["80x24", "132x48"])
def test_the_page_fits_a_small_terminal(size, tmp_path):
    drawn = draw_frame("aiko_services.actors.dashboard.recorder_plugin",
        "RecorderFrame", NEWEST, tmp_path, size=size)

    assert drawn["ok"], drawn.get("traceback") or drawn.get("error")
    assert drawn["size"] == list(size)

@needs_pty
def test_the_page_draws_with_an_empty_shared_state(tmp_path):
    """The state arrives after the page opens"""

    drawn = draw_frame("aiko_services.actors.dashboard.recorder_plugin",
        "RecorderFrame", {}, tmp_path)

    assert drawn["ok"], drawn.get("traceback") or drawn.get("error")

# --------------------------------------------------------------------------- #
